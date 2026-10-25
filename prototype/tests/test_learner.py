import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from m3_learner.fsrs import (Card, W, due_cards, interval_for_retention, retrievability)
from m3_learner.ingest import ingest_recap, recompute_window_counts
from m3_learner.review import build_review_scenario, select_target_codes
from m3_learner.store import LearnerStore

T0 = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def recap_with(codes, session_id="s1"):
    return dict(session_id=session_id, batch=dict(
        confirmed=[dict(utterance_id=i + 1, code=c, observed="x", expected="y",
                        detected_by="asr_llm", confidence=0.9, merged_provisional=False)
                   for i, c in enumerate(codes)],
        discarded=[dict(code="G09", observed="very like")]))


class FsrsTests(unittest.TestCase):
    def test_retrievability_at_stability_is_target(self):
        self.assertAlmostEqual(retrievability(3.173, 3.173), 0.9, places=6)
        self.assertAlmostEqual(interval_for_retention(3.173), 3.173, places=6)

    def test_new_card_good(self):
        card = Card.new("error:G04", now=T0)
        days, _ = card.review(3, now=T0)
        self.assertAlmostEqual(card.stability, W[2])
        self.assertAlmostEqual(days, W[2], places=6)
        self.assertEqual(card.state, "review")
        self.assertEqual(card.reps, 1)
        self.assertEqual(datetime.fromisoformat(card.due) - T0, timedelta(days=days))

    def test_initial_difficulty_order(self):
        d = {}
        for rating in (1, 2, 3, 4):
            card = Card.new("x", now=T0)
            card.review(rating, now=T0)
            d[rating] = card.difficulty
        self.assertGreater(d[1], d[2])
        self.assertGreater(d[2], d[3])
        self.assertGreater(d[3], d[4])

    def test_review_good_increases_stability_again_decreases(self):
        good = Card.new("x", now=T0)
        good.review(3, now=T0)
        good.review(3, now=T0 + timedelta(days=3))
        self.assertGreater(good.stability, W[2])

        again = Card.new("x", now=T0)
        again.review(3, now=T0)
        before = again.stability
        again.review(1, now=T0 + timedelta(days=3))
        self.assertLess(again.stability, before)
        self.assertEqual(again.lapses, 1)
        self.assertGreater(again.difficulty, 5.0)

    def test_due_cards_filter_and_order(self):
        a, b = Card.new("a", now=T0), Card.new("b", now=T0 + timedelta(days=2))
        now = T0 + timedelta(days=1)
        self.assertEqual([c.item_id for c in due_cards([b, a], now)], ["a"])
        self.assertEqual(due_cards([a, b], T0 + timedelta(days=3))[0].item_id, "a")

    def test_bad_rating_rejected(self):
        with self.assertRaises(ValueError):
            Card.new("x", now=T0).review(0, now=T0)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "learner.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_reload_export_delete(self):
        store = LearnerStore(self.path)
        ingest_recap(store, recap_with(["G04"]), now=T0)
        again = LearnerStore(self.path)
        self.assertIn("G04", again.data["error_patterns"])
        exported = json.loads(again.export())
        self.assertEqual(exported["error_patterns"]["G04"]["count_total"], 1)
        again.delete()
        self.assertFalse(self.path.exists())
        self.assertEqual(again.data["error_patterns"], {})


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_confirmed_counted_discarded_ignored(self):
        result = ingest_recap(self.store, recap_with(["G04", "G04", "G13"]), now=T0)
        self.assertTrue(result["ingested"])
        self.assertEqual(result["instances"], 3)
        patterns = self.store.data["error_patterns"]
        self.assertEqual(patterns["G04"]["count_total"], 2)
        self.assertEqual(patterns["G04"]["count_30d"], 2)
        self.assertNotIn("G09", patterns)  # discarded 不计入
        self.assertEqual(len(self.store.data["error_instances"]), 3)
        self.assertTrue(all(i["status"] == "confirmed" for i in self.store.data["error_instances"]))
        self.assertEqual(patterns["G04"]["remediation"]["status"], "scheduled")
        self.assertTrue(self.store.has_card("error:G04"))
        self.assertTrue(self.store.has_card("error:G13"))
        self.assertEqual(len(self.store.data["cards"]), 2)

    def test_duplicate_session_skipped(self):
        recap = recap_with(["G04"])
        ingest_recap(self.store, recap, now=T0)
        result = ingest_recap(self.store, recap, now=T0)
        self.assertFalse(result["ingested"])
        self.assertEqual(result["reason"], "session_already_ingested")
        self.assertEqual(self.store.data["error_patterns"]["G04"]["count_total"], 1)

    def test_no_batch_no_write(self):
        result = ingest_recap(self.store, dict(session_id="s2", recasts=[]), now=T0)
        self.assertFalse(result["ingested"])
        self.assertEqual(self.store.data["error_patterns"], {})

    def test_x00_only_archived_not_patterned(self):
        result = ingest_recap(self.store, recap_with(["X00", "G04"]), now=T0)
        patterns = self.store.data["error_patterns"]
        self.assertNotIn("X00", patterns)
        self.assertFalse(self.store.has_card("error:X00"))
        self.assertIn("G04", patterns)
        codes = [i["code"] for i in self.store.data["error_instances"]]
        self.assertEqual(codes, ["X00", "G04"])

    def test_window_counts_recompute(self):
        old = T0 - timedelta(days=40)
        self.store.data["error_patterns"]["G04"] = dict(
            code="G04", count_total=2, count_30d=2, count_7d=2,
            event_dates=[old.isoformat(), T0.isoformat()],
            remediation=dict(status="scheduled"))
        recompute_window_counts(self.store, now=T0)
        pattern = self.store.data["error_patterns"]["G04"]
        self.assertEqual(pattern["count_30d"], 1)
        self.assertEqual(pattern["count_7d"], 1)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LearnerStore(Path(self.tmp.name) / "learner.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_due_codes_forced_then_frequency(self):
        ingest_recap(self.store, recap_with(["G13", "G13", "G04", "G08", "G08", "G03"]), now=T0)
        # G04 评分复习后推到未来，其余新卡仍到期；第三个名额给同频但字母序在前的 G03
        card = next(c for c in self.store.cards() if c.item_id == "error:G04")
        card.review(4, now=T0)
        self.store.put_card(card)
        codes = select_target_codes(self.store, now=T0)
        self.assertEqual(codes[:2], ["G13", "G08"])
        self.assertEqual(codes, ["G13", "G08", "G03"])
        self.assertNotIn("G04", codes)

    def test_scenario_injects_codes(self):
        ingest_recap(self.store, recap_with(["G04"]), now=T0)
        scenario = build_review_scenario(self.store, now=T0)
        self.assertEqual(scenario["target_error_codes"], ["G04"])
        self.assertEqual(scenario["based_on"], "m2-project-delay")
        self.assertTrue(any("G04" in o for o in scenario["objectives"]))

    def test_empty_store_gives_free_talk(self):
        scenario = build_review_scenario(self.store, now=T0)
        self.assertEqual(scenario["target_error_codes"], [])
        self.assertEqual(scenario["objectives"], ["自由对话，没有到期复习项"])


if __name__ == "__main__":
    unittest.main()
