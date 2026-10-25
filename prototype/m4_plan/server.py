"""M4 进度页本地服务。只监听 127.0.0.1，读 M3 存储，证据写入走同一 JSON 文件。"""

from __future__ import annotations

import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from m3_learner.store import LearnerStore
from m4_plan.can_do import load_statements, progress, progress_summary, record_evidence
from m4_plan.planner import build_plan

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
}

STORE = None


def default_store_path():
    return Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json"


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-m4"

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
                self._json(200, dict(summary=progress_summary(items), items=items))
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
        path = urlparse(self.path).path
        if path not in ("/api/evidence", "/api/review"):
            self._json(404, {"error": "没有这个接口"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/review":
                item_id = str(body.get("item_id", ""))
                rating = int(body.get("rating", 0))
                cards = {c.item_id: c for c in STORE.cards()}
                if item_id not in cards:
                    raise ValueError(f"没有这张复习卡：{item_id}")
                card = cards[item_id]
                days, retrievability = card.review(rating)
                STORE.put_card(card)
                STORE.save()
                self._json(200, dict(item_id=item_id, due=card.due,
                                     stability=card.stability, difficulty=card.difficulty,
                                     interval_days=round(days, 3),
                                     retrievability=round(retrievability, 3)))
                return
            record_evidence(STORE, str(body.get("can_do_id", "")), str(body.get("verdict", "")),
                            session_id=str(body.get("session_id", "")), source="manual")
            self._json(200, dict(ok=True))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "服务器内部错误"})

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
    STORE = store or LearnerStore(os.environ.get("HEARSAY_M3_STORE", default_store_path()))
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    raw_port = os.environ.get("HEARSAY_M4_PORT", "8767")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("HEARSAY_M4_PORT 必须是整数") from exc
    try:
        httpd = make_server(port)
    except OSError as exc:
        raise SystemExit(f"无法监听 127.0.0.1:{port}") from exc
    print(f"M4 每日计划与 can-do 进度  http://127.0.0.1:{httpd.server_address[1]}/")
    print("只读本机 M3 存储并追加人工证据；不自动判 can-do。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
