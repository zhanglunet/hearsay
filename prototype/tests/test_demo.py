import array
import json
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.demo import AUDIO_PATH, MANIFEST_PATH, load_demo_payload
from m1_shadow.segment import parse_words, segment_by_word_timestamps, tokenize


class DemoFixtureTests(unittest.TestCase):
    def test_demo_is_synthetic_speech_and_segments(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertFalse(manifest["learner_recording"])
        self.assertTrue(manifest["synthetic"])
        self.assertEqual(len(manifest["sentences_text"]), 6)
        for sentence in manifest["sentences_text"]:
            self.assertGreaterEqual(len(tokenize(sentence)), 6)
        words = parse_words(manifest["word_timestamps"])
        spans = segment_by_word_timestamps(
            manifest["sentences_text"],
            words,
            tail_pad_ms=manifest["tail_pad_ms"],
        )
        with wave.open(str(AUDIO_PATH)) as handle:
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getsampwidth(), 2)
            frames = handle.getnframes()
            rate = handle.getframerate()
            samples = array.array("h")
            samples.frombytes(handle.readframes(frames))
        duration_ms = frames / rate * 1000
        self.assertGreaterEqual(duration_ms, spans[-1].end_ms)
        rms = (sum(value * value for value in samples) / len(samples)) ** 0.5
        self.assertGreater(rms, 100)
        payload = load_demo_payload()
        self.assertEqual(len(payload["sentences"]), 6)
        self.assertFalse(payload["learner_recording"])
        self.assertFalse(payload["phoneme_feedback"])
        self.assertEqual(payload["error_instances"], [])
        self.assertIsNone(payload["phoneme_profile"])
        self.assertIn("0.148", payload["product_rule"])
        self.assertEqual(payload["session_type"], "shadow")


if __name__ == "__main__":
    unittest.main()
