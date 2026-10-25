"""统一首页：今日计划、到期复习卡、各切片入口。只监听 127.0.0.1。"""

from __future__ import annotations

import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from m3_learner.store import LearnerStore
from m4_plan.can_do import progress_summary, progress
from m4_plan.planner import build_plan

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
}

STORE = None
SLICES = [
    ("listen", "听 · 理解题", 8769),
    ("shadow", "跟读 · M1", 8765),
    ("retell", "复述", 8768),
    ("converse", "对话 / 复习", 8766),
    ("plan", "计划与进度 · M4", 8767),
]


def m3_store_path():
    return os.environ.get("HEARSAY_M3_STORE",
                          Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json")


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-home"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/plan":
                minutes = int(parse_qs(parsed.query).get("minutes", ["15"])[0])
                if not 5 <= minutes <= 120:
                    raise ValueError("minutes 应在 5–120 之间")
                self._json(200, build_plan(STORE, minutes=minutes))
                return
            if path == "/api/progress":
                items = progress(STORE)
                self._json(200, dict(summary=progress_summary(items),
                                     slices=[dict(kind=k, title=t, port=p) for k, t, p in SLICES]))
                return
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "服务器内部错误"})
            return
        static = STATIC.get(path)
        if static is None or not static[0].is_file():
            self._json(404, {"error": "没有这个页面"})
            return
        file_path, content_type = static
        self._bytes(200, file_path.read_bytes(), content_type)

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._bytes(status, data, "application/json; charset=utf-8")

    def _bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def make_server(port: int, store=None) -> ThreadingHTTPServer:
    global STORE
    STORE = store or LearnerStore(m3_store_path())
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((os.environ.get("HEARSAY_HOST", "127.0.0.1"), port), Handler)


def main() -> None:
    port = int(os.environ.get("HEARSAY_HOME_PORT", "8764"))
    httpd = make_server(port)
    print(f"Hearsay 统一首页  http://127.0.0.1:{httpd.server_address[1]}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
