"""M4 命令行。

    python -m m4_plan --demo     # 种入样例数据并启动进度页（默认 127.0.0.1:8767）
    python -m m4_plan            # 直接启动进度页
    python -m m4_plan --plan     # 打印今日计划 JSON 后退出
    python -m m4_plan --evidence SI-A2-01 --verdict partial
"""

import argparse, json

from m3_learner.ingest import ingest_recap
from m3_learner.store import LearnerStore
from m4_plan.can_do import record_evidence
from m4_plan.planner import build_plan
from m4_plan.server import default_store_path, main as serve_main


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--minutes", type=int, default=15)
    p.add_argument("--evidence")
    p.add_argument("--verdict", default="partial")
    args = p.parse_args()

    if args.demo:
        from m3_learner.__main__ import SAMPLE_RECAP
        store = LearnerStore(default_store_path())
        if not store.data["error_patterns"]:
            print("种入样例 M2 复盘与一条 can-do 证据（仅本地演示）")
            ingest_recap(store, SAMPLE_RECAP)
            record_evidence(store, "SI-A2-01", "partial", session_id="demo", source="demo")
    if args.plan:
        store = LearnerStore(default_store_path())
        print(json.dumps(build_plan(store, minutes=args.minutes), ensure_ascii=False, indent=1))
        return
    if args.evidence:
        store = LearnerStore(default_store_path())
        record_evidence(store, args.evidence, args.verdict, source="manual")
        print(f"已记录：{args.evidence} {args.verdict}")
        return
    serve_main()


if __name__ == "__main__":
    main()
