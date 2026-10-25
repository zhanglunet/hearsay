import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m2_dialogue.coverage import coverage
from m2_dialogue.recast import scan_recasts
from m2_dialogue.scenario import OPENING, UNEXPECTED_QUESTION
from m2_dialogue.server import make_server
from m2_dialogue.session import DialogueError, DialogueSession
from m2_dialogue.tutor import MockTutor, TutorError, make_tutor


class RecastTests(unittest.TestCase):
    def test_rules_fire_with_code_and_provisional_status(self):
        cases = {
            "It is more better than mine.": "G13",
            "We discussed about the plan.": "G08",
            "I very like this movie.": "G09",
            "She go to work by bus.": "G03",
            "I will see you in Monday.": "G08",
        }
        for text, code in cases.items():
            hits = scan_recasts(text)
            self.assertEqual(len(hits), 1, text)
            self.assertEqual(hits[0]["code"], code)
            self.assertEqual(hits[0]["status"], "provisional")
            self.assertEqual(hits[0]["detected_by"], "rule")
            self.assertTrue(hits[0]["observed"])

    def test_clean_text_has_no_recast(self):
        self.assertEqual(scan_recasts("She goes to work. I really like it. See you on Monday."), [])


class CoverageTests(unittest.TestCase):
    def test_reason_and_date(self):
        self.assertEqual(coverage(["It is delayed because we are waiting for data."], False, 0)[:2],
                         [True, False])
        self.assertEqual(coverage(["I can finish it next Monday."], False, 0)[:2], [False, True])

    def test_third_objective_needs_event_and_reply(self):
        self.assertEqual(coverage(["sure"], False, 0), [False, False, False])
        self.assertEqual(coverage(["sure"], True, 0)[2], False)
        self.assertEqual(coverage(["sure"], True, 1)[2], True)


class SessionTests(unittest.TestCase):
    def test_full_flow_and_recap(self):
        s = DialogueSession(MockTutor())
        self.assertEqual(s.turns[0]["text"], OPENING)
        s.add_learner_turn("Hi Alex. It is more better to wait.")
        self.assertEqual(len(s.recasts), 1)
        reply = s.add_learner_turn("It is delayed because we are waiting for the data.")
        self.assertEqual(reply, UNEXPECTED_QUESTION)
        self.assertTrue(s.event_fired)
        s.add_learner_turn("Sure, I can send the summary today.")
        self.assertEqual(s.replies_after_event, 1)
        s.add_learner_turn("I will finish the report next Monday.")
        recap = s.end()
        self.assertEqual(recap["n_learner_turns"], 4)
        self.assertEqual(recap["n_agent_turns"], 5)
        self.assertTrue(recap["scripted_event_fired"])
        self.assertEqual([o["covered"] for o in recap["objectives"]], [True, True, True])
        self.assertEqual(recap["learner_words"], sum(len(t.split()) for t in s.learner_texts))
        self.assertGreater(recap["learner_word_share"], 0)
        self.assertEqual(recap["recasts"][0]["code"], "G13")
        self.assertIn("待核对", recap["summary_zh"])
        self.assertEqual(recap["session_type"], "converse")

    def test_wrap_up_after_five_turns(self):
        s = DialogueSession(MockTutor())
        for _ in range(5):
            reply = s.add_learner_turn("Because of problems. Next Friday. Sure.")
        self.assertIn("Good luck", reply)

    def test_empty_and_after_end_rejected(self):
        s = DialogueSession(MockTutor())
        with self.assertRaises(DialogueError):
            s.add_learner_turn("   ")
        s.end()
        with self.assertRaises(DialogueError):
            s.add_learner_turn("hello")
        self.assertEqual(s.end()["session_id"], s.id)


class TutorFactoryTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("HEARSAY_LLM", None)
        os.environ.pop("HEARSAY_ANTHROPIC_API_KEY", None)

    def test_default_is_mock(self):
        os.environ.pop("HEARSAY_LLM", None)
        self.assertEqual(make_tutor().name, "mock")

    def test_unknown_backend(self):
        os.environ["HEARSAY_LLM"] = "something"
        with self.assertRaises(TutorError):
            make_tutor()

    def test_anthropic_requires_key(self):
        os.environ["HEARSAY_LLM"] = "anthropic"
        os.environ.pop("HEARSAY_ANTHROPIC_API_KEY", None)
        with self.assertRaises(TutorError):
            make_tutor()


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = make_server(0, tutor=MockTutor())
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.httpd.server_address
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def request(self, path, payload=None, method=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_scenario_and_full_dialogue(self):
        status, payload = self.request("/api/scenario")
        self.assertEqual(status, 200)
        self.assertEqual(payload["tutor"], "mock")
        self.assertEqual(payload["scenario"]["id"], "m2-project-delay")

        status, payload = self.request("/api/session", {})
        self.assertEqual(status, 200)
        sid = payload["session_id"]
        self.assertEqual(payload["opening"], OPENING)

        status, payload = self.request("/api/turn", {"session_id": sid, "text": "I very like this project. Next Friday."})
        self.assertEqual(status, 200)
        self.assertEqual(payload["new_recasts"][0]["code"], "G09")
        self.assertEqual(payload["error_instances"], [])
        self.assertFalse(payload["phoneme_feedback"])

        status, recap = self.request("/api/end", {"session_id": sid})
        self.assertEqual(status, 200)
        self.assertEqual(recap["n_learner_turns"], 1)
        self.assertEqual(recap["error_instances"], [])
        self.assertIn("provisional", recap["product_rule"])
        self.assertEqual(len(recap["objectives"]), 3)

        status, payload = self.request("/api/turn", {"session_id": sid, "text": "hello"})
        self.assertEqual(status, 400)

    def test_bad_requests(self):
        status, payload = self.request("/api/turn", {"session_id": "nope", "text": "hi"})
        self.assertEqual(status, 400)
        self.assertIn("没有这个会话", payload["error"])
        status, _ = self.request("/api/nope", {})
        self.assertEqual(status, 404)
        status, payload = self.request("/api/session", {})
        self.assertEqual(status, 200)
        status, payload = self.request("/api/turn", {"session_id": payload["session_id"], "text": " "})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
