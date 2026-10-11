"""Run scheduled news ingestion followed by pending AI processing."""

import logging

from .database.repository import Repository
from .embeddings import LocalSentenceTransformerEmbeddingProvider
from .intelligence_processing import process_pending_intelligence
from .runner import IngestionRunStats, initialize_enrichment_provider, run_ingestion

logger = logging.getLogger(__name__)


def run_automated_pipeline() -> IngestionRunStats:
    """Ingest news, then process missing enrichment and embeddings."""
    stats = run_ingestion()
    repo = Repository()

    try:
        enrichment_provider = initialize_enrichment_provider()

        try:
            embedding_provider = LocalSentenceTransformerEmbeddingProvider()
        except Exception:
            logger.exception(
                "Embedding provider initialization failed; "
                "pending embeddings will be retried on a later run."
            )
            embedding_provider = None

        try:
            summary = process_pending_intelligence(
                repo,
                enrichment_provider=enrichment_provider,
                embedding_provider=embedding_provider,
            )
        except Exception:
            logger.exception(
                "Intelligence processing stage failed; "
                "pending work can be retried on a later run."
            )
            return stats

        logger.info(
            "Intelligence processing: examined=%s, "
            "enrichments_created=%s, enrichment_failures=%s, "
            "embeddings_created=%s, embedding_failures=%s, skipped=%s",
            summary.items_examined,
            summary.enrichments_created,
            summary.enrichment_failures,
            summary.embeddings_created,
            summary.embedding_failures,
            summary.items_skipped,
        )

        if (
            summary.enrichment_failures
            or summary.embedding_failures
            or summary.skip_reasons
        ):
            logger.warning(
                "Some intelligence work remains pending: %s",
                summary.skip_reasons,
            )

        return stats
    finally:
        repo.session.close()
