"""自定义听力材料生成：LLM 出材料与理解题，严格校验后才给学习者用。

浏览器 speechSynthesis 朗读，不需要 TTS 模型。音频不是真人声，
词级时间戳没有，播放按句调用。生成与判定都是 LLM/规则分层，不改判分逻辑。
"""

import json
import os
import re
import uuid

from m2_dialogue.tutor import (DEFAULT_MODEL, TutorError, anthropic_request,
                               llm_api_key, llm_endpoint, response_text)
from m4_plan.can_do import load_statements

GENERATE_PROMPT = """你是英语听力材料编写器，为中文母语的英语学习者出一段材料和理解题。
要求：
- 等级 {level}，话题「{topic}」，写 6 句自然、简单的英文（日常场景，互相连贯）。
- 出 4 道题：1 道 gist（主旨选择）、1 道 detail（关键词简答）、1 道 dictation（听写整句）、
  1 道 discrimination（二选一听辨，含一处容易听混的对立，如 can/can't、ship/sheep）。
- 每题给 q_zh（中文题干）；gist/discrimination 给 options 和正确答案下标 answer；
  detail 给 required_keywords（判分必需英文关键词）和 answer（参考答案）；
  dictation 给 sentence_idx（听写哪一句，0 起）。
- 能映射就给 can_do_id（如 L-A2-01 主旨、L-A2-02 细节、L-B1-04 连读弱读），没有就 null。
- 只输出 JSON：{{"title":"...","sentences":["..."],"questions":[...]}}，不要解释。"""

CODE_H = re.compile(r"^H\d{2}$")


def _idx(value, n, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, int) or not 0 <= value < n:
        raise ValueError(f"sentence_idx 越界：{value}")
    return value


def _infer_idx_from_options(options, sentences):
    """discrimination 缺句序时，取与某选项最相似的句子；相似度过低说明题目与材料脱节。"""
    import difflib
    best, best_i = 0.0, None
    for i, sentence in enumerate(sentences):
        for option in options:
            ratio = difflib.SequenceMatcher(a=sentence.lower(), b=str(option).lower(),
                                            autojunk=False).ratio()
            if ratio > best:
                best, best_i = ratio, i
    if best_i is None or best < 0.5:
        raise ValueError("无法推断 discrimination 的 sentence_idx（选项与材料句子不匹配）")
    return best_i


def validate_material(raw):
    """校验并规范化 LLM 生成的材料。不合格抛 ValueError，不带原文细节。"""
    if not isinstance(raw, dict):
        raise ValueError("材料不是 JSON 对象")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title 缺失")
    sentences = raw.get("sentences")
    if not isinstance(sentences, list) or not 3 <= len(sentences) <= 12:
        raise ValueError("sentences 应为 3–12 句")
    sentences = [s.strip() for s in sentences if isinstance(s, str) and s.strip()]
    can_do_ids = {s.id for s in load_statements()}
    questions = []
    for i, q in enumerate(raw.get("questions", []), 1):
        if not isinstance(q, dict):
            raise ValueError("题目不是对象")
        qtype = q.get("type")
        q_zh = q.get("q_zh")
        if not isinstance(q_zh, str) or not q_zh.strip():
            raise ValueError(f"第 {i} 题缺 q_zh")
        out = dict(id=f"q{i}", type=qtype, q_zh=q_zh.strip(),
                   sentence_idx=_idx(q.get("sentence_idx"), len(sentences), required=False),
                   can_do_id=q.get("can_do_id") if q.get("can_do_id") in can_do_ids else None,
                   error_codes=[c for c in q.get("error_codes", []) if CODE_H.match(str(c))])
        if qtype in ("gist", "discrimination"):
            options = q.get("options")
            if not isinstance(options, list) or not 2 <= len(options) <= 4:
                raise ValueError(f"第 {i} 题 options 应为 2–4 项")
            if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(options):
                raise ValueError(f"第 {i} 题 answer 下标不合法")
            if qtype == "discrimination" and out["sentence_idx"] is None:
                out["sentence_idx"] = _infer_idx_from_options(options, sentences)
            out.update(options=[str(o) for o in options], answer=q["answer"])
        elif qtype == "detail":
            keys = q.get("required_keywords")
            if not isinstance(keys, list) or not keys:
                raise ValueError(f"第 {i} 题缺 required_keywords")
            if out["sentence_idx"] is None:
                # LLM 没给句序时按关键词反查；查不到保留 None（不用于 H 错误定位）
                lowered = [str(k).lower() for k in keys]
                out["sentence_idx"] = next(
                    (i for i, s in enumerate(sentences)
                     if any(k in s.lower() for k in lowered)), None)
            out.update(required_keywords=[str(k) for k in keys], answer=str(q.get("answer", "")))
        elif qtype == "dictation":
            if out["sentence_idx"] is None:
                # 没指定听写句时选最长的一句（更适合听写）
                out["sentence_idx"] = max(range(len(sentences)),
                                          key=lambda i: len(sentences[i].split()))
            out["answer"] = sentences[out["sentence_idx"]]
            out["threshold"] = 0.8
        else:
            raise ValueError(f"第 {i} 题类型不支持：{qtype}")
        questions.append(out)
    if not questions:
        raise ValueError("没有题目")
    return dict(id=f"gen-{uuid.uuid4().hex[:8]}", title=title.strip(),
                target_cefr=raw.get("target_cefr", "A2"),
                sentences=[dict(idx=i, text=s) for i, s in enumerate(sentences)],
                questions=questions, generated_by="llm")


def generate_material(level, topic):
    api_key = llm_api_key()
    if not api_key:
        raise TutorError("材料生成需要 HEARSAY_LLM_API_KEY（或 HEARSAY_ANTHROPIC_API_KEY）。")
    payload = dict(model=os.environ.get("HEARSAY_LLM_MODEL") or DEFAULT_MODEL,
                   max_tokens=4096,
                   system="你是材料编写器，只输出 JSON。",
                   messages=[dict(role="user", content=GENERATE_PROMPT.format(level=level, topic=topic))])
    data = anthropic_request(payload, api_key, llm_endpoint())
    text = response_text(data)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise TutorError("材料生成没有返回 JSON。")
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise TutorError("材料生成的 JSON 不合法。") from exc
    return validate_material(raw)
