"""回归：Cloudflare Containers 的主机名超长，socket.getfqdn 会抛 UnicodeError。
各服务监听 0.0.0.0 时必须照样能起来（2026-10-27 线上首页因此崩溃）。"""

import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from threading import Thread
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hearsay_http import HearsayHTTPServer


def boom(*_a, **_k):
    raise UnicodeError("encoding with 'idna' codec failed (UnicodeError: label too long)")


class GetfqdnCrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HEARSAY_M3_STORE"] = str(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        os.environ.pop("HEARSAY_M3_STORE", None)
        os.environ.pop("HEARSAY_HOST", None)
        self.tmp.cleanup()

    def test_stdlib_server_crashes_without_fix(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        with mock.patch.object(socket, "getfqdn", boom):
            with self.assertRaises(UnicodeError):
                ThreadingHTTPServer(("0.0.0.0", 0), BaseHTTPRequestHandler).server_close()

    def test_home_binds_all_interfaces_and_serves(self):
        from home.server import make_server
        os.environ["HEARSAY_HOST"] = "0.0.0.0"
        with mock.patch.object(socket, "getfqdn", boom):
            httpd = make_server(0)
        self.assertIsInstance(httpd, HearsayHTTPServer)
        Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            port = httpd.server_address[1]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                self.assertEqual(r.status, 200)
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_every_slice_survives_long_hostname(self):
        from listen.server import make_server as listen
        from m1_shadow.server import make_server as shadow
        from m2_dialogue.server import make_server as dialogue
        from m4_plan.server import make_server as plan
        from retell.server import make_server as retell
        with mock.patch.object(socket, "getfqdn", boom):
            for factory in (listen, shadow, dialogue, plan, retell):
                httpd = factory(0, host="0.0.0.0")
                self.assertIsInstance(httpd, HearsayHTTPServer, factory.__module__)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
