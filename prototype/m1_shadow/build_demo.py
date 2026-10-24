"""用 espeak-ng 生成可提交的演示参考音。

CI 不跑这个脚本，也不要求机器上有 espeak-ng。
生成物是合成语音，不是学习者录音，可以入库。

在 prototype 目录执行：python -m m1_shadow.build_demo
"""

from __future__ import annotations

import array
import json
import subprocess
import tempfile
import wave
from pathlib import Path

from m1_shadow.demo import AUDIO_PATH, MANIFEST_PATH
from m1_shadow.segment import (
    TAIL_PAD_MS,
    TIMING_NOTES,
    WordStamp,
    allocate_positive,
    segment_by_word_timestamps,
    tokenize,
)

DEMO_SENTENCES = [
    "I usually take the subway to work because the traffic is terrible.",
    "Could you send me the report before the meeting today?",
    "We were planning to go hiking this weekend but it will rain.",
    "The restaurant on the corner has really good noodles.",
    "I have been learning English for about three years now.",
    "Please record yourself and listen to it again tomorrow.",
]

INTER_SENTENCE_MS = 450
SPEECH_RATE = "148"


def _synth(text: str, dest: Path) -> None:
    try:
        subprocess.run(
            ["espeak-ng", "-v", "en-us", "-s", SPEECH_RATE, "-g", "0", "-w", str(dest), text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise SystemExit("需要本机的 espeak-ng 才能重新生成演示音频。运行原型本身不需要它。") from exc


def _read_wav(path: Path) -> tuple[int, array.array]:
    with wave.open(str(path)) as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise SystemExit(f"espeak 输出的 wav 格式不是单声道 16-bit：{path}")
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
        return handle.getframerate(), samples


def _trim(samples: array.array, sample_rate: int) -> array.array:
    threshold = 300
    hop = max(1, int(sample_rate * 0.005))
    first = None
    last = None
    for offset in range(0, len(samples), hop):
        chunk = samples[offset : offset + hop]
        if not chunk:
            break
        rms = (sum(value * value for value in chunk) / len(chunk)) ** 0.5
        if rms > threshold:
            if first is None:
                first = offset
            last = offset + len(chunk)
    if first is None or last is None:
        return samples
    pad = int(sample_rate * 0.04)
    start = max(0, first - pad)
    end = min(len(samples), last + pad)
    if end - start < int(sample_rate * 0.08):
        return samples
    return samples[start:end]


def _silence(sample_rate: int, duration_ms: int) -> array.array:
    count = int(sample_rate * duration_ms / 1000)
    return array.array("h", [0] * count)


def _ms(samples: int, sample_rate: int) -> int:
    return int(round(samples / sample_rate * 1000))


def build() -> None:
    pieces: list[array.array] = []
    words: list[WordStamp] = []
    sample_rate = None
    cursor = 0
    with tempfile.TemporaryDirectory(prefix="hearsay-demo-") as temp_name:
        temp = Path(temp_name)
        for sentence in DEMO_SENTENCES:
            tokens = tokenize(sentence)
            if len(tokens) < 6:
                raise SystemExit(f"演示句短于 6 个词：{sentence}")
            sentence_wav = temp / "sentence.wav"
            _synth(sentence, sentence_wav)
            rate, sentence_audio = _read_wav(sentence_wav)
            sentence_audio = _trim(sentence_audio, rate)
            if sample_rate is None:
                sample_rate = rate
            elif rate != sample_rate:
                raise SystemExit("espeak 采样率不一致")
            lengths = []
            for token in tokens:
                word_wav = temp / "word.wav"
                _synth(token, word_wav)
                word_rate, word_audio = _read_wav(word_wav)
                if word_rate != rate:
                    raise SystemExit("espeak 采样率不一致")
                lengths.append(max(len(_trim(word_audio, word_rate)), 1))
            assigned = allocate_positive(lengths, len(sentence_audio))
            offset = 0
            for token, length in zip(tokens, assigned):
                start = cursor + offset
                end = start + length
                start_ms = _ms(start, sample_rate)
                end_ms = _ms(end, sample_rate)
                if words and start_ms < words[-1].end_ms:
                    start_ms = words[-1].end_ms
                if end_ms <= start_ms:
                    end_ms = start_ms + 1
                words.append(WordStamp(token, start_ms, end_ms))
                offset += length
            pieces.append(sentence_audio)
            pieces.append(_silence(sample_rate, INTER_SENTENCE_MS))
            cursor += len(sentence_audio) + int(sample_rate * INTER_SENTENCE_MS / 1000)

    assert sample_rate is not None
    merged = array.array("h")
    for piece in pieces:
        merged.extend(piece)
    AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(AUDIO_PATH), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(merged.tobytes())

    spans = segment_by_word_timestamps(DEMO_SENTENCES, words, tail_pad_ms=TAIL_PAD_MS)
    duration_ms = _ms(len(merged), sample_rate)
    if spans[-1].end_ms > duration_ms:
        raise SystemExit("句尾留白超出了音频长度")
    manifest = {
        "id": "demo-espeak-shadow-6",
        "kind": "monologue",
        "title": "日常口语六句（合成演示）",
        "target_cefr": "A2",
        "topic_tags": ["daily", "work"],
        "generated_by": "imported",
        "learner_recording": False,
        "synthetic": True,
        "voice": "espeak-ng en-us",
        "speech_rate": int(SPEECH_RATE),
        "audio_ref": "reference.wav",
        "sample_rate": sample_rate,
        "duration_ms": duration_ms,
        "timing_source": "espeak_sentence_concat",
        "timing_note_zh": TIMING_NOTES["espeak_sentence_concat"],
        "tail_pad_ms": TAIL_PAD_MS,
        "inter_sentence_silence_ms": INTER_SENTENCE_MS,
        "sentences_text": DEMO_SENTENCES,
        "word_timestamps": [
            {"word": word.word, "start_ms": word.start_ms, "end_ms": word.end_ms} for word in words
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {AUDIO_PATH} ({duration_ms} ms, {sample_rate} Hz)")
    print(f"wrote {MANIFEST_PATH} ({len(spans)} sentences)")


if __name__ == "__main__":
    build()
