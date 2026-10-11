import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.models import Base, ContentEnrichment
from app.database.repository import Repository
from app.enrichment import (
    ContentEnrichmentResult,
    EnrichmentCategory,
    MistralEnrichmentProvider,
    OpenAIEnrichmentProvider,
    build_enrichment_input,
    normalize_mistral_enrichment_payload,
)


class TestEnrichment(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self.repo = Repository(session=self.session)
        self.item = self.repo.create_content_item(
            "Test Source", "web", "enrichment-test", "article",
            "A test title", "https://example.com/test", datetime(2026, 1, 1),
            description="A test description",
        )

    def tearDown(self):
        self.session.close()

    def result(self):
        return ContentEnrichmentResult(
            category=EnrichmentCategory.RESEARCH,
            topics=["machine learning"],
            entities=["OpenAI"],
            importance=0.8,
            novelty=0.7,
            technical_depth=0.6,
            impact=0.5,
            source_quality=0.9,
        )

    def test_schema_validation(self):
        self.assertEqual(self.result().category, EnrichmentCategory.RESEARCH)
        for field in ("importance", "novelty", "technical_depth", "impact", "source_quality"):
            with self.assertRaises(ValidationError):
                ContentEnrichmentResult(**{**self.result().model_dump(), field: -0.1})
            with self.assertRaises(ValidationError):
                ContentEnrichmentResult(**{**self.result().model_dump(), field: 1.1})
        with self.assertRaises(ValidationError):
            ContentEnrichmentResult(
                **{**self.result().model_dump(), "category": "not-a-category"}
            )

    def test_repository_create_read_and_upsert(self):
        created = self.repo.create_content_enrichment(
            self.item.id, self.result(), "test-model", "v1"
        )
        self.assertIsNotNone(created)
        self.assertEqual(self.repo.get_content_enrichment(self.item.id).category, "research")
        self.assertIsNone(
            self.repo.create_content_enrichment(self.item.id, self.result(), "test-model", "v1")
        )
        updated = self.repo.upsert_content_enrichment(
            self.item.id, self.result().model_copy(update={"impact": 1.0}), "test-model-2", "v2"
        )
        self.assertEqual(updated.impact, 1.0)
        self.assertEqual(self.session.query(ContentEnrichment).count(), 1)

    def test_provider_returns_structured_result_and_receives_content(self):
        response = Mock(output_parsed=self.result())
        client = Mock()
        client.responses.parse.return_value = response
        provider = OpenAIEnrichmentProvider(client=client)
        result = provider.enrich(self.item)
        self.assertEqual(result.category, EnrichmentCategory.RESEARCH)
        prompt_input = client.responses.parse.call_args.kwargs["input"]
        self.assertIn("A test title", prompt_input)
        self.assertIn("Test Source", prompt_input)

    def test_large_content_is_deterministically_truncated(self):
        self.item.raw_content = "x" * 20000
        first = build_enrichment_input(self.item, max_chars=100)
        second = build_enrichment_input(self.item, max_chars=100)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 100)

    def test_foreign_key_rejects_missing_item(self):
        self.assertIsNone(
            self.repo.create_content_enrichment("missing", self.result(), "model", "v1")
        )

    def test_mistral_payload_normalizes_observed_codestral_shape(self):
        normalized = normalize_mistral_enrichment_payload({
            "categories": ["AI", "Natural Language Processing"],
            "topics": ["language models"],
            "entities": ["Codestral"],
            "importance": 8,
            "novelty": 7,
            "technical_depth": 9,
            "impact": 7,
            "source_quality": 10,
        })
        result = ContentEnrichmentResult.model_validate(normalized)
        self.assertEqual(result.category, EnrichmentCategory.INDUSTRY)
        self.assertEqual(result.importance, 0.8)
        self.assertEqual(result.novelty, 0.7)
        self.assertEqual(result.technical_depth, 0.9)
        self.assertEqual(result.source_quality, 1.0)

    def test_mistral_payload_preserves_normalized_scores(self):
        normalized = normalize_mistral_enrichment_payload({
            "category": "research",
            "topics": [],
            "entities": [],
            "importance": 0.8,
            "novelty": 0.7,
            "technical_depth": 1.0,
            "impact": 0.0,
            "source_quality": 0.9,
        })
        self.assertEqual(normalized["importance"], 0.8)
        self.assertEqual(normalized["technical_depth"], 1.0)

    def test_mistral_payload_rejects_invalid_scores_and_categories(self):
        base = {
            "category": "research", "topics": [], "entities": [],
            "importance": 0.8, "novelty": 0.7, "technical_depth": 0.6,
            "impact": 0.5, "source_quality": 0.9,
        }
        for field, value in (("importance", -1), ("impact", 11), ("novelty", "high")):
            with self.assertRaises(ValueError):
                normalize_mistral_enrichment_payload({**base, field: value})
        with self.assertRaises(ValueError):
            normalize_mistral_enrichment_payload({**base, "category": "unrelated"})
        with self.assertRaises(ValueError):
            normalize_mistral_enrichment_payload({**base, "extra": True})

    def test_mistral_provider_normalizes_production_payload(self):
        client = Mock()
        client.model = "codestral-2508"
        client.complete_json.return_value = {
            "categories": ["AI", "Natural Language Processing"],
            "topics": ["language models"],
            "entities": ["Codestral"],
            "importance": 8,
            "novelty": 7,
            "technical_depth": 9,
            "impact": 7,
            "source_quality": 10,
        }
        provider = MistralEnrichmentProvider(client=client)
        result = provider.enrich(self.item)
        self.assertEqual(result.category, EnrichmentCategory.INDUSTRY)
        self.assertEqual(result.importance, 0.8)
        client.complete_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
