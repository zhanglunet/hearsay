"""LLM 公共调用：可选关闭 thinking、停止原因检查。不发真实请求。"""

import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m2_dialogue import tutor
from m2_dialogue.tutor import TutorError, anthropic_request, llm_thinking, response_text


class FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ThinkingTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop(tutor.THINKING_ENV, None)

    def tearDown(self):
        os.environ.pop(tutor.THINKING_ENV, None)
        if self._old is not None:
            os.environ[tutor.THINKING_ENV] = self._old

    def sent_payload(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["body"] = json.loads(req.data.decode())
            captured["headers"] = dict(req.header_items())
            return FakeResp(json.dumps({"content": [{"type": "text", "text": "hi"}],
                                        "stop_reason": "end_turn"}).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            anthropic_request({"model": "m", "max_tokens": 10, "messages": []}, "k", "https://x/v1/messages")
        return captured

    def test_unset_omits_thinking(self):
        self.assertIsNone(llm_thinking())
        self.assertNotIn("thinking", self.sent_payload()["body"])

    def test_disabled_is_sent(self):
        os.environ[tutor.THINKING_ENV] = "disabled"
        sent = self.sent_payload()
        self.assertEqual(sent["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(sent["headers"].get("X-api-key"), "k")

    def test_explicit_thinking_in_payload_wins(self):
        os.environ[tutor.THINKING_ENV] = "disabled"
        captured = {}

        def fake_urlopen(req, timeout):
            captured["body"] = json.loads(req.data.decode())
            return FakeResp(b'{"content":[{"type":"text","text":"x"}]}')

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            anthropic_request({"model": "m", "thinking": {"type": "adaptive"}}, "k", "https://x")
        self.assertEqual(captured["body"]["thinking"], {"type": "adaptive"})

    def test_unknown_value_rejected(self):
        os.environ[tutor.THINKING_ENV] = "off"
        with self.assertRaises(TutorError):
            llm_thinking()


class ResponseTextTests(unittest.TestCase):
    def test_skips_thinking_blocks(self):
        data = {"content": [{"type": "thinking", "thinking": "hmm"},
                            {"type": "text", "text": "Hello"}], "stop_reason": "end_turn"}
        self.assertEqual(response_text(data), "Hello")

    def test_refusal(self):
        with self.assertRaisesRegex(TutorError, "拒绝"):
            response_text({"content": [], "stop_reason": "refusal"})

    def test_truncated_without_text(self):
        data = {"content": [{"type": "thinking", "thinking": "long..."}], "stop_reason": "max_tokens"}
        with self.assertRaisesRegex(TutorError, "max_tokens"):
            response_text(data)

    def test_truncated_with_text_is_returned(self):
        data = {"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"}
        self.assertEqual(response_text(data), "partial")

    def test_empty(self):
        with self.assertRaises(TutorError):
            response_text({"content": [], "stop_reason": "end_turn"})

    def test_malformed(self):
        with self.assertRaises(TutorError):
            response_text({"nope": 1})


if __name__ == "__main__":
    unittest.main()
