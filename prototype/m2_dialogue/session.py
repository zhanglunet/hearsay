"""对话会话状态机与复盘。内存保存，不落盘；学习者模型写入走 M3 ingest。"""

import time
import uuid

from m2_dialogue.coverage import coverage
from m2_dialogue.recast import scan_recasts
from m2_dialogue.scenario import PRODUCT_RULE_M2, SCENARIO


class DialogueError(ValueError):
    """调用方把这句话作为 400 返回。"""


def count_words(text):
    return len(text.split())


class DialogueSession:
    def __init__(self, tutor, level="A2", scenario=None):
        self.id = uuid.uuid4().hex[:12]
        self.tutor = tutor
        self.level = level
        self.scenario = scenario or SCENARIO
        self.started_at = time.time()
        self.ended_at = None
        self.turns = [dict(speaker="agent", text=tutor.opening())]
        self.recasts = []
        self.event_fired = False
        self.event_turn = None

    @property
    def learner_texts(self):
        return [t["text"] for t in self.turns if t["speaker"] == "learner"]

    @property
    def learner_turn_count(self):
        return len(self.learner_texts)

    @property
    def replies_after_event(self):
        return 0 if self.event_turn is None else self.learner_turn_count - self.event_turn

    def add_learner_turn(self, text):
        if self.ended_at is not None:
            raise DialogueError("会话已结束，不能继续发言。请重新开始。")
        text = " ".join(text.split())
        if not text:
            raise DialogueError("发言是空的。说点什么，或打字输入。")
        if len(text) > 4000:
            raise DialogueError("单轮发言过长（>4000 字符）。")
        uid = self.learner_turn_count + 1
        self.turns.append(dict(speaker="learner", text=text, utterance_id=uid, audio_ref=None))
        for hit in scan_recasts(text):
            self.recasts.append(dict(hit, utterance_id=uid))
        agent_text = self.tutor.reply(self, text)
        self.turns.append(dict(speaker="agent", text=agent_text))
        return agent_text

    def attach_audio(self, path):
        """把刚上传的音频挂到最后一轮学习者话语上（批处理用）。"""
        for turn in reversed(self.turns):
            if turn["speaker"] == "learner":
                turn["audio_ref"] = path
                return
        raise DialogueError("还没有学习者发言，无法挂音频。")

    def end(self, batch_result=None):
        if self.ended_at is None:
            self.ended_at = time.time()
        return self.recap(batch_result)

    def _objectives(self):
        """默认场景用关键词启发式评覆盖；复习场景的目标是否用对，留给评分通道，
        这里 covered=None，不做假装精确的判定。"""
        texts = self.scenario["objectives"]
        if self.scenario["id"] != SCENARIO["id"]:
            return [dict(text=t, covered=None) for t in texts], None
        cov = coverage(self.learner_texts, self.event_fired, self.replies_after_event)
        return [dict(text=t, covered=hit) for t, hit in zip(texts, cov)], sum(cov)

    def recap(self, batch_result=None):
        learner_words = sum(count_words(t) for t in self.learner_texts)
        agent_words = sum(count_words(t["text"]) for t in self.turns if t["speaker"] == "agent")
        objectives, covered_n = self._objectives()
        share = round(learner_words / (learner_words + agent_words), 3) if learner_words + agent_words else 0.0
        summary = (
            f"本次对话你说了 {self.learner_turn_count} 轮、约 {learner_words} 词，"
            f"输出词数占比 {share:.0%}（目标：说的时间占一半以上）。"
        )
        if covered_n is None:
            summary += "复习目标是否用对，请到 M4 页面给对应复习卡评分。"
        else:
            summary += f"三个目标覆盖了 {covered_n} 个。"
            if covered_n < len(objectives):
                missing = "、".join(o["text"] for o in objectives if not o["covered"])
                summary += f"还没覆盖：{missing}。"
        if self.recasts:
            summary += (f"有 {len(self.recasts)} 条待核对的 recast 提示，"
                        "它们还没经过事后批处理确认，不计入错误统计。")
        else:
            summary += "规则没有扫到典型迁移错误；这不等于没有错误，完整检测要等事后批处理。"
        if batch_result is not None:
            n_confirmed = len(batch_result["confirmed"])
            n_discarded = len(batch_result["discarded"])
            summary += (f"事后批处理用时 {batch_result['duration_sec']} 秒："
                        f"confirmed {n_confirmed} 条、discarded {n_discarded} 条")
            rate = batch_result["false_positive_rate"]
            if rate is not None:
                summary += f"，实时提示误报率 {rate:.1%}（规则口径，非 LLM 实时链路）"
            summary += "。"
        recap = dict(
            session_id=self.id,
            scenario_id=self.scenario["id"],
            session_type="converse",
            duration_sec=int((self.ended_at or time.time()) - self.started_at),
            n_learner_turns=self.learner_turn_count,
            n_agent_turns=len(self.turns) - self.learner_turn_count,
            learner_words=learner_words,
            agent_words=agent_words,
            learner_word_share=share,
            scripted_event_fired=self.event_fired,
            objectives=objectives,
            target_error_codes=self.scenario.get("target_error_codes", []),
            recasts=self.recasts,
            summary_zh=summary,
            notes=PRODUCT_RULE_M2,
        )
        if batch_result is not None:
            recap["batch"] = batch_result
        return recap


SESSIONS = {}


def create_session(tutor, level="A2", scenario=None):
    session = DialogueSession(tutor, level, scenario)
    SESSIONS[session.id] = session
    return session


def get_session(session_id):
    session = SESSIONS.get(session_id or "")
    if session is None:
        raise DialogueError("没有这个会话，或它已随服务重启消失。请重新开始。")
    return session
