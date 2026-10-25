"""LLM 判 can-do 的一致性（M0 §6：同一转写判 5 次，verdict 一致率 ≥ 80%）。

需要 HEARSAY_ANTHROPIC_API_KEY；转写会发给 Anthropic。不写入任何学习者模型。

    python exp_e_dialogue/can_do_consistency.py --demo
    python exp_e_dialogue/can_do_consistency.py --transcript /path/session.json \
        --id SI-A2-01 --statement "能解释延期原因并提出新日期" --runs 5

transcript 文件：M2 实时会话记录（含 utterances）或 [{speaker, text}, ...]。
verdict 取 pass / fail / insufficient；一致率 = 最多的一类占比。结果写 results_cando.json。
"""
import argparse, json, os, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "prototype"))

from m2_dialogue.tutor import (DEFAULT_MODEL, anthropic_request, llm_api_key,
                               llm_endpoint, response_text)

THRESHOLD = 0.80

DEMO_TRANSCRIPT = [
    dict(speaker="agent", text="Hey, it's Alex. Are we still on track to send the report on Friday?"),
    dict(speaker="learner", text="No, I am sorry. It is delayed because we are waiting for the data from another team."),
    dict(speaker="agent", text="I see. When can you finish it?"),
    dict(speaker="learner", text="I will finish it next Monday. And I can send a one-page summary to the client today."),
]

PROMPT = """你在评估英语学习者的口语互动能力。给定一段对话转写和一条 CEFR can-do 描述，
只根据转写里的证据判断学习者是否做到了。证据不足就判 insufficient，不要脑补。
只输出 JSON：{{"verdict":"pass"|"fail"|"insufficient","reason":"一句话中文理由"}}。

can-do（{cid}）：{statement}
对话转写：
{transcript}"""


def agreement(verdicts):
    """最多一类 verdict 的占比；空列表返回 None。"""
    if not verdicts:
        return None
    return round(Counter(verdicts).most_common(1)[0][1] / len(verdicts), 3)


def load_transcript(path):
    data = json.loads(Path(path).read_text())
    turns = data.get("utterances", data) if isinstance(data, dict) else data
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)


def judge(transcript_text, cid, statement, model):
    payload = dict(model=model, max_tokens=200,
                   system="你是严格的 CEFR 评估器，只输出 JSON。",
                   messages=[dict(role="user", content=PROMPT.format(
                       cid=cid, statement=statement, transcript=transcript_text))])
    data = anthropic_request(payload, llm_api_key(), llm_endpoint())
    text = response_text(data)
    import re
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"LLM 没有返回 JSON：{text[:100]}")
    parsed = json.loads(m.group(0))
    if parsed.get("verdict") not in ("pass", "fail", "insufficient"):
        raise ValueError(f"verdict 不合法：{parsed}")
    return parsed


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--transcript")
    p.add_argument("--id", default="SI-A2-demo")
    p.add_argument("--statement", default="能解释延期原因并提出新的完成日期")
    p.add_argument("--runs", type=int, default=5)
    args = p.parse_args()
    if not llm_api_key():
        raise SystemExit("需要 HEARSAY_LLM_API_KEY（或 HEARSAY_ANTHROPIC_API_KEY）。没有 key 时本实验无法运行。")
    if args.demo:
        transcript_text = "\n".join(f"{t['speaker']}: {t['text']}" for t in DEMO_TRANSCRIPT)
    elif args.transcript:
        transcript_text = load_transcript(args.transcript)
    else:
        raise SystemExit("给 --demo 或 --transcript PATH")

    model = os.environ.get("HEARSAY_LLM_MODEL") or DEFAULT_MODEL
    results = []
    for i in range(args.runs):
        r = judge(transcript_text, args.id, args.statement, model)
        results.append(r)
        print(f"run {i + 1}: {r['verdict']} — {r.get('reason', '')}", flush=True)
    verdicts = [r["verdict"] for r in results]
    rate = agreement(verdicts)
    report = dict(can_do_id=args.id, statement=args.statement, runs=args.runs,
                  verdicts=verdicts, agreement=rate, threshold=THRESHOLD,
                  passed=rate is not None and rate >= THRESHOLD,
                  note="同一转写重复判定；不写 CanDoEvidence。")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    out = HERE / "results_cando.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
