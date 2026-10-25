import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from home.server import make_server
from m3_learner.store import LearnerStore


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")
        self.httpd = make_server(0, store=self.store)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            return response.status, response.read()

    def test_plan_progress_and_page(self):
        status, plan = self.get("/api/plan?minutes=15")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(plan)["total_minutes"], 15)
        status, payload = self.get("/api/progress")
        payload = json.loads(payload)
        self.assertEqual(payload["summary"]["total"], 109)
        self.assertEqual(len(payload["slices"]), 5)
        self.assertIn(8769, [s["port"] for s in payload["slices"]])
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("app.js", html.decode())

    def test_minutes_validation(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/plan?minutes=1000")
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
