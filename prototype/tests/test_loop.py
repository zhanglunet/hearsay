"""一天的闭环：M4 复习场景 → M2 对话 → 复盘自动入 M3 → M4 评分回流 FSRS。"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m2_dialogue.server import make_server as make_m2_server
from m2_dialogue.tutor import ELICIT_QUESTIONS, MockTutor
from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore
from m4_plan.server import make_server as make_m4_server


def confirmed_recap(session_id, code):
    return dict(session_id=session_id, batch=dict(
        confirmed=[dict(utterance_id=1, code=code, observed="x", expected="y",
                        detected_by="asr_llm", confidence=0.9, merged_provisional=False)],
        discarded=[]))


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp.name) / "learner.json"
        os.environ["HEARSAY_M3_STORE"] = str(self.store_path)
        os.environ.pop("HEARSAY_M3_INGEST", None)
        store = LearnerStore(self.store_path)
        ingest_recap(store, confirmed_recap("seed-1", "G04"))
        self.m2 = make_m2_server(0, tutor=MockTutor())
        self.m4 = make_m4_server(0, store=LearnerStore(self.store_path))
        self.threads = []
        for server in (self.m2, self.m4):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.m2_base = f"http://127.0.0.1:{self.m2.server_address[1]}"
        self.m4_base = f"http://127.0.0.1:{self.m4.server_address[1]}"

    def tearDown(self):
        for server in (self.m2, self.m4):
            server.shutdown()
            server.server_close()
        os.environ.pop("HEARSAY_M3_STORE", None)
        self.tmp.cleanup()

    def request(self, base, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_full_day_loop(self):
        # 1) M4 复习场景直接进入 M2：带 G04 目标，导师制造过去时使用机会
        status, payload = self.request(self.m2_base, "/api/session", {"mode": "review"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["scenario_id"], "m3-review-delay")
        self.assertEqual(payload["scenario"]["target_error_codes"], ["G04"])
        sid = payload["session_id"]
        for text in ["It is delayed because of data.", "Sure, I can do that.",
                     "I will finish next Monday."]:
            status, payload = self.request(self.m2_base, "/api/turn",
                                           {"session_id": sid, "text": text})
            self.assertEqual(status, 200)
        self.assertEqual(payload["agent_text"], ELICIT_QUESTIONS["G04"])

        # 2) 复盘自动入 M3：批处理确认 G04 后错误档案 +1（幂等）
        fake_batch = dict(confirmed=[dict(utterance_id=1, code="G04", observed="I go",
                                          expected="I went", detected_by="asr_llm",
                                          confidence=0.9, merged_provisional=False)],
                          discarded=[], false_positive_rate=None, duration_sec=0.1,
                          transcripts=[], asr="whisperx_verbatim", detection="asr_llm")
        with mock.patch("m2_dialogue.server.batch_enabled", return_value=True), \
             mock.patch("m2_dialogue.server.run_batch", return_value=fake_batch):
            status, recap = self.request(self.m2_base, "/api/end", {"session_id": sid})
            self.assertEqual(status, 200)
            self.assertTrue(recap["ingest"]["ingested"])
            self.assertEqual(recap["target_error_codes"], ["G04"])
            self.assertTrue(all(o["covered"] is None for o in recap["objectives"]))
            store = LearnerStore(self.store_path)
            self.assertEqual(store.data["error_patterns"]["G04"]["count_total"], 2)
            status, recap2 = self.request(self.m2_base, "/api/end", {"session_id": sid})
            self.assertEqual(recap2["ingest"]["reason"], "session_already_ingested")
            store = LearnerStore(self.store_path)
            self.assertEqual(store.data["error_patterns"]["G04"]["count_total"], 2)

        # 3) M4 评分回流：评分后卡推到未来，计划里不再到期
        status, plan = self.request(self.m4_base, "/api/plan?minutes=15")
        self.assertEqual(status, 200)
        self.assertTrue(any(c["item_id"] == "error:G04" for c in plan["due_items"]))
        status, payload = self.request(self.m4_base, "/api/review",
                                       {"item_id": "error:G04", "rating": 3})
        self.assertEqual(status, 200)
        self.assertGreater(payload["stability"], 0)
        status, plan = self.request(self.m4_base, "/api/plan?minutes=15")
        self.assertFalse(any(c["item_id"] == "error:G04" for c in plan["due_items"]))
        # 注意：按频率选取时 G04 仍可能留在 target_error_codes，这是设计行为

    def test_review_validation(self):
        status, payload = self.request(self.m4_base, "/api/review",
                                       {"item_id": "error:G99", "rating": 3})
        self.assertEqual(status, 400)
        status, payload = self.request(self.m4_base, "/api/review",
                                       {"item_id": "error:G04", "rating": 9})
        self.assertEqual(status, 400)

    def test_end_without_batch_does_not_write(self):
        status, payload = self.request(self.m2_base, "/api/session", {})
        sid = payload["session_id"]
        self.request(self.m2_base, "/api/turn", {"session_id": sid, "text": "hello"})
        status, recap = self.request(self.m2_base, "/api/end", {"session_id": sid})
        self.assertEqual(status, 200)
        self.assertEqual(recap["ingest"]["reason"], "no_batch_no_confirmed")
        self.assertEqual(LearnerStore(self.store_path).data["error_patterns"]["G04"]["count_total"], 1)


if __name__ == "__main__":
    unittest.main()
