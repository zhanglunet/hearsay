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
from m1_shadow.server import make_server as make_shadow
from m3_learner.store import LearnerStore
from m4_plan.server import make_server as make_plan


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
        # 没有网关路由时，入口退回各切片的本地端口
        self.assertIn("http://127.0.0.1:8769/", [s["href"] for s in payload["slices"]])
        status, html = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("app.js", html.decode())

    def test_minutes_validation(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/plan?minutes=1000")
        self.assertEqual(ctx.exception.code, 400)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GatewayTests(unittest.TestCase):
    """单端口：/<kind>/ 由首页反向代理到只监听 127.0.0.1 的切片。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")
        self.servers = [make_plan(0, store=self.store, host="127.0.0.1"),
                        make_shadow(0, host="127.0.0.1")]
        routes = {"plan": ("127.0.0.1", self.servers[0].server_address[1]),
                  "shadow": ("127.0.0.1", self.servers[1].server_address[1])}
        self.home = make_server(0, store=self.store, routes=routes)
        self.servers.append(self.home)
        for server in self.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.home.server_address[1]}"

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.tmp.cleanup()

    def request(self, path, payload=None, opener=urllib.request.urlopen):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with opener(req) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_slice_links_are_same_origin(self):
        _, _, body = self.request("/api/progress")
        hrefs = {s["kind"]: s["href"] for s in json.loads(body)["slices"]}
        self.assertEqual(hrefs["plan"], "plan/")
        self.assertEqual(hrefs["shadow"], "shadow/")
        # 没配路由的切片仍指向本地端口
        self.assertEqual(hrefs["listen"], "http://127.0.0.1:8769/")

    def test_prefix_redirects_to_trailing_slash(self):
        opener = urllib.request.build_opener(_NoRedirect).open
        status, headers, _ = self.request("/plan?x=1", opener=opener)
        self.assertEqual(status, 301)
        self.assertEqual(headers["Location"], "/plan/?x=1")

    def test_static_and_api_proxied(self):
        status, headers, body = self.request("/plan/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b'src="app.js"', body)
        status, _, body = self.request("/plan/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b'fetch("api/progress")', body)
        status, _, body = self.request("/plan/api/plan?minutes=20")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["minutes"], 20)
        status, _, _ = self.request("/plan/api/plan?minutes=1000")
        self.assertEqual(status, 400)

    def test_post_and_binary_proxied(self):
        status, _, _ = self.request("/plan/api/evidence",
                                    dict(can_do_id="SI-A2-01", verdict="partial"))
        self.assertEqual(status, 200)
        _, _, body = self.request("/plan/api/progress")
        item = next(i for i in json.loads(body)["items"] if i["id"] == "SI-A2-01")
        self.assertEqual(item["status"], "emerging")
        _, _, body = self.request("/shadow/api/demo")
        self.assertEqual(json.loads(body)["audio_url"], "media/reference.wav")
        status, headers, body = self.request("/shadow/media/reference.wav")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertTrue(body.startswith(b"RIFF"))

    def test_unknown_paths(self):
        status, _, _ = self.request("/nope/")
        self.assertEqual(status, 404)
        status, _, _ = self.request("/api/nope", {})
        self.assertEqual(status, 404)

    def test_dead_slice_is_502(self):
        self.servers[1].shutdown()
        self.servers[1].server_close()
        self.servers.pop(1)
        status, _, _ = self.request("/shadow/api/demo")
        self.assertEqual(status, 502)


if __name__ == "__main__":
    unittest.main()
