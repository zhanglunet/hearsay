"""本地页面。只监听 127.0.0.1。

学习者录音默认留在浏览器内存里。本机 ASR 若被显式打开，音频写到系统临时目录，
用完即删，不进仓库。
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hearsay_http import HearsayHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from m1_shadow.asr import (
    AsrDisabled,
    asr_disabled_reason,
    asr_enabled,
    faster_whisper_installed,
    transcribe_file,
)
from m1_shadow.demo import AUDIO_PATH, load_demo_payload
from m1_shadow.feedback import FeedbackError, feedback_request, summarize_request
from m1_shadow.limits import seal_no_phoneme_writes
from m1_shadow.segment import SegmentationError, segment_request

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
JSON_LIMIT = 1_000_000
AUDIO_LIMIT = 8_000_000

STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    # 与听力、复述、对话共用的语音模块（线上走 Workers AI，本地退回浏览器接口）
    "/voice.js": (WEB_DIR.parent / "shared" / "voice.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
    "/media/reference.wav": (AUDIO_PATH, "audio/wav"),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-m1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/demo":
            try:
                self._json(200, load_demo_payload())
            except (OSError, ValueError, KeyError):
                traceback.print_exc()
                self._json(500, {"error": "演示材料读不出来"})
            return
        static = STATIC.get(path)
        if static is None or not static[0].is_file():
            self._json(404, {"error": "没有这个页面"})
            return
        file_path, content_type = static
        data = file_path.read_bytes()
        self._bytes(200, data, content_type)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/transcribe":
            self._transcribe()
            return
        limit = JSON_LIMIT
        try:
            body = self._read_json(limit)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            if path == "/api/segment":
                payload = segment_request(body)
            elif path == "/api/feedback":
                payload = feedback_request(body)
            elif path == "/api/shadow-summary":
                payload = summarize_request(body)
            else:
                self._json(404, {"error": "没有这个接口"})
                return
        except (SegmentationError, FeedbackError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "服务器内部错误"})
            return
        self._json(200, payload)

    def _transcribe(self) -> None:
        try:
            raw, content_type = self._read_body(AUDIO_LIMIT)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        reason = asr_disabled_reason()
        if reason is not None:
            self._json(409, {"error": reason})
            return
        suffix = ".webm" if "webm" in content_type else ".wav"
        fd, name = tempfile.mkstemp(prefix="hearsay-m1-", suffix=suffix)
        os.close(fd)
        path = Path(name)
        try:
            path.write_bytes(raw)
            text = transcribe_file(path)
        except AsrDisabled as exc:
            self._json(409, {"error": str(exc)})
            return
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "本机转写失败"})
            return
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        self._json(200, {"text": text})

    def _read_body(self, limit: int) -> tuple[bytes, str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 不合法") from exc
        if length < 0:
            raise ValueError("Content-Length 不合法")
        if length > limit:
            raise ValueError("请求体过大")
        data = self.rfile.read(length) if length else b""
        if len(data) != length:
            raise ValueError("请求体不完整")
        content_type = self.headers.get("Content-Type", "")
        return data, content_type

    def _read_json(self, limit: int) -> dict:
        data, _content_type = self._read_body(limit)
        if not data:
            raise ValueError("请求体是空的")
        try:
            body = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求体不是 UTF-8 JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return body

    def _json(self, status: int, payload: dict) -> None:
        sealed = seal_no_phoneme_writes(dict(payload))
        data = json.dumps(sealed, ensure_ascii=False).encode("utf-8")
        self._bytes(status, data, "application/json; charset=utf-8")

    def _bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        # 只保留访问行。请求体里可能有转写，不从这里打出来。
        super().log_message(fmt, *args)


def make_server(port: int, host=None) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    return HearsayHTTPServer((host or os.environ.get("HEARSAY_HOST", "127.0.0.1"), port), Handler)


def main() -> None:
    raw_port = os.environ.get("HEARSAY_M1_PORT", "8765")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("HEARSAY_M1_PORT 必须是整数") from exc
    if not (1 <= port <= 65535):
        raise SystemExit("HEARSAY_M1_PORT 超出端口范围")
    try:
        httpd = make_server(port)
    except OSError as exc:
        raise SystemExit(f"无法监听 127.0.0.1:{port}") from exc
    print(f"M1 跟读原型  http://127.0.0.1:{httpd.server_address[1]}/")
    if asr_enabled():
        print("本机 ASR：已启用 faster-whisper（首次转写会下载模型）")
    elif faster_whisper_installed():
        print("本机 ASR：faster-whisper 已安装，但被 HEARSAY_ASR 强制关闭")
    else:
        print("本机 ASR：未安装 faster-whisper（安装后重启自动启用；也可粘贴转写）")
    print("页面只在本机打开。跟读录音留在浏览器里，不写入仓库。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
