"""把 M2 复盘里的 confirmed 错误写进学习者模型。

口径（M0 §4.1）：统计只读 confirmed；discarded 不计入任何数字。
没有 batch 的复盘不产生任何写入。同一 session_id 重复导入会被跳过。
"""

from datetime import timedelta

from m3_learner.fsrs import Card
from m3_learner.store import utcnow


def _pattern(store, code, now_iso):
    patterns = store.data["error_patterns"]
    if code not in patterns:
        patterns[code] = dict(code=code, count_total=0, count_30d=0, count_7d=0,
                              opportunities_30d=None, opportunities_7d=None,
                              error_rate_30d=None, error_rate_7d=None,
                              trend="insufficient_data",
                              first_seen_at=now_iso, last_seen_at=now_iso,
                              remediation=dict(status="none", fsrs=None, resolved_at=None),
                              updated_at=now_iso, event_dates=[])
    return patterns[code]


def ingest_recap(store, recap, now=None):
    """返回 {ingested, instances, new_codes, reason}。ingested=False 表示被跳过。"""
    now = now or utcnow()
    now_iso = now.isoformat()
    session_id = recap.get("session_id", "")
    if session_id and session_id in store.data["sessions_ingested"]:
        return dict(ingested=False, instances=0, new_codes=[], reason="session_already_ingested")
    batch = recap.get("batch")
    if not batch:
        return dict(ingested=False, instances=0, new_codes=[], reason="no_batch_no_confirmed")

    confirmed = batch.get("confirmed", [])
    new_codes = []
    for item in confirmed:
        code = item["code"]
        store.data["error_instances"].append(dict(
            session_id=session_id, utterance_id=item.get("utterance_id"),
            code=code, observed=item.get("observed", ""), expected=item.get("expected", ""),
            detected_by=item.get("detected_by", "unknown"), status="confirmed",
            confidence=item.get("confidence"), created_at=now_iso))
        if code == "X00":
            # 保留码：实时无法分类的实例只留档，不进错误档案和复习卡
            continue
        pattern = _pattern(store, code, now_iso)
        pattern["count_total"] += 1
        pattern["count_30d"] += 1
        pattern["count_7d"] += 1
        pattern["event_dates"].append(now_iso)
        pattern["last_seen_at"] = now_iso
        pattern["updated_at"] = now_iso
        if code not in new_codes:
            new_codes.append(code)

    for code in new_codes:
        item_id = f"error:{code}"
        if not store.has_card(item_id):
            store.put_card(Card.new(item_id, kind="error", now=now))
        pattern = store.data["error_patterns"][code]
        pattern["remediation"]["status"] = "scheduled"
        pattern["remediation"]["fsrs"] = item_id

    if session_id:
        store.data["sessions_ingested"].append(session_id)
    store.save()
    return dict(ingested=True, instances=len(confirmed), new_codes=new_codes, reason="ok")


def recompute_window_counts(store, now=None):
    """按 event_dates 重算 7/30 天计数（导入历史数据或跨天后调用）。"""
    now = now or utcnow()
    for pattern in store.data["error_patterns"].values():
        dates = pattern.get("event_dates", [])
        from datetime import datetime
        parsed = [datetime.fromisoformat(d) for d in dates]
        pattern["count_30d"] = sum(1 for d in parsed if now - d <= timedelta(days=30))
        pattern["count_7d"] = sum(1 for d in parsed if now - d <= timedelta(days=7))
    store.save()
