"""听力理解题引擎与演示题（M0 §2.8 六种题型的离线子集）。

本切片支持：gist/detail（选择）、detail（关键词简答）、dictation（听写，容忍拼写）、
discrimination（二选一听辨）。inference 与 spoken_response 需要 LLM 判，未接。
规则判定的 can-do 证据可以写（source=rule）；LLM 判定的一致性验证见 exp_e_dialogue。
"""

import difflib
import re

from retell.retell import norm_word

# 字段对齐 M0 Material.comprehension_questions；answer 不发给前端。
DEMO_QUESTIONS = [
    dict(id="q1", type="gist", sentence_idx=None,
         q_zh="这段话主要在谈什么？",
         options=["说话人的日常安排与计划", "一家餐厅的面条", "英语语法规则"],
         answer=0, can_do_id="L-A2-01", error_codes=[]),
    dict(id="q2", type="detail", sentence_idx=0,
         q_zh="说话人为什么坐地铁上班？用英文关键词回答。",
         required_keywords=["traffic"],
         answer="because the traffic is terrible", can_do_id=None, error_codes=[]),
    dict(id="q3", type="dictation", sentence_idx=1,
         q_zh="听第 2 句，把整句打出来（允许少量拼写误差）。",
         answer="Could you send me the report before the meeting today?",
         threshold=0.8, can_do_id=None, error_codes=["H02"]),
    dict(id="q4", type="discrimination", sentence_idx=1,
         q_zh="你听到的是哪一句？",
         options=["Could you send me the report?", "Couldn't you send me the report?"],
         answer=0, can_do_id="L-B1-04", error_codes=["H02"]),
]


def norm_tokens(text):
    return [norm_word(w) for w in re.sub(r"[.!?]+", " ", text).split() if norm_word(w)]


def dictation_score(reference, answer):
    """逐词对比：difflib 相似度 ≥0.85 的词算拼写容忍内的命中。返回 0–1。"""
    ref = norm_tokens(reference)
    hyp = norm_tokens(answer)
    if not ref:
        return 0.0
    used = set()
    matched = 0
    for rw in ref:
        best, best_j = 0.0, None
        for j, hw in enumerate(hyp):
            if j in used:
                continue
            sim = difflib.SequenceMatcher(a=rw, b=hw, autojunk=False).ratio()
            if sim > best:
                best, best_j = sim, j
        if best >= 0.85:
            matched += 1
            used.add(best_j)
    return round(matched / len(ref), 3)


def evaluate(question, answer):
    """返回 {score, passed}。choice/discrimination 用选项下标，其他用文本。"""
    qtype = question["type"]
    if qtype in ("gist", "discrimination"):
        passed = int(answer) == question["answer"]
        return dict(score=1.0 if passed else 0.0, passed=passed)
    if qtype == "detail":
        hyp = set(norm_tokens(str(answer)))
        required = [norm_word(k) for k in question["required_keywords"]]
        found = sum(1 for k in required if k in hyp)
        score = round(found / len(required), 3) if required else 0.0
        return dict(score=score, passed=score >= 1.0)
    if qtype == "dictation":
        score = dictation_score(question["answer"], str(answer))
        return dict(score=score, passed=score >= question.get("threshold", 0.8))
    raise ValueError(f"本切片不支持的题型：{qtype}（inference / spoken_response 需 LLM 判，未接）")


def can_do_verdicts(results):
    """按 can_do_id 汇总：通过率 ≥0.8 demonstrated，≥0.64 partial，否则 failed。"""
    grouped = {}
    for r in results:
        cid = r["question"].get("can_do_id")
        if cid:
            grouped.setdefault(cid, []).append(r["passed"])
    out = {}
    for cid, passes in grouped.items():
        ratio = sum(passes) / len(passes)
        out[cid] = "demonstrated" if ratio >= 0.8 else ("partial" if ratio >= 0.64 else "failed")
    return out


def public_question(question):
    """去掉答案与判分字段，只发题干。"""
    return {k: v for k, v in question.items()
            if k in ("id", "type", "sentence_idx", "q_zh", "options")}
