from typing import List, Dict, Any, Optional
import logging
from .database.repository import Repository
from .normalizer import normalize
from .scrapers.base import registry
from .enrichment import EnrichmentProvider, OpenAIEnrichmentProvider
from . import scrapers as _scrapers_pkg  # noqa: F401 — side-effect import to populate registry

logger = logging.getLogger(__name__)


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


def run_scrapers(
    hours: int = 24, enrichment_provider: Optional[EnrichmentProvider] = None
) -> dict:
    repo = Repository()
    results: Dict[str, List] = {}
    if enrichment_provider is None:
        try:
            enrichment_provider = OpenAIEnrichmentProvider()
        except Exception as exc:
            logger.warning("AI enrichment disabled: provider initialization failed: %s", exc)
            enrichment_provider = None

    adapters = registry.get_all()

    logger.info("\n--- Ingestion Summary ---")
    logger.info(f"{'Source':<22} {'Status':<10} Items")
    logger.info("-" * 44)

    for adapter in adapters:
        source_name = adapter.source_name
        source_type = adapter.source_type

        try:
            items = adapter.fetch(hours=hours)
            normalized_items = [normalize(item) for item in items]

            if normalized_items:
                new_external_ids = [
                    item["external_id"]
                    for item in normalized_items
                    if repo.get_content_item_by_external_id(item["external_id"]) is None
                ]
                repo.bulk_create_content_items(source_name, source_type, normalized_items)
                if enrichment_provider is not None:
                    for external_id in new_external_ids:
                        content_item = repo.get_content_item_by_external_id(external_id)
                        if content_item is not None:
                            enrich_content_item(repo, content_item, enrichment_provider)

            key = source_name.lower().replace(" ", "_").replace("/", "_")
            results[key] = items
            logger.info(f"{source_name:<22} {'success':<10} {len(items)}")

        except Exception as e:
            logger.error(f"[INGESTION ERROR] {source_name}: {e}", exc_info=True)
            logger.info(f"{source_name:<22} {'failed':<10} 0")
            # Failure isolation: log and continue — other sources are unaffected
            continue

    logger.info("-" * 44)
    return results


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(message)s")
    result = run_scrapers(hours=24)
    for source_key, items in result.items():
        print(f"{source_key}: {len(items)}")
