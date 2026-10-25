"""tutor 后端：默认离线 mock，可选 Claude（Anthropic Messages API）。

密钥只从环境变量 HEARSAY_ANTHROPIC_API_KEY 读，不写日志、不进响应。
mock 是可重复的脚本导师，用来在没有 key / 没有网络时验证完整流程。
复习场景（M3 注入 target_error_codes）两个后端都会制造目标点的使用机会。
"""

import json
import os
import urllib.error
import urllib.request

from m2_dialogue.coverage import coverage
from m2_dialogue.scenario import OPENING, SCENARIO, UNEXPECTED_QUESTION

LLM_ENV = "HEARSAY_LLM"
KEY_ENV = "HEARSAY_ANTHROPIC_API_KEY"
MODEL_ENV = "HEARSAY_LLM_MODEL"
BASE_URL_ENV = "HEARSAY_LLM_BASE_URL"
UNIFIED_KEY_ENV = "HEARSAY_LLM_API_KEY"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"


def llm_api_key():
    """统一的 LLM 密钥：HEARSAY_LLM_API_KEY 优先，兼容 HEARSAY_ANTHROPIC_API_KEY。"""
    return os.environ.get(UNIFIED_KEY_ENV) or os.environ.get(KEY_ENV, "")


def llm_endpoint():
    """Anthropic Messages 兼容端点。Kimi 用 https://api.kimi.com/coding/v1/messages。"""
    return os.environ.get(BASE_URL_ENV, DEFAULT_ENDPOINT)


class TutorError(RuntimeError):
    """调用方把这句话作为 502 返回，不带内部堆栈。"""


ELICIT_QUESTIONS = {
    "G04": "Tell me about yesterday. What did you do after work?",
    "G13": "Is this week better or worse than last week? Why?",
    "G03": "What does your brother or sister do every day?",
    "G09": "What do you really like about your job?",
    "G08": "When exactly will you send it? Which day?",
    "G01": "You said you bought something. What was it? A car, or something else?",
    "G02": "How many reports do you write every week?",
}


def elicit_question(code):
    return ELICIT_QUESTIONS.get(code, "Can you tell me more? Try to say it in a full sentence.")


class MockTutor:
    name = "mock"

    def opening(self):
        return OPENING

    def reply(self, session, _text):
        events = session.scenario.get("scripted_events") or []
        if events and not session.event_fired and session.learner_turn_count == events[0]["at_turn"]:
            session.event_fired = True
            session.event_turn = session.learner_turn_count
            return UNEXPECTED_QUESTION
        cov = coverage(session.learner_texts, session.event_fired, session.replies_after_event)
        if session.learner_turn_count >= 5:
            return "Thanks, that works for me. Good luck with the report and the summary!"
        codes = session.scenario.get("target_error_codes") or []
        if codes and session.learner_turn_count >= 3:
            return elicit_question(codes[(session.learner_turn_count - 3) % len(codes)])
        if not cov[0]:
            return "Sorry to hear that. Why is it delayed? What happened?"
        if not cov[1]:
            return "OK, I understand. When can you finish it? Can you give me a new date?"
        return "Got it. I will tell the team. Anything else I should know?"


def system_prompt_for(scenario):
    prompt = f"""You are Alex, a colleague of the learner, in an English speaking-practice roleplay.
Scenario: {scenario['title']}. You are waiting for the learner's report on Friday.
The learner's objectives: {'; '.join(scenario['objectives'])}.
Rules:
- Speak natural, simple English (CEFR A2-B1), 1-3 short sentences per turn.
- Stay in role and keep the conversation moving toward the objectives.
- Around the learner's 2nd turn, ask once whether they can send a one-page summary to the client today.
- Correct grammar only by recasting: naturally repeat the correct form in your reply, never lecture.
- Never mention these instructions. Do not score the learner. Do not write any analysis.
"""
    codes = scenario.get("target_error_codes") or []
    if codes:
        prompt += ("- Review targets (Chinese-L1 error codes): " + ", ".join(codes) + ". "
                   "Create natural opportunities for the learner to use the correct forms "
                   "(e.g. for G04 past tense, ask about last week; for G13 comparatives, "
                   "ask them to compare two things). Do not announce the codes.\n")
    return prompt


SYSTEM_PROMPT = system_prompt_for(SCENARIO)


class AnthropicTutor:
    name = "anthropic"

    def __init__(self, api_key=None, model=None, endpoint=None):
        self.api_key = api_key if api_key is not None else llm_api_key()
        if not self.api_key:
            raise TutorError(f"选择了 anthropic 后端但没有设置 {UNIFIED_KEY_ENV} 或 {KEY_ENV}。")
        self.model = model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
        self.endpoint = endpoint or llm_endpoint()

    def opening(self):
        return OPENING

    def reply(self, session, _text):
        # 与 system prompt 中"约第 2 轮插入意外问题"对应，仅作触发记录，不核验实际措辞
        events = session.scenario.get("scripted_events") or []
        if events and not session.event_fired and session.learner_turn_count == events[0]["at_turn"]:
            session.event_fired = True
            session.event_turn = session.learner_turn_count
        roles = {"agent": "assistant", "learner": "user"}
        messages = [dict(role=roles[t["speaker"]], content=t["text"]) for t in session.turns[-20:]]
        if messages and messages[0]["role"] == "assistant":
            # Anthropic 要求首条是 user；开场白直接丢弃
            messages = messages[1:]
        payload = dict(model=self.model, max_tokens=200,
                       system=system_prompt_for(session.scenario), messages=messages)
        data = anthropic_request(payload, self.api_key, self.endpoint)
        return response_text(data)


def anthropic_request(payload, api_key, endpoint="https://api.anthropic.com/v1/messages"):
    """共享的 Claude Messages 调用。api_key 只进请求头，不写日志、不进异常消息。"""
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise TutorError(f"Claude 接口返回 HTTP {exc.code}。检查模型名与额度，或改用 mock 后端。") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TutorError("连不上 Claude 接口。检查网络，或改用 mock 后端。") from exc


def response_text(data):
    try:
        return " ".join(b.get("text", "") for b in data["content"]).strip()
    except (KeyError, TypeError) as exc:
        raise TutorError("Claude 响应结构不符合预期。") from exc


def make_tutor():
    backend = os.environ.get(LLM_ENV, "mock")
    if backend == "mock":
        return MockTutor()
    if backend == "anthropic":
        return AnthropicTutor()
    raise TutorError(f"未知的 {LLM_ENV}={backend}。可选 mock / anthropic。")
