"""20 段对话的实时 recast 误报率测量（M0 §6，阈值 ≤20%）。

端到端驱动 M2 本地服务：每段会话 2 轮学习者发言（无音频，走 realtime_fallback），
结束后跑批处理（LLM 检测），复盘 JSON 存入输出目录，最后汇总误报率。

    # 环境：HEARSAY_LLM=anthropic + Kimi/Claude 的 key、端点、模型；
    # HEARSAY_M2_BATCH=whisperx（无音频时不需要 whisperX 本体）
    python exp_e_dialogue/run_recast_sessions.py --sessions 20 --out /path/recaps

语料：exp_a_grammar 的 24 句（含植入语法错误）+ exp_c_timestamps 的 50 句（干净）。
错误句与干净句交替，覆盖「该纠的没纠」和「不该纠的乱纠」两类失败。
M3 存储用输出目录里的 learner.json，不碰日常使用的那份。
"""
import argparse, json, os, sys, threading, time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "prototype"))

from aggregate import aggregate
from m2_dialogue.server import make_server
from m2_dialogue.tutor import AnthropicTutor

A_SENTENCES = json.loads((HERE.parent / "exp_a_grammar" / "sentences.json").read_text())
C_SENTENCES = [l.strip() for l in (HERE.parent / "exp_c_timestamps" / "sentences.txt").read_text().splitlines() if l.strip()]

FOLLOW_UP = "I see. I will send the summary tomorrow morning."


def build_session_plan(n):
    """前 n 段会话的首轮语料：错误句与干净句交替，各取所需数量。"""
    plan = []
    for i in range(n):
        if i % 2 == 0:
            s = A_SENTENCES[(i // 2) % len(A_SENTENCES)]
            plan.append(dict(text=s["text"], source=f"exp_a_grammar:{s['id']}"))
        else:
            idx = (i // 2) % len(C_SENTENCES)
            plan.append(dict(text=C_SENTENCES[idx], source=f"exp_c_timestamps:{idx + 1}"))
    return plan


def post(base, path, payload):
    import urllib.error
    import urllib.request
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
                raise
            time.sleep(2 * (attempt + 1))
    raise last


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sessions", type=int, default=20)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    os.environ["HEARSAY_M3_STORE"] = str(out / "learner.json")
    os.environ.setdefault("HEARSAY_M2_BATCH", "whisperx")

    tutor = AnthropicTutor()
    httpd = make_server(0, tutor=tutor)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"M2 服务：{base}（tutor={tutor.name}，模型 {tutor.model}）", flush=True)
    try:
        for i, item in enumerate(build_session_plan(args.sessions), 1):
            try:
                session = post(base, "/api/session", {})
                sid = session["session_id"]
                post(base, "/api/turn", {"session_id": sid, "text": item["text"]})
                time.sleep(0.3)
                post(base, "/api/turn", {"session_id": sid, "text": FOLLOW_UP})
                recap = post(base, "/api/end", {"session_id": sid})
            except Exception as exc:
                # 单段失败（如上游 502）不拖垮整轮测量，记录后继续
                print(f"[{i:02d}] {item['source']} 跳过：{exc}", flush=True)
                continue
            recap["corpus"] = item
            (out / f"{i:02d}.json").write_text(json.dumps(recap, ensure_ascii=False, indent=1))
            batch = recap.get("batch", {})
            print(f"[{i:02d}] {item['source']} 实时 {len(recap['recasts'])} 条，"
                  f"confirmed {len(batch.get('confirmed', []))}，"
                  f"discarded {len(batch.get('discarded', []))}", flush=True)
            time.sleep(0.3)
    finally:
        httpd.shutdown()
        httpd.server_close()

    recaps = [json.loads(p.read_text()) for p in sorted(out.glob("[0-9][0-9].json"))]
    report = aggregate(recaps)
    report.update(sessions_detail=[dict(file=p.name,
                                        corpus=json.loads(p.read_text())["corpus"],
                                        recasts=len(json.loads(p.read_text())["recasts"]))
                                   for p in sorted(out.glob("[0-9][0-9].json"))])
    (out / "aggregate_fpr.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "sessions_detail"},
                     ensure_ascii=False, indent=1))
    print("wrote", out / "aggregate_fpr.json")


if __name__ == "__main__":
    main()
