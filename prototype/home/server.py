"""统一首页：今日计划、到期复习卡、各切片入口。默认只监听 127.0.0.1。

给了 routes 时兼做单端口网关：/<kind>/... 反向代理到该切片的内部端口，
这样上公网只需要开放首页一个端口。"""

from __future__ import annotations

import http.client
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
ROUTES: dict[str, tuple[str, int]] = {}
# 网关整体读入请求体再转发；上限略高于各切片自己的最大限制（M2 turn 12MB）
PROXY_BODY_LIMIT = 16_000_000
PROXY_TIMEOUT = 600
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
SLICES = [
    ("listen", "听 · 理解题", 8769),
    ("shadow", "跟读 · M1", 8765),
    ("retell", "复述", 8768),
    ("converse", "对话 / 复习", 8766),
    ("plan", "计划与进度 · M4", 8767),
]


def slice_href(kind, port):
    """有网关路由时走同源相对路径；单独起首页时退回各切片的本地端口。"""
    return f"{kind}/" if kind in ROUTES else f"http://127.0.0.1:{port}/"


def m3_store_path():
    return os.environ.get("HEARSAY_M3_STORE",
                          Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json")


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-home"

    def do_GET(self) -> None:
        if self._route():
            return
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
                                     slices=[dict(kind=k, title=t, port=p, href=slice_href(k, p))
                                             for k, t, p in SLICES]))
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

    def do_POST(self) -> None:
        if not self._route():
            self._json(404, {"error": "没有这个接口"})

    def _route(self) -> bool:
        """/<kind> 跳到 /<kind>/，/<kind>/... 转发给切片。不是切片路径时返回 False。"""
        parsed = urlparse(self.path)
        kind, sep, rest = parsed.path.lstrip("/").partition("/")
        if kind not in ROUTES:
            return False
        query = f"?{parsed.query}" if parsed.query else ""
        if not sep:
            self.send_response(301)
            self.send_header("Location", f"/{kind}/{query}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        self._proxy(kind, f"/{rest}{query}")
        return True

    def _proxy(self, kind, upstream_path):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "Content-Length 不合法"})
            return
        if length < 0 or length > PROXY_BODY_LIMIT:
            self._json(413, {"error": "请求体太大"})
            return
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        host, port = ROUTES[kind]
        conn = http.client.HTTPConnection(host, port, timeout=PROXY_TIMEOUT)
        try:
            conn.request(self.command, upstream_path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read()
            status, upstream_headers = response.status, response.getheaders()
        except OSError:
            traceback.print_exc()
            self._json(502, {"error": f"{kind} 切片没有响应"})
            return
        finally:
            conn.close()
        self.send_response(status)
        for key, value in upstream_headers:
            if key.lower() not in HOP_HEADERS | {"date", "server"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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


def make_server(port: int, store=None, routes=None) -> ThreadingHTTPServer:
    """routes：{kind: (host, port)}，给了就在同一端口上转发 /<kind>/ 到对应切片。"""
    global STORE
    STORE = store or LearnerStore(m3_store_path())
    ROUTES.clear()
    ROUTES.update(routes or {})
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
