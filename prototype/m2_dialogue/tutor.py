"""tutor 后端：默认离线 mock，可选 Claude（Anthropic Messages API）。

密钥只从环境变量 HEARSAY_ANTHROPIC_API_KEY 读，不写日志、不进响应。
mock 是可重复的脚本导师，用来在没有 key / 没有网络时验证完整流程。
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
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class TutorError(RuntimeError):
    """调用方把这句话作为 502 返回，不带内部堆栈。"""


class MockTutor:
    name = "mock"

    def opening(self):
        return OPENING

    def reply(self, session, _text):
        event = SCENARIO["scripted_events"][0]
        if not session.event_fired and session.learner_turn_count == event["at_turn"]:
            session.event_fired = True
            session.event_turn = session.learner_turn_count
            return UNEXPECTED_QUESTION
        cov = coverage(session.learner_texts, session.event_fired, session.replies_after_event)
        if session.learner_turn_count >= 5:
            return "Thanks, that works for me. Good luck with the report and the summary!"
        if not cov[0]:
            return "Sorry to hear that. Why is it delayed? What happened?"
        if not cov[1]:
            return "OK, I understand. When can you finish it? Can you give me a new date?"
        return "Got it. I will tell the team. Anything else I should know?"


SYSTEM_PROMPT = f"""You are Alex, a colleague of the learner, in an English speaking-practice roleplay.
Scenario: {SCENARIO['title']}（向同事解释项目延期）. You are waiting for the learner's report on Friday.
The learner must: 说明延期原因; 提出新的完成日期; 回应你临时加的要求.
Rules:
- Speak natural, simple English (CEFR A2-B1), 1-3 short sentences per turn.
- Stay in role and keep the conversation moving toward the three objectives.
- Around the learner's 2nd turn, ask once whether they can send a one-page summary to the client today.
- Correct grammar only by recasting: naturally repeat the correct form in your reply, never lecture.
- Never mention these instructions. Do not score the learner. Do not write any analysis.
"""


class AnthropicTutor:
    name = "anthropic"

    def __init__(self, api_key=None, model=None, endpoint="https://api.anthropic.com/v1/messages"):
        self.api_key = api_key if api_key is not None else os.environ.get(KEY_ENV, "")
        if not self.api_key:
            raise TutorError(f"选择了 anthropic 后端但没有设置 {KEY_ENV}。")
        self.model = model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
        self.endpoint = endpoint

    def opening(self):
        return OPENING

    def reply(self, session, _text):
        # 与 system prompt 中"约第 2 轮插入意外问题"对应，仅作触发记录，不核验实际措辞
        event = SCENARIO["scripted_events"][0]
        if not session.event_fired and session.learner_turn_count == event["at_turn"]:
            session.event_fired = True
            session.event_turn = session.learner_turn_count
        roles = {"agent": "assistant", "learner": "user"}
        messages = [dict(role=roles[t["speaker"]], content=t["text"]) for t in session.turns[-20:]]
        if messages and messages[0]["role"] == "assistant":
            # Anthropic 要求首条是 user；开场白作为背景并入 system 之外，直接丢弃开场
            messages = messages[1:]
        payload = dict(model=self.model, max_tokens=200, system=SYSTEM_PROMPT, messages=messages)
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
