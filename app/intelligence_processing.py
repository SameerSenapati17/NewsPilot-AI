"""Standalone processing for missing ContentItem intelligence records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

from sqlalchemy.exc import IntegrityError

from .database.models import ContentItem
from .database.repository import Repository
from .embeddings import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbeddingProvider,
    embedding_text_hash,
    prepare_embedding_text,
)
from .enrichment import EnrichmentProvider, MistralEnrichmentProvider
from .runner import initialize_enrichment_provider

logger = logging.getLogger(__name__)


@dataclass
class IntelligenceProcessingSummary:
    items_examined: int = 0
    enrichment_present: int = 0
    enrichments_pending: int = 0
    enrichments_created: int = 0
    enrichment_failures: int = 0
    embeddings_present: int = 0
    embeddings_pending: int = 0
    embeddings_created: int = 0
    embedding_failures: int = 0
    items_skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.items_skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


def _items(repo: Repository):
    return repo.session.query(ContentItem).order_by(
        ContentItem.published_at.desc(),
        ContentItem.id.asc(),
    ).all()


def _label(item: ContentItem) -> str:
    return f"{item.title} [{item.id}]"


def _create_enrichment(
    repo: Repository,
    item: ContentItem,
    provider: EnrichmentProvider,
) -> bool:
    if repo.get_content_enrichment(item.id) is not None:
        return False
    result = provider.enrich(item)
    if repo.get_content_enrichment(item.id) is not None:
        return False
    try:
        record = repo.create_content_enrichment(
            item.id,
            result,
            provider.model_name,
            provider.prompt_version,
        )
    except IntegrityError:
        repo.session.rollback()
        if repo.get_content_enrichment(item.id) is not None:
            return False
        raise
    if record is None:
        return False
    return True


def _create_embedding(
    repo: Repository,
    item: ContentItem,
    provider: EmbeddingProvider,
) -> bool:
    if repo.get_content_embedding(item.id) is not None:
        return False
    text = prepare_embedding_text(item)
    result = provider.embed_batch([text])[0]
    if repo.get_content_embedding(item.id) is not None:
        return False
    try:
        record = repo.create_content_embedding(
            item.id,
            result.embedding,
            provider.model_name,
            result.dimensions,
            embedding_text_hash(text),
        )
    except IntegrityError:
        repo.session.rollback()
        if repo.get_content_embedding(item.id) is not None:
            return False
        raise
    if record is None:
        return False
    return True


def process_pending_intelligence(
    repo: Repository,
    *,
    enrichment_provider: Optional[EnrichmentProvider] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
    dry_run: bool = False,
) -> IntelligenceProcessingSummary:
    items = _items(repo)
    summary = IntelligenceProcessingSummary(items_examined=len(items))
    if dry_run:
        for item in items:
            has_enrichment = repo.get_content_enrichment(item.id) is not None
            has_embedding = repo.get_content_embedding(item.id) is not None
            if has_enrichment:
                summary.enrichment_present += 1
            else:
                summary.enrichments_pending += 1
                summary.skip("enrichment pending")
            if has_embedding:
                summary.embeddings_present += 1
            else:
                summary.embeddings_pending += 1
                summary.skip("embedding pending")
        return summary

    for item in items:
        has_enrichment = repo.get_content_enrichment(item.id) is not None
        has_embedding = repo.get_content_embedding(item.id) is not None
        if has_enrichment:
            summary.enrichment_present += 1
        if has_embedding:
            summary.embeddings_present += 1

        if not has_enrichment:
            if enrichment_provider is None:
                summary.skip("enrichment provider unavailable")
            else:
                try:
                    if _create_enrichment(repo, item, enrichment_provider):
                        summary.enrichments_created += 1
                    else:
                        summary.enrichment_present += 1
                except Exception:
                    summary.enrichment_failures += 1
                    logger.exception("Enrichment failed for %s", _label(item))

        if not has_embedding:
            if embedding_provider is None:
                summary.skip("embedding provider unavailable")
            else:
                try:
                    if _create_embedding(repo, item, embedding_provider):
                        summary.embeddings_created += 1
                    else:
                        summary.embeddings_present += 1
                except Exception:
                    summary.embedding_failures += 1
                    logger.exception("Embedding failed for %s", _label(item))

    return summary


def create_default_providers() -> tuple[
    Optional[EnrichmentProvider], EmbeddingProvider
]:
    return (
        initialize_enrichment_provider(),
        LocalSentenceTransformerEmbeddingProvider(),
    )
