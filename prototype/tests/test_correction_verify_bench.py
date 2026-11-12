# -*- coding: utf-8 -*-
"""PRD-388/T2 测试（trend #1892 的 T2 环节）：纠正验证台。

运行：python3 -m unittest discover prototype/tests -p "test_correction_verify_bench.py"（仓库根执行）
基线声明：prototype/tests 既有 1 例环境性失败（test_dialogue_batch），与本 PR 无关。
覆盖（T1 §4 + R1~R4）：verify_correction 八件套校验（缺一 BENCH_INCOMPLETE）；
真实 word_feedback 对齐串联（同 reference+hypothesis 重跑 → error_instances
一致 VERIFIED；不一致/已修复 → UNVERIFIED 词表封闭）；verify_corrections
陪练反馈出口包装（UNVERIFIED 拦下）；CorrectionBenchLedger JSONL 真实落库
+八件套缺一/词表外/REPRO_MISMATCH 声称拒绝；reverify 语料变更二次验证
（指纹不符 BENCH_STALE 拒绝复用/一致正常复验）；AST 零网络零子进程零
phoneme 写。零网络；全合成占位。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTO))

from m1_shadow.correction_verify_bench import (  # noqa: E402
    BENCH_SCHEMA,
    CorrectionBenchError,
    CorrectionBenchLedger,
    ERROR_CODES,
    VERDICTS,
    corpus_fingerprint,
    verify_correction,
    verify_corrections,
)
from m1_shadow.feedback import word_feedback  # noqa: E402

NOW = "2026-11-13T09:00:00Z"
CORPUS = [{"reference": "I have two books.",
           "hypothesis": "I have two book.",
           "note": "参考句+学员作答快照（占位）"}]


def recheck_fn(corpus):
    """注入式发音模型复核重跑（复用 word_feedback 既有对齐形态）。"""
    out = []
    for c in (corpus or []):
        ref = str(c.get("reference") or "")
        hyp = str(c.get("hypothesis") or "")
        if not ref or not hyp:
            continue
        fb = word_feedback(ref, hyp)
        inst = [f"{a.get('ref', '')}->{a.get('hyp', '')}"
                for a in fb.get("alignment", []) if a.get("op") != "match"]
        out.append({"reference": ref, "hypothesis": hyp,
                    "error_instances": inst})
    return out


CORRECTION = {"correction_id": "c-001", "learner_id": "learner-1（占位）",
              "kind": "word_recall",
              "source_ref": "m1-shadow-feedback/v1#corrections[0]（占位）",
              "reference": "I have two books.",
              "hypothesis": "I have two book.",
              "error_instances": ["books->book"]}


class TestVerifyCorrection(unittest.TestCase):
    def test_verified_with_real_alignment_rerun(self):
        """真实 word_feedback 对齐串联：重跑 error_instances 与纠正一致 →
        VERIFIED；语料指纹 sha16: 前缀确定性。"""
        fb = word_feedback("I have two books.", "I have two book.")
        inst = [f"{a.get('ref', '')}->{a.get('hyp', '')}"
                for a in fb.get("alignment", []) if a.get("op") != "match"]
        correction = dict(CORRECTION, error_instances=inst)
        out = verify_correction(correction, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "VERIFIED")
        self.assertEqual(out["schema"], BENCH_SCHEMA)
        fp = corpus_fingerprint(CORPUS)
        self.assertTrue(fp.startswith("sha16:"))
        self.assertEqual(out["corpus_fingerprint"], fp)

    def test_unverified_when_instances_differ(self):
        out = verify_correction(dict(CORRECTION, error_instances=["x->y"]),
                                CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "UNVERIFIED")
        self.assertFalse(out["reproduce"]["instances_match"])

    def test_incomplete_refused(self):
        bad = dict(CORRECTION)
        del bad["error_instances"]
        out = verify_correction(bad, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_INCOMPLETE")
        out2 = verify_correction(CORRECTION, CORPUS, None, at=NOW)
        self.assertEqual(out2["refused"], "BENCH_INCOMPLETE")

    def test_verdict_vocab_closed(self):
        self.assertEqual(set(VERDICTS), {"VERIFIED", "UNVERIFIED"})


class TestVerifyCorrections(unittest.TestCase):
    def test_outlet_blocks_unverified(self):
        """陪练反馈出口包装：UNVERIFIED 拦下不进陪练反馈（R1）。"""
        corrections = [CORRECTION, dict(CORRECTION, correction_id="c-002",
                                        error_instances=["x->y"])]
        out = verify_corrections(corrections, CORPUS, recheck_fn, at=NOW)
        self.assertEqual(len(out["verified"]), 1)
        self.assertEqual(out["unverified_count"], 1)
        self.assertEqual(out["unverified"][0]["correction_id"], "c-002")


class TestCorrectionBenchLedger(unittest.TestCase):
    def test_jsonl_persistence_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cbench" / "ledger.jsonl"
            led = CorrectionBenchLedger(path)
            led.record(verify_correction(dict(CORRECTION,
                                              error_instances=["books->book"]),
                                         CORPUS, recheck_fn, at=NOW),
                       at=NOW)
            led.record(verify_correction(dict(CORRECTION,
                                              correction_id="c-002",
                                              error_instances=["books->book"]),
                                         CORPUS, recheck_fn, at=NOW),
                       at=NOW)
            self.assertEqual(len(led.entries()), 2)
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["correction_id"], "c-001")

    def test_record_refusals(self):
        led = CorrectionBenchLedger(None)
        with self.assertRaisesRegex(CorrectionBenchError, "BENCH_INCOMPLETE"):
            led.record({"schema": BENCH_SCHEMA}, at=NOW)
        with self.assertRaisesRegex(CorrectionBenchError,
                                    "BENCH_REPRO_MISMATCH"):
            bad = verify_correction(dict(CORRECTION,
                                         error_instances=["books->book"]),
                                    CORPUS, recheck_fn, at=NOW)
            bad = dict(bad, verdict="VERIFIED",
                       reproduce={"instances_match": False,
                                  "detail": "改（占位）"})
            led.record(bad, at=NOW)


class TestReverify(unittest.TestCase):
    def test_stale_refuses_reuse(self):
        """语料变更 → BENCH_STALE 拒绝复用旧 VERIFIED。"""
        led = CorrectionBenchLedger(None)
        led.record(verify_correction(dict(CORRECTION,
                                          error_instances=["books->book"]),
                                     CORPUS, recheck_fn, at=NOW), at=NOW)
        new_corpus = [{"reference": "She has three books.（占位）",
                       "hypothesis": "She has three book.（占位）"}]
        out = led.reverify("c-001", new_corpus, recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")

    def test_same_corpus_reverify_ok(self):
        led = CorrectionBenchLedger(None)
        led.record(verify_correction(dict(CORRECTION,
                                          error_instances=["books->book"]),
                                     CORPUS, recheck_fn, at=NOW), at=NOW)
        out = led.reverify("c-001", CORPUS, recheck_fn, at=NOW)
        self.assertEqual(out["verdict"], "VERIFIED")


class TestRedline(unittest.TestCase):
    def test_ast_zero_network_zero_subprocess_zero_phoneme(self):
        """AST：零网络零子进程零 phoneme 写词面（PHONEME_PRODUCT_RULE seal
        红线不变）。"""
        banned = {"urllib", "requests", "socket", "http", "subprocess"}
        src = PROTO / "m1_shadow" / "correction_verify_bench.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)
        names = {n.id.lower() for n in ast.walk(tree)
                 if isinstance(n, ast.Name)}
        names |= {n.attr.lower() for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute)}
        for word in ("phoneme_write", "write_phoneme"):
            self.assertNotIn(word, names, f"出现 phoneme 写词面 {word}")

    def test_error_codes_closed(self):
        self.assertEqual(set(ERROR_CODES),
                         {"BENCH_INCOMPLETE", "BENCH_REPRO_MISMATCH",
                          "BENCH_STALE"})


if __name__ == "__main__":
    unittest.main()
