from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from time import monotonic
import logging
from .database.repository import Repository
from .normalizer import normalize
from .scrapers.base import registry
from .enrichment import EnrichmentProvider, MistralEnrichmentProvider
from .embeddings import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbeddingProvider,
    embedding_text_hash,
    prepare_embedding_text,
)
from .config import MISTRAL_API_KEY
from .story_clustering import cluster_content_item
from . import scrapers as _scrapers_pkg  # noqa: F401 — side-effect import to populate registry

logger = logging.getLogger(__name__)


@dataclass
class IngestionRunStats:
    sources_checked: int = 0
    successful_sources: int = 0
    items_fetched: int = 0
    new_items: int = 0
    duplicates_skipped: int = 0
    failed_items: int = 0
    failed_sources: int = 0
    duration_seconds: float = 0.0



def initialize_enrichment_provider(
    enrichment_provider: Optional[EnrichmentProvider] = None,
) -> Optional[EnrichmentProvider]:
    if enrichment_provider is not None:
        return enrichment_provider
    if not MISTRAL_API_KEY or not MISTRAL_API_KEY.strip():
        logger.warning(
            "Mistral API key not configured; AI enrichment disabled for this run. "
            "Local embeddings remain enabled."
        )
        return None
    try:
        return MistralEnrichmentProvider()
    except Exception as exc:
        logger.warning("AI enrichment disabled: provider initialization failed: %s", exc)
        return None


def enrich_content_item(repo: Repository, content_item, provider: EnrichmentProvider) -> bool:
    if repo.get_content_enrichment(content_item.id) is not None:
        return False
    try:
        result = provider.enrich(content_item)
        repo.upsert_content_enrichment(
            content_item.id, result, provider.model_name, provider.prompt_version
        )
        return True
    except Exception as exc:
        logger.error("[ENRICHMENT ERROR] %s: %s", content_item.external_id, exc, exc_info=True)
        return False


def embed_content_item(repo: Repository, content_item, provider: EmbeddingProvider) -> bool:
    text_hash = embedding_text_hash(prepare_embedding_text(content_item))
    existing = repo.get_content_embedding(content_item.id)
    if existing is not None and existing.text_hash == text_hash:
        return False
    try:
        result = provider.embed_batch([prepare_embedding_text(content_item)])[0]
        repo.upsert_content_embedding(
            content_item.id,
            result.embedding,
            provider.model_name,
            result.dimensions,
            text_hash,
        )
        return True
    except Exception as exc:
        logger.error("[EMBEDDING ERROR] %s: %s", content_item.external_id, exc, exc_info=True)
        return False
def _run_ingestion(
    hours: int = 24,
    enrichment_provider: Optional[EnrichmentProvider] = None,
    process_ai: bool = True,
) -> tuple[dict, IngestionRunStats]:
    repo = Repository()
    try:
        results: Dict[str, List] = {}
        stats = IngestionRunStats()
        started = monotonic()
        if process_ai:
            enrichment_provider = initialize_enrichment_provider(enrichment_provider)
        else:
            enrichment_provider = None
        embedding_provider = None
        if process_ai:
            try:
                embedding_provider = LocalSentenceTransformerEmbeddingProvider()
            except Exception as exc:
                logger.warning("Embeddings disabled: provider initialization failed: %s", exc)
                embedding_provider = None

        adapters = registry.get_all()
        stats.sources_checked = len(adapters)

        logger.info("\n--- Ingestion Summary ---")
        logger.info(f"{'Source':<22} {'Status':<10} Items")
        logger.info("-" * 44)

        for adapter in adapters:
            source_name = adapter.source_name
            source_type = adapter.source_type

            try:
                items = adapter.fetch(hours=hours)
                stats.items_fetched += len(items)
                normalized_items = [normalize(item) for item in items]
                unique_items = []
                seen_external_ids = set()
                for item in normalized_items:
                    external_id = item["external_id"]
                    if external_id in seen_external_ids:
                        continue
                    seen_external_ids.add(external_id)
                    unique_items.append(item)

                if unique_items:
                    new_external_ids = {
                        item["external_id"]
                        for item in unique_items
                        if repo.get_content_item_by_external_id(item["external_id"]) is None
                    }
                    inserted_count = repo.bulk_create_content_items(
                        source_name, source_type, unique_items
                    )
                    stats.new_items += inserted_count
                    stats.duplicates_skipped += len(normalized_items) - inserted_count
                    insertion_results_are_complete = (
                        inserted_count == len(new_external_ids)
                        and all(
                            repo.get_content_item_by_external_id(external_id) is not None
                            for external_id in new_external_ids
                        )
                    )
                    for item in unique_items:
                        external_id = item["external_id"]
                        content_item = repo.get_content_item_by_external_id(external_id)
                        if content_item is not None and (
                            external_id in new_external_ids
                            or content_item.story_content is None
                        ):
                            try:
                                cluster_content_item(repo, content_item)
                            except Exception as exc:
                                logger.error(
                                    "[STORY CLUSTERING ERROR] %s: %s",
                                    content_item.external_id,
                                    exc,
                                    exc_info=True,
                                )
                            if (
                                insertion_results_are_complete
                                and external_id in new_external_ids
                                and process_ai
                                and enrichment_provider is not None
                            ):
                                enrich_content_item(repo, content_item, enrichment_provider)
                            if (
                                insertion_results_are_complete
                                and external_id in new_external_ids
                                and process_ai
                                and embedding_provider is not None
                            ):
                                embed_content_item(repo, content_item, embedding_provider)

                key = source_name.lower().replace(" ", "_").replace("/", "_")
                results[key] = items
                stats.successful_sources += 1
                logger.info(f"{source_name:<22} {'success':<10} {len(items)}")

            except Exception as e:
                stats.failed_sources += 1
                stats.failed_items += 1
                logger.error(f"[INGESTION ERROR] {source_name}: {e}", exc_info=True)
                logger.info(f"{source_name:<22} {'failed':<10} 0")
                # Failure isolation: log and continue — other sources are unaffected
                continue

        logger.info("-" * 44)
        stats.duration_seconds = monotonic() - started
        return results, stats
    finally:
        repo.session.close()


def run_ingestion(hours: int = 24) -> IngestionRunStats:
    """Run adapter ingestion without adding enrichment or embedding orchestration."""
    _, stats = _run_ingestion(hours=hours, process_ai=False)
    return stats


def run_scrapers(
    hours: int = 24, enrichment_provider: Optional[EnrichmentProvider] = None
) -> dict:
    """Legacy one-shot ingestion API, preserving its existing return shape."""
    results, _ = _run_ingestion(
        hours=hours,
        enrichment_provider=enrichment_provider,
        process_ai=True,
    )
    return results


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(message)s")
    result = run_scrapers(hours=24)
    for source_key, items in result.items():
        print(f"{source_key}: {len(items)}")
