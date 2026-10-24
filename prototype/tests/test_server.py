import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("HEARSAY_ASR", None)
        cls.httpd = make_server(0)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.httpd.server_address
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, path, payload=None, raw=None, content_type="application/json"):
        data = raw if raw is not None else (None if payload is None else json.dumps(payload).encode())
        headers = {}
        if data is not None and content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read()
                return response.status, response.headers.get("Content-Type", ""), body
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read()

    def test_pages_and_demo_audio(self):
        status, content_type, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("跟读".encode(), body)
        status, content_type, body = self.request("/media/reference.wav")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "audio/wav")
        self.assertTrue(body.startswith(b"RIFF"))
        status, _content_type, body = self.request("/media/../web/index.html")
        self.assertEqual(status, 404)
        payload = json.loads(body)
        self.assertEqual(payload["error_instances"], [])

    def test_feedback_and_summary_drop_phonemes(self):
        status, _content_type, body = self.request(
            "/api/feedback",
            {
                "reference": "I have two book",
                "hypothesis": "I have",
                "phonemes": [{"heard": "S"}],
                "error_instances": [{"code": "P01"}],
            },
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["low_score"])
        self.assertEqual(payload["error_instances"], [])
        self.assertIsNone(payload["phoneme_profile"])
        self.assertIsNone(payload["common_substitution"])
        self.assertFalse(payload["phoneme_feedback"])
        self.assertIn("phonemes", payload["ignored_inputs"])

        status, _content_type, body = self.request(
            "/api/shadow-summary",
            {
                "sentences": [
                    {"idx": 0, "reference": "I have two book", "hypothesis": "I have two book"},
                    {"idx": 2, "reference": "the restaurant has noodles", "hypothesis": "nope"},
                ]
            },
        )
        summary = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(summary["low_score_sentence_idxs"], [2])
        self.assertEqual(summary["error_instances"], [])
        self.assertEqual(summary["session_type"], "shadow")

    def test_segment_word_timestamps_and_bad_json(self):
        status, _content_type, body = self.request(
            "/api/segment",
            {
                "sentences": ["a b", "c d"],
                "words": [
                    {"word": "a", "start_ms": 0, "end_ms": 100},
                    {"word": "b", "start_ms": 100, "end_ms": 200},
                    {"word": "c", "start_ms": 700, "end_ms": 800},
                    {"word": "d", "start_ms": 800, "end_ms": 900},
                ],
            },
        )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["timing_source"], "word_timestamps")
        self.assertEqual(payload["sentences"][0]["end_ms"], 450)
        self.assertEqual(payload["error_instances"], [])

        status, _content_type, body = self.request("/api/feedback", raw=b"not-json")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error_instances"], [])

    def test_transcribe_is_off_and_writes_no_temp_audio(self):
        before = set(Path("/tmp").glob("hearsay-m1-*"))
        with mock.patch("m1_shadow.asr.find_spec", return_value=None):
            status, _content_type, body = self.request(
                "/api/transcribe",
                raw=b"not-audio",
                content_type="audio/wav",
            )
        after = set(Path("/tmp").glob("hearsay-m1-*"))
        self.assertEqual(status, 409)
        payload = json.loads(body)
        self.assertIn("pip install faster-whisper", payload["error"])
        self.assertIn("粘贴", payload["error"])
        self.assertEqual(payload["error_instances"], [])
        self.assertFalse(payload["phoneme_feedback"])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
