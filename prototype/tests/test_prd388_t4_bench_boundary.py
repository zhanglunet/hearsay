# -*- coding: utf-8 -*-
"""PRD-388/T4 测试（trend #1892 的 T4 环节）：纠正验证台划界断言。
运行：python3 -m unittest discover prototype/tests -p "test_prd388_t4_bench_boundary.py"
覆盖（T1 §0/§3，验收「划界断言通过」）：bench/gates 零导入 m3_learner
（学习记录下游零感知——新仓链浅，本条以「验证台不触碰学习记录」为隔离
主体）+ 借鉴词零出现（仅代码标识符扫描）+ 标准库-only 钉值（gates 只
import 同链 corpus_fingerprint）+ 零网络 AST+R1 拦截钉值+R3 八件套/词表
封闭+R4 方法面封闭+STALE+确定性复现+word_feedback 面符号不变钉值。
零网络；全合成占位。
"""
import ast
import sys
import unittest
from pathlib import Path

PROTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTO))

from m1_shadow.correction_verify_bench import (  # noqa: E402
    BENCH_SCHEMA,
    ERROR_CODES,
    CorrectionBenchError,
    CorrectionBenchLedger,
    VERDICTS,
    corpus_fingerprint,
    verify_corrections,
    verify_correction,
)
from m1_shadow.feedback import word_feedback  # noqa: E402

NOW = "2026-11-13T09:00:00Z"
CORPUS = [{"reference": "I have two books.",
           "hypothesis": "I have two book.",
           "note": "参考句+学员作答快照（占位）"}]
CORRECTION = {"correction_id": "c-001", "learner_id": "learner-1（占位）",
              "kind": "word_recall",
              "source_ref": "m1-shadow-feedback/v1#corrections[0]（占位）",
              "reference": "I have two books.", "hypothesis": "I have two book.",
              "error_instances": ["books->book"]}

BENCH_MODULES = ["correction_verify_bench.py",
                 "correction_verify_bench_gates.py"]


def recheck_fn(corpus):
    out = []
    for c in (corpus or []):
        ref, hyp = str(c.get("reference") or ""), str(c.get("hypothesis") or "")
        if not ref or not hyp:
            continue
        fb = word_feedback(ref, hyp)
        inst = [f"{a.get('ref', '')}->{a.get('hyp', '')}"
                for a in fb.get("alignment", []) if a.get("op") != "match"]
        out.append({"reference": ref, "hypothesis": hyp,
                    "error_instances": inst})
    return out


def _imports_of(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _code_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


class TestModuleIsolation(unittest.TestCase):
    def test_bench_never_imports_learner_store(self):
        """验证台面零触碰学习记录（m3_learner——下游零感知）。"""
        for mod in BENCH_MODULES:
            imported = _imports_of(PROTO / "m1_shadow" / mod)
            for banned in ("m3_learner", "store"):
                self.assertNotIn(banned, imported, f"{mod} 导入 {banned}")
            names = _code_names(PROTO / "m1_shadow" / mod)
            for symbol in ("fsrs", "review"):
                self.assertNotIn(symbol, names, f"{mod} 引用 {symbol}")

    def test_upstream_zero_symbols(self):
        """借鉴仓（codex-security Apache-2.0/security-audit-skill MIT 实测）
        零符号——只借控制面形态（仅代码标识符扫描）。"""
        for mod in BENCH_MODULES:
            names = {n.lower() for n in _code_names(PROTO / "m1_shadow" / mod)}
            for word in ("codex", "audit_skill"):
                self.assertNotIn(word, names, f"{mod} 出现 {word}")

    def test_stdlib_only_and_redline_ast(self):
        """标准库-only 钉值：bench 静态导入全标准库（gates 只 import 同链
        corpus_fingerprint）；零网络零子进程零 phoneme 写。"""
        imported = _imports_of(PROTO / "m1_shadow" / "correction_verify_bench.py")
        self.assertLessEqual(imported - {"__future__", "copy", "hashlib",
                                         "json", "pathlib", "typing"},
                             set(), imported)
        gates_imported = _imports_of(
            PROTO / "m1_shadow" / "correction_verify_bench_gates.py")
        self.assertLessEqual(gates_imported - {"__future__", "typing",
                                               "m1_shadow"}, set())
        tree = ast.parse((PROTO / "m1_shadow" / "correction_verify_bench_gates.py")
                         .read_text(encoding="utf-8"))
        from_mods = {n.module for n in ast.walk(tree)
                     if isinstance(n, ast.ImportFrom) and n.module}
        self.assertIn("m1_shadow.correction_verify_bench", from_mods,
                      from_mods)
        for mod in BENCH_MODULES:
            names = {n.lower() for n in _code_names(PROTO / "m1_shadow" / mod)}
            for word in ("phoneme_write", "write_phoneme"):
                self.assertNotIn(word, names, f"{mod} 出现 phoneme 写词面 {word}")


class TestRedLinePins(unittest.TestCase):
    def test_r2_deterministic(self):
        """R2：同一输入 verify_correction 两遍逐字节一致（确定性复现）。"""
        a = verify_correction(CORRECTION, CORPUS, recheck_fn, at=NOW)
        b = verify_correction(CORRECTION, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(a, b)

    def test_r1_unverified_blocked_at_outlet(self):
        """R1 拦截钉值：UNVERIFIED 不进 verified 分组（不进陪练反馈）。"""
        out = verify_corrections([dict(CORRECTION, error_instances=["x->y"])],
                                 CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verified"], [])
        self.assertEqual(out["unverified_count"], 1)

    def test_r3_eight_piece_closed_and_fp_family(self):
        """R3 钉值：账目缺件 BENCH_INCOMPLETE；verdict 词表封闭；语料指纹
        sha16 同族钉值（确定性）。"""
        led = CorrectionBenchLedger(None)
        with self.assertRaisesRegex(CorrectionBenchError, "BENCH_INCOMPLETE"):
            led.record({"schema": BENCH_SCHEMA}, at=NOW)
        self.assertEqual(set(VERDICTS), {"VERIFIED", "UNVERIFIED"})
        fp = corpus_fingerprint(CORPUS)
        self.assertTrue(fp.startswith("sha16:"))
        self.assertEqual(fp, corpus_fingerprint(CORPUS))

    def test_r4_ledger_surface_closed_and_stale(self):
        """R4：Ledger 方法面封闭（零删除方法）+reverify 语料变更 BENCH_STALE
        拒绝复用。"""
        led = CorrectionBenchLedger(None)
        methods = {n for n in dir(led) if not n.startswith("_")}
        self.assertLessEqual(methods, {"record", "entries", "latest_for",
                                       "reverify"}, methods)
        led.record(verify_correction(CORRECTION, CORPUS, recheck_fn, at=NOW),
                   at=NOW)
        out = led.reverify("c-001", [{"reference": "She has three books.（占位）",
                                      "hypothesis": "She has three book.（占位）"}],
                           recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")


class TestDemarcationPins(unittest.TestCase):
    def test_feedback_surface_unchanged(self):
        """§3 划界钉值：word_feedback 对齐形态不变（alignment 词表
        match/substitution/deletion/insertion）——纠正产出归 feedback、
        验证台零新增纠正，互不越界。"""
        fb = word_feedback("I have two books.", "I have two book.")
        ops = {a["op"] for a in fb.get("alignment", [])}
        self.assertLessEqual(ops, {"match", "substitution", "deletion",
                                   "insertion"}, ops)
        self.assertEqual(fb["word_recall"], 0.75)   # 对齐口径钉值


if __name__ == "__main__":
    unittest.main()
