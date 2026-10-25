"""retest_human 的核心逻辑测试：只用标准库，不加载 whisperX / torch。

在仓库根目录运行：python -m unittest discover -s experiments/exp_c_timestamps -p "test_*.py"
"""
import tempfile, unittest
from pathlib import Path

from retest_human import (evaluate_clip, match_sentence_boundaries, read_annotations,
                          ref_words, summarize)


def hyp_word(word, start, end):
    return dict(word=word, start=start, end=end)


class RefWordsTests(unittest.TestCase):
    def test_spans_cover_each_sentence(self):
        words, spans = ref_words([3, 1])
        self.assertEqual(words[spans[0][0]:spans[0][1] + 1],
                         "Could you send me the report before the meeting so I have time to read it carefully?".split())
        self.assertEqual(spans[1][0], spans[0][1] + 1)
        self.assertEqual(words[spans[1][0]], "I")
        self.assertEqual(words[spans[1][1]], "morning.")

    def test_out_of_range_line_rejected(self):
        with self.assertRaises(ValueError):
            ref_words([999])


class MatchTests(unittest.TestCase):
    def test_first_last_words_with_punctuation_and_substitution(self):
        words = "I usually take the subway to work".split()
        spans = [(0, 6)]
        hyp = [hyp_word("i", 0.10, 0.30), hyp_word("usually", 0.30, 0.70),
               hyp_word("take", 0.70, 0.90), hyp_word("a", 0.90, 1.00),
               hyp_word("subway", 1.00, 1.40), hyp_word("to", 1.40, 1.50),
               hyp_word("work,", 1.50, 1.90)]
        self.assertEqual(match_sentence_boundaries(words, spans, hyp), [(0.10, 1.90)])

    def test_unmatched_last_word_returns_none(self):
        words = "I usually take the subway".split()
        hyp = [hyp_word("i", 0.0, 0.2), hyp_word("usually", 0.2, 0.6)]
        self.assertEqual(match_sentence_boundaries(words, [(0, 3)], hyp), [None])


class EvaluateClipTests(unittest.TestCase):
    def test_multi_sentence_clip_and_speaker_rows(self):
        annotations = [dict(clip="C_03", line=3, tmin=0.0, tmax=1.0),
                       dict(clip="C_03", line=3, tmin=2.0, tmax=3.0)]
        # 两句同一句子连录：首末词各出现两次，difflib 应按词序对齐
        sent = "Could you send me the report before the meeting so I have time to read it carefully?".split()
        hyp = []
        t = 0.0
        for _ in range(2):
            for w in sent:
                hyp.append(hyp_word(w, t, t + 0.04))
                t += 0.05
            t += 1.0
        rows = evaluate_clip(annotations, hyp)
        self.assertEqual(len(rows), 2)
        self.assertLess(rows[0]["ds"], 0.05)
        self.assertGreater(rows[1]["h_start"], rows[0]["h_end"])


class SummarizeTests(unittest.TestCase):
    def row(self, ds, de):
        return dict(ds=ds, de=de)

    def test_threshold_boundary(self):
        rows = [self.row(0.01, 0.02)] * 9 + [self.row(0.30, 0.02)]
        rep = summarize(rows)
        self.assertEqual(rep["sent_boundary_frac_lt_150ms"], 0.95)
        self.assertTrue(rep["passed"])

    def test_below_threshold_fails(self):
        rows = [self.row(0.01, 0.02)] * 7 + [self.row(0.30, 0.40)] * 3
        rep = summarize(rows)
        self.assertEqual(rep["sent_boundary_frac_lt_150ms"], 0.7)
        self.assertFalse(rep["passed"])

    def test_unmatched_counted_separately(self):
        rows = [self.row(0.01, 0.02), self.row(None, None)]
        rep = summarize(rows)
        self.assertEqual(rep["matched"], 1)
        self.assertEqual(rep["unmatched"], 1)
        self.assertTrue(rep["passed"])

    def test_all_unmatched_does_not_pass(self):
        rep = summarize([self.row(None, None)])
        self.assertIsNone(rep["sent_boundary_frac_lt_150ms"])
        self.assertFalse(rep["passed"])


class ReadAnnotationsTests(unittest.TestCase):
    def test_parse(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S01_C_boundaries.csv"
            p.write_text("clip,tmin,tmax,line\nC_03,0.42,3.85,3\nC_07,0.10,2.00,7\n")
            rows = read_annotations(p)
        self.assertEqual(rows[0], dict(clip="C_03", line=3, tmin=0.42, tmax=3.85))
        self.assertEqual(rows[1]["line"], 7)


class ScaffoldTests(unittest.TestCase):
    def test_scaffold_creates_templates(self):
        from scaffold_human import scaffold
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "m1_human_audio"
            made = scaffold(root, ["S01", "S02"], [3, 7, 12])
            self.assertEqual(len(made), 2)
            text = made[0].read_text()
            self.assertTrue(text.startswith("clip,tmin,tmax,line\n"))
            self.assertIn("C_03,,,3", text)
            self.assertIn("C_12,,,12", text)
            self.assertTrue((root / "audio" / "S01").is_dir())
            self.assertTrue((root / "consents").is_dir())
            self.assertIn("speaker_id", (root / "manifests" / "speakers.csv").read_text())
            self.assertIn("A_01.wav", (root / "README_LOCAL.md").read_text())


if __name__ == "__main__":
    unittest.main()
