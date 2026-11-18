"""PRD-493/T3 测试（trend #2387 的 T3 环节）：陪练技能评估监督回路闸门。
运行：python3 -m unittest discover prototype/tests -p "test_skill_evaluation_gate.py"（仓库根执行）
覆盖（T1 红线）：只放行"过关"且非重叠的技能/未评定拦下但不进整改清单/
未过关拦下进清单/疑似失效拦下进清单/疑似重叠拦下待人确认/未知技能先记账
再拒绝/放行与拦截审计留痕/加固出口批量过闸/整改清单 append-only/词表封闭/
AST 零网络/无发布路径/T2 真实评估直连（run_evaluation 产物直接过闸）。
零网络；全合成占位。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))
MODULE_DIR = MOD_DIR

from skill_evaluation import run_evaluation  # noqa: E402
from skill_evaluation_gate import (  # noqa: E402
    BLOCK_REASON_CODES, GATE_AUDIT_KINDS, GATE_SCHEMA, GateError,
    SkillEvaluationLedger, VERDICT_FAIL, VERDICT_PASS, VERDICT_PENDING,
    admit_to_downstream, check_gate, enforce_gate,
    format_remediation_line, gate_outlet)

NOW = "2026-11-17T09:00:00Z"
BY = "reviewer（占位）"


def make_report(specs):
    """合成 T2 报告：specs = [(skill_id, verdict, overlapped)]。"""
    skills = []
    gates = {}
    overlap = []
    for i, spec in enumerate(specs):
        sid, verdict = spec[0], spec[1]
        skills.append({"id": sid, "name": sid,
                       "source": f"skills/{sid}/SKILL.md"})
        gates[sid] = {"verdict": verdict, "reason": "合成占位"}
        if len(spec) > 2 and spec[2]:
            overlap.append({"skill_a": sid, "skill_b": f"other-{i}",
                             "jaccard": 0.9, "tfidf_cosine": 0.95})
    return {"prd": 493, "repo": "hearsay", "version": "v1",
            "date": "2026-11-17", "skills": skills,
            "quality_gate_variant": "three-metric",
            "quality_gate": gates, "overlap_candidates": overlap,
            "remediation_new_entries": []}


def make_real_report(specs):
    """经 T2 run_evaluation 跑真实产物（skills 传文本，measurements 合成）。"""
    skills = [{"id": sid, "name": sid,
              "text": same_text if (len(rest) > 1 and rest[1])
              else f"{sid}-" + "".join(
                  chr(0x4e00 + i * 20 + j) for j in range(12))}
              for i, (sid, *rest) in enumerate(specs)]
    measurements = {}
    for sid, verdict, *rest2 in specs:
        if verdict == "过关":
            measurements[sid] = {"baseline_error_rate": 0.50,
                                  "skill_error_rate": 0.04,
                                  "category_worsening_pp": {},
                                  "baseline_miss_rate": 0.10,
                                  "skill_miss_rate": 0.08,
                                  "trigger_rate": 0.30,
                                  "control_reproducible": True}
        elif verdict in ("不过关", "未过关", "失效"):
            measurements[sid] = {"baseline_error_rate": 0.50,
                                  "skill_error_rate": 0.60,
                                  "category_worsening_pp": {},
                                  "baseline_miss_rate": 0.10,
                                  "skill_miss_rate": 0.30,
                                  "trigger_rate": 0.30,
                                  "control_reproducible": True}
        elif verdict == "疑似失效":
            measurements[sid] = {"baseline_error_rate": 0.50,
                                  "skill_error_rate": 0.10,
                                  "category_worsening_pp": {},
                                  "baseline_miss_rate": 0.10,
                                  "skill_miss_rate": 0.05,
                                  "trigger_rate": 0.05,
                                  "control_reproducible": True}
    return run_evaluation(skills, measurements, "three-metric", 493, "hearsay")


same_text = "占位 相同 文本"
same = False


def codes(verdict):
    return [r["code"] for r in verdict["reasons"]]


OK = ("skill-a", "过关")
PENDING = ("skill-c", "未评定")
FAIL = ("skill-d", "不过关")
SUSPECT = ("skill-e", "疑似失效")


class TestGate(unittest.TestCase):
    def test_passing_skill_allowed(self):
        d = check_gate(make_report([OK]), "skill-a")
        self.assertTrue(d["allowed"])

    def test_pending_blocked_without_remediation(self):
        d = check_gate(make_report([PENDING]), "skill-c")
        self.assertFalse(d["allowed"])
        self.assertIn("INSUFFICIENT_EVIDENCE", codes(d))
        self.assertNotIn("REMEDIATE", codes(d))

    def test_fail_blocked_with_remediation_code(self):
        d = check_gate(make_report([FAIL]), "skill-d")
        self.assertFalse(d["allowed"])
        self.assertIn("REMEDIATE", codes(d))

    def test_suspect_fail_blocked_with_remediation_code(self):
        d = check_gate(make_report([SUSPECT]), "skill-e")
        self.assertFalse(d["allowed"])
        self.assertIn("REMEDIATE", codes(d))

    def test_overlap_blocked_even_if_passing(self):
        d = check_gate(make_report([("skill-a", "过关", True)]), "skill-a")
        self.assertFalse(d["allowed"])
        self.assertIn("SUSPECTED_OVERLAP", codes(d))

    def test_unknown_skill_raises(self):
        with self.assertRaisesRegex(GateError, "UNKNOWN_SKILL"):
            check_gate(make_report([OK]), "nope")

    def test_bad_reports_blocked(self):
        for bad in [None, "x", {}, {"prd": 999, "repo": "hearsay"},
                    {"prd": 493, "repo": "other"}]:
            d = check_gate(bad, "skill-a")
            self.assertFalse(d["allowed"])
            self.assertIn("BAD_REPORT", codes(d))
        for bad in [{"prd": 493, "repo": "hearsay", "skills": [], "quality_gate": "x"},
                    {"prd": 493, "repo": "hearsay", "skills": [], "quality_gate": {},
                      "overlap_candidates": "x"}]:
            d = check_gate(bad, "skill-a")
            self.assertFalse(d["allowed"])
            self.assertIn("BAD_REPORT", codes(d))

    def test_verdict_out_of_vocab_is_bad_report(self):
        d = check_gate(make_report([("skill-a", "瞎编结论")]), "skill-a")
        self.assertFalse(d["allowed"])
        self.assertIn("BAD_REPORT", codes(d))

    def test_per_skill_verdict_does_not_leak(self):
        report = make_report([FAIL, OK])
        self.assertFalse(check_gate(report, "skill-d")["allowed"])
        self.assertTrue(check_gate(report, "skill-a")["allowed"])

    def test_enforce_gate_raises_and_passes(self):
        with self.assertRaisesRegex(GateError, "GATE_BLOCKED"):
            enforce_gate(make_report([PENDING]), "skill-c")
        self.assertEqual(
            enforce_gate(make_report([OK]), "skill-a")["allowed"], True)


class TestLedger(unittest.TestCase):
    def test_admit_blocks_with_remediation_entry(self):
        with tempfile.TemporaryDirectory() as td:
            led = SkillEvaluationLedger(Path(td) / "gate.jsonl")
            with self.assertRaisesRegex(GateError, "GATE_BLOCKED"):
                admit_to_downstream(make_report([FAIL]), "skill-d",
                                    ledger=led, by=BY, at=NOW)
            kinds = [e["kind"] for e in led.entries()]
            self.assertEqual(kinds.count("gate_blocked"), 1)
            self.assertEqual(kinds.count("remediation"), 1)

    def test_pending_block_records_audit_without_remediation(self):
        with tempfile.TemporaryDirectory() as td:
            led = SkillEvaluationLedger(Path(td) / "gate.jsonl")
            with self.assertRaises(GateError):
                admit_to_downstream(make_report([PENDING]), "skill-c",
                                    ledger=led, by=BY, at=NOW)
            kinds = [e["kind"] for e in led.entries()]
            self.assertIn("gate_blocked", kinds)
            self.assertNotIn("remediation", kinds)

    def test_pass_records_audit(self):
        with tempfile.TemporaryDirectory() as td:
            led = SkillEvaluationLedger(Path(td) / "gate.jsonl")
            out = admit_to_downstream(make_report([OK]), "skill-a",
                                      ledger=led, by=BY, at=NOW)
            self.assertTrue(out["verdict"]["allowed"])
            self.assertEqual([e["kind"] for e in led.entries()],
                             ["gate_passed"])

    def test_ledger_requires_by(self):
        led = SkillEvaluationLedger(None)
        with self.assertRaisesRegex(GateError, "by"):
            admit_to_downstream(make_report([OK]), "skill-a",
                                ledger=led, by="", at=NOW)

    def test_ledger_append_only_and_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gate.jsonl"
            led = SkillEvaluationLedger(path)
            led.record({"prd": 493}, {"kind": "gate_passed",
                                          "skill_id": "s", "by": BY, "at": NOW})
            led.record({"prd": 493}, {"kind": "gate_blocked",
                                          "skill_id": "s2", "by": BY, "at": NOW})
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            snapshot = led.entries()
            snapshot[0]["kind"] = "改（占位）"
            self.assertEqual(led.entries()[0]["kind"], "gate_passed")

    def test_unknown_skill_recorded_then_refused(self):
        with tempfile.TemporaryDirectory() as td:
            led = SkillEvaluationLedger(Path(td) / "gate.jsonl")
            with self.assertRaisesRegex(GateError, "GATE_BLOCKED"):
                admit_to_downstream(make_report([OK]), "ghost",
                                    ledger=led, by=BY, at=NOW)
            self.assertEqual(led.latest_for("ghost")["kind"], "gate_blocked")

    def test_format_remediation_line(self):
        line = format_remediation_line({"skill_id": "s", "at": NOW,
                                        "reason": "质量门未过关", "evidence": "报告",
                                        "due": "待定", "action": "修"})
        self.assertIn("技能 s", line)
        self.assertIn("整改期限 待定", line)


class TestOutlet(unittest.TestCase):
    def test_gate_outlet_blocks_all_pending(self):
        out = gate_outlet(make_report([PENDING, OK]), ["skill-c", "skill-a"],
                          by=BY, at=NOW)
        self.assertEqual([p["skill_id"] for p in out["passed"]], ["skill-a"])
        self.assertEqual(out["blocked_count"], 1)

    def test_gate_outlet_with_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            led = SkillEvaluationLedger(Path(td) / "g.jsonl")
            out = gate_outlet(make_report([OK, FAIL]), ["skill-a", "skill-d"],
                              ledger=led, by=BY, at=NOW)
            self.assertEqual(len(out["passed"]), 1)
            self.assertEqual(len(out["blocked"]), 1)
            kinds = [e["kind"] for e in led.entries()]
            self.assertEqual(kinds.count("gate_passed"), 1)
            self.assertEqual(kinds.count("gate_blocked"), 1)
            self.assertEqual(kinds.count("remediation"), 1)


class TestRealEvaluation(unittest.TestCase):
    def test_t2_report_roundtrip_gates(self):
        # T2 run_evaluation 真实产物直接过闸：过关放行、未过关/疑似失效拦下。
        report = make_real_report([OK, FAIL, SUSPECT])
        self.assertTrue(check_gate(report, "skill-a")["allowed"])
        self.assertFalse(check_gate(report, "skill-d")["allowed"])
        self.assertFalse(check_gate(report, "skill-e")["allowed"])

    def test_t2_report_two_pass_byte_identical(self):
        a = json.dumps(make_real_report([OK, FAIL]), sort_keys=True,
                       ensure_ascii=False)
        b = json.dumps(make_real_report([OK, FAIL]), sort_keys=True,
                       ensure_ascii=False)
        self.assertEqual(a, b)


class TestRedlines(unittest.TestCase):
    def test_vocab_closed(self):
        self.assertEqual(VERDICT_PASS, "过关")
        for w in VERDICT_PENDING + VERDICT_FAIL:
            self.assertIsInstance(w, str)
        self.assertEqual(set(BLOCK_REASON_CODES),
                         {"BAD_REPORT", "UNKNOWN_SKILL", "REMEDIATE",
                           "INSUFFICIENT_EVIDENCE", "SUSPECTED_OVERLAP"})
        self.assertEqual(set(GATE_AUDIT_KINDS),
                         {"gate_passed", "gate_blocked", "remediation"})

    def test_no_publish_path(self):
        src = (MODULE_DIR / "skill_evaluation_gate.py").read_text(encoding="utf-8")
        for word in ("publish", "delete_skill", "remove_skill", "merge_skill"):
            self.assertNotIn(word, src.lower())

    def test_ast_zero_network(self):
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        for name in ("skill_evaluation.py", "skill_evaluation_gate.py"):
            src = (MODULE_DIR / name).read_text(encoding="utf-8")
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned, name)


if __name__ == "__main__":
    unittest.main()
