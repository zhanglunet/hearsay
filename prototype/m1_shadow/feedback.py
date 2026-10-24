"""词级相似度。只比较转写里的词，不产生音素错误。

低分规则：参考词召回 < 0.75（恰好 0.75 不算低分）。
召回 = 对齐上的词数 / 参考词数。多说出来的词会拉低精确率，但只要参考词都在，
就不因为语气词把整句标低。这个门槛只用于界面高亮。
"""

from __future__ import annotations

import difflib

from m1_shadow.limits import LOW_SCORE_RECALL
from m1_shadow.segment import tokenize


class FeedbackError(ValueError):
    """反馈算不出来，通常是缺了原文或转写字段。"""


def _align(reference: list[str], hypothesis: list[str]) -> list[dict]:
    matcher = difflib.SequenceMatcher(a=reference, b=hypothesis, autojunk=False)
    rows: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                rows.append({"op": "match", "ref": reference[i], "hyp": hypothesis[j]})
        elif tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for offset in range(paired):
                rows.append(
                    {
                        "op": "substitution",
                        "ref": reference[i1 + offset],
                        "hyp": hypothesis[j1 + offset],
                    }
                )
            for i in range(i1 + paired, i2):
                rows.append({"op": "deletion", "ref": reference[i], "hyp": None})
            for j in range(j1 + paired, j2):
                rows.append({"op": "insertion", "ref": None, "hyp": hypothesis[j]})
        elif tag == "delete":
            for i in range(i1, i2):
                rows.append({"op": "deletion", "ref": reference[i], "hyp": None})
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append({"op": "insertion", "ref": None, "hyp": hypothesis[j]})
    return rows


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 3)


def word_feedback(reference: str, hypothesis: str) -> dict:
    if not isinstance(reference, str) or not isinstance(hypothesis, str):
        raise FeedbackError("reference 和 hypothesis 必须是字符串")
    reference_tokens = tokenize(reference)
    hypothesis_tokens = tokenize(hypothesis)
    if not reference_tokens:
        raise FeedbackError("参考句里没有可比较的英文词")
    alignment = _align(reference_tokens, hypothesis_tokens)
    counts = {
        "reference": len(reference_tokens),
        "hypothesis": len(hypothesis_tokens),
        "match": sum(1 for row in alignment if row["op"] == "match"),
        "substitution": sum(1 for row in alignment if row["op"] == "substitution"),
        "deletion": sum(1 for row in alignment if row["op"] == "deletion"),
        "insertion": sum(1 for row in alignment if row["op"] == "insertion"),
    }
    # 一个参考词都没对上时，不要把「i → hello」这种错配显示成替换。
    # 那只是序列对齐硬凑的，跟读反馈里看成「整句没说出来 + 多出来的词」更清楚。
    if counts["match"] == 0:
        alignment = [
            {"op": "deletion", "ref": token, "hyp": None} for token in reference_tokens
        ] + [
            {"op": "insertion", "ref": None, "hyp": token} for token in hypothesis_tokens
        ]
        counts["substitution"] = 0
        counts["deletion"] = len(reference_tokens)
        counts["insertion"] = len(hypothesis_tokens)
    recall = counts["match"] / counts["reference"]
    precision = (
        counts["match"] / counts["hypothesis"] if counts["hypothesis"] else 0.0
    )
    if precision + recall == 0:
        similarity = 0.0
    else:
        similarity = 2 * precision * recall / (precision + recall)
    # 用整数比较，避免 0.75 的浮点边界把「刚好四分之三」标成低分。
    low_score = counts["match"] * 4 < counts["reference"] * 3
    return {
        "reference_text": reference,
        "hypothesis_text": hypothesis,
        "reference_tokens": reference_tokens,
        "hypothesis_tokens": hypothesis_tokens,
        "alignment": alignment,
        "counts": counts,
        "word_recall": _ratio(counts["match"], counts["reference"]),
        "word_precision": _ratio(counts["match"], counts["hypothesis"]),
        "similarity": round(similarity, 3),
        "low_score": low_score,
        "low_score_rule": f"word_recall < {LOW_SCORE_RECALL}",
        "threshold": LOW_SCORE_RECALL,
    }


_IGNORED_INPUTS = (
    "phonemes",
    "phones",
    "expected_phones",
    "heard_phones",
    "error_instances",
    "phoneme_profile",
    "common_substitution",
    "differences",
)


def feedback_request(body: dict) -> dict:
    if not isinstance(body, dict):
        raise FeedbackError("请求体必须是 JSON 对象")
    reference = body.get("reference")
    hypothesis = body.get("hypothesis")
    if not isinstance(reference, str) or not isinstance(hypothesis, str):
        raise FeedbackError("需要 reference 和 hypothesis 字符串。没有转写时不能算词级相似度。")
    result = word_feedback(reference, hypothesis)
    ignored = [key for key in _IGNORED_INPUTS if key in body]
    if ignored:
        result["ignored_inputs"] = ignored
    if "idx" in body:
        result["idx"] = body["idx"]
    return result


def summarize_request(body: dict) -> dict:
    """一次 shadow 会话里哪些句子该高亮。仍然不写 ErrorInstance。"""

    if not isinstance(body, dict):
        raise FeedbackError("请求体必须是 JSON 对象")
    items = body.get("sentences")
    if not isinstance(items, list):
        raise FeedbackError("需要 sentences 数组")
    low: list = []
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            raise FeedbackError("sentences 里必须是对象")
        reference = item.get("reference")
        hypothesis = item.get("hypothesis")
        if not isinstance(reference, str) or not isinstance(hypothesis, str):
            raise FeedbackError("每个句子都需要 reference 和 hypothesis 字符串")
        scored = word_feedback(reference, hypothesis)
        idx = item.get("idx")
        if scored["low_score"]:
            low.append(idx)
        rows.append(
            {
                "idx": idx,
                "word_recall": scored["word_recall"],
                "low_score": scored["low_score"],
            }
        )
    return {
        "session_type": "shadow",
        "low_score_sentence_idxs": low,
        "sentences": rows,
    }
