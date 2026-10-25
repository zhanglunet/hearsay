import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore
from m4_plan.can_do import load_statements, progress, progress_summary, record_evidence
from m4_plan.planner import build_plan
from m4_plan.server import make_server

T0 = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def sample_recap(session_id="s1"):
    return dict(session_id=session_id, batch=dict(
        confirmed=[dict(utterance_id=1, code="G04", observed="x", expected="y",
                        detected_by="asr_llm", confidence=0.9, merged_provisional=False),
                   dict(utterance_id=2, code="G04", observed="x", expected="y",
                        detected_by="asr_llm", confidence=0.9, merged_provisional=False)],
        discarded=[]))


class CanDoListTests(unittest.TestCase):
    def test_parse_109_statements(self):
        statements = load_statements()
        self.assertEqual(len(statements), 109)
        self.assertEqual(statements[0].id, "L-A1-01")
        self.assertEqual(statements[0].skill, "L")
        self.assertEqual(statements[0].level, "A1")
        self.assertTrue(statements[0].zh)
        ids = {s.id for s in statements}
        self.assertIn("SI-A2-01", ids)
        self.assertIn("PH-B2-01", ids)

    def test_schedulable_levels(self):
        store = LearnerStore(Path(tempfile.mkdtemp()) / "x.json")
        items = progress(store)
        by_level = {}
        for item in items:
            by_level.setdefault(item["level"], item["schedulable"])
        for level in ("A1", "A2", "B1", "B2"):
            self.assertTrue(by_level[level])
        self.assertFalse(by_level["C1"])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_flow(self):
        items = {i["id"]: i for i in progress(self.store)}
        self.assertEqual(items["SI-A2-01"]["status"], "not_started")
        record_evidence(self.store, "SI-A2-01", "partial", now=T0)
        items = {i["id"]: i for i in progress(self.store)}
        self.assertEqual(items["SI-A2-01"]["status"], "emerging")
        self.assertEqual(items["SI-A2-01"]["partial"], 1)
        record_evidence(self.store, "SI-A2-01", "demonstrated", now=T0)
        items = {i["id"]: i for i in progress(self.store)}
        self.assertEqual(items["SI-A2-01"]["status"], "demonstrated")
        self.assertEqual(items["SI-A2-01"]["evidence"], 2)
        summary = progress_summary(list(items.values()))
        self.assertEqual(summary["demonstrated"], 1)
        self.assertEqual(summary["total"], 109)

    def test_validation(self):
        with self.assertRaises(ValueError):
            record_evidence(self.store, "SI-A2-99", "partial")
        with self.assertRaises(ValueError):
            record_evidence(self.store, "SI-A2-01", "great")


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_store_plan(self):
        plan = build_plan(self.store, now=T0)
        self.assertEqual([b["type"] for b in plan["blocks"]], ["listen", "shadow", "retell", "converse"])
        self.assertEqual(plan["total_minutes"], 15)
        self.assertIn("建立基线", plan["rationale_zh"])
        self.assertEqual(plan["target_error_codes"], [])
        self.assertEqual(plan["target_can_do_ids"], [])

    def test_b2_and_scaling(self):
        plan = build_plan(self.store, now=T0, minutes=30, level="B2")
        self.assertEqual(plan["blocks"][0]["minutes"], 10)
        self.assertEqual(plan["total_minutes"], 30)

    def test_rationale_uses_error_patterns(self):
        ingest_recap(self.store, sample_recap(), now=T0)
        plan = build_plan(self.store, now=T0)
        self.assertIn("G04 出现 2 次", plan["rationale_zh"])
        self.assertEqual(plan["target_error_codes"], ["G04"])
        self.assertIn("复习卡到期", plan["rationale_zh"])
        converse = plan["blocks"][-1]
        self.assertEqual(converse["scenario"]["target_error_codes"], ["G04"])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")
        self.httpd = make_server(0, store=self.store)
        import threading
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_plan_and_progress_and_evidence(self):
        status, plan = self.get("/api/plan?minutes=20")
        self.assertEqual(status, 200)
        self.assertEqual(plan["minutes"], 20)
        status, payload = self.get("/api/progress")
        self.assertEqual(status, 200)
        self.assertEqual(payload["summary"]["total"], 109)

        req = urllib.request.Request(self.base + "/api/evidence",
                                     data=json.dumps(dict(can_do_id="SI-A2-01", verdict="partial")).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
        _, payload = self.get("/api/progress")
        item = next(i for i in payload["items"] if i["id"] == "SI-A2-01")
        self.assertEqual(item["status"], "emerging")

        status, payload = self.get("/api/plan?minutes=1000")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
