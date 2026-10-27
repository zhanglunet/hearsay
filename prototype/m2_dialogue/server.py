"""M2 对话切片本地服务。只监听 127.0.0.1，会话在内存，密钥不进日志。"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hearsay_http import HearsayHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from m1_shadow.limits import seal_no_phoneme_writes
from m2_dialogue.batch import batch_enabled, run_batch
from m2_dialogue.scenario import PRODUCT_RULE_M2, SCENARIO
from m2_dialogue.session import DialogueError, create_session, get_session
from m2_dialogue.review_score import apply_scores, score_review
from m2_dialogue.tutor import TutorError, make_tutor
from m3_learner.ingest import ingest_recap
from m3_learner.review import build_review_scenario
from m3_learner.store import LearnerStore

WEB_DIR = Path(__file__).resolve().parent / "web"
JSON_LIMIT = 100_000
TURN_JSON_LIMIT = 12_000_000
AUDIO_BYTES_LIMIT = 8_000_000

STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
}

TUTOR = None


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-m2"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/scenario":
            self._json(200, dict(scenario=SCENARIO, tutor=TUTOR.name, notes=PRODUCT_RULE_M2))
            return
        static = STATIC.get(path)
        if static is None or not static[0].is_file():
            self._json(404, {"error": "没有这个页面"})
            return
        file_path, content_type = static
        self._bytes(200, file_path.read_bytes(), content_type)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json(TURN_JSON_LIMIT if path == "/api/turn" else JSON_LIMIT)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            if path == "/api/session":
                scenario = None
                if body.get("mode") == "review":
                    scenario = build_review_scenario(LearnerStore(_m3_store_path()))
                session = create_session(TUTOR, level=str(body.get("level", "A2")), scenario=scenario)
                self._json(200, dict(session_id=session.id, opening=session.turns[0]["text"],
                                     scenario_id=session.scenario["id"], scenario=session.scenario))
                return
            if path not in ("/api/turn", "/api/end"):
                self._json(404, {"error": "没有这个接口"})
                return
            session = get_session(body.get("session_id"))
            if path == "/api/turn":
                before = len(session.recasts)
                agent_text = session.add_learner_turn(str(body.get("text", "")))
                self._store_audio(session, body)
                self._json(200, dict(agent_text=agent_text,
                                     new_recasts=session.recasts[before:],
                                     n_learner_turns=session.learner_turn_count,
                                     scripted_event_fired=session.event_fired))
            elif path == "/api/end":
                try:
                    batch_result = run_batch(session) if batch_enabled() else None
                    recap = session.end(batch_result)
                finally:
                    # 先清理再响应，调用方拿到复盘时音频已删除
                    _cleanup_audio(session)
                if os.environ.get("HEARSAY_M3_INGEST", "1") != "0":
                    # confirmed 进 M3 学习者存储（幂等；无 batch 时不产生写入）
                    recap["ingest"] = ingest_recap(LearnerStore(_m3_store_path()), recap)
                if (session.scenario.get("target_error_codes")
                        and os.environ.get("HEARSAY_M2_REVIEW_SCORE", "1") != "0"):
                    try:
                        scores = score_review(session)
                    except TutorError:
                        scores = None  # 评分失败不阻断复盘，退回 M4 手动评分
                    if scores:
                        recap["review_scores"] = scores
                        recap["review_applied"] = apply_scores(
                            LearnerStore(_m3_store_path()), scores)
                self._json(200, recap)
        except DialogueError as exc:
            self._json(400, {"error": str(exc)})
        except TutorError as exc:
            self._json(502, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "服务器内部错误"})

    def _store_audio(self, session, body) -> None:
        """批处理启用时才把本轮录音写到系统临时目录；否则直接忽略，不落盘。"""
        if not batch_enabled() or not body.get("audio_b64"):
            return
        try:
            raw = base64.b64decode(body["audio_b64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise DialogueError("audio_b64 不是合法的 base64。") from exc
        if not raw or len(raw) > AUDIO_BYTES_LIMIT:
            raise DialogueError("音频为空或超过 8MB 上限。")
        suffix = ".webm" if "webm" in str(body.get("audio_type", "")) else ".wav"
        if not getattr(session, "audio_dir", None):
            session.audio_dir = Path(tempfile.mkdtemp(prefix="hearsay-m2-"))
        path = session.audio_dir / f"turn_{session.learner_turn_count}{suffix}"
        path.write_bytes(raw)
        session.attach_audio(path)

    def _read_json(self, limit) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length 不合法") from exc
        if length < 0 or length > limit:
            raise ValueError("请求体大小不合法")
        data = self.rfile.read(length) if length else b""
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
        sealed["product_rule"] = PRODUCT_RULE_M2
        data = json.dumps(sealed, ensure_ascii=False).encode("utf-8")
        self._bytes(status, data, "application/json; charset=utf-8")

    def _bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def _m3_store_path():
    return Path(os.environ.get("HEARSAY_M3_STORE",
                               Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json"))


def _cleanup_audio(session) -> None:
    audio_dir = getattr(session, "audio_dir", None)
    if audio_dir:
        shutil.rmtree(audio_dir, ignore_errors=True)
        session.audio_dir = None


def make_server(port: int, tutor=None, host=None) -> ThreadingHTTPServer:
    global TUTOR
    TUTOR = tutor or make_tutor()
    ThreadingHTTPServer.allow_reuse_address = True
    return HearsayHTTPServer((host or os.environ.get("HEARSAY_HOST", "127.0.0.1"), port), Handler)


def main() -> None:
    raw_port = os.environ.get("HEARSAY_M2_PORT", "8766")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("HEARSAY_M2_PORT 必须是整数") from exc
    if not (1 <= port <= 65535):
        raise SystemExit("HEARSAY_M2_PORT 超出端口范围")
    try:
        httpd = make_server(port)
    except TutorError as exc:
        raise SystemExit(str(exc)) from exc
    except OSError as exc:
        raise SystemExit(f"无法监听 127.0.0.1:{port}") from exc
    print(f"M2 对话原型  http://127.0.0.1:{httpd.server_address[1]}/")
    print(f"tutor 后端：{TUTOR.name}（mock 为离线脚本；anthropic 需要 HEARSAY_ANTHROPIC_API_KEY）")
    print("会话只在内存。复盘里的 recast 是待核对提示，不写学习者模型。")
    if batch_enabled():
        print("事后批处理：已启用 whisperX（verbatim，首次转写加载模型；解码需 ffmpeg）")
    else:
        print("事后批处理：未启用（设 HEARSAY_M2_BATCH=whisperx 开启；录音不上传落盘）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
