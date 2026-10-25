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

from m3_learner.store import LearnerStore
from retell.retell import build_summary, coverage, fluency, keywords, norm_word
from retell.server import make_server


class CoverageTests(unittest.TestCase):
    def test_keywords_stopwords_dedup_cap(self):
        text = "The report is delayed because the data team is waiting for the report and more data"
        keys = keywords(text)
        self.assertNotIn("the", keys)
        self.assertEqual(keys.count("report"), 1)
        self.assertIn("delayed", keys)
        self.assertLessEqual(len(keywords("word " * 50)), 12)

    def test_norm_word(self):
        self.assertEqual(norm_word("Books,"), "book")
        self.assertEqual(norm_word("class"), "class")
        self.assertEqual(norm_word("John's"), "john")

    def test_coverage(self):
        result = coverage("I usually take the subway to work",
                          "I take the bus to work")
        self.assertIn("subway", result["keywords"])
        self.assertIn("subway", result["missing"])
        self.assertIn("work", result["matched"])
        self.assertGreater(result["coverage"], 0)
        self.assertLess(result["coverage"], 1)

    def test_fluency_and_summary(self):
        self.assertEqual(fluency("one two three", 30)["wpm"], 6.0)
        self.assertIsNone(fluency("one two")["wpm"])
        result = build_summary("I go to work by bus", "I go work bus", 60)
        self.assertIn("词", result["summary_zh"])
        self.assertEqual(result["session_type"] if "session_type" in result else "retell", "retell")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HEARSAY_M3_STORE"] = str(Path(self.tmp.name) / "learner.json")
        os.environ.pop("HEARSAY_M3_INGEST", None)
        os.environ.pop("HEARSAY_ANTHROPIC_API_KEY", None)
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

    def test_demo(self):
        status, payload = self.request("/api/demo")
        self.assertEqual(status, 200)
        self.assertIn(" ", payload["material_text"])

    def test_evaluate_and_ingest(self):
        status, payload = self.request("/api/evaluate", dict(
            material_text="It is much better to finish the report on Friday",
            retell_text="It is more better to finish report on Friday", duration_sec=20))
        self.assertEqual(status, 200)
        self.assertEqual(payload["session_type"], "retell")
        self.assertEqual(payload["detection"], "rule_on_batch_text")
        self.assertEqual(payload["errors"][0]["code"], "G13")
        self.assertTrue(payload["ingest"]["ingested"])
        store = LearnerStore(os.environ["HEARSAY_M3_STORE"])
        self.assertEqual(store.data["error_patterns"]["G13"]["count_total"], 1)
        self.assertTrue(store.has_card("error:G13"))
        # 新一次评估是新 session，会再累计一次
        status, payload2 = self.request("/api/evaluate", dict(
            material_text="better report", retell_text="more better report"))
        self.assertNotEqual(payload["session_id"], payload2["session_id"])
        store = LearnerStore(os.environ["HEARSAY_M3_STORE"])
        self.assertEqual(store.data["error_patterns"]["G13"]["count_total"], 2)

    def test_validation(self):
        status, payload = self.request("/api/evaluate", dict(material_text="", retell_text="x"))
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
