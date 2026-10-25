import base64
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

from m2_dialogue.batch import (batch_enabled, detect_errors, llm_detect, reconcile,
                               run_batch, validate_llm_errors)
from m2_dialogue.server import make_server
from m2_dialogue.session import DialogueSession
from m2_dialogue.tutor import MockTutor


def prov(uid, code):
    return dict(utterance_id=uid, code=code, observed="x", expected="y",
                status="provisional", detected_by="rule")


class ReconcileTests(unittest.TestCase):
    def test_merge_discard_and_new(self):
        result = reconcile([prov(1, "G13"), prov(2, "G09")],
                           [prov(1, "G13"), prov(3, "G08")])
        self.assertEqual(len(result["confirmed"]), 2)
        merged = [c for c in result["confirmed"] if c["merged_provisional"]]
        new = [c for c in result["confirmed"] if not c["merged_provisional"]]
        self.assertEqual([(c["utterance_id"], c["code"]) for c in merged], [(1, "G13")])
        self.assertEqual([(c["utterance_id"], c["code"]) for c in new], [(3, "G08")])
        self.assertEqual([(d["utterance_id"], d["status"]) for d in result["discarded"]],
                         [(2, "discarded")])
        self.assertEqual(result["false_positive_rate"], 0.5)
        self.assertTrue(all(c["status"] == "confirmed" for c in result["confirmed"]))

    def test_no_provisional(self):
        result = reconcile([], [prov(1, "G03")])
        self.assertIsNone(result["false_positive_rate"])
        self.assertEqual(len(result["confirmed"]), 1)

    def test_same_code_other_utterance_does_not_merge(self):
        result = reconcile([prov(1, "G03")], [prov(2, "G03")])
        self.assertEqual(len(result["discarded"]), 1)
        self.assertFalse(result["confirmed"][0]["merged_provisional"])

    def test_x00_merges_with_any_code_same_utterance(self):
        result = reconcile([prov(1, "X00")], [prov(1, "G01")])
        self.assertEqual(result["discarded"], [])
        self.assertTrue(result["confirmed"][0]["merged_provisional"])
        self.assertEqual(result["confirmed"][0]["code"], "G01")
        # 但 X00 不跨话语合并
        result = reconcile([prov(1, "X00")], [prov(2, "G01")])
        self.assertEqual(len(result["discarded"]), 1)

    def test_x00_passes_validation(self):
        kept = validate_llm_errors(
            [dict(utterance_id=1, code="X00", observed="I go", expected="I went", confidence=0.7)],
            TRANSCRIPTS)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["code"], "X00")


class RunBatchTests(unittest.TestCase):
    def setUp(self):
        # 默认检测路径应是规则：清掉会让它走 LLM 的环境变量
        for key in ("HEARSAY_ANTHROPIC_API_KEY", "HEARSAY_M2_DETECT"):
            os.environ.pop(key, None)

    def make_session(self):
        s = DialogueSession(MockTutor())
        s.add_learner_turn("It is more better to wait.")
        s.attach_audio("/tmp/fake-turn-1.webm")
        s.add_learner_turn("I very like this plan.")
        return s

    def test_recap_with_injected_transcriber(self):
        s = self.make_session()
        self.assertEqual(s.turns[1]["utterance_id"], 1)
        self.assertEqual(s.turns[3]["utterance_id"], 2)
        self.assertEqual(s.turns[1]["audio_ref"], "/tmp/fake-turn-1.webm")
        self.assertEqual([r["utterance_id"] for r in s.recasts], [1, 2])

        def fake_transcribe(path):
            self.assertEqual(path, "/tmp/fake-turn-1.webm")
            return "It is much better now. She go home."

        result = run_batch(s, transcribe=fake_transcribe)
        # 实时 G13 在权威文本里不存在 → discarded；G03 是批处理新发现；G09 走实时文本兜底合并
        self.assertEqual([(d["code"], d["utterance_id"]) for d in result["discarded"]], [("G13", 1)])
        codes = sorted((c["code"], c["merged_provisional"]) for c in result["confirmed"])
        self.assertEqual(codes, [("G03", False), ("G09", True)])
        self.assertEqual(result["false_positive_rate"], 0.5)
        self.assertEqual(result["transcripts"][0]["source"], "whisperx_verbatim")
        self.assertEqual(result["transcripts"][1]["source"], "realtime_fallback")
        self.assertEqual(s.turns[1]["batch_text"], "It is much better now. She go home.")

        recap = s.end(result)
        self.assertIn("batch", recap)
        self.assertIn("confirmed 2 条", recap["summary_zh"])
        self.assertIn("误报率 50.0%", recap["summary_zh"])

    def test_text_only_session_does_not_load_whisperx(self):
        s = DialogueSession(MockTutor())
        s.add_learner_turn("It is more better now.")
        with mock.patch("m2_dialogue.batch.whisperx_transcriber",
                        side_effect=AssertionError("不应加载模型")):
            result = run_batch(s)
        self.assertEqual(result["transcripts"][0]["source"], "realtime_fallback")
        self.assertEqual(result["transcripts"][0]["batch_text"], "It is more better now.")
        self.assertEqual(len(result["confirmed"]), 1)

    def test_batch_env_gate(self):
        os.environ.pop("HEARSAY_M2_BATCH", None)
        self.assertFalse(batch_enabled())
        os.environ["HEARSAY_M2_BATCH"] = "whisperx"
        try:
            self.assertTrue(batch_enabled())
        finally:
            os.environ.pop("HEARSAY_M2_BATCH", None)


FAKE_BATCH = dict(confirmed=[], discarded=[], false_positive_rate=None,
                  duration_sec=0.01, transcripts=[], asr="whisperx_verbatim",
                  detection="rule_on_batch_text")


class ServerAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HEARSAY_M3_INGEST"] = "0"
        cls.httpd = make_server(0, tutor=MockTutor())
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.httpd.server_address
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("HEARSAY_M3_INGEST", None)

    def request(self, path, payload):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def temp_dirs(self):
        return set(Path("/tmp").glob("hearsay-m2-*"))

    def test_audio_ignored_when_batch_disabled(self):
        _, payload = self.request("/api/session", {})
        sid = payload["session_id"]
        before = self.temp_dirs()
        status, _ = self.request("/api/turn", {
            "session_id": sid, "text": "hello",
            "audio_b64": base64.b64encode(b"fake").decode(), "audio_type": "audio/webm"})
        self.assertEqual(status, 200)
        self.assertEqual(self.temp_dirs(), before)

    def test_audio_stored_and_cleaned_with_batch(self):
        _, payload = self.request("/api/session", {})
        sid = payload["session_id"]
        before = self.temp_dirs()
        with mock.patch("m2_dialogue.server.batch_enabled", return_value=True), \
             mock.patch("m2_dialogue.server.run_batch", return_value=FAKE_BATCH):
            status, _ = self.request("/api/turn", {
                "session_id": sid, "text": "It is more better.",
                "audio_b64": base64.b64encode(b"fake-audio").decode(), "audio_type": "audio/webm"})
            self.assertEqual(status, 200)
            created = self.temp_dirs() - before
            self.assertEqual(len(created), 1)
            files = list(created.pop().iterdir())
            self.assertEqual([f.name for f in files], ["turn_1.webm"])
            self.assertEqual(files[0].read_bytes(), b"fake-audio")

            status, payload = self.request("/api/end", {"session_id": sid})
            self.assertEqual(status, 200)
            self.assertEqual(payload["batch"], FAKE_BATCH)
        self.assertFalse(any((d / "turn_1.webm").exists() for d in self.temp_dirs()))

    def test_invalid_base64_rejected(self):
        _, payload = self.request("/api/session", {})
        sid = payload["session_id"]
        with mock.patch("m2_dialogue.server.batch_enabled", return_value=True):
            status, payload = self.request("/api/turn", {
                "session_id": sid, "text": "hello", "audio_b64": "!!not-base64!!"})
        self.assertEqual(status, 400)
        self.assertIn("base64", payload["error"])


TRANSCRIPTS = [dict(utterance_id=1, realtime_text="x", source="test",
                    batch_text="Yesterday I go to the park and it is more better.")]


def fake_claude_response(errors):
    body = {"content": [{"type": "text", "text": json.dumps({"errors": errors})}]}
    response = mock.MagicMock()
    response.read.return_value = json.dumps(body).encode()
    response.__enter__.return_value = response
    return response


class LlmDetectTests(unittest.TestCase):
    def setUp(self):
        os.environ["HEARSAY_ANTHROPIC_API_KEY"] = "test-key"
        os.environ.pop("HEARSAY_M2_DETECT", None)

    def tearDown(self):
        os.environ.pop("HEARSAY_ANTHROPIC_API_KEY", None)
        os.environ.pop("HEARSAY_M2_DETECT", None)

    def test_validate_drops_bad_entries(self):
        raw = [
            dict(utterance_id=1, code="G04", observed="I go", expected="I went", confidence=0.9),
            dict(utterance_id=1, code="P01", observed="I go", expected="x", confidence=0.9),
            dict(utterance_id=99, code="G04", observed="I go", expected="x", confidence=0.9),
            dict(utterance_id=1, code="G04", observed="I go", expected="x", confidence=0.5),
            dict(utterance_id=1, code="G13", observed="never said this", expected="x", confidence=0.9),
            dict(utterance_id=1, code="G13", observed="more better", expected="better", confidence=0.8),
        ]
        kept = validate_llm_errors(raw, TRANSCRIPTS)
        self.assertEqual([(e["code"], e["observed"]) for e in kept],
                         [("G04", "I go"), ("G13", "more better")])
        self.assertTrue(all(e["detected_by"] == "asr_llm" for e in kept))

    def test_llm_detect_with_fake_http(self):
        with mock.patch("m2_dialogue.tutor.urllib.request.urlopen",
                        return_value=fake_claude_response([
                            dict(utterance_id=1, code="G04", observed="I go",
                                 expected="I went", confidence=0.92)])):
            detected = llm_detect(TRANSCRIPTS)
        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0]["code"], "G04")
        self.assertEqual(detected[0]["confidence"], 0.92)

    def test_detect_errors_falls_back_on_http_error(self):
        import urllib.error as ue
        with mock.patch("m2_dialogue.tutor.urllib.request.urlopen",
                        side_effect=ue.URLError("down")):
            detected, name = detect_errors(TRANSCRIPTS)
        self.assertEqual(name, "rule_fallback_after_llm_error")
        self.assertEqual([d["code"] for d in detected], ["G13"])

    def test_detect_errors_rule_without_key(self):
        os.environ.pop("HEARSAY_ANTHROPIC_API_KEY", None)
        detected, name = detect_errors(TRANSCRIPTS)
        self.assertEqual(name, "rule_on_batch_text")
        self.assertEqual([d["code"] for d in detected], ["G13"])

    def test_llm_malformed_json_falls_back(self):
        response = mock.MagicMock()
        response.read.return_value = json.dumps({"content": [{"text": "not json at all"}]}).encode()
        response.__enter__.return_value = response
        with mock.patch("m2_dialogue.tutor.urllib.request.urlopen", return_value=response):
            detected, name = detect_errors(TRANSCRIPTS)
        self.assertEqual(name, "rule_fallback_after_llm_error")
        self.assertEqual([d["code"] for d in detected], ["G13"])


if __name__ == "__main__":
    unittest.main()
