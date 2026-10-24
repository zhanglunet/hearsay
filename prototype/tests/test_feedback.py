import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.feedback import FeedbackError, feedback_request, summarize_request, word_feedback
from m1_shadow.limits import PHONEME_PRODUCT_RULE, seal_no_phoneme_writes


class FeedbackTests(unittest.TestCase):
    def test_identical_sentence_is_not_low_and_has_no_phoneme_write(self):
        result = word_feedback("I have two book.", "I have two book.")
        self.assertEqual(result["word_recall"], 1.0)
        self.assertFalse(result["low_score"])
        self.assertNotIn("error_instances", result)
        self.assertNotIn("phoneme_profile", result)
        self.assertNotIn("common_substitution", result)

    def test_exact_three_quarters_is_not_low(self):
        result = word_feedback("I have two book", "I have two")
        self.assertEqual(result["counts"]["match"], 3)
        self.assertEqual(result["counts"]["reference"], 4)
        self.assertFalse(result["low_score"])

    def test_missing_half_is_low_and_marks_deletions(self):
        result = word_feedback("I have two book", "I have")
        self.assertTrue(result["low_score"])
        self.assertEqual(result["counts"]["deletion"], 2)
        self.assertLess(result["word_recall"], 0.75)

    def test_extra_words_do_not_lower_recall(self):
        result = word_feedback("I have two book", "um I have two book please")
        self.assertEqual(result["word_recall"], 1.0)
        self.assertFalse(result["low_score"])
        self.assertGreater(result["counts"]["insertion"], 0)
        self.assertLess(result["word_precision"], 1)

    def test_unrelated_hypothesis_is_not_paired_as_substitutions(self):
        result = word_feedback("I usually take the subway", "hello there")
        self.assertEqual(result["counts"]["match"], 0)
        self.assertEqual(result["counts"]["substitution"], 0)
        self.assertEqual(result["counts"]["insertion"], 2)
        self.assertTrue(result["low_score"])
        self.assertTrue(all(row["op"] != "substitution" for row in result["alignment"]))

    def test_substitution_is_visible(self):
        result = word_feedback("I have two book", "I have two books")
        self.assertEqual(result["counts"]["substitution"], 1)
        self.assertFalse(result["low_score"])

    def test_empty_hypothesis_is_low(self):
        result = word_feedback("Please record yourself tomorrow", "")
        self.assertEqual(result["word_recall"], 0.0)
        self.assertTrue(result["low_score"])

    def test_reference_without_english_words_fails(self):
        with self.assertRaises(FeedbackError):
            word_feedback("……", "hello")

    def test_phoneme_payload_is_ignored(self):
        result = feedback_request(
            {
                "reference": "the cat sat",
                "hypothesis": "the cat sat",
                "phonemes": [{"expected": "TH", "heard": "S"}],
                "common_substitution": "S",
                "error_instances": [{"code": "P01"}],
                "phoneme_profile": {"phoneme": "TH", "accuracy_mean_30d": 0.2},
            }
        )
        self.assertIn("phonemes", result["ignored_inputs"])
        self.assertIn("common_substitution", result["ignored_inputs"])
        sealed = seal_no_phoneme_writes(result)
        self.assertEqual(sealed["error_instances"], [])
        self.assertIsNone(sealed["phoneme_profile"])
        self.assertIsNone(sealed["common_substitution"])
        self.assertFalse(sealed["phoneme_feedback"])
        self.assertIn("0.148", sealed["product_rule"])
        self.assertIn("0.148", PHONEME_PRODUCT_RULE)

    def test_summary_lists_low_sentences_without_error_instances(self):
        summary = summarize_request(
            {
                "sentences": [
                    {"idx": 0, "reference": "I have two book", "hypothesis": "I have two book"},
                    {"idx": 1, "reference": "the restaurant has noodles", "hypothesis": "hello"},
                ]
            }
        )
        self.assertEqual(summary["session_type"], "shadow")
        self.assertEqual(summary["low_score_sentence_idxs"], [1])
        self.assertNotIn("error_instances", summary)
        self.assertNotIn("phoneme_profile", summary)


if __name__ == "__main__":
    unittest.main()
