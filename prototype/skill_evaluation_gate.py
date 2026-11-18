"""PRD-493/T3（trend issue #2387 的 T3 环节）：陪练技能评估 监督回路闸门。

按 T1 设计（docs/plans/2026-11-17-prd-493-hearsay-skill-evaluation-design.md）落地：把"评估未过关的技能不得进入陪练反馈"做成
强制检查。T2 只产出评估报告（quality_gate 逐技能结论 + 重叠候选 + 整改
候选），没有任何东西拦住未过关技能的产物进陪练反馈；T3 只加检查，不改
T2 的评估逻辑与报告格式，按技能过闸：
  - check_gate(report, skill_id)：纯函数；以 T2 报告的 quality_gate 结论为准
    重新推导"该技能是否可进陪练反馈"——结论为"过关"且不在疑似重叠对里，
    两项缺一不可；"未评定"（无对照数据）拦下但不进整改清单；"不过关/未过关/
    待整改/疑似失效"拦下并进整改清单；疑似重叠拦下待人确认（不自动合并）。
  - enforce_gate：不通过即显形拒绝（GateError，GATE_BLOCKED）。
  - admit_to_downstream：陪练反馈唯一允许的入口——先过闸，再把放行/拦截的
    审计条目写进 SkillEvaluationLedger（拦截也留痕，绕关尝试有据可查）；
    未过关/疑似失效而被拦的技能，另追加一条整改条目（append-only，原因/
    证据/整改期限/复测结果齐全，期限待人填、不编造）。
  - gate_outlet：加固版批量出口，逐技能过闸；未知/残缺技能按拦截处理，
    永不抛错漏放。
  - 整改清单 append-only：SkillEvaluationLedger 只追加、不改历史条目。

口径（按 T1 设计"陪练技能包定期体检，坏技能进清单修，学员只收到评估过关的技能出的纠正。"）：
  - 今天真实技能包的对照数据仍为合成演示数据，结论"待真实对照复核"——闸门
    会全拦，这是实情，不是闸门太严：实测在 T5 补，跑分出来重评"过关"后才能
    放行。报告缺 quality_gate / 缺 overlap_candidates 按 BAD_REPORT 拦下。

本模块不重跑评估、不改报告、不碰技能包——只有检查与审计，没有放行的后门；
评估结论的改动仍走 T2 的评估流程；发布仍人工确认。零网络零子进程；示例全
虚构占位。
测试：prototype/tests/test_skill_evaluation_gate.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

GATE_SCHEMA = "skill-evaluation-gate/v1"
GATE_PRD = 493
GATE_REPO = "hearsay"
VERDICT_PASS = "过关"
VERDICT_PENDING = ("未评定",)
VERDICT_FAIL = ("不过关", "未过关", "待整改", "疑似失效")
BLOCK_REASON_CODES = ("BAD_REPORT", "UNKNOWN_SKILL", "REMEDIATE",
                      "INSUFFICIENT_EVIDENCE", "SUSPECTED_OVERLAP")
GATE_AUDIT_KINDS = ("gate_passed", "gate_blocked", "remediation")


class GateError(ValueError):
    """评估闸门违规——显形拒绝。"""


def _now(at: str) -> str:
    return at or "1970-01-01T00:00:00Z"


def _reason(code: str, target: Any, detail: str) -> dict[str, Any]:
    return {"code": code, "target": target, "detail": detail}


def _row_for(report: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    for row in report.get("skills") or []:
        if isinstance(row, dict) and row.get("id") == skill_id:
            return row
    return None


def _gate_for(report: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    gates = report.get("quality_gate")
    if isinstance(gates, dict):
        g = gates.get(skill_id)
        if isinstance(g, dict):
            return g
    return None


def _overlapped(report: dict[str, Any], skill_id: str) -> bool:
    for pair in report.get("overlap_candidates") or []:
        if isinstance(pair, dict) and skill_id in (pair.get("skill_a"),
                                                   pair.get("skill_b")):
            return True
    return False


def check_gate(report: dict[str, Any] | None,
               skill_id: str) -> dict[str, Any]:
    """强制复核：以 T2 报告为准重新推导"该技能是否可进陪练反馈"。

    返回 {"allowed": bool, "reasons": [...]}；报告残缺时只拦下不抛错；
    技能不在报告里则显形拒绝（UNKNOWN_SKILL）。
    """
    if not isinstance(report, dict):
        return {"allowed": False,
                "reasons": [_reason("BAD_REPORT", None, "评估报告不是 dict")]}
    if report.get("prd") != GATE_PRD or report.get("repo") != GATE_REPO:
        return {"allowed": False,
                "reasons": [_reason(
                    "BAD_REPORT", report.get("prd"),
                    f"评估报告非 PRD-{GATE_PRD}（{GATE_REPO}）")]}
    if not isinstance(report.get("skills"), list):
        return {"allowed": False,
                "reasons": [_reason("BAD_REPORT", skill_id, "报告无 skills 列表")]}
    if not isinstance(report.get("quality_gate"), dict):
        return {"allowed": False,
                "reasons": [_reason("BAD_REPORT", skill_id,
                                    "报告无 quality_gate——缺质量门结论不得放行")]}
    if not isinstance(report.get("overlap_candidates"), list):
        return {"allowed": False,
                "reasons": [_reason("BAD_REPORT", skill_id,
                                    "报告无 overlap_candidates——缺重叠结果不得放行")]}
    row = _row_for(report, skill_id)
    if row is None:
        raise GateError(f"UNKNOWN_SKILL：报告里无此技能 skill_id={skill_id!r}")
    reasons: list[dict[str, Any]] = []
    gate = _gate_for(report, skill_id)
    verdict = gate.get("verdict") if gate else None
    if verdict == VERDICT_PASS:
        pass
    elif verdict in VERDICT_PENDING:
        reasons.append(_reason(
            "INSUFFICIENT_EVIDENCE", skill_id,
            f"技能 {skill_id!r} 未评定（无对照数据）：{(gate or {}).get('reason')}"))
    elif verdict in VERDICT_FAIL:
        reasons.append(_reason(
            "REMEDIATE", skill_id,
            f"技能 {skill_id!r} 质量门未过关（{verdict}）：{(gate or {}).get('reason')}"))
    else:
        reasons.append(_reason(
            "BAD_REPORT", skill_id,
            f"技能 {skill_id!r} 结论词表外 verdict={verdict!r}"))
    if _overlapped(report, skill_id):
        reasons.append(_reason(
            "SUSPECTED_OVERLAP", skill_id,
            f"技能 {skill_id!r} 在疑似重叠对里，待人确认（不自动合并）"))
    return {"allowed": not reasons, "reasons": reasons}


def enforce_gate(report: dict[str, Any] | None,
                 skill_id: str) -> dict[str, Any]:
    """过闸：不通过即显形拒绝；通过返回 check_gate 的裁决。"""
    verdict = check_gate(report, skill_id)
    if not verdict["allowed"]:
        codes = "; ".join(
            f"{r['code']}({r['target']})" for r in verdict["reasons"])
        raise GateError(f"GATE_BLOCKED：评估未过关不进陪练反馈——{codes}")
    return verdict


def _record_decision(ledger: Any, report: dict[str, Any] | None,
                     skill_id: str, verdict: dict[str, Any],
                     by: str, at: str) -> None:
    """记一条闸门审计；未过关/疑似失效被拦时，另追加一条整改条目。"""
    entry = {"kind": "gate_passed" if verdict["allowed"] else "gate_blocked",
             "skill_id": skill_id, "by": by, "at": _now(at),
             "reasons": [r["code"] for r in verdict["reasons"]],
             "targets": [r["target"] for r in verdict["reasons"]]}

    ledger.record(report if isinstance(report, dict) else {}, entry)
    if verdict["allowed"]:
        return
    if not any(r["code"] == "REMEDIATE" for r in verdict["reasons"]):
        return
    reason = next((r["detail"] for r in verdict["reasons"]
                   if r["code"] == "REMEDIATE"), "")
    date = report.get("date") if isinstance(report, dict) else None
    ledger.record(report if isinstance(report, dict) else {}, {
        "kind": "remediation", "skill_id": skill_id, "by": by,
        "at": _now(at),
        "reason": reason,
        "evidence": f"评估报告 {date or '未知日期'}",
        "due": "待定", "action": "修", "retest": None})


def admit_to_downstream(report: dict[str, Any] | None, skill_id: str, *,
                        ledger: Any = None, by: str,
                        at: str = "") -> dict[str, Any]:
    """陪练反馈唯一允许的入口：先过闸，再把裁决写进账本留痕。

    放行返回 {"admitted": 技能准入记录, "verdict": 裁决}；拦截时先记一条
    gate_blocked 审计（绕关尝试有据可查），再显形拒绝。未知技能也先记账
    再拒绝。ledger 给了就必须给 by（审计须署名），否则拒绝入账。
    """
    try:
        verdict = check_gate(report, skill_id)
    except GateError as exc:
        verdict = {"allowed": False,
                   "reasons": [_reason("UNKNOWN_SKILL", skill_id, str(exc))]}
    if ledger is not None:
        if not by:
            raise GateError("GATE_BLOCKED：审计留痕须 by（裁决人必填）")
        _record_decision(ledger, report, skill_id, verdict, by, at)
    if not verdict["allowed"]:
        codes = "; ".join(
            f"{r['code']}({r['target']})" for r in verdict["reasons"])
        raise GateError(f"GATE_BLOCKED：评估未过关不进陪练反馈——{codes}")
    row = _row_for(report, skill_id) if isinstance(report, dict) else None
    gate = _gate_for(report, skill_id) if isinstance(report, dict) else None
    return {"admitted": {
        "skill_id": skill_id,
        "verdict": gate.get("verdict") if gate else None,
        "report_date": report.get("date") if isinstance(report, dict) else None},
        "verdict": verdict}


def gate_outlet(report: dict[str, Any] | None,
                skill_ids: list[str] | None, *,
                ledger: Any = None, by: str,
                at: str = "") -> dict[str, Any]:
    """加固版批量出口：逐技能过闸，只放行 check_gate 通过的技能。"""
    passed, blocked = [], []
    for skill_id in skill_ids or []:
        try:
            verdict = check_gate(report, skill_id)
        except GateError as exc:
            verdict = {"allowed": False,
                       "reasons": [_reason("UNKNOWN_SKILL", skill_id, str(exc))]}
        if ledger is not None:
            if not by:
                raise GateError("GATE_BLOCKED：审计留痕须 by（裁决人必填）")
            _record_decision(ledger, report, skill_id, verdict, by, at)
        if verdict["allowed"]:
            passed.append({"skill_id": skill_id})
        else:
            blocked.append({"skill_id": skill_id, "reasons": verdict["reasons"]})
    return {"schema": GATE_SCHEMA, "passed": passed, "blocked": blocked,
            "blocked_count": len(blocked)}


def format_remediation_line(entry: dict[str, Any]) -> str:
    """整改条目 → remediation 清单的行格式（只渲染，不改历史条目）。"""
    date = str(entry.get("at") or "")[:10] or "未知日期"
    retest = entry.get("retest")
    return (f"- {date} 技能 {entry.get('skill_id')}：{entry.get('reason')} / "
            f"证据（{entry.get('evidence')}）/ 整改期限 {entry.get('due')} / "
            f"建议动作 {entry.get('action')} / 复测结果 {retest or '待复测'}")


class SkillEvaluationLedger:
    """评估闸门留痕账本：JSONL append-only（路径注入），缺件拒绝入账。

    三种条目：gate_passed / gate_blocked（闸门审计）、remediation（整改条目）。
    只追加、不改历史条目；entries() 返回深拷贝，改返回结果不污染账本。
    """

    _REQUIRED = ("skill_id", "kind", "by", "at")

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._path = Path(path) if path else None

    def record(self, report: dict[str, Any] | None,
               entry: dict[str, Any]) -> dict[str, Any]:
        report = report if isinstance(report, dict) else {}
        rec = {"schema": GATE_SCHEMA, "prd": report.get("prd"),
               **copy.deepcopy(entry)}
        missing = [k for k in self._REQUIRED
                   if k not in rec or rec.get(k) in (None, "")]
        if missing:
            raise GateError(f"GATE_BLOCKED：账目缺 {missing}")
        self._records.append(copy.deepcopy(rec))
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        return dict(rec)

    def entries(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._records)

    def latest_for(self, skill_id: str) -> dict[str, Any] | None:
        found = [r for r in self._records if r.get("skill_id") == skill_id]
        return copy.deepcopy(found[-1]) if found else None
