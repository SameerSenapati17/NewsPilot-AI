import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.profiles.user_profile import UserProfile
from app.ranking import (
    PersonalizedRanker,
    RankingCandidate,
    RankingConfig,
    freshness_score,
)


def candidate(
    item_id,
    story_id=None,
    similarity=0.5,
    topics=None,
    entities=None,
    published_at=None,
    source_name=None,
    source_quality=None,
):
    return RankingCandidate(
        content_item_id=item_id,
        story_id=story_id,
        title=item_id,
        similarity=similarity,
        topics=topics or [],
        entities=entities or [],
        published_at=published_at,
        source_name=source_name,
        source_quality=source_quality,
    )


class TestRanking(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        self.ranker = PersonalizedRanker(now=self.now)

    def test_empty_candidates(self):
        self.assertEqual(self.ranker.rank([]), [])

    def test_default_profile_is_valid(self):
        result = self.ranker.rank([candidate("a")], UserProfile())
        self.assertEqual(len(result), 1)

    def test_preferred_topic_match_and_mismatch(self):
        profile = UserProfile(preferred_topics=["AI Agents"])
        results = self.ranker.rank([
            candidate("match", topics=["ai agents"]),
            candidate("miss", topics=["robotics"]),
        ], profile)
        self.assertEqual(results[0].content_item_id, "match")
        self.assertEqual(results[0].explanation.matched_topics, ["AI Agents"])

    def test_preferred_entity_match_and_mismatch(self):
        profile = UserProfile(preferred_entities=["OpenAI"])
        results = self.ranker.rank([
            candidate("match", entities=["openai"]),
            candidate("miss", entities=["Anthropic"]),
        ], profile)
        self.assertEqual(results[0].content_item_id, "match")
        self.assertEqual(results[0].explanation.matched_entities, ["OpenAI"])

    def test_exclusions_are_explained_and_penalized(self):
        profile = UserProfile(excluded_topics=["Crypto"])
        result = self.ranker.rank([candidate("a", topics=["cryptocurrency"])], profile)[0]
        self.assertTrue(result.explanation.exclusion_applied)
        self.assertIn("Excluded", result.explanation.reasons[-1])

    def test_entity_exclusion(self):
        profile = UserProfile(excluded_entities=["Company X"])
        result = self.ranker.rank([candidate("a", entities=["company x"])], profile)[0]
        self.assertTrue(result.explanation.exclusion_applied)

    def test_freshness_ordering(self):
        results = self.ranker.rank([
            candidate("old", similarity=0.5, published_at=self.now - timedelta(days=30)),
            candidate("new", similarity=0.5, published_at=self.now),
        ])
        self.assertEqual(results[0].content_item_id, "new")

    def test_missing_and_future_dates_are_safe(self):
        self.assertEqual(freshness_score(None, self.now), 0.0)
        self.assertEqual(freshness_score(self.now + timedelta(days=5), self.now), 1.0)

    def test_source_quality_mapping_and_unknown_default(self):
        config = RankingConfig(source_quality={"official": 1.0})
        ranker = PersonalizedRanker(config=config, now=self.now)
        known = ranker.rank([candidate("known", source_name="official")])[0]
        unknown = ranker.rank([candidate("unknown", source_name="other")])[0]
        self.assertEqual(known.explanation.source_score, 1.0)
        self.assertEqual(unknown.explanation.source_score, 0.5)

    def test_explicit_source_quality(self):
        result = self.ranker.rank([candidate("a", source_quality=0.9)])[0]
        self.assertEqual(result.explanation.source_score, 0.9)

    def test_semantic_score_contributes(self):
        results = self.ranker.rank([
            candidate("high", similarity=0.9),
            candidate("low", similarity=0.1),
        ])
        self.assertEqual(results[0].content_item_id, "high")
        self.assertEqual(results[0].explanation.semantic_score, 0.9)

    def test_weighted_score_is_deterministic(self):
        config = RankingConfig(
            semantic_weight=1.0, topic_weight=0.0, entity_weight=0.0,
            freshness_weight=0.0, source_weight=0.0,
        )
        result = PersonalizedRanker(config=config).rank([candidate("a", similarity=0.7)])[0]
        self.assertEqual(result.final_score, 0.7)

    def test_custom_weights_change_order(self):
        candidates = [
            candidate("semantic", similarity=0.9, topics=["other"]),
            candidate("topic", similarity=0.2, topics=["ai"]),
        ]
        profile = UserProfile(preferred_topics=["ai"])
        semantic_first = PersonalizedRanker(
            RankingConfig(semantic_weight=1, topic_weight=0, entity_weight=0,
                          freshness_weight=0, source_weight=0)
        ).rank(candidates, profile)
        topic_first = PersonalizedRanker(
            RankingConfig(semantic_weight=0, topic_weight=1, entity_weight=0,
                          freshness_weight=0, source_weight=0)
        ).rank(candidates, profile)
        self.assertEqual(semantic_first[0].content_item_id, "semantic")
        self.assertEqual(topic_first[0].content_item_id, "topic")

    def test_story_deduplication_keeps_strongest(self):
        results = self.ranker.rank([
            candidate("weak", "story-1", similarity=0.2),
            candidate("strong", "story-1", similarity=0.9),
            candidate("other", "story-2", similarity=0.3),
        ])
        self.assertEqual([item.content_item_id for item in results],
                         ["strong", "other"])

    def test_different_stories_remain(self):
        results = self.ranker.rank([
            candidate("a", "story-a", similarity=0.8),
            candidate("b", "story-b", similarity=0.7),
        ])
        self.assertEqual(len(results), 2)

    def test_explanations_are_structured(self):
        result = self.ranker.rank([
            candidate("a", topics=["AI"], entities=["OpenAI"], similarity=0.9)
        ], UserProfile(preferred_topics=["AI"], preferred_entities=["OpenAI"]))[0]
        self.assertTrue(result.explanation.reasons)
        self.assertEqual(result.explanation.final_score, result.final_score)

    def test_no_llm_or_external_dependency(self):
        result = self.ranker.rank([candidate("a")])
        self.assertIsNotNone(result[0])


if __name__ == "__main__":
    unittest.main()
