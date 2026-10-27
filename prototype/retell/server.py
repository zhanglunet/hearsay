"""复述切片本地服务。只监听 127.0.0.1；confirmed 错误回流 M3（可关）。"""

from __future__ import annotations

import json
import os
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hearsay_http import HearsayHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from m1_shadow.demo import load_demo_payload
from m2_dialogue.batch import detect_errors
from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore
from retell.retell import build_summary

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    # 听力、复述、对话共用的语音模块（线上走 Workers AI，本地退回浏览器接口）
    "/voice.js": (WEB_DIR.parents[1] / "shared" / "voice.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
}


def m3_store_path():
    return Path(os.environ.get("HEARSAY_M3_STORE",
                               Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json"))


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-retell"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/demo":
            try:
                demo = load_demo_payload()
                self._json(200, dict(title=demo["title"],
                                     material_text=" ".join(s["text"] for s in demo["sentences"])))
            except (OSError, ValueError, KeyError):
                traceback.print_exc()
                self._json(500, {"error": "演示材料读不出来"})
            return
        static = STATIC.get(path)
        if static is None or not static[0].is_file():
            self._json(404, {"error": "没有这个页面"})
            return
        file_path, content_type = static
        self._bytes(200, file_path.read_bytes(), content_type)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/evaluate":
            self._json(404, {"error": "没有这个接口"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200_000:
                raise ValueError("请求体过大")
            body = json.loads(self.rfile.read(length) or b"{}")
            material = str(body.get("material_text", "")).strip()
            retell = str(body.get("retell_text", "")).strip()
            if not material or not retell:
                raise ValueError("材料原文和复述内容都不能为空")
            duration = body.get("duration_sec")
            duration = float(duration) if duration else None
            result = build_summary(material, retell, duration)
            detected, detection = detect_errors([
                dict(utterance_id=1, realtime_text=retell, batch_text=retell, source="retell")])
            result.update(session_id=uuid.uuid4().hex[:12], session_type="retell",
                          errors=detected, detection=detection)
            if os.environ.get("HEARSAY_M3_INGEST", "1") != "0":
                recap = dict(session_id=result["session_id"],
                             batch=dict(confirmed=detected, discarded=[]))
                result["ingest"] = ingest_recap(LearnerStore(m3_store_path()), recap)
            self._json(200, result)
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


def make_server(port: int, host=None) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    return HearsayHTTPServer((host or os.environ.get("HEARSAY_HOST", "127.0.0.1"), port), Handler)


def main() -> None:
    port = int(os.environ.get("HEARSAY_RETELL_PORT", "8768"))
    httpd = make_server(port)
    print(f"复述原型  http://127.0.0.1:{httpd.server_address[1]}/")
    print("覆盖度为词级启发式；语法检测有 key 走 Claude，否则规则；confirmed 回流 M3。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
