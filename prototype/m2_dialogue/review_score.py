"""复习场景自动评分（M0 §4.3）：机会出现且犯错 again / 犯错但自我纠正 hard /
机会出现且未犯错 good。词项评分未接，只覆盖错误代码。

LLM 判定，输出逐条校验（代码必须在场景 target_error_codes 里、outcome 枚举、
evidence 必须是学习者原文片段）。LLM 不可用时返回 None，退回 M4 手动评分。
"""

import json
import os
import re

from m2_dialogue.tutor import (DEFAULT_MODEL, TutorError, anthropic_request,
                               llm_api_key, llm_endpoint, response_text)

OUTCOME_RATING = {"again": 1, "hard": 2, "good": 3}

SCORE_PROMPT = """你在给英语学习者的复习对话评分。场景要复习的错误代码：{codes}。
代码含义：G01 冠词、G02 单复数、G03 主谓一致、G04 时态、G05 完成时、G06 缺动词、
G07 名词数、G08 介词、G09 句式、G10 代词、G11 关联词、G12 there be、G13 比较级、G16 虚拟、L10 词性。
逐个代码判断：
- again：本应用对的机会出现了，学习者仍犯错（或该用没用出来）
- hard：犯错了但在后续发言里自己纠正了
- good：机会出现且没有犯错（用对了，或自然避开了）
没有给代码出现使用机会时也记 again（该练没练到）。
只输出 JSON：{{"scores":[{{"code":"G04","outcome":"good","evidence":"学习者原文片段"}}]}}。
evidence 必须是学习者说过的话里的连续片段，不要解释。对话：
{dialogue}"""


def validate_scores(raw_scores, target_codes, learner_text):
    out = []
    for item in raw_scores:
        if not isinstance(item, dict):
            continue
        code, outcome = item.get("code"), item.get("outcome")
        evidence = item.get("evidence", "")
        if code not in target_codes or outcome not in OUTCOME_RATING:
            continue
        if not isinstance(evidence, str) or not evidence.strip():
            continue
        if " ".join(evidence.lower().split()) not in " ".join(learner_text.lower().split()):
            continue
        out.append(dict(code=code, outcome=outcome, rating=OUTCOME_RATING[outcome],
                        evidence=evidence))
    return out


def score_review(session):
    """返回 [{code, outcome, rating, evidence}]；场景无目标代码或 LLM 不可用返回 None。"""
    codes = session.scenario.get("target_error_codes") or []
    if not codes:
        return None
    api_key = llm_api_key()
    if not api_key:
        return None
    dialogue = "\n".join(f"{t['speaker']}: {t['text']}" for t in session.turns)
    learner_text = " ".join(session.learner_texts)
    payload = dict(model=os.environ.get("HEARSAY_LLM_MODEL") or DEFAULT_MODEL,
                   max_tokens=2048,
                   system="你是复习评分器，只输出 JSON。",
                   messages=[dict(role="user", content=SCORE_PROMPT.format(
                       codes=", ".join(codes), dialogue=dialogue))])
    data = anthropic_request(payload, api_key, llm_endpoint())
    text = response_text(data)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise TutorError("复习评分没有返回 JSON。")
    try:
        raw = json.loads(m.group(0))["scores"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise TutorError("复习评分的 JSON 结构不合法。") from exc
    return validate_scores(raw, codes, learner_text)


def apply_scores(store, scores):
    """把评分应用到 M3 复习卡（M0 §4.3 的 again/hard/good）。返回已应用的 item_id 列表。"""
    applied = []
    cards = {c.item_id: c for c in store.cards()}
    for score in scores:
        item_id = f"error:{score['code']}"
        if item_id in cards:
            card = cards[item_id]
            card.review(score["rating"])
            store.put_card(card)
            applied.append(item_id)
    if applied:
        store.save()
    return applied
