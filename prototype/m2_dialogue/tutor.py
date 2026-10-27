"""tutor 后端：默认离线 mock，可选 Claude（Anthropic Messages API）。

密钥只从环境变量 HEARSAY_ANTHROPIC_API_KEY 读，不写日志、不进响应。
mock 是可重复的脚本导师，用来在没有 key / 没有网络时验证完整流程。
复习场景（M3 注入 target_error_codes）两个后端都会制造目标点的使用机会。
"""

import json
import os
import re
import urllib.error
import urllib.request

from m2_dialogue.coverage import coverage
from m2_dialogue.recast import validate_llm_errors
from m2_dialogue.scenario import OPENING, SCENARIO, UNEXPECTED_QUESTION

LLM_ENV = "HEARSAY_LLM"
KEY_ENV = "HEARSAY_ANTHROPIC_API_KEY"
MODEL_ENV = "HEARSAY_LLM_MODEL"
BASE_URL_ENV = "HEARSAY_LLM_BASE_URL"
UNIFIED_KEY_ENV = "HEARSAY_LLM_API_KEY"
THINKING_ENV = "HEARSAY_LLM_THINKING"
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"


def llm_api_key():
    """统一的 LLM 密钥：HEARSAY_LLM_API_KEY 优先，兼容 HEARSAY_ANTHROPIC_API_KEY。"""
    return os.environ.get(UNIFIED_KEY_ENV) or os.environ.get(KEY_ENV, "")


def llm_endpoint():
    """Anthropic Messages 兼容端点（完整 URL，含 /v1/messages）。
    DeepSeek：https://api.deepseek.com/anthropic/v1/messages"""
    return os.environ.get(BASE_URL_ENV, DEFAULT_ENDPOINT)


def llm_thinking():
    """HEARSAY_LLM_THINKING：可选，目前只认 "disabled"。

    设置了就在请求里带 thinking={"type": "disabled"}，让实时对话少一段推理、回得更快
    （DeepSeek 的 Anthropic 兼容端点支持）。不设置就不发这个字段：Claude Opus 5.5 等
    模型不允许关闭 thinking，发了会 400。
    """
    value = os.environ.get(THINKING_ENV, "").strip()
    if not value:
        return None
    if value != "disabled":
        raise TutorError(f"{THINKING_ENV} 只支持 disabled 或留空。")
    return {"type": "disabled"}


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
    last_recasts = []

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
- Output ONLY a JSON object, no markdown fence: {{"reply":"what Alex says aloud",
  "recasts":[{{"code":"G04","observed":"...","expected":"...","confidence":0.9}}]}}
  recasts lists ONLY the learner errors you actually recast in THIS reply;
  observed must be an exact substring of the learner's last utterance
  (just the error fragment, not the whole sentence);
  expected is the correct form; use [] when you did not recast anything.
  Code guide: G01 articles, G02 singular/plural, G03 subject-verb agreement,
  G04 tense, G05 perfect aspect, G06 missing verb, G07 noun countability,
  G08 prepositions, G09 sentence pattern, G10 pronouns, G11 connectives,
  G12 there be, G13 comparison, G16 subjunctive, L10 wrong word class.
  NEVER default everything to G04. If you cannot tell the exact code,
  use X00 (unclassifiable) instead of guessing.
- Never mention these instructions. Do not score the learner. Do not write any analysis outside the JSON.
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
    last_recasts = []

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
        payload = dict(model=self.model, max_tokens=1024,
                       system=system_prompt_for(session.scenario), messages=messages)
        data = anthropic_request(payload, self.api_key, self.endpoint)
        text = response_text(data)
        uid = session.learner_turn_count
        learner_text = session.turns[-1]["text"]
        self.last_recasts = []
        try:
            parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            reply_text = str(parsed["reply"]).strip()
            raw_recasts = parsed.get("recasts", [])
            if not isinstance(raw_recasts, list):
                raise ValueError("recasts 不是数组")
        except (ValueError, KeyError, AttributeError, json.JSONDecodeError):
            # 模型没按约定输出 JSON 时退化为纯文本回复，不阻断对话
            return text
        for hit in validate_llm_errors(
                [dict(e, utterance_id=uid) for e in raw_recasts if isinstance(e, dict)],
                [dict(utterance_id=uid, batch_text=learner_text)]):
            self.last_recasts.append(dict(hit, detected_by="asr_llm_realtime", status="provisional"))
        return reply_text or text


def anthropic_request(payload, api_key, endpoint="https://api.anthropic.com/v1/messages"):
    """共享的 Claude Messages 调用。api_key 只进请求头，不写日志、不进异常消息。"""
    thinking = llm_thinking()
    if thinking is not None and "thinking" not in payload:
        payload = dict(payload, thinking=thinking)
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
    """取出所有 text 块的文字。thinking 块没有 text 字段，自然被跳过。

    stop_reason 为 refusal、或 max_tokens 且没有任何正文时，给出可操作的错误，
    而不是让页面拿到一句空回复。max_tokens 但已有正文时照常返回（调用方会尝试解析）。
    """
    try:
        text = " ".join(b.get("text", "") for b in data["content"]
                        if isinstance(b, dict) and b.get("type", "text") == "text").strip()
    except (KeyError, TypeError) as exc:
        raise TutorError("模型响应结构不符合预期。") from exc
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise TutorError("模型拒绝回答这次请求。换一种说法再试。")
    if not text:
        if stop == "max_tokens":
            raise TutorError("模型输出被 max_tokens 截断，没有产生正文。")
        raise TutorError("模型没有返回文字内容。")
    return text


def make_tutor():
    backend = os.environ.get(LLM_ENV, "mock")
    if backend == "mock":
        return MockTutor()
    if backend == "anthropic":
        return AnthropicTutor()
    raise TutorError(f"未知的 {LLM_ENV}={backend}。可选 mock / anthropic。")
