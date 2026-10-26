"""每日计划编排（M0 §5.3 模板的离线版）。

从 M3 存储读错误档案与 FSRS 卡：到期代码注入 converse 场景；
rationale_zh 必须能回答「为什么今天是这个」。
听力材料生成器、跟读选材器和复述评测都还没接，所以这些块写的是
「用什么现成切片完成」，不是自动生成的内容。
"""

from m3_learner.fsrs import due_cards
from m3_learner.review import build_review_scenario, select_target_codes
from m3_learner.store import utcnow

BASE_TEMPLATE = [("listen", 3), ("shadow", 4), ("retell", 3), ("converse", 5)]


def build_plan(store, now=None, minutes=15, level=None):
    now = now or utcnow()
    level = level or store.data["learner"].get("speaking_level", "A2")
    template = list(BASE_TEMPLATE)
    if level == "B2":
        template[0] = ("listen", 5)
    base_total = sum(m for _, m in template)
    scale = minutes / 15
    target_codes = select_target_codes(store, now)
    scenario = build_review_scenario(store, now)
    due = due_cards(store.cards(), now)
    due_n = len(due)

    blocks = []
    for kind, base_min in template:
        block_min = max(1, round(base_min * scale))
        block = dict(type=kind, minutes=block_min)
        if kind == "listen":
            block["content_zh"] = "用 listen 切片听材料做理解题：主旨/细节/听写/听辨，规则判定并回流 can-do 与 H 类错误；可用 LLM 生成自定义材料"
        elif kind == "shadow":
            block["content_zh"] = "用 M1 切片跟读 4–6 句；优先含近期错误代码的句子（自动选材未接）"
        elif kind == "retell":
            block["content_zh"] = "用 retell 切片复述刚听的材料：词级覆盖度、WPM、语法反馈并回流 M3"
        else:
            block["content_zh"] = f"对话场景：{scenario['title']}，注入复习代码 {target_codes or '无'}"
            block["scenario"] = scenario
        blocks.append(block)

    patterns = store.data["error_patterns"]
    top = sorted(patterns.values(), key=lambda p: -p["count_30d"])[:3]
    rationale = []
    if top:
        rationale.append("近 30 天 " + "、".join(f"{p['code']} 出现 {p['count_30d']} 次" for p in top))
    if due_n:
        rationale.append(f"{due_n} 张复习卡到期，已注入今天的对话场景")
    if not rationale:
        rationale.append("还没有错误档案，先做一次对话建立基线")
    rationale.append(f"今天时间预算 {minutes} 分钟，按 {level} 模板分配")

    # 缩放后把总时长收敛回预算，差额由对话块吸收（B2 模板块合计超过 15 分钟时同理）
    diff = sum(b["minutes"] for b in blocks) - minutes
    if diff:
        blocks[-1]["minutes"] = max(1, blocks[-1]["minutes"] - diff)

    return dict(
        date=now.date().isoformat(), minutes=minutes, level=level,
        blocks=blocks, total_minutes=sum(b["minutes"] for b in blocks),
        due_items=[dict(item_id=c.item_id, due=c.due,
                        stability=round(c.stability, 3), difficulty=round(c.difficulty, 3))
                   for c in due],
        target_error_codes=target_codes,
        target_can_do_ids=[],
        rationale_zh="；".join(rationale) + "。",
        notes="编排器离线版：材料生成、自动选材、can-do 目标选取未接；"
              "target_can_do_ids 留空，等 LLM 判定一致性验证。",
    )
