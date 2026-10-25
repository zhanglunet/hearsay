"""实时 recast 误报率汇总（M0 §6：provisional 被 discarded 的比例 ≤ 20%）。

输入：一个目录，里面是若干次 M2 `/api/end` 返回的复盘 JSON（含 batch 字段）。
每次会话的 provisional = 合并的 confirmed + discarded；批处理新发现的 confirmed
不计入分母（它们不是实时链路产生的）。

    python exp_e_dialogue/aggregate.py /path/recaps/

输出汇总 JSON 并打印；达到 / 未达到按 0.20 判定。纯标准库，可离线跑。
"""
import json, sys
from pathlib import Path

THRESHOLD = 0.20


def session_counts(recap):
    batch = recap["batch"]
    merged = sum(1 for c in batch["confirmed"] if c.get("merged_provisional"))
    new = sum(1 for c in batch["confirmed"] if not c.get("merged_provisional"))
    discarded = len(batch["discarded"])
    return dict(provisional=merged + discarded, discarded=discarded, batch_new=new,
                detection=batch.get("detection", "unknown"))


def aggregate(recaps):
    per_session = [session_counts(r) for r in recaps]
    provisional = sum(s["provisional"] for s in per_session)
    discarded = sum(s["discarded"] for s in per_session)
    rate = round(discarded / provisional, 3) if provisional else None
    return dict(sessions=len(per_session), provisional=provisional, discarded=discarded,
                batch_new=sum(s["batch_new"] for s in per_session),
                detections=sorted({s["detection"] for s in per_session}),
                false_positive_rate=rate, threshold=THRESHOLD,
                passed=rate is not None and rate <= THRESHOLD)


def main():
    root = Path(sys.argv[1])
    recaps = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text())
        if "batch" in data:
            recaps.append(data)
    if not recaps:
        raise SystemExit(f"{root} 下没有含 batch 字段的复盘 JSON。先跑 M2 会话并保存 /api/end 响应。")
    report = aggregate(recaps)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    out = root / "aggregate_fpr.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
