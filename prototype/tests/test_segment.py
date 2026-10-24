import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m1_shadow.segment import (
    SegmentationError,
    WordStamp,
    allocate_positive,
    estimate_proportional,
    parse_transcript,
    parse_words,
    segment_by_word_timestamps,
    segment_request,
    tokenize,
)


def words(*rows):
    return [WordStamp(word, start, end) for word, start, end in rows]


class SegmentTests(unittest.TestCase):
    def test_tokenize_keeps_contraction_and_drops_punctuation(self):
        self.assertEqual(tokenize("I'm going."), ["i'm", "going"])
        self.assertEqual(tokenize("Today?"), ["today"])

    def test_multiline_transcript_is_one_sentence_per_line(self):
        text = "I usually take the subway.\nCould you send the report?"
        self.assertEqual(
            parse_transcript(text),
            ["I usually take the subway.", "Could you send the report?"],
        )

    def test_single_paragraph_splits_on_punctuation(self):
        text = "I usually take the subway. Could you send the report?"
        self.assertEqual(len(parse_transcript(text)), 2)

    def test_tail_pad_stops_before_the_next_sentence(self):
        stamped = words(
            ("a", 0, 100),
            ("b", 100, 200),
            ("c", 700, 800),
            ("d", 800, 900),
        )
        spans = segment_by_word_timestamps(["a b", "c d"], stamped, tail_pad_ms=250)
        self.assertEqual(spans[0].start_ms, 0)
        self.assertEqual(spans[0].end_ms, 450)
        self.assertEqual(spans[1].start_ms, 700)
        self.assertEqual(spans[1].end_ms, 1150)

    def test_repeated_word_stays_in_order(self):
        stamped = words(
            ("the", 0, 10),
            ("cat", 10, 40),
            ("sat", 40, 80),
            ("the", 400, 420),
            ("dog", 420, 500),
        )
        spans = segment_by_word_timestamps(["the cat sat", "the dog"], stamped, tail_pad_ms=0)
        self.assertEqual(spans[0].last_word_index, 2)
        self.assertEqual(spans[1].first_word_index, 3)
        self.assertEqual(spans[1].start_ms, 400)

    def test_mismatch_is_an_error(self):
        stamped = words(("the", 0, 10), ("cat", 10, 40))
        with self.assertRaises(SegmentationError):
            segment_by_word_timestamps(["the cat sat"], stamped)

    def test_leftover_timestamps_are_an_error(self):
        stamped = words(("the", 0, 10), ("cat", 10, 40), ("sat", 40, 80))
        with self.assertRaises(SegmentationError):
            segment_by_word_timestamps(["the cat"], stamped)

    def test_whisperx_seconds_are_accepted(self):
        parsed = parse_words([{"word": "Hello", "start": 0.0, "end": 0.4}])
        self.assertEqual(parsed[0].start_ms, 0)
        self.assertEqual(parsed[0].end_ms, 400)

    def test_proportional_spans_cover_the_duration_without_gaps(self):
        spans = estimate_proportional(["one two", "three", "four five six"], 1000)
        self.assertEqual(spans[0].start_ms, 0)
        self.assertEqual(spans[-1].end_ms, 1000)
        for earlier, later in zip(spans, spans[1:]):
            self.assertEqual(earlier.end_ms, later.start_ms)
            self.assertGreater(later.end_ms, later.start_ms)
        self.assertEqual(sum(span.end_ms - span.start_ms for span in spans), 1000)
        self.assertTrue(all(span.first_word_index == -1 for span in spans))

    def test_allocate_sums_and_stays_positive(self):
        lengths = allocate_positive([1, 1, 1], 10)
        self.assertEqual(sum(lengths), 10)
        self.assertTrue(all(length >= 1 for length in lengths))

    def test_fallback_to_proportional_keeps_the_warning(self):
        payload = segment_request(
            {
                "text": "the cat sat\nthe dog ran",
                "duration_ms": 2000,
                "words": [{"word": "nope", "start_ms": 0, "end_ms": 10}],
                "fallback": "proportional",
            }
        )
        self.assertEqual(payload["timing_source"], "proportional_estimate")
        self.assertIn("nope", payload["warning"])
        self.assertEqual(payload["sentences"][-1]["end_ms"], 2000)

    def test_word_timestamps_do_not_fallback_unless_asked(self):
        with self.assertRaises(SegmentationError):
            segment_request(
                {
                    "sentences": ["the cat sat"],
                    "words": [{"word": "the", "start_ms": 0, "end_ms": 10}],
                }
            )


if __name__ == "__main__":
    unittest.main()
