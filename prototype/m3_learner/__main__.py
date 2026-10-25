"""M3 最小切片演示 / 命令行。

    python -m m3_learner --demo                 # 离线演示：导入样例复盘 → 复习计划
    python -m m3_learner --store PATH --recap RECAP.json   # 导入真实 M2 复盘
    python -m m3_learner --store PATH --plan    # 看当前复习计划
    python -m m3_learner --store PATH --review error:G04 --rating 3
    python -m m3_learner --store PATH --export  # 整体导出 JSON
    python -m m3_learner --store PATH --delete  # 删除全部学习者数据

默认 store 在 prototype/runtime/m3-learner.json（已 gitignore）。
"""

import argparse, json
from pathlib import Path

from m3_learner.fsrs import Card
from m3_learner.ingest import ingest_recap
from m3_learner.review import review_plan
from m3_learner.store import LearnerStore

DEFAULT_STORE = Path(__file__).resolve().parents[1] / "runtime" / "m3-learner.json"

SAMPLE_RECAP = dict(
    session_id="demo-m2-session-1",
    batch=dict(
        detection="asr_llm",
        confirmed=[
            dict(utterance_id=1, code="G04", observed="Yesterday I go", expected="Yesterday I went",
                 detected_by="asr_llm", confidence=0.9, merged_provisional=True),
            dict(utterance_id=2, code="G04", observed="I see my friend yesterday", expected="I saw",
                 detected_by="asr_llm", confidence=0.85, merged_provisional=False),
            dict(utterance_id=2, code="G13", observed="more better", expected="better",
                 detected_by="asr_llm", confidence=0.9, merged_provisional=True),
        ],
        discarded=[dict(utterance_id=3, code="G09", observed="very like")],
    ),
)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default=str(DEFAULT_STORE))
    p.add_argument("--demo", action="store_true")
    p.add_argument("--recap")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--review", help="卡片 item_id，如 error:G04")
    p.add_argument("--rating", type=int, default=3)
    p.add_argument("--export", action="store_true")
    p.add_argument("--delete", action="store_true")
    args = p.parse_args()

    store = LearnerStore(args.store)
    if args.delete:
        store.delete()
        print("已删除学习者数据：", args.store)
        return
    if args.demo:
        print("导入样例 M2 复盘（confirmed 3 条；discarded 不计入）…")
        print(json.dumps(ingest_recap(store, SAMPLE_RECAP), ensure_ascii=False))
    if args.recap:
        print(json.dumps(ingest_recap(store, json.loads(Path(args.recap).read_text())),
                         ensure_ascii=False))
    if args.review:
        cards = {c.item_id: c for c in store.cards()}
        if args.review not in cards:
            raise SystemExit(f"没有这张卡：{args.review}。现有：{list(cards)}")
        card = cards[args.review]
        days, r = card.review(args.rating)
        store.put_card(card)
        store.save()
        print(f"{card.item_id}: rating={args.rating} 可提取率={r:.3f} "
              f"间隔={days:.2f} 天 stability={card.stability:.3f} difficulty={card.difficulty:.3f}")
    if args.export:
        print(store.export())
        return
    if args.demo or args.plan or args.recap or args.review:
        print(json.dumps(review_plan(store), ensure_ascii=False, indent=1))
        print("错误档案：")
        for code, pat in sorted(store.data["error_patterns"].items()):
            print(f"  {code}: total={pat['count_total']} 30d={pat['count_30d']} "
                  f"remediation={pat['remediation']['status']} trend={pat['trend']}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
