"""把材料切成跟读句。

材料侧的做法对应风险报告 §4.4：已知原文句子，用词级时间戳定句界，
不要用 whisperX transcribe 的 VAD 分段。句尾在末词终点后再留一段，
并且不超过下一词的起点，避免把下一句切进来，也避免尾音被削掉。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TAIL_PAD_MS = 250

TIMING_NOTES = {
    "word_timestamps": (
        "按原文词序对齐你提供的词级时间戳切句。"
        "句尾在末词终点后再留最多 250ms，并且不会越过下一词的起点"
        "（风险报告 §4.4）。"
    ),
    "proportional_estimate": (
        "没有可用的词级时间戳，按各句词数把整段时长比例切开。"
        "这不是 whisperX 对齐，句界可能落在词中间，只适合把导入流程跑通。"
    ),
    "espeak_sentence_concat": (
        "演示音频由 espeak-ng 整句合成后拼接，句与句之间有静音。"
        "句界来自拼接位置；句内词时间是把孤立词的时长比例铺进该句。"
        "播放用句界，不逐词裁剪。"
    ),
}

_TOKEN = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
_SENT_SPLIT = re.compile(r"[^.!?]+(?:[.!?]+|$)")


class SegmentationError(ValueError):
    """切句失败。调用方可以改走比例估计，但不能假装对齐成功。"""


@dataclass(frozen=True)
class WordStamp:
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class SentenceSpan:
    idx: int
    text: str
    start_ms: int
    end_ms: int
    first_word_index: int
    last_word_index: int

    def as_dict(self) -> dict:
        return {
            "idx": self.idx,
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "first_word_index": self.first_word_index,
            "last_word_index": self.last_word_index,
        }


def normalize_text(text: str) -> str:
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN.finditer(normalize_text(text))]


def split_paragraph(text: str) -> list[str]:
    parts = [part.strip() for part in _SENT_SPLIT.findall(normalize_text(text).strip())]
    return [part for part in parts if part and tokenize(part)]


def parse_transcript(text: str) -> list[str]:
    """两行及以上时，一行一句。只有一段时才按 .?! 切开。"""

    if not isinstance(text, str):
        raise SegmentationError("文本必须是字符串")
    normalized = normalize_text(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        raise SegmentationError("文本是空的")
    sentences = lines if len(lines) >= 2 else split_paragraph(lines[0])
    if not sentences:
        raise SegmentationError("没有解析出句子")
    return sentences


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise SegmentationError(f"{name} 必须是数字")
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise SegmentationError(f"{name} 必须是数字") from exc
    if number <= 0:
        raise SegmentationError(f"{name} 必须为正")
    return number


def allocate_positive(weights: list[int], total: int) -> list[int]:
    """把 total 分成 len(weights) 份正整数，总和恰好等于 total。"""

    if not weights:
        raise SegmentationError("没有可分配的句子")
    if any(weight <= 0 for weight in weights):
        raise SegmentationError("分配权重必须为正")
    if total < len(weights):
        raise SegmentationError("音频短于句子数，无法每句至少分到 1ms")
    weight_sum = sum(weights)
    remain = total - len(weights)
    extras = [int(remain * weight / weight_sum) for weight in weights]
    leftover = remain - sum(extras)
    order = sorted(
        range(len(weights)),
        key=lambda i: ((remain * weights[i] / weight_sum) - extras[i], -i),
        reverse=True,
    )
    for index in order[:leftover]:
        extras[index] += 1
    lengths = [1 + extra for extra in extras]
    if sum(lengths) != total:
        raise SegmentationError("时长分配没有对齐")
    return lengths


def _validate_word_order(words: list[WordStamp]) -> None:
    previous_end = None
    for index, word in enumerate(words):
        if word.end_ms < word.start_ms:
            raise SegmentationError(f"第 {index + 1} 个词的终点早于起点")
        if previous_end is not None and word.start_ms < previous_end:
            raise SegmentationError(f"第 {index + 1} 个词与前一个词重叠或倒退")
        previous_end = word.end_ms


def parse_words(payload: object) -> list[WordStamp]:
    if isinstance(payload, dict):
        if "word_timestamps" in payload:
            payload = payload["word_timestamps"]
        elif "words" in payload:
            payload = payload["words"]
        else:
            raise SegmentationError("词级时间戳需要是数组，或包含 words / word_timestamps")
    if not isinstance(payload, list):
        raise SegmentationError("词级时间戳需要是数组")
    words: list[WordStamp] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise SegmentationError(f"第 {index + 1} 个词时间戳不是对象")
        raw_word = item.get("word", item.get("text"))
        if not isinstance(raw_word, str) or not tokenize(raw_word):
            raise SegmentationError(f"第 {index + 1} 个词时间戳没有英文词面")
        if "start_ms" in item or "end_ms" in item:
            if "start_ms" not in item or "end_ms" not in item:
                raise SegmentationError(f"第 {index + 1} 个词需要同时有 start_ms 和 end_ms")
            start = int(round(float(item["start_ms"])))
            end = int(round(float(item["end_ms"])))
        elif "start" in item and "end" in item:
            start = int(round(float(item["start"]) * 1000))
            end = int(round(float(item["end"]) * 1000))
        else:
            raise SegmentationError(f"第 {index + 1} 个词缺少时间")
        words.append(WordStamp(raw_word, start, end))
    if not words:
        raise SegmentationError("词级时间戳是空的")
    _validate_word_order(words)
    return words


def segment_by_word_timestamps(
    sentences: list[str],
    words: list[WordStamp],
    tail_pad_ms: int = TAIL_PAD_MS,
) -> list[SentenceSpan]:
    """按词序逐句消耗时间戳。多出来或对不上的词直接失败，不悄悄跳过。"""

    if tail_pad_ms < 0:
        raise SegmentationError("tail_pad_ms 不能为负")
    if not sentences:
        raise SegmentationError("没有句子")
    if not words:
        raise SegmentationError("词级时间戳是空的")
    _validate_word_order(words)
    position = 0
    spans: list[SentenceSpan] = []
    for idx, text in enumerate(sentences):
        tokens = tokenize(text)
        if not tokens:
            raise SegmentationError(f"第 {idx + 1} 句没有可对齐的英文词")
        first = position
        for token in tokens:
            if position >= len(words):
                raise SegmentationError(
                    f"第 {idx + 1} 句的词「{token}」在时间戳里对不上（时间戳先用完了）"
                )
            got = tokenize(words[position].word)
            if got != [token]:
                raise SegmentationError(
                    f"第 {idx + 1} 句期望词「{token}」，"
                    f"时间戳第 {position + 1} 个是「{words[position].word}」"
                )
            position += 1
        last = position - 1
        start_ms = words[first].start_ms
        end_ms = words[last].end_ms + tail_pad_ms
        if position < len(words):
            end_ms = min(end_ms, words[position].start_ms)
        if end_ms < words[last].end_ms:
            end_ms = words[last].end_ms
        spans.append(SentenceSpan(idx, text, start_ms, end_ms, first, last))
    if position != len(words):
        raise SegmentationError(f"时间戳还有 {len(words) - position} 个词没有对应到句子")
    return spans


def estimate_proportional(sentences: list[str], duration_ms: int) -> list[SentenceSpan]:
    if not sentences:
        raise SegmentationError("没有句子")
    duration_ms = _positive_int(duration_ms, "duration_ms")
    weights = [max(len(tokenize(sentence)), 1) for sentence in sentences]
    lengths = allocate_positive(weights, duration_ms)
    cursor = 0
    spans: list[SentenceSpan] = []
    for idx, (text, length) in enumerate(zip(sentences, lengths)):
        spans.append(SentenceSpan(idx, text, cursor, cursor + length, -1, -1))
        cursor += length
    return spans


def segment_request(body: dict) -> dict:
    if not isinstance(body, dict):
        raise SegmentationError("请求体必须是 JSON 对象")
    if body.get("sentences") is not None:
        raw_sentences = body["sentences"]
        if not isinstance(raw_sentences, list) or not all(isinstance(s, str) for s in raw_sentences):
            raise SegmentationError("sentences 必须是字符串数组")
        sentences = [sentence.strip() for sentence in raw_sentences if sentence.strip()]
        if not sentences:
            raise SegmentationError("没有句子")
    elif "text" in body:
        sentences = parse_transcript(body["text"])
    else:
        raise SegmentationError("需要 text 或 sentences")

    tail_pad_ms = TAIL_PAD_MS
    if "tail_pad_ms" in body:
        if isinstance(body["tail_pad_ms"], bool):
            raise SegmentationError("tail_pad_ms 必须是数字")
        try:
            tail_pad_ms = int(round(float(body["tail_pad_ms"])))
        except (TypeError, ValueError) as exc:
            raise SegmentationError("tail_pad_ms 必须是数字") from exc
        if tail_pad_ms < 0:
            raise SegmentationError("tail_pad_ms 不能为负")

    warning = None
    words_payload = body.get("words")
    duration = body.get("duration_ms")
    if words_payload:
        try:
            words = parse_words(words_payload)
            spans = segment_by_word_timestamps(sentences, words, tail_pad_ms=tail_pad_ms)
            source = "word_timestamps"
        except SegmentationError as exc:
            if body.get("fallback") == "proportional" and duration is not None:
                spans = estimate_proportional(sentences, _positive_int(duration, "duration_ms"))
                source = "proportional_estimate"
                warning = str(exc)
            else:
                raise
    elif duration is not None:
        spans = estimate_proportional(sentences, _positive_int(duration, "duration_ms"))
        source = "proportional_estimate"
    else:
        raise SegmentationError("需要词级时间戳，或提供 duration_ms 以按比例估计")

    return {
        "timing_source": source,
        "timing_note_zh": TIMING_NOTES[source],
        "warning": warning,
        "tail_pad_ms": tail_pad_ms if source == "word_timestamps" else 0,
        "sentences": [span.as_dict() for span in spans],
    }
