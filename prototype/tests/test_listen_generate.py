"""材料生成：听辨题校验与模型输出不合格时的重试。不发真实请求。"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from listen.generate import GENERATE_ATTEMPTS, _heard_in, generate_material, validate_material
from m2_dialogue.tutor import TutorError

# 2026-10-27 线上 DeepSeek 实际生成成功的那份材料（节选）
SENTENCES = ["Hi Tom, do you have a minute to talk about the project?",
             "I'm afraid we can't finish the report by Friday.",
             "Two of our team members were sick last week, so we lost some time."]


def material(discrimination):
    return dict(title="Delay", sentences=list(SENTENCES), questions=[
        dict(type="gist", q_zh="主旨？", options=["延期", "请假"], answer=0),
        dict(dict(type="discrimination", q_zh="can 还是 can't？"), **discrimination)])


class DiscriminationTests(unittest.TestCase):
    def test_partial_sentence_option_from_production_passes(self):
        m = validate_material(material(dict(
            options=["We can finish the report by Friday.", "We can't finish the report by Friday."],
            answer=1)))
        self.assertEqual(m["questions"][1]["sentence_idx"], 1)

    def test_verbatim_sentence_with_idx_passes(self):
        m = validate_material(material(dict(
            sentence_idx=1, answer=0,
            options=["I'm afraid we can't finish the report by Friday.",
                     "I'm afraid we can finish the report by Friday."])))
        self.assertEqual(m["questions"][1]["sentence_idx"], 1)

    def test_correct_option_not_in_sentence_rejected(self):
        with self.assertRaisesRegex(ValueError, "正确选项"):
            validate_material(material(dict(
                sentence_idx=1, answer=0,
                options=["We can finish the report by Friday.", "We can't finish it."])))

    def test_distractor_also_in_sentence_rejected(self):
        with self.assertRaisesRegex(ValueError, "干扰项"):
            validate_material(material(dict(
                sentence_idx=1, answer=0, options=["can't finish", "finish"])))

    def test_correct_option_nowhere_rejected(self):
        with self.assertRaisesRegex(ValueError, "不在任何一句"):
            validate_material(material(dict(answer=0, options=["ship", "sheep"])))

    def test_can_and_cant_are_different_words(self):
        self.assertFalse(_heard_in("can", "we can't go"))
        self.assertTrue(_heard_in("can't", "We can’t go."))
        self.assertTrue(_heard_in("we CAN'T go", "We can't go!"))


def reply(raw):
    return {"content": [{"type": "text", "text": raw if isinstance(raw, str) else json.dumps(raw)}],
            "stop_reason": "end_turn"}


GOOD = material(dict(sentence_idx=1, answer=0, options=[SENTENCES[1], SENTENCES[1].replace("can't", "can")]))
BAD = material(dict(sentence_idx=1, answer=0, options=["ship", "sheep"]))


class RetryTests(unittest.TestCase):
    def run_with(self, side_effect):
        calls = mock.Mock(side_effect=side_effect)
        with mock.patch("listen.generate.anthropic_request", calls), \
             mock.patch.dict(os.environ, {"HEARSAY_LLM_API_KEY": "test-key"}):
            try:
                return generate_material("B1", "项目延期"), calls.call_count
            except TutorError as exc:
                return exc, calls.call_count

    def test_retries_once_after_invalid_output(self):
        result, calls = self.run_with([reply(BAD), reply(GOOD)])
        self.assertEqual(calls, 2)
        self.assertEqual(result["title"], "Delay")

    def test_retries_once_after_non_json(self):
        result, calls = self.run_with([reply("sorry, here you go"), reply(GOOD)])
        self.assertEqual(calls, 2)
        self.assertIsInstance(result, dict)

    def test_gives_up_after_attempts_with_reasons(self):
        result, calls = self.run_with([reply(BAD), reply("not json")])
        self.assertEqual(calls, GENERATE_ATTEMPTS)
        self.assertIsInstance(result, TutorError)
        self.assertIn("正确选项", str(result))
        self.assertIn("没有返回 JSON", str(result))

    def test_api_error_is_not_retried(self):
        result, calls = self.run_with([TutorError("Claude 接口返回 HTTP 401。")])
        self.assertEqual(calls, 1)
        self.assertIn("401", str(result))

    def test_prompt_states_discrimination_rules(self):
        captured = {}

        def fake(payload, *_a):
            captured["prompt"] = payload["messages"][0]["content"]
            return reply(GOOD)

        with mock.patch("listen.generate.anthropic_request", fake), \
             mock.patch.dict(os.environ, {"HEARSAY_LLM_API_KEY": "test-key"}):
            generate_material("B1", "项目延期")
        for must in ('"type"', "sentence_idx", "一字不改", "干扰项", "项目延期", "B1"):
            self.assertIn(must, captured["prompt"])


if __name__ == "__main__":
    unittest.main()
