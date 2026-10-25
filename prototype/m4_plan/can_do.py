"""can-do 清单解析与证据进度。

清单是 docs/design/cefr-can-do-listening-speaking.md 的 Markdown 表格，
ID 形如 L-A1-01 / SP-B1-03 / SI-A2-02 / PH-A1-01，技能与等级从 ID 读出。
证据只来自显式记录（record_evidence），切片不自动判 can-do：
LLM 判定一致性（M0 §6，≥80%）未验证，所以这里没有自动 demonstrated。
"""

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIST = (Path(__file__).resolve().parents[2]
                / "docs" / "design" / "cefr-can-do-listening-speaking.md")
ROW = re.compile(r"^\|\s*((?:L|SP|SI|PH)-([ABC]\d)-(\d{2}))\s*\|([^|]*)\|([^|]*)\|([^|]*)\|")
VERDICTS = ("demonstrated", "partial", "failed")
SCHEDULABLE_LEVELS = ("A1", "A2", "B1", "B2")  # v1 只安排 A1–B2；C1 保留 ID，C2 占位


@dataclass
class Statement:
    id: str
    skill: str
    level: str
    zh: str
    en: str
    verification: str


def load_statements(path=None):
    statements = []
    for line in Path(path or DEFAULT_LIST).read_text().splitlines():
        m = ROW.match(line.strip())
        if m:
            cid, level, _num, zh, en, verification = m.groups()
            statements.append(Statement(id=cid, skill=cid.split("-")[0], level=level,
                                        zh=zh.strip(), en=en.strip(), verification=verification.strip()))
    if not statements:
        raise ValueError("没有解析到 can-do 条目，清单格式可能变了")
    return statements


def record_evidence(store, can_do_id, verdict, session_id="", source="manual", now=None):
    from m3_learner.store import utcnow
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 必须是 {VERDICTS} 之一")
    ids = {s.id for s in load_statements()}
    if can_do_id not in ids:
        raise ValueError(f"清单里没有这条 can-do：{can_do_id}")
    store.data.setdefault("can_do_evidence", []).append(dict(
        can_do_id=can_do_id, verdict=verdict, session_id=session_id,
        source=source, at=(now or utcnow()).isoformat()))
    store.save()


def progress(store, statements=None):
    """每条 can-do 的证据计数与状态。demonstrated 优先；有证据但未达标为 emerging。"""
    statements = statements or load_statements()
    evidence = store.data.get("can_do_evidence", [])
    out = []
    for s in statements:
        mine = [e for e in evidence if e["can_do_id"] == s.id]
        demonstrated = sum(1 for e in mine if e["verdict"] == "demonstrated")
        partial = sum(1 for e in mine if e["verdict"] == "partial")
        if demonstrated:
            status = "demonstrated"
        elif mine:
            status = "emerging"
        else:
            status = "not_started"
        out.append(dict(id=s.id, skill=s.skill, level=s.level, zh=s.zh, en=s.en,
                        status=status, evidence=len(mine),
                        demonstrated=demonstrated, partial=partial,
                        schedulable=s.level in SCHEDULABLE_LEVELS))
    return out


def progress_summary(items):
    return dict(total=len(items),
                demonstrated=sum(1 for i in items if i["status"] == "demonstrated"),
                emerging=sum(1 for i in items if i["status"] == "emerging"),
                not_started=sum(1 for i in items if i["status"] == "not_started"))
