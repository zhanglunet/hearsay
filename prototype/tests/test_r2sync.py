"""R2 镜像层：SigV4 签名（AWS 公开测试向量）与 LearnerStore 的拉取/上传/删除。

不连真实 R2：用本地 HTTP 服务模拟 S3 的 GET/PUT/DELETE，并校验每个请求都带签名。
"""

import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m3_learner import r2sync
from m3_learner.r2sync import R2Client, R2Config, R2Error, sign
from m3_learner.store import LearnerStore


class SigV4VectorTests(unittest.TestCase):
    def test_aws_sigv4_suite_get_vanilla(self):
        # aws-sig-v4-test-suite / get-vanilla
        auth = sign("GET", "https://example.amazonaws.com/",
                    {"Host": "example.amazonaws.com", "X-Amz-Date": "20150830T123600Z"},
                    r2sync.EMPTY_SHA256, "AKIDEXAMPLE",
                    "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
                    "us-east-1", "service", "20150830T123600Z")
        self.assertEqual(auth, (
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"))

    def test_s3_doc_example_get_object_with_range(self):
        # S3 API 参考「Signature Calculations for the Authorization Header」中的 GET Object 示例
        auth = sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt",
                    {"Host": "examplebucket.s3.amazonaws.com", "Range": "bytes=0-9",
                     "x-amz-content-sha256": r2sync.EMPTY_SHA256,
                     "x-amz-date": "20130524T000000Z"},
                    r2sync.EMPTY_SHA256, "AKIAIOSFODNN7EXAMPLE",
                    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "us-east-1", "s3", "20130524T000000Z")
        self.assertTrue(auth.endswith(
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"), auth)
        self.assertIn("SignedHeaders=host;range;x-amz-content-sha256;x-amz-date", auth)


class ConfigTests(unittest.TestCase):
    FULL = {"HEARSAY_R2_ACCOUNT_ID": "acct", "HEARSAY_R2_BUCKET": "b",
            "HEARSAY_R2_ACCESS_KEY_ID": "k", "HEARSAY_R2_SECRET_ACCESS_KEY": "s"}

    def test_disabled_unless_all_set(self):
        self.assertIsNone(R2Config.from_env({}))
        for missing in self.FULL:
            env = {k: v for k, v in self.FULL.items() if k != missing}
            self.assertIsNone(R2Config.from_env(env), missing)

    def test_defaults(self):
        c = R2Config.from_env(self.FULL)
        self.assertEqual(c.endpoint, "https://acct.r2.cloudflarestorage.com")
        self.assertEqual(c.key, r2sync.DEFAULT_KEY)

    def test_endpoint_override_and_key(self):
        c = R2Config.from_env(dict(self.FULL, HEARSAY_R2_ENDPOINT="http://127.0.0.1:9/",
                                   HEARSAY_R2_KEY="/x/y.json"))
        self.assertEqual(c.endpoint, "http://127.0.0.1:9")
        self.assertEqual(c.key, "x/y.json")


class FakeS3:
    """最小 S3：内存对象表，记录请求，要求 Authorization 与 x-amz-content-sha256。"""

    def __init__(self):
        self.objects = {}
        self.requests = []
        self.fail_put = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _check(self):
                outer.requests.append((self.command, self.path, dict(self.headers)))
                auth = self.headers.get("Authorization", "")
                ok = (auth.startswith("AWS4-HMAC-SHA256 Credential=AKID/")
                      and "/auto/s3/aws4_request" in auth
                      and self.headers.get("x-amz-content-sha256"))
                if not ok:
                    self.send_response(403); self.end_headers()
                return ok

            def do_GET(self):
                if not self._check():
                    return
                if self.path in outer.objects:
                    body = outer.objects[self.path]
                    self.send_response(200); self.send_header("Content-Length", str(len(body)))
                    self.end_headers(); self.wfile.write(body)
                else:
                    self.send_response(404); self.end_headers()

            def do_PUT(self):
                n = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(n)
                if not self._check():
                    return
                if outer.fail_put:
                    self.send_response(500); self.end_headers(); return
                import hashlib
                if hashlib.sha256(body).hexdigest() != self.headers["x-amz-content-sha256"]:
                    self.send_response(400); self.end_headers(); return
                outer.objects[self.path] = body
                self.send_response(200); self.end_headers()

            def do_DELETE(self):
                if not self._check():
                    return
                outer.objects.pop(self.path, None)
                self.send_response(204); self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown(); self.server.server_close()


class StoreMirrorTests(unittest.TestCase):
    def setUp(self):
        self.s3 = FakeS3()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "runtime" / "m3-learner.json"
        self.client = R2Client(R2Config(self.s3.endpoint, "hearsay", "learner/m3-learner.json",
                                        "AKID", "secret"),
                               now=lambda: datetime(2026, 10, 27, tzinfo=timezone.utc))
        self.obj = "/hearsay/learner/m3-learner.json"
        self.stderr = sys.stderr
        sys.stderr = open(Path(self.tmp.name) / "stderr.txt", "w")

    def tearDown(self):
        sys.stderr.close(); sys.stderr = self.stderr
        self.s3.close(); self.tmp.cleanup()

    def stderr_text(self):
        sys.stderr.flush()
        return (Path(self.tmp.name) / "stderr.txt").read_text()

    def test_save_uploads_same_bytes(self):
        store = LearnerStore(self.path, remote=self.client)
        store.data["learner"]["speaking_level"] = "B1"
        store.save()
        self.assertEqual(self.s3.objects[self.obj], self.path.read_bytes())
        self.assertEqual(json.loads(self.s3.objects[self.obj])["learner"]["speaking_level"], "B1")

    def test_fresh_container_pulls_from_r2(self):
        LearnerStore(self.path, remote=self.client).save()
        saved = LearnerStore(self.path, remote=self.client)
        saved.data["cards"].append(dict(item_id="error:G04"))
        saved.save()
        self.path.unlink()  # 模拟容器休眠后磁盘重建
        restored = LearnerStore(self.path, remote=self.client)
        self.assertEqual(restored.data["cards"], [dict(item_id="error:G04")])
        self.assertTrue(self.path.exists())

    def test_local_file_wins_over_r2(self):
        self.s3.objects[self.obj] = json.dumps(dict(remote=True)).encode()
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(dict(local=True)))
        gets_before = sum(1 for r in self.s3.requests if r[0] == "GET")
        store = LearnerStore(self.path, remote=self.client)
        self.assertEqual(store.data, dict(local=True))
        self.assertEqual(sum(1 for r in self.s3.requests if r[0] == "GET"), gets_before)

    def test_missing_object_starts_empty(self):
        store = LearnerStore(self.path, remote=self.client)
        self.assertEqual(store.data["cards"], [])
        self.assertFalse(self.path.exists())

    def test_delete_removes_remote(self):
        store = LearnerStore(self.path, remote=self.client)
        store.save()
        store.delete()
        self.assertNotIn(self.obj, self.s3.objects)
        self.assertFalse(self.path.exists())

    def test_upload_failure_keeps_local_and_warns_without_secret(self):
        self.s3.fail_put = True
        store = LearnerStore(self.path, remote=self.client)
        store.save()
        self.assertTrue(self.path.exists())
        text = self.stderr_text()
        self.assertIn("HTTP 500", text)
        self.assertNotIn("secret", text)

    def test_unreachable_r2_starts_empty(self):
        dead = R2Client(R2Config("http://127.0.0.1:9", "b", "k", "AKID", "secret"))
        store = LearnerStore(self.path, remote=dead)
        self.assertEqual(store.data["cards"], [])
        self.assertIn("拉取学习者数据失败", self.stderr_text())

    def test_invalid_json_in_r2_is_ignored(self):
        self.s3.objects[self.obj] = b"not json"
        store = LearnerStore(self.path, remote=self.client)
        self.assertEqual(store.data["cards"], [])
        self.assertFalse(self.path.exists())

    def test_client_get_raises_on_403(self):
        bad = R2Client(R2Config(self.s3.endpoint, "hearsay", "k", "WRONG", "secret"))
        with self.assertRaises(R2Error):
            bad.get()

    def test_disabled_by_default(self):
        import os
        for k in list(os.environ):
            if k.startswith("HEARSAY_R2_"):
                self.skipTest("测试环境设置了 HEARSAY_R2_*")
        self.assertIsNone(LearnerStore(self.path).remote)


if __name__ == "__main__":
    unittest.main()
