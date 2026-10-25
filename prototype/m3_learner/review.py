"""复习项调度与场景回注：把错误代码变成新场景里的使用机会。

简化版 M0 §5.2：FSRS 到期的代码强制进入，其余按 count_30d 取前 3；
没有 tier_weight / stubbornness / 词项（那些需要完整 ErrorPattern 统计）。
"""

from m2_dialogue.scenario import SCENARIO
from m3_learner.fsrs import due_cards
from m3_learner.store import utcnow


def select_target_codes(store, now=None, n=3):
    now = now or utcnow()
    due_ids = {c.item_id for c in due_cards(store.cards(), now)}
    patterns = store.data["error_patterns"]
    due = [code for code in patterns if f"error:{code}" in due_ids
           and patterns[code]["remediation"]["status"] != "resolved"]
    rest = sorted((code for code in patterns if code not in due
                   and patterns[code]["remediation"]["status"] != "resolved"),
                  key=lambda c: (-patterns[c]["count_30d"], c))
    return (due + rest)[:n]


def build_review_scenario(store, now=None):
    codes = select_target_codes(store, now)
    scenario = dict(SCENARIO)
    scenario.update(
        id="m3-review-delay",
        title="复习：在新对话里用对你犯过的错",
        objectives=[f"自然地说出{code}对应的正确形式（导师会制造机会）" for code in codes]
                   or ["自由对话，没有到期复习项"],
        target_error_codes=codes,
        target_items=[],
        based_on=SCENARIO["id"],
    )
    return scenario


def review_plan(store, now=None):
    now = now or utcnow()
    due = due_cards(store.cards(), now)
    scenario = build_review_scenario(store, now)
    return dict(
        generated_at=now.isoformat(),
        due_items=[dict(item_id=c.item_id, due=c.due,
                        stability=round(c.stability, 3), difficulty=round(c.difficulty, 3))
                   for c in due],
        target_error_codes=scenario["target_error_codes"],
        scenario=scenario,
        note="复习不是翻卡片：到期错误代码被注入新场景的 objectives，"
             "要求在新对话里再次用对。尚未接学习者模型的其余部分（见 M3 README）。",
    )
