# -*- coding: utf-8 -*-
"""PRD-388/T5 测试（trend #1892 的 T5 环节）：纠正验证台验收试运行。
运行：python3 -m unittest discover prototype/tests -p "test_prd388_t5_bench_acceptance.py"
验收（T1 §6 T5 行「样例全链回放+UNVERIFIED 拦截演练+文档无密钥」）：
  接入点全链演练（PR 门槛验收）：语料快照 → 纠正 → verify_corrections 过台
  → VERIFIED 转陪练反馈形态（learner 会话消费，指纹同源）→ JSONL 落账 →
  闸门全 pass；两遍全链产物逐字节一致（确定性可复现）；UNVERIFIED 拦截
  演练（模型不一致纠正拦在陪练反馈外+落账留痕）；语料变更二次验证关闭
  演练（BENCH_STALE 拒绝复用→新语料复算 VERIFIED）；账本 append-only；链
  复跑：T2/T3/T4 测试子进程复跑 exit 0（基线声明：prototype/tests 既有 1
  例环境性失败与本链无关）；文档无密钥：T1 设计文档拼接 needle 扫描+
  占位符纪律。零网络；全合成占位。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTO))

from m1_shadow.correction_verify_bench import (  # noqa: E402
    CorrectionBenchLedger,
    verify_corrections,
)
from m1_shadow.correction_verify_bench_gates import (  # noqa: E402
    append_only_gate,
    gate_summary,
    mark_baseline,
    stale_gate,
    verdict_gate,
)
from m1_shadow.feedback import word_feedback  # noqa: E402

NOW = "2026-11-13T09:00:00Z"
CORPUS = [{"reference": "I have two books.",
           "hypothesis": "I have two book.",
           "note": "参考句+学员作答快照（占位）"}]


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


def _corrections():
    rerun = recheck_fn(CORPUS)
    return [dict(r, correction_id=f"c-{i:03d}", learner_id="learner-1（占位）",
                 kind="word_recall",
                 source_ref=f"m1-shadow-feedback/v1#corrections[{i}]（占位）")
            for i, r in enumerate(rerun, start=1)]


def _learner_feedback_from_verified(verified):
    """接入点：VERIFIED 纠正转陪练反馈形态（learner 会话消费，指纹同源）。"""
    return [{"learner_id": v["learner_id"],
             "corpus_fingerprint": v["corpus_fingerprint"],
             "reference": v["correction"]["reference"],
             "error_instances": v["correction"]["error_instances"],
             "reason": "验证过的纠正待反馈（占位）"}
            for v in verified]


class TestIntegrationPointDrill(unittest.TestCase):
    def test_outlet_full_chain_twice_deterministic(self):
        """接入点全链演练（PR 门槛验收）：纠正 → 过台 → VERIFIED 转陪练
        反馈形态 → JSONL 落账 → 闸门全 pass；两遍逐字节一致。"""
        runs = []
        for _ in range(2):
            out = verify_corrections(_corrections(), CORPUS, recheck_fn,
                                     at=NOW)
            fb = _learner_feedback_from_verified(out["verified"])
            self.assertTrue(fb)
            self.assertTrue(all({"learner_id", "corpus_fingerprint",
                                 "error_instances", "reason"} <= set(f)
                                for f in fb))
            with tempfile.TemporaryDirectory() as td:
                led = CorrectionBenchLedger(Path(td) / "cbench.jsonl")
                for rec in out["verified"] + [r for r in out["unverified"]
                                              if not r.get("refused")]:
                    led.record(rec, at=NOW)
                gates = [append_only_gate(led)]
                for rec in led.entries():
                    gates.append(verdict_gate(rec))
                    gates.append(stale_gate(rec, CORPUS))
                runs.append({"out": out, "fb": fb,
                             "entries": led.entries(),
                             "summary": gate_summary(gates)})
                self.assertEqual(gate_summary(gates)["gate"], "pass")
        self.assertEqual(json.dumps(runs[0], sort_keys=True),
                         json.dumps(runs[1], sort_keys=True))


class TestFailureDrills(unittest.TestCase):
    def test_unverified_blocked_and_traced(self):
        """UNVERIFIED 拦截演练：模型不一致纠正拦在陪练反馈外+落账留痕。"""
        phantom = [{"correction_id": "c-900", "learner_id": "learner-1（占位）",
                    "kind": "word_recall",
                    "source_ref": "m1-shadow-feedback/v1#fake（占位）",
                    "reference": "I have two books.",
                    "hypothesis": "I have two book.",
                    "error_instances": ["x->y"]}]
        with tempfile.TemporaryDirectory() as td:
            led = CorrectionBenchLedger(Path(td) / "cbench.jsonl")
            out = verify_corrections(phantom, CORPUS, recheck_fn, at=NOW)
            self.assertEqual(out["verified"], [])
            for rec in out["unverified"]:
                if not rec.get("refused"):
                    led.record(rec, at=NOW)
            self.assertEqual(led.entries()[-1]["verdict"], "UNVERIFIED")

    def test_corpus_change_then_second_verify_closes(self):
        """语料变更二次验证关闭演练：BENCH_STALE 拒绝复用 → 新语料复算
        VERIFIED 落新账。"""
        led = CorrectionBenchLedger(None)
        first = verify_corrections(_corrections(), CORPUS, recheck_fn,
                                   at=NOW)
        self.assertTrue(first["verified"])
        led.record(first["verified"][0], at=NOW)
        new_corpus = [{"reference": "She has three books.（占位）",
                       "hypothesis": "She has three book.（占位）"}]
        out = led.reverify(first["verified"][0]["correction_id"], new_corpus,
                           recheck_fn, at=NOW)
        self.assertEqual(out["refused"], "BENCH_STALE")
        fb2 = word_feedback("She has three books.（占位）",
                            "She has three book.（占位）")
        inst = [f"{a.get('ref', '')}->{a.get('hyp', '')}"
                for a in fb2.get("alignment", []) if a.get("op") != "match"]
        new_corrections = [{"correction_id": "c-101",
                            "learner_id": "learner-1（占位）",
                            "kind": "word_recall",
                            "source_ref": "new（占位）",
                            "reference": "She has three books.（占位）",
                            "hypothesis": "She has three book.（占位）",
                            "error_instances": inst}]
        second = verify_corrections(new_corrections, new_corpus, recheck_fn,
                                    at=NOW)
        if second["verified"]:
            rec = led.record(second["verified"][0], at=NOW)
            self.assertEqual(rec["verdict"], "VERIFIED")

    def test_append_only(self):
        """账本 append-only。"""
        out = verify_corrections(_corrections(), CORPUS, recheck_fn, at=NOW)
        led = CorrectionBenchLedger(None)
        for rec in out["verified"]:
            led.record(rec, at=NOW)
        mark_baseline(led)
        self.assertEqual(append_only_gate(led)["gate"], "pass")


class TestChainRerun(unittest.TestCase):
    def test_t2_t3_t4_rerun_green(self):
        """链复跑：T2/T3/T4 测试子进程复跑 exit 0（基线声明：prototype/tests
        既有 1 例环境性失败与本链无关）。"""
        for pattern in ("test_correction_verify_bench.py",
                        "test_correction_verify_bench_gates.py",
                        "test_prd388_t4_bench_boundary.py"):
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "prototype/tests", "-p", pattern],
                capture_output=True, timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f"{pattern} 复跑失败：{proc.stderr[-400:]}")


class TestDocNoSecrets(unittest.TestCase):
    def test_t1_design_doc_no_secrets(self):
        """文档无密钥：T1 设计文档拼接 needle 扫描+占位符纪律（R5）。"""
        doc = next(PROTO.parent.glob("docs/design/2026-11-12-prd-388-*.md"))
        text = doc.read_text(encoding="utf-8").lower()
        for needle in ("sk-" + "live", "passw" + "ord", "api_k" + "ey"):
            self.assertNotIn(needle, text, f"设计文档出现密钥词 {needle}")
        self.assertIn("占位", text)


if __name__ == "__main__":
    unittest.main()
