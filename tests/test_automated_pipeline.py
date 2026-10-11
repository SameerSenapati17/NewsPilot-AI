import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automated_pipeline import run_automated_pipeline
from app.runner import IngestionRunStats


class TestAutomatedPipeline(unittest.TestCase):
    def setUp(self):
        self.stats = IngestionRunStats(sources_checked=1)
        self.repo = Mock()
        self.enrichment_provider = Mock()
        self.embedding_provider = Mock()

    # ------------------------------------------------------------------
    # Existing tests (preserved verbatim)
    # ------------------------------------------------------------------

    def test_processing_success_closes_repository_session(self):
        summary = Mock(
            items_examined=2,
            enrichments_created=2,
            enrichment_failures=0,
            embeddings_created=2,
            embedding_failures=0,
            items_skipped=0,
            skip_reasons={},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            return_value=self.embedding_provider,
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ) as process:
            result = run_automated_pipeline()

        self.assertIs(result, self.stats)
        process.assert_called_once_with(
            self.repo,
            enrichment_provider=self.enrichment_provider,
            embedding_provider=self.embedding_provider,
        )
        self.repo.session.close.assert_called_once_with()

    def test_processing_failure_is_logged_and_closes_repository_session(self):
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            return_value=self.embedding_provider,
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            side_effect=RuntimeError("processing failed"),
        ), self.assertLogs("app.automated_pipeline", level="ERROR") as logs:
            result = run_automated_pipeline()

        self.assertIs(result, self.stats)
        self.assertTrue(
            any("Intelligence processing stage failed" in record.message for record in logs.records)
        )
        self.repo.session.close.assert_called_once_with()

    # ------------------------------------------------------------------
    # Ingestion invocation
    # ------------------------------------------------------------------

    def test_run_ingestion_is_called_once(self):
        """run_ingestion() must be called exactly once per pipeline run."""
        summary = Mock(
            items_examined=0, enrichments_created=0, enrichment_failures=0,
            embeddings_created=0, embedding_failures=0, items_skipped=0,
            skip_reasons={},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ) as mock_ingest, patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            return_value=self.embedding_provider,
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ):
            run_automated_pipeline()

        mock_ingest.assert_called_once_with()

    def test_returns_ingestion_stats_not_summary(self):
        """The return value must be the IngestionRunStats object, not the intelligence summary."""
        specific_stats = IngestionRunStats(sources_checked=7, new_items=42)
        summary = Mock(
            items_examined=10, enrichments_created=5, enrichment_failures=0,
            embeddings_created=5, embedding_failures=0, items_skipped=0,
            skip_reasons={},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=specific_stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            return_value=self.embedding_provider,
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ):
            result = run_automated_pipeline()

        self.assertIs(result, specific_stats)
        self.assertEqual(result.sources_checked, 7)
        self.assertEqual(result.new_items, 42)

    # ------------------------------------------------------------------
    # Embedding provider initialisation failure
    # ------------------------------------------------------------------

    def test_embedding_init_failure_is_logged_and_provider_is_none(self):
        """
        When LocalSentenceTransformerEmbeddingProvider raises, the pipeline
        must log the failure, pass embedding_provider=None to
        process_pending_intelligence, and return the ingestion stats.
        """
        summary = Mock(
            items_examined=1, enrichments_created=0, enrichment_failures=0,
            embeddings_created=0, embedding_failures=0, items_skipped=1,
            skip_reasons={"embedding provider unavailable": 1},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            side_effect=OSError("model weights not found"),
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ) as mock_process, self.assertLogs(
            "app.automated_pipeline", level="ERROR"
        ) as log_ctx:
            result = run_automated_pipeline()

        # Still returns ingestion stats.
        self.assertIs(result, self.stats)

        # process_pending_intelligence must be called with embedding_provider=None.
        call_kwargs = mock_process.call_args.kwargs
        self.assertIsNone(call_kwargs["embedding_provider"])

        # The failure must be logged.
        self.assertTrue(
            any("Embedding provider initialization failed" in msg for msg in log_ctx.output),
            msg="Expected embedding init failure message; got: {}".format(log_ctx.output),
        )

    def test_embedding_init_failure_does_not_raise(self):
        """An embedding provider init failure must not propagate to the caller."""
        summary = Mock(
            items_examined=0, enrichments_created=0, enrichment_failures=0,
            embeddings_created=0, embedding_failures=0, items_skipped=0,
            skip_reasons={},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            side_effect=RuntimeError("no GPU"),
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ), self.assertLogs("app.automated_pipeline", level="ERROR"):
            # Must not raise.
            run_automated_pipeline()

    def test_embedding_init_failure_still_closes_session(self):
        """Session must close even when embedding provider init raises."""
        summary = Mock(
            items_examined=0, enrichments_created=0, enrichment_failures=0,
            embeddings_created=0, embedding_failures=0, items_skipped=0,
            skip_reasons={},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            side_effect=RuntimeError("no GPU"),
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ), self.assertLogs("app.automated_pipeline", level="ERROR"):
            run_automated_pipeline()

        self.repo.session.close.assert_called_once_with()

    # ------------------------------------------------------------------
    # Partial intelligence failures produce a warning
    # ------------------------------------------------------------------

    def test_partial_intelligence_failures_produce_warning_log(self):
        """
        A summary with enrichment/embedding failures or non-empty skip_reasons
        must produce a WARNING-level log entry about pending work.
        """
        summary = Mock(
            items_examined=3,
            enrichments_created=1,
            enrichment_failures=1,
            embeddings_created=1,
            embedding_failures=1,
            items_skipped=1,
            skip_reasons={"enrichment provider unavailable": 1},
        )
        with patch(
            "app.automated_pipeline.run_ingestion", return_value=self.stats
        ), patch(
            "app.automated_pipeline.Repository", return_value=self.repo
        ), patch(
            "app.automated_pipeline.initialize_enrichment_provider",
            return_value=self.enrichment_provider,
        ), patch(
            "app.automated_pipeline.LocalSentenceTransformerEmbeddingProvider",
            return_value=self.embedding_provider,
        ), patch(
            "app.automated_pipeline.process_pending_intelligence",
            return_value=summary,
        ), self.assertLogs(
            "app.automated_pipeline", level="WARNING"
        ) as log_ctx:
            run_automated_pipeline()

        self.assertTrue(
            any("Some intelligence work remains pending" in msg for msg in log_ctx.output),
            msg="Expected pending-work warning; got: {}".format(log_ctx.output),
        )


if __name__ == "__main__":
    unittest.main()
