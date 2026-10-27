"""听力理解题本地服务。规则判定；H 类错误与 can-do 证据写 M3 同一存储。
自定义材料由 LLM 生成（validate_material 校验），浏览器 TTS 朗读，不需 TTS 模型。"""

from __future__ import annotations

import json
import os
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hearsay_http import HearsayHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from listen.generate import generate_material
from listen.questions import DEMO_QUESTIONS, can_do_verdicts, evaluate, public_question
from m1_shadow.demo import AUDIO_PATH, load_demo_payload
from m2_dialogue.tutor import TutorError
from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore
from m4_plan.can_do import record_evidence

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {
    "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/index.html": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
    "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
    "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
    "/media/reference.wav": (AUDIO_PATH, "audio/wav"),
}

SESSIONS = {}
MATERIALS = {}


def m3_store():
    return LearnerStore(os.environ.get(
        "HEARSAY_M3_STORE", Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json"))


class ListenError(ValueError):
    pass


def material_payload(material, use_tts, audio_url=None):
    return dict(material_id=material.get("id", "demo"), title=material["title"],
                use_tts=use_tts, audio_url=audio_url,
                sentences=material["sentences"],
                questions=[public_question(q) for q in material["questions"]])


def finish_session(session):
    if session.get("recap"):
        return session["recap"]
    results = list(session["results"].values())
    if not results:
        raise ListenError("还没有作答任何题目")
    by_id = {q["id"]: q for q in session["questions"]}
    for r in results:
        r["question"] = by_id[r["question_id"]]
    verdicts = can_do_verdicts(results)
    ingest = None
    if os.environ.get("HEARSAY_M3_INGEST", "1") != "0":
        store = m3_store()
        for cid, verdict in verdicts.items():
            record_evidence(store, cid, verdict, session_id=session["id"], source="rule")
        errors = []
        for r in results:
            if r["passed"]:
                continue
            q = r["question"]
            expected = q["options"][q["answer"]] if "options" in q else q["answer"]
            for code in q["error_codes"]:
                errors.append(dict(utterance_id=(q["sentence_idx"] or 0) + 1, code=code,
                                   observed=str(r["answer"])[:200], expected=str(expected),
                                   detected_by="rule", confidence=1.0, merged_provisional=False))
        ingest = ingest_recap(store, dict(session_id=session["id"],
                                          batch=dict(confirmed=errors, discarded=[])))
    else:
        errors = []
    recap = dict(
        session_id=session["id"], session_type="listen",
        answered=len(results), total=len(session["questions"]),
        passed=sum(1 for r in results if r["passed"]),
        score=round(sum(r["score"] for r in results) / len(results), 3),
        results=[dict(question_id=r["question_id"], score=r["score"], passed=r["passed"]) for r in results],
        can_do=verdicts, h_errors=len(errors), ingest=ingest,
        note="规则判定。inference / spoken_response 需 LLM 判，未接；"
             "can-do 证据 source=rule，仅来自本次演示题。",
    )
    session["recap"] = recap
    return recap


class Handler(BaseHTTPRequestHandler):
    server_version = "hearsay-listen"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/material":
            demo = load_demo_payload()
            material = dict(id="demo", title=demo["title"],
                            sentences=[dict(idx=s["idx"], text=s["text"],
                                            start_ms=s["start_ms"], end_ms=s["end_ms"])
                                       for s in demo["sentences"]],
                            questions=DEMO_QUESTIONS)
            self._json(200, material_payload(material, use_tts=False,
                                             audio_url="media/reference.wav"))
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
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                raise ValueError("请求体过大")
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/answer":
                self._json(200, self._answer(body))
            elif path == "/api/generate":
                level = str(body.get("level", "A2"))
                topic = str(body.get("topic", "")).strip()
                if not topic:
                    raise ListenError("话题不能为空")
                material = generate_material(level, topic)
                MATERIALS[material["id"]] = material
                self._json(200, material_payload(material, use_tts=True))
            elif path == "/api/finish":
                session = SESSIONS.get(str(body.get("session_id", "")))
                if session is None:
                    raise ListenError("没有这个会话，请先作答")
                self._json(200, finish_session(session))
            else:
                self._json(404, {"error": "没有这个接口"})
        except (ValueError, TypeError, json.JSONDecodeError, KeyError) as exc:
            self._json(400, {"error": str(exc)})
        except TutorError as exc:
            self._json(502, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "服务器内部错误"})

    def _answer(self, body):
        qid = str(body.get("question_id", ""))
        material_id = str(body.get("material_id", "demo"))
        questions = MATERIALS[material_id]["questions"] if material_id in MATERIALS else DEMO_QUESTIONS
        question = next((q for q in questions if q["id"] == qid), None)
        if question is None:
            raise ListenError(f"没有这道题：{qid}")
        answer = body.get("answer")
        if answer is None or str(answer).strip() == "":
            raise ListenError("答案是空的")
        sid = str(body.get("session_id") or uuid.uuid4().hex[:12])
        session = SESSIONS.setdefault(sid, dict(id=sid, results={}, recap=None, questions=questions))
        if session["recap"]:
            raise ListenError("本次练习已结束，请重新开始")
        verdict = evaluate(question, answer)
        expected = question["options"][question["answer"]] if "options" in question else question["answer"]
        session["results"][qid] = dict(question_id=qid, answer=answer, **verdict)
        return dict(session_id=sid, question_id=qid, expected=expected, **verdict)

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
    port = int(os.environ.get("HEARSAY_LISTEN_PORT", "8769"))
    httpd = make_server(port)
    print(f"听力理解题原型  http://127.0.0.1:{httpd.server_address[1]}/")
    print("规则判定；H 类错误与 can-do 证据写 M3 同一存储（rule 口径）。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
