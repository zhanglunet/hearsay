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

材料：等级 {level}，话题「{topic}」，写 6 句自然、简单、互相连贯的英文。

出 4 道题，每题都必须有 "type" 字段，取值依次是 gist、detail、dictation、discrimination：
- gist（主旨选择）：q_zh、options（3–4 个中文选项）、answer（正确选项下标，0 起）。
- detail（关键词简答）：q_zh、sentence_idx（答案所在句，0 起）、required_keywords（判分必需的英文关键词，出自该句）、answer（参考答案）。
- dictation（听写）：q_zh、sentence_idx（听写哪一句，0 起）。
- discrimination（二选一听辨）：
  - 先选定材料里的一句，sentence_idx 写它的下标（0 起）。这句里必须含一处容易听混的对立，如 can/can't、ship/sheep、thirteen/thirty。
  - options 正好 2 项。正确的一项必须是这句原文，一字不改地照抄（大小写和标点可以不同）；另一项只把那个对立词换掉，其余一字不改。
  - answer 是照抄原文那一项的下标。干扰项不能和原文相同。
  - 例：材料第 2 句是 "I'm afraid we can't finish the report by Friday."，则 sentence_idx=1，options=["I'm afraid we can't finish the report by Friday.", "I'm afraid we can finish the report by Friday."]，answer=0。
  - 可加 error_codes，如 ["H02"]（弱读听辨）。

每题能映射就给 can_do_id（如 L-A2-01 主旨、L-A2-02 细节、L-B1-04 连读弱读），没有就 null。

只输出一个 JSON 对象，不要解释、不要 Markdown 代码块：
{{"title":"...","sentences":["...","..."],"questions":[{{"type":"gist",...}},{{"type":"detail",...}},{{"type":"dictation",...}},{{"type":"discrimination",...}}]}}"""

GENERATE_ATTEMPTS = 2  # 模型输出不合格（无 JSON / JSON 坏 / 校验不过）时最多再试 1 次

CODE_H = re.compile(r"^H\d{2}$")


def _idx(value, n, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, int) or not 0 <= value < n:
        raise ValueError(f"sentence_idx 越界：{value}")
    return value


_NORM = re.compile(r"[^a-z0-9' ]+")


def _norm(text):
    """小写，去掉标点但保留撇号（can 与 can't 要分开），合并空白。"""
    return " ".join(_NORM.sub(" ", str(text).lower().replace("’", "'")).split())


def _heard_in(option, sentence):
    """选项是否就是这句话：整句相同，或是句中一个完整的词或短语。"""
    o, s = _norm(option), _norm(sentence)
    return bool(o) and (o == s or f" {o} " in f" {s} ")


def _check_discrimination(options, answer, sentence_idx, sentences):
    """听辨题的正确项必须是学习者实际听到的内容，干扰项不能也出现在原句里。

    没给 sentence_idx 时，按正确项能在哪一句里找到来定位。返回确定的句下标。
    """
    correct = options[answer]
    if sentence_idx is None:
        hits = [i for i, s in enumerate(sentences) if _heard_in(correct, s)]
        if not hits:
            raise ValueError("discrimination 的正确选项不在任何一句材料里")
        sentence_idx = hits[0]
    sentence = sentences[sentence_idx]
    if not _heard_in(correct, sentence):
        raise ValueError("discrimination 的正确选项与所选句子原文不一致")
    for i, option in enumerate(options):
        if i != answer and _heard_in(option, sentence):
            raise ValueError("discrimination 的干扰项也出现在原句里，无法判分")
    return sentence_idx


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
            if qtype == "discrimination":
                out["sentence_idx"] = _check_discrimination(
                    options, q["answer"], out["sentence_idx"], sentences)
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


def _parse_material(text):
    """从模型输出里取出 JSON 并校验；不合格抛 ValueError。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("没有返回 JSON")
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON 不合法") from exc
    return validate_material(raw)


def generate_material(level, topic):
    api_key = llm_api_key()
    if not api_key:
        raise TutorError("材料生成需要 HEARSAY_LLM_API_KEY（或 HEARSAY_ANTHROPIC_API_KEY）。")
    payload = dict(model=os.environ.get("HEARSAY_LLM_MODEL") or DEFAULT_MODEL,
                   max_tokens=4096,
                   system="你是材料编写器，只输出 JSON。",
                   messages=[dict(role="user", content=GENERATE_PROMPT.format(level=level, topic=topic))])
    # 只在模型输出不合格时重试；缺密钥、接口报错（TutorError）直接抛出，重试也没用
    reasons = []
    for _attempt in range(GENERATE_ATTEMPTS):
        text = response_text(anthropic_request(payload, api_key, llm_endpoint()))
        try:
            return _parse_material(text)
        except ValueError as exc:
            reasons.append(str(exc))
    raise TutorError(f"模型连续 {GENERATE_ATTEMPTS} 次没有生成合格的材料：{'；'.join(reasons)}。请重试或换个话题。")
