"""听力、复述、对话三个切片都提供共用语音模块 /voice.js，页面在 app.js 之前加载它。"""

import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROTOTYPE = Path(__file__).resolve().parents[1]
SHARED = (PROTOTYPE / "shared" / "voice.js").read_text(encoding="utf-8")


class VoiceStaticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HEARSAY_M3_STORE"] = str(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        os.environ.pop("HEARSAY_M3_STORE", None)
        self.tmp.cleanup()

    def test_slices_serve_shared_voice_module(self):
        from listen.server import make_server as listen
        from m2_dialogue.server import make_server as dialogue
        from retell.server import make_server as retell
        for factory in (listen, retell, dialogue):
            httpd = factory(0, host="127.0.0.1")
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                port = httpd.server_address[1]
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/voice.js", timeout=5) as r:
                    self.assertEqual(r.status, 200, factory.__module__)
                    self.assertIn("javascript", r.headers["Content-Type"])
                    self.assertEqual(r.read().decode("utf-8"), SHARED)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_pages_load_voice_before_app(self):
        for slice_ in ("listen", "retell", "m2_dialogue"):
            html = (PROTOTYPE / slice_ / "web" / "index.html").read_text(encoding="utf-8")
            self.assertLess(html.index('src="voice.js"'), html.index('src="app.js"'), slice_)

    def test_module_uses_worker_voice_endpoints(self):
        for path in ("/voice/status", "/voice/tts", "/voice/asr"):
            self.assertIn(path, SHARED)


if __name__ == "__main__":
    unittest.main()
