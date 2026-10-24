"""读取已提交的合成演示材料。音频不是学习者录音。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from m1_shadow.limits import seal_no_phoneme_writes
from m1_shadow.segment import parse_words, segment_by_word_timestamps, tokenize

DEMO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
MANIFEST_PATH = DEMO_DIR / "manifest.json"
AUDIO_PATH = DEMO_DIR / "reference.wav"


@lru_cache(maxsize=1)
def load_demo_payload() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    words = parse_words(manifest["word_timestamps"])
    sentences = manifest["sentences_text"]
    spans = segment_by_word_timestamps(
        sentences,
        words,
        tail_pad_ms=int(manifest.get("tail_pad_ms", 250)),
    )
    tokens = sum(len(tokenize(sentence)) for sentence in sentences)
    spoken_ms = max(1, words[-1].end_ms - words[0].start_ms)
    return seal_no_phoneme_writes(
        {
            "id": manifest["id"],
            "kind": manifest["kind"],
            "title": manifest["title"],
            "target_cefr": manifest["target_cefr"],
            "topic_tags": manifest["topic_tags"],
            "generated_by": "imported",
            "session_type": "shadow",
            "learner_recording": False,
            "audio_url": "/media/reference.wav",
            "timing_source": manifest["timing_source"],
            "timing_note_zh": manifest["timing_note_zh"],
            "tail_pad_ms": int(manifest.get("tail_pad_ms", 250)),
            "wpm": round(tokens / spoken_ms * 60000, 1),
            "sentences": [span.as_dict() for span in spans],
        }
    )
