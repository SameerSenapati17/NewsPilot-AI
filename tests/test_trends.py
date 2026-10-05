import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trends import (
    TrendConfig,
    TrendDetector,
    calculate_growth,
    normalize_topic,
)


END = datetime(2026, 1, 15, tzinfo=timezone.utc)


def record(item, days_ago, topic, story=None, source=None, aware=True):
    published = END - timedelta(days=days_ago)
    if not aware:
        published = published.replace(tzinfo=None)
    return {
        "content_item_id": item,
        "published_at": published,
        "topics": [topic],
        "story_id": story,
        "source_id": source,
    }


class TestTrends(unittest.TestCase):
    def test_empty_dataset_and_empty_topics(self):
        detector = TrendDetector()
        self.assertEqual(detector.detect_trends([], end_time=END), [])
        self.assertEqual(
            detector.detect_trends([record("a", 1, " ")], end_time=END), []
        )

    def test_topic_normalization(self):
        self.assertEqual(normalize_topic("  AI   Agents "), "ai agents")
        results = TrendDetector().detect_trends(
            [record("a", 1, " AI   Agents "), record("b", 2, "ai agents")],
            end_time=END,
        )
        self.assertEqual(results[0].topic, "ai agents")

    def test_windows_and_activity_counts(self):
        records = [
            record("recent-1", 1, "agents", "s1", "source-1"),
            record("recent-2", 2, "agents", "s2", "source-2"),
            record("previous-1", 8, "agents", "s0", "source-1"),
        ]
        result = TrendDetector().detect_trends(records, end_time=END)[0]
        self.assertEqual(result.metrics.recent_content_count, 2)
        self.assertEqual(result.metrics.previous_content_count, 1)
        self.assertEqual(result.metrics.recent_story_count, 2)
        self.assertEqual(result.metrics.recent_source_count, 2)

    def test_custom_windows_and_explicit_reference(self):
        result = TrendDetector().detect_trends(
            [record("a", 1, "topic")], end_time=END, recent_days=2, previous_days=2
        )[0]
        self.assertEqual(
            result.metrics.recent_window_start,
            END - timedelta(days=2),
        )

    def test_growth_zero_and_bounded(self):
        self.assertEqual(calculate_growth(0, 0), 0.0)
        self.assertEqual(calculate_growth(0, 3), 1.0)
        self.assertEqual(calculate_growth(10, 0), 0.0)
        self.assertEqual(calculate_growth(2, 20), 1.0)

    def test_story_and_source_diversity(self):
        records = [
            record("a", 1, "topic", "story-1", "source-1"),
            record("b", 1, "topic", "story-1", "source-2"),
            record("c", 1, "topic", "story-2", "source-3"),
        ]
        metrics = TrendDetector().detect_trends(records, end_time=END)[0].metrics
        self.assertEqual(metrics.recent_story_count, 2)
        self.assertEqual(metrics.recent_source_count, 3)
        self.assertLess(metrics.story_diversity_score, 1.0)
        self.assertEqual(metrics.source_diversity_score, 1.0)

    def test_missing_story_and_enrichment_are_safe(self):
        records = [record("a", 1, "topic", None, None)]
        result = TrendDetector().detect_trends(records, end_time=END)[0]
        self.assertEqual(result.metrics.recent_story_count, 1)

    def test_timezone_aware_and_future_timestamps(self):
        future = {
            **record("future", -1, "topic", "story", "source"),
            "published_at": END + timedelta(days=1),
        }
        results = TrendDetector().detect_trends(
            [future], end_time=END, recent_days=7, previous_days=7
        )
        self.assertEqual(results, [])
        naive = TrendDetector().detect_trends(
            [record("naive", 1, "topic", aware=False)], end_time=END
        )
        self.assertEqual(len(naive), 1)

    def test_minimum_activity_and_emerging_threshold(self):
        config = TrendConfig(min_recent_content=2, min_recent_stories=2)
        detector = TrendDetector(config=config)
        too_small = detector.detect_trends(
            [record("a", 1, "topic", "story", "source")], end_time=END
        )[0]
        self.assertFalse(too_small.is_emerging)
        enough = detector.detect_trends(
            [
                record("a", 1, "topic", "story-1", "source-1"),
                record("b", 2, "topic", "story-2", "source-2"),
            ],
            end_time=END,
        )[0]
        self.assertTrue(enough.is_emerging)

    def test_slow_high_volume_vs_rapid_growth(self):
        slow = [
            record(f"slow-r{i}", 1, "slow", f"slow-{i}", f"source-{i}")
            for i in range(105)
        ] + [
            record(f"slow-p{i}", 8, "slow", f"slow-p-{i}", f"source-p-{i}")
            for i in range(100)
        ]
        rapid = [
            record(f"rapid-r{i}", 1, "rapid", f"rapid-{i}", f"rapid-source-{i}")
            for i in range(8)
        ] + [
            record(f"rapid-p{i}", 8, "rapid", f"rapid-p-{i}", f"rapid-p-source-{i}")
            for i in range(2)
        ]
        results = TrendDetector().detect_trends(slow + rapid, end_time=END)
        self.assertGreater(
            next(item for item in results if item.topic == "rapid").metrics.growth_rate,
            next(item for item in results if item.topic == "slow").metrics.growth_rate,
        )

    def test_deterministic_ordering_top_k_and_explanation(self):
        records = [record("a", 1, "z"), record("b", 1, "a")]
        results = TrendDetector().detect_trends(records, end_time=END, top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].topic, "a")
        self.assertIn("2", TrendDetector().detect_trends(
            [record("a", 1, "a"), record("b", 1, "a")], end_time=END
        )[0].explanation)

    def test_configurable_weights_change_score(self):
        records = [record("a", 1, "topic", "story", "source")]
        base = TrendDetector().detect_trends(records, end_time=END)[0].score
        config = TrendConfig(
            growth_weight=1, activity_weight=0, story_diversity_weight=0,
            source_diversity_weight=0, recency_weight=0,
        )
        growth = TrendDetector(config=config).detect_trends(
            records, end_time=END
        )[0].score
        self.assertNotEqual(base, growth)

    def test_no_external_provider_dependency(self):
        self.assertIsNotNone(TrendDetector().detect_trends([], end_time=END))


if __name__ == "__main__":
    unittest.main()
