import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from listen.questions import (DEMO_QUESTIONS, can_do_verdicts, dictation_score,
                              evaluate, public_question)
from listen.server import make_server
from m3_learner.store import LearnerStore


class EngineTests(unittest.TestCase):
    def test_dictation_exact_typo_and_missing(self):
        ref = "Could you send me the report before the meeting today?"
        self.assertEqual(dictation_score(ref, ref), 1.0)
        self.assertEqual(dictation_score(ref, "could you send me the report before the meeting today"), 1.0)
        self.assertEqual(dictation_score(ref, "Could you send me the reprt before the meeting today"), 1.0)
        partial = dictation_score(ref, "Could you send me the report")
        self.assertGreater(partial, 0.5)
        self.assertLess(partial, 1.0)

    def test_evaluate_types(self):
        q1, q2, q3, q4 = DEMO_QUESTIONS
        self.assertTrue(evaluate(q1, 0)["passed"])
        self.assertFalse(evaluate(q1, 2)["passed"])
        self.assertTrue(evaluate(q2, "because traffic is terrible")["passed"])
        self.assertFalse(evaluate(q2, "I like it")["passed"])
        self.assertTrue(evaluate(q3, q3["answer"])["passed"])
        self.assertFalse(evaluate(q3, "hello world")["passed"])
        self.assertTrue(evaluate(q4, 0)["passed"])
        self.assertFalse(evaluate(q4, 1)["passed"])

    def test_unsupported_type(self):
        with self.assertRaises(ValueError):
            evaluate(dict(type="spoken_response"), "hi")

    def test_can_do_verdicts(self):
        results = [dict(question=dict(can_do_id="L-A2-01"), passed=True),
                   dict(question=dict(can_do_id="L-A2-01"), passed=True),
                   dict(question=dict(can_do_id="L-A2-01"), passed=True),
                   dict(question=dict(can_do_id="L-A2-01"), passed=False),
                   dict(question=dict(can_do_id="L-B1-04"), passed=True),
                   dict(question=dict(can_do_id="L-A1-01"), passed=True),
                   dict(question=dict(can_do_id="L-A1-01"), passed=False),
                   dict(question=dict(can_do_id=None), passed=False)]
        verdicts = can_do_verdicts(results)
        self.assertEqual(verdicts["L-A2-01"], "partial")      # 0.75
        self.assertEqual(verdicts["L-B1-04"], "demonstrated")
        self.assertEqual(verdicts["L-A1-01"], "failed")       # 0.5
        self.assertNotIn(None, verdicts)

    def test_public_question_hides_answer(self):
        for q in DEMO_QUESTIONS:
            self.assertNotIn("answer", public_question(q))
            self.assertNotIn("required_keywords", public_question(q))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HEARSAY_M3_STORE"] = str(Path(self.tmp.name) / "learner.json")
        os.environ.pop("HEARSAY_M3_INGEST", None)
        self.httpd = make_server(0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        os.environ.pop("HEARSAY_M3_STORE", None)
        self.tmp.cleanup()

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_full_listen_flow(self):
        status, material = self.request("/api/material")
        self.assertEqual(status, 200)
        self.assertEqual(len(material["questions"]), 4)
        self.assertEqual(len(material["sentences"]), 6)
        self.assertNotIn("answer", material["questions"][0])

        status, payload = self.request("/api/answer", dict(question_id="q1", answer=0))
        self.assertTrue(payload["passed"])
        sid = payload["session_id"]
        status, payload = self.request("/api/answer",
                                       dict(session_id=sid, question_id="q4", answer=1))
        self.assertFalse(payload["passed"])
        self.assertIn("Could", payload["expected"])
        status, payload = self.request("/api/answer",
                                       dict(session_id=sid, question_id="q3", answer="hello"))
        self.assertFalse(payload["passed"])

        status, recap = self.request("/api/finish", dict(session_id=sid))
        self.assertEqual(status, 200)
        self.assertEqual(recap["answered"], 3)
        self.assertEqual(recap["passed"], 1)
        self.assertEqual(recap["can_do"]["L-A2-01"], "demonstrated")
        self.assertEqual(recap["can_do"]["L-B1-04"], "failed")
        self.assertEqual(recap["h_errors"], 2)  # q4、q3 各一条 H02
        store = LearnerStore(os.environ["HEARSAY_M3_STORE"])
        self.assertEqual(store.data["error_patterns"]["H02"]["count_total"], 2)
        evidence = store.data["can_do_evidence"]
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(e["source"] == "rule" for e in evidence))

        # 再次 finish 返回缓存，不重复写证据与错误
        status, _ = self.request("/api/finish", dict(session_id=sid))
        store = LearnerStore(os.environ["HEARSAY_M3_STORE"])
        self.assertEqual(len(store.data["can_do_evidence"]), 2)
        self.assertEqual(store.data["error_patterns"]["H02"]["count_total"], 2)

    def test_answer_validation(self):
        status, payload = self.request("/api/answer", dict(question_id="q99", answer=1))
        self.assertEqual(status, 400)
        status, payload = self.request("/api/finish", dict(session_id="nope"))
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
