import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runner import (
    _run_ingestion,
    embed_content_item,
    enrich_content_item,
    initialize_enrichment_provider,
)


class TestRunnerProviderDegradation(unittest.TestCase):
    def test_missing_mistral_key_disables_enrichment_once(self):
        with patch("app.runner.MISTRAL_API_KEY", ""), patch(
            "app.runner.MistralEnrichmentProvider"
        ) as provider_class, self.assertLogs("app.runner", level="WARNING") as logs:
            provider = initialize_enrichment_provider()

        self.assertIsNone(provider)
        provider_class.assert_not_called()
        self.assertEqual(len(logs.records), 1)
        self.assertIn("AI enrichment disabled for this run", logs.records[0].message)
        self.assertIn("Local embeddings remain enabled", logs.records[0].message)

    def test_configured_mistral_uses_existing_provider_path(self):
        provider = Mock()
        with patch("app.runner.MISTRAL_API_KEY", "configured"), patch(
            "app.runner.MistralEnrichmentProvider", return_value=provider
        ) as provider_class:
            result = initialize_enrichment_provider()

        self.assertIs(result, provider)
        provider_class.assert_called_once_with()

    def test_embedding_processing_is_unaffected(self):
        repo = Mock()
        repo.get_content_embedding.return_value = None
        item = Mock(
            id="item-1",
            external_id="external-1",
            title="Title",
            source=Mock(name="Source"),
            content_type="article",
            published_at=datetime(2026, 1, 1),
            raw_content="Body",
            transcript=None,
            description="Description",
        )
        provider = Mock()
        provider.model_name = "local-model"
        provider.embed_batch.return_value = [
            Mock(embedding=[0.1, 0.2], dimensions=2)
        ]

        self.assertTrue(embed_content_item(repo, item, provider))
        provider.embed_batch.assert_called_once()
        repo.upsert_content_embedding.assert_called_once()

    def test_configured_enrichment_follows_existing_path(self):
        repo = Mock()
        repo.get_content_enrichment.return_value = None
        item = Mock(id="item-1", external_id="external-1")
        provider = Mock()
        provider.model_name = "codestral-2508"
        provider.prompt_version = "v1"
        provider.enrich.return_value = "result"

        self.assertTrue(enrich_content_item(repo, item, provider))
        provider.enrich.assert_called_once_with(item)
        repo.upsert_content_enrichment.assert_called_once_with(
            "item-1", "result", "codestral-2508", "v1"
        )

    def test_ingestion_closes_session_after_success(self):
        repo = Mock()
        repo.session = Mock()
        adapter = Mock(source_name="Source", source_type="rss")
        adapter.fetch.return_value = []

        with patch("app.runner.Repository", return_value=repo), patch(
            "app.runner.registry.get_all", return_value=[adapter]
        ):
            _, stats = _run_ingestion(process_ai=False)

        self.assertEqual(stats.successful_sources, 1)
        repo.session.close.assert_called_once_with()

    def test_ingestion_closes_session_after_unexpected_exception(self):
        repo = Mock()
        repo.session = Mock()

        with patch("app.runner.Repository", return_value=repo), patch(
            "app.runner.registry.get_all", side_effect=RuntimeError("registry failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "registry failure"):
                _run_ingestion(process_ai=False)

        repo.session.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
