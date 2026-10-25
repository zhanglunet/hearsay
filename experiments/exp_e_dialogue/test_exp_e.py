"""exp_e_dialogue 的纯逻辑测试：标准库，不调 LLM、不加载模型。

在仓库根目录：python -m unittest discover -s experiments/exp_e_dialogue -p "test_*.py"
"""
import unittest

from aggregate import aggregate, session_counts
from batch_latency import summarize_timings
from can_do_consistency import agreement


def recap(merged, discarded, new):
    confirmed = [dict(merged_provisional=True)] * merged + [dict(merged_provisional=False)] * new
    return dict(batch=dict(confirmed=confirmed, discarded=[{}] * discarded,
                           detection="asr_llm"))


class AggregateTests(unittest.TestCase):
    def test_counts_and_rate(self):
        report = aggregate([recap(4, 1, 2), recap(3, 1, 0)])
        self.assertEqual(report["sessions"], 2)
        self.assertEqual(report["provisional"], 9)
        self.assertEqual(report["discarded"], 2)
        self.assertEqual(report["batch_new"], 2)
        self.assertEqual(report["false_positive_rate"], round(2 / 9, 3))
        self.assertFalse(report["passed"])

    def test_threshold_pass_and_empty(self):
        self.assertTrue(aggregate([recap(9, 1, 0)])["passed"])
        self.assertTrue(aggregate([recap(8, 2, 0)])["passed"])  # 恰好 0.20 也算过
        report = aggregate([recap(0, 0, 3)])
        self.assertIsNone(report["false_positive_rate"])
        self.assertFalse(report["passed"])

    def test_session_counts_requires_batch(self):
        with self.assertRaises(KeyError):
            session_counts({})


class AgreementTests(unittest.TestCase):
    def test_agreement(self):
        self.assertEqual(agreement(["pass"] * 5), 1.0)
        self.assertEqual(agreement(["pass"] * 4 + ["fail"]), 0.8)
        self.assertEqual(agreement(["pass"] * 3 + ["fail", "insufficient"]), 0.6)
        self.assertIsNone(agreement([]))


class LatencyTests(unittest.TestCase):
    def test_total_and_threshold(self):
        report = summarize_timings({"transcribe": 40.0, "detect": 10.0, "summary": 5.0})
        self.assertEqual(report["total_sec"], 55.0)
        self.assertTrue(report["passed"])
        report = summarize_timings({"transcribe": 55.0, "detect": 10.0, "summary": 5.0})
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
