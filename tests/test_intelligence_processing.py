import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.models import Base
from app.database.repository import Repository
from app.enrichment import ContentEnrichmentResult, EnrichmentCategory
from app.intelligence_processing import (
    _create_embedding,
    _create_enrichment,
    process_pending_intelligence,
)


class TestIntelligenceProcessing(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.repo = Repository(session=self.session)
        self.items = [
            self.repo.create_content_item(
                "Test Source",
                "rss",
                f"item-{index}",
                "article",
                f"Title {index}",
                f"https://example.com/{index}",
                datetime(2026, 1, index + 1),
                description=f"Description {index}",
            )
            for index in range(3)
        ]

    def tearDown(self):
        self.session.close()

    def _enrichment_provider(self, side_effect=None):
        provider = Mock()
        provider.model_name = "test-mistral"
        provider.prompt_version = "test-v1"
        provider.enrich.side_effect = side_effect
        if side_effect is None:
            provider.enrich.side_effect = lambda item: ContentEnrichmentResult(
                category=EnrichmentCategory.RESEARCH,
                topics=[item.title],
                entities=[],
                importance=0.5,
                novelty=0.5,
                technical_depth=0.5,
                impact=0.5,
                source_quality=1.0,
            )
        return provider

    def _embedding_provider(self, side_effect=None):
        provider = Mock()
        provider.model_name = "test-embedding"
        result = Mock(embedding=[0.1] * 384, dimensions=384)
        provider.embed_batch.side_effect = side_effect or (
            lambda texts: [result for _ in texts]
        )
        return provider

    def test_successful_processing_and_rerun_is_idempotent(self):
        enrichment = self._enrichment_provider()
        embedding = self._embedding_provider()
        first = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        second = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        self.assertEqual(first.enrichments_created, 3)
        self.assertEqual(first.embeddings_created, 3)
        self.assertEqual(second.enrichments_created, 0)
        self.assertEqual(second.embeddings_created, 0)
        self.assertEqual(enrichment.enrich.call_count, 3)
        self.assertEqual(embedding.embed_batch.call_count, 3)

    def test_existing_records_are_preserved(self):
        enrichment = self._enrichment_provider()
        embedding = self._embedding_provider()
        process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        original = self.repo.get_content_enrichment(self.items[0].id).topics
        second = process_pending_intelligence(
            self.repo,
            enrichment_provider=self._enrichment_provider(),
            embedding_provider=self._embedding_provider(),
        )
        self.assertEqual(second.enrichments_created, 0)
        self.assertEqual(self.repo.get_content_enrichment(self.items[0].id).topics, original)

    def test_enrichment_failure_does_not_block_embedding(self):
        enrichment = self._enrichment_provider(
            side_effect=RuntimeError("mistral failure")
        )
        embedding = self._embedding_provider()
        summary = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        self.assertEqual(summary.enrichment_failures, 3)
        self.assertEqual(summary.embeddings_created, 3)

    def test_embedding_failure_does_not_block_enrichment(self):
        enrichment = self._enrichment_provider()
        embedding = self._embedding_provider(
            side_effect=RuntimeError("embedding failure")
        )
        summary = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        self.assertEqual(summary.enrichments_created, 3)
        self.assertEqual(summary.embedding_failures, 3)

    def test_partial_failure_retries_only_missing_operation(self):
        calls = {"count": 0}

        def fail_first(_texts):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("one failure")
            return [Mock(embedding=[0.1] * 384, dimensions=384)]

        enrichment = self._enrichment_provider()
        embedding = self._embedding_provider(side_effect=fail_first)
        first = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        second = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
        )
        self.assertEqual(first.embeddings_created, 2)
        self.assertEqual(first.embedding_failures, 1)
        self.assertEqual(second.embeddings_created, 1)
        self.assertEqual(enrichment.enrich.call_count, 3)

    def test_dry_run_does_not_call_providers_or_write(self):
        enrichment = self._enrichment_provider()
        embedding = self._embedding_provider()
        summary = process_pending_intelligence(
            self.repo,
            enrichment_provider=enrichment,
            embedding_provider=embedding,
            dry_run=True,
        )
        self.assertEqual(summary.items_examined, 3)
        self.assertEqual(summary.enrichments_created, 0)
        self.assertEqual(summary.embeddings_created, 0)
        enrichment.enrich.assert_not_called()
        embedding.embed_batch.assert_not_called()
        self.assertIsNone(self.repo.get_content_enrichment(self.items[0].id))
        self.assertIsNone(self.repo.get_content_embedding(self.items[0].id))

    def test_dry_run_reports_pending_operations(self):
        summary = process_pending_intelligence(
            self.repo,
            enrichment_provider=self._enrichment_provider(),
            embedding_provider=self._embedding_provider(),
            dry_run=True,
        )
        self.assertEqual(summary.enrichments_pending, 3)
        self.assertEqual(summary.embeddings_pending, 3)
        self.assertEqual(summary.items_skipped, 6)

    def test_enrichment_conflict_preserves_existing_record(self):
        existing = self.repo.create_content_enrichment(
            self.items[0].id,
            self._enrichment_provider().enrich(self.items[0]),
            "test-mistral",
            "test-v1",
        )
        self.assertIsNotNone(existing)
        provider = self._enrichment_provider()
        conflict_repo = Mock(wraps=self.repo)
        conflict_repo.get_content_enrichment.side_effect = [
            None,
            None,
            self.repo.get_content_enrichment(self.items[0].id),
        ]
        conflict_repo.create_content_enrichment.side_effect = IntegrityError(
            "insert",
            {},
            Exception("dup"),
        )

        self.assertFalse(_create_enrichment(conflict_repo, self.items[0], provider))
        preserved = self.repo.get_content_enrichment(self.items[0].id)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved.model_name, "test-mistral")

    def test_embedding_conflict_preserves_existing_record(self):
        existing = self.repo.create_content_embedding(
            self.items[0].id,
            [0.2] * 384,
            "test-embedding",
            384,
            "original-hash",
        )
        self.assertIsNotNone(existing)
        provider = self._embedding_provider()
        conflict_repo = Mock(wraps=self.repo)
        conflict_repo.get_content_embedding.side_effect = [
            None,
            None,
            self.repo.get_content_embedding(self.items[0].id),
        ]
        conflict_repo.create_content_embedding.side_effect = IntegrityError(
            "insert",
            {},
            Exception("dup"),
        )

        self.assertFalse(_create_embedding(conflict_repo, self.items[0], provider))
        preserved = self.repo.get_content_embedding(self.items[0].id)
        self.assertIsNotNone(preserved)
        self.assertEqual(preserved.embedding_model, "test-embedding")

    def test_cli_closes_session_on_success_and_failure(self):
        import scripts.process_pending_intelligence as script

        success_repo = Mock()
        success_repo.session = Mock()
        success_summary = SimpleNamespace(
            items_examined=1,
            enrichment_present=0,
            enrichments_pending=1,
            enrichments_created=1,
            enrichment_failures=0,
            embeddings_present=0,
            embeddings_pending=1,
            embeddings_created=1,
            embedding_failures=0,
            items_skipped=2,
            skip_reasons={},
        )
        with patch.object(script, "Repository", return_value=success_repo), patch.object(
            script, "_args", return_value=SimpleNamespace(dry_run=False)
        ), patch.object(
            script, "initialize_enrichment_provider", return_value=Mock()
        ), patch.object(
            script, "LocalSentenceTransformerEmbeddingProvider", return_value=Mock()
        ), patch.object(
            script, "process_pending_intelligence", return_value=success_summary
        ), patch("builtins.print"):
            self.assertEqual(script.main(), 0)
        success_repo.session.close.assert_called_once()

        fail_repo = Mock()
        fail_repo.session = Mock()
        failure_summary = SimpleNamespace(
            items_examined=1,
            enrichment_present=0,
            enrichments_pending=1,
            enrichments_created=0,
            enrichment_failures=1,
            embeddings_present=0,
            embeddings_pending=1,
            embeddings_created=0,
            embedding_failures=0,
            items_skipped=2,
            skip_reasons={"enrichment provider unavailable": 1},
        )
        with patch.object(script, "Repository", return_value=fail_repo), patch.object(
            script, "_args", return_value=SimpleNamespace(dry_run=False)
        ), patch.object(
            script, "initialize_enrichment_provider", return_value=Mock()
        ), patch.object(
            script, "LocalSentenceTransformerEmbeddingProvider", return_value=Mock()
        ), patch.object(
            script, "process_pending_intelligence", return_value=failure_summary
        ), patch("builtins.print"):
            self.assertEqual(script.main(), 1)
        fail_repo.session.close.assert_called_once()

    def test_cli_closes_session_on_exception(self):
        import scripts.process_pending_intelligence as script

        error_repo = Mock()
        error_repo.session = Mock()
        with patch.object(script, "Repository", return_value=error_repo), patch.object(
            script, "_args", return_value=SimpleNamespace(dry_run=False)
        ), patch.object(
            script, "initialize_enrichment_provider", return_value=Mock()
        ), patch.object(
            script, "LocalSentenceTransformerEmbeddingProvider", return_value=Mock()
        ), patch.object(
            script, "process_pending_intelligence", side_effect=RuntimeError("boom")
        ), patch("builtins.print"):
            with self.assertRaises(RuntimeError):
                script.main()
        error_repo.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
