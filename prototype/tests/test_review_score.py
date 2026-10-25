import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m2_dialogue.review_score import apply_scores, score_review, validate_scores
from m2_dialogue.server import make_server
from m2_dialogue.tutor import MockTutor
from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore


class ValidateScoresTests(unittest.TestCase):
    def test_validation(self):
        raw = [
            dict(code="G04", outcome="good", evidence="I went home"),
            dict(code="G99", outcome="good", evidence="I went home"),
            dict(code="G04", outcome="perfect", evidence="I went home"),
            dict(code="G04", outcome="again", evidence="not said at all"),
            dict(code="G13", outcome="again", evidence="It is more better"),
        ]
        scores = validate_scores(raw, ["G04", "G13"], "I went home. It is more better.")
        self.assertEqual([(s["code"], s["outcome"], s["rating"]) for s in scores],
                         [("G04", "good", 3), ("G13", "again", 1)])

    def test_apply_scores_moves_card(self):
        with tempfile.TemporaryDirectory() as d:
            store = LearnerStore(Path(d) / "x.json")
            recap = dict(session_id="s1", batch=dict(confirmed=[
                dict(utterance_id=1, code="G04", observed="x", expected="y",
                     detected_by="asr_llm", confidence=0.9, merged_provisional=False)], discarded=[]))
            ingest_recap(store, recap)
            applied = apply_scores(store, [dict(code="G04", outcome="good", rating=3, evidence="x")])
            self.assertEqual(applied, ["error:G04"])
            card = next(c for c in store.cards() if c.item_id == "error:G04")
            self.assertGreater(card.stability, 0)
            self.assertEqual(card.reps, 1)


class ServerScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HEARSAY_M3_STORE"] = str(Path(self.tmp.name) / "learner.json")
        os.environ["HEARSAY_LLM_API_KEY"] = "test-key"
        store = LearnerStore(os.environ["HEARSAY_M3_STORE"])
        ingest_recap(store, dict(session_id="seed", batch=dict(confirmed=[
            dict(utterance_id=1, code="G04", observed="x", expected="y",
                 detected_by="asr_llm", confidence=0.9, merged_provisional=False)], discarded=[])))
        self.httpd = make_server(0, tutor=MockTutor())
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        os.environ.pop("HEARSAY_M3_STORE", None)
        os.environ.pop("HEARSAY_LLM_API_KEY", None)
        self.tmp.cleanup()

    def test_end_applies_llm_scores(self):
        def post(path, payload):
            req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())

        payload = post("/api/session", {"mode": "review"})
        sid = payload["session_id"]
        post("/api/turn", {"session_id": sid, "text": "Yesterday I went to the park."})
        scoring = {"content": [{"text": json.dumps({"scores": [
            {"code": "G04", "outcome": "good", "evidence": "I went to the park"}]})}]}
        with mock.patch("m2_dialogue.review_score.anthropic_request", return_value=scoring):
            recap = post("/api/end", {"session_id": sid})
        self.assertEqual(recap["review_scores"][0]["outcome"], "good")
        self.assertEqual(recap["review_applied"], ["error:G04"])
        card = next(c for c in LearnerStore(os.environ["HEARSAY_M3_STORE"]).cards()
                    if c.item_id == "error:G04")
        self.assertEqual(card.reps, 1)


if __name__ == "__main__":
    unittest.main()
