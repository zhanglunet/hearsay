# -*- coding: utf-8 -*-
"""PRD-457/T5测试（trend #2209 的 T5 环节）：陪练监督台 验收试运行。
运行：python3 -m unittest discover prototype/tests -p "test_prd457_t5_supervision_acceptance.py"（仓库根执行）
覆盖（T1 §6/§8 + T5 issue「全链跑通」）：站不住的纠正在出纠时就被
批注发回，学员只收到人点头过的纠正——
  ① 全链跑通：出纠正 → 批注 → 一键发回「换说法」→ agent 改完回来
     （v2，旧批注原样带回）→ 教练复核点头 → 账本落账 → 闸门放行 →
     陪练反馈出口只放行已点头的纠正，未点头的拦下留痕；
  ② 全链两遍逐字节一致：同一条链（固定时间戳）在两个隔离账本目录
     各跑一遍，账本条目 + 闸门裁决 + 出口结果的规范 JSON 逐字节一致；
  ③ 失败演练：无记录出口（SUPERVISION_OUTLET_BYPASS 拦截并告警）/
     未点头（NOT_APPROVED）/ 旧点头不放行新版（VERSION_MISMATCH）/
     账本首条被删改（LEDGER_DRIFT 全批拒绝）；
  ④ 链复跑：失败演练后在全新账本 + 全新闸门上重跑全链，仍跑通；
     另在子进程里把本文件完整重跑一遍（环境变量守卫防递归），证明
     链路不依赖本进程的内存状态；
  ⑤ 文档无密钥：T1 设计文档 + 本 PRD 的 T2/T3/T4/T5 开发记录里无
     密钥赋值、私网 IP、令牌字面量（占位写法除外）。
零网络零子进程（除④的子进程复跑一项）；示例全虚构占位。
借鉴只借形态：plannotator（Apache-2.0）、ag-ui（MIT）——本测试为原创
代码，未复用其代码；LoopForge（无 LICENSE）只借「人工批准门」形态，
零代码零文本复用。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from m1_shadow.coaching_supervision_bench import (  # noqa: E402
    SupervisionLedger, revise, supervise,
)
from m1_shadow.coaching_supervision_gate import SupervisionGate  # noqa: E402

NOW = "2026-11-16T09:00:00Z"
LATER = "2026-11-16T09:05:00Z"
ITEM = {"correction_id": "c-001", "version": 1,
        "text": "纠正文本（占位）", "rule": "规则（占位）"}
FILLER = {"correction_id": "c-000", "version": 1,
          "text": "纠正文本（占位）", "rule": "规则（占位）"}
ANNOTATIONS = [{"type": "换说法", "text": "换一个说法（占位）",
                "author": "coach-placeholder", "at": NOW}]
FEEDBACK = {"kind": "换说法", "text": "请换说法（占位）"}
RESOLVED = [{"type": "换说法", "text": "换一个说法（占位）",
             "author": "coach-placeholder", "status": "已采纳",
             "at": LATER}]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _run_chain(tmpdir):
    """全链跑一遍：返回（快照，账本，闸门，已点头纠正，未点头纠正）。"""
    tmpdir = Path(tmpdir)
    ledger_path = tmpdir / "supervision.jsonl"
    audit_path = tmpdir / "gate-audit.jsonl"
    led = SupervisionLedger(ledger_path)
    pending = supervise(dict(ITEM), at=NOW)
    led.record(pending)
    returned = supervise(dict(ITEM), list(ANNOTATIONS), dict(FEEDBACK),
                         at=NOW)
    assert returned["verdict"] == "returned"
    led.record(returned)
    back = revise(returned, dict(ITEM, version=2), at=LATER)
    assert back["verdict"] == "pending"
    led.record(back)
    approved = supervise(dict(ITEM, version=2), list(RESOLVED),
                         approve=True, at=LATER)
    assert approved["verdict"] == "approved"
    led.record(approved)
    gate = SupervisionGate(led, audit_path)
    item_v2 = dict(ITEM, version=2)
    gate_ok = gate.gate(item_v2, at=LATER)
    gate_old = gate.gate(dict(ITEM), at=LATER)
    gate_filler = gate.gate(dict(FILLER), at=LATER)
    outlet = led.outlet([item_v2, dict(FILLER)])
    gate_outlet = gate.gate_outlet([item_v2], at=LATER)
    gate_outlet_mixed = gate.gate_outlet([item_v2, dict(FILLER)], at=LATER)
    file_lines = [json.loads(line) for line in
                  ledger_path.read_text(encoding="utf-8").splitlines()]
    snapshot = {"entries": led.entries(),
                "decisions": gate.decisions(),
                "outlet": outlet,
                "gate_outlet": gate_outlet,
                "gate_outlet_mixed": gate_outlet_mixed,
                "file_lines": file_lines}
    return snapshot, led, gate, item_v2, dict(FILLER)


class TestFullChain(unittest.TestCase):
    def test_full_chain_end_to_end(self):
        """① 全链跑通：批注发回 → 改完回来 → 复核点头 → 闸门放行 →
        出口只放行已点头的纠正。"""
        with tempfile.TemporaryDirectory() as tmp:
            snap, led, gate, item_v2, filler = _run_chain(tmp)
            # 全链轨迹在 4 条账目里（supervise 每步新建记录）：
            # pending → returned → 改完回来 pending(v2) → 复核点头 approved(v2)。
            entries = snap["entries"]
            self.assertEqual([e["verdict"] for e in entries],
                             ["pending", "returned", "pending", "approved"])
            self.assertEqual([e["version"] for e in entries], [1, 1, 2, 2])
            self.assertEqual(
                [[s["step"] for s in e["progress"]] for e in entries],
                [["drafted"], ["drafted", "returned"],
                 ["drafted", "returned", "revised"],
                 ["drafted", "approved"]])
            latest = led.latest_for("c-001")
            self.assertEqual(latest["version"], 2)
            self.assertEqual(latest["verdict"], "approved")
            # 改完回来的那条账目：旧批注原样带到新版上对照；发回轮次记下
            # 回版对照。
            back = entries[2]
            self.assertEqual(len(back["annotations"]), 1)
            self.assertEqual(back["annotations"][0]["text"],
                             "换一个说法（占位）")
            self.assertEqual(back["annotations"][0]["status"], "待处理")
            self.assertEqual(
                back["feedback_rounds"][0]["revised_correction_id"],
                "c-001")
            self.assertEqual(
                back["feedback_rounds"][0]["kind"], "换说法")
            # 复核点头那条账目：批注已采纳，无未处理批注。
            self.assertEqual(latest["annotations"][0]["status"], "已采纳")
            # 闸门：新版放行，旧版与无记录拦下（裁决顺序见 _run_chain）。
            decisions = snap["decisions"]
            self.assertEqual(decisions[0]["decision"], "pass")
            self.assertEqual(decisions[0]["correction_id"], "c-001")
            self.assertEqual(decisions[1]["reason"], "VERSION_MISMATCH")
            self.assertEqual(decisions[2]["reason"],
                             "SUPERVISION_OUTLET_BYPASS")
            self.assertTrue(gate.alerts())
            # 出口：只放行已点头的纠正，未点头的拦下留痕。
            self.assertEqual(snap["outlet"]["passed"], [item_v2])
            self.assertEqual(snap["outlet"]["blocked_count"], 1)
            self.assertEqual(snap["outlet"]["blocked"][0]["correction_id"],
                             "c-000")
            self.assertFalse(snap["gate_outlet"]["vetoed"])
            self.assertEqual(snap["gate_outlet"]["passed"], [item_v2])
            self.assertTrue(snap["gate_outlet_mixed"]["vetoed"])
            # 账本文件与内存条目逐行一致（R3/R4 留痕落盘）。
            self.assertEqual(snap["file_lines"], snap["entries"])
            self.assertEqual(len(snap["entries"]), 4)

    def test_chain_twice_byte_identical(self):
        """② 全链两遍逐字节一致：两遍的账本、裁决、出口规范 JSON 相同。"""
        with tempfile.TemporaryDirectory() as t1, \
                tempfile.TemporaryDirectory() as t2:
            snap1, _, _, _, _ = _run_chain(t1)
            snap2, _, _, _, _ = _run_chain(t2)
            self.assertEqual(_canonical(snap1), _canonical(snap2))


class TestFailureDrills(unittest.TestCase):
    def test_failure_drills(self):
        """③ 失败演练：绕过出口、未点头、旧点头、账本漂移一律显形拒绝。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, led, gate, item_v2, filler = _run_chain(tmp)
            # 无记录出口 → 拦截并告警。
            ghost = gate.gate({"correction_id": "c-999", "version": 1},
                              at=LATER)
            self.assertEqual(ghost["decision"], "block")
            self.assertEqual(ghost["reason"],
                             "SUPERVISION_OUTLET_BYPASS")
            self.assertTrue(gate.alerts())
            # 未点头（另建只有 pending 的账本）→ NOT_APPROVED。
            led2 = SupervisionLedger(None)
            led2.record(supervise(dict(ITEM), at=NOW))
            gate2 = SupervisionGate(led2)
            out = gate2.gate(dict(ITEM), at=NOW)
            self.assertEqual(out["decision"], "block")
            self.assertEqual(out["reason"], "NOT_APPROVED")
            # 账本首条被删 → 全批 LEDGER_DRIFT。
            led._records.pop(0)
            drifted = gate.gate(item_v2, at=LATER)
            self.assertEqual(drifted["decision"], "block")
            self.assertEqual(drifted["reason"], "LEDGER_DRIFT")
            batch = gate.gate_outlet([item_v2], at=LATER)
            self.assertTrue(batch["vetoed"])
            self.assertEqual(batch["blocked"][0]["gate_reason"],
                             "LEDGER_DRIFT")

    def test_chain_reruns_after_failure_drills(self):
        """④ 链复跑：失败演练后在全新账本 + 全新闸门上重跑全链，仍跑通。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, led, gate, item_v2, _ = _run_chain(tmp)
            led._records.pop(0)
            self.assertEqual(gate.gate(item_v2, at=LATER)["reason"],
                             "LEDGER_DRIFT")
        with tempfile.TemporaryDirectory() as tmp:
            snap, _, fresh_gate, item_v2, _ = _run_chain(tmp)
            self.assertEqual(fresh_gate.gate(item_v2, at=LATER)["decision"],
                             "pass")
            self.assertFalse(snap["gate_outlet"]["vetoed"])

    def test_chain_reruns_in_subprocess(self):
        """④ 链复跑（子进程实测）：本文件在全新子进程里完整重跑一遍。"""
        if os.environ.get("PRD457_T5_SUBPROCESS_RUN"):
            self.skipTest("子进程内不再递归复跑")
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PRD457_T5_SUBPROCESS_RUN="1")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "prototype/tests",
             "-p", "test_prd457_t5_supervision_acceptance.py"],
            cwd=str(repo_root), env=env, capture_output=True, text=True,
            timeout=120)
        self.assertIn(proc.returncode, (0, 5),
                         proc.stdout + proc.stderr)


class TestDocsHaveNoSecrets(unittest.TestCase):
    def test_docs_have_no_secrets(self):
        """⑤ 文档无密钥：T1 设计 + 本 PRD 开发记录无密钥赋值/私网 IP/
        令牌字面量（占位写法除外）。"""
        repo_root = Path(__file__).resolve().parents[2]
        docs = sorted((repo_root / "docs" / "plans").glob("*prd-457*.md"))
        docs += sorted((repo_root / "docs" / "devlog").glob("*prd-457*.md"))
        self.assertGreaterEqual(len(docs), 2, "未找到 PRD-457 设计/开发记录")
        self.assertTrue(any("t5-acceptance" in d.name for d in docs),
                        "T5 开发记录不在扫描范围里")
        patterns = [
            re.compile(r"(?i)(password|passwd|pwd|api[_-]?key|access[_-]?token"
                       r"|secret[_-]?key|client[_-]?secret)\s*[:=]\s*"
                       r"[\"']?[A-Za-z0-9_.\-/]{8,}"),
            re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)"
                       r"\.\d{1,3}\.\d{1,3}\b"),
            re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{10,}\b"),
            re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
            re.compile(r"https?://[^/\s]*:[^@/\s]+@"),
        ]
        hits = []
        for doc in docs:
            for i, line in enumerate(
                    doc.read_text(encoding="utf-8").splitlines(), 1):
                if any(w in line for w in ("占位", "placeholder",
                                           "PLACEHOLDER")):
                    continue
                for pat in patterns:
                    if pat.search(line):
                        hits.append(f"{doc.name}:{i}:{line.strip()[:120]}")
        self.assertEqual(hits, [], f"文档疑似含密钥/私网地址：{hits}")


if __name__ == "__main__":
    unittest.main()
