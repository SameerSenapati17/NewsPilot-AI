from typing import List, Dict, Any
import logging
from .database.repository import Repository
from .normalizer import normalize
from .scrapers.base import registry
from . import scrapers as _scrapers_pkg  # noqa: F401 — side-effect import to populate registry

logger = logging.getLogger(__name__)


def run_scrapers(hours: int = 24) -> dict:
    repo = Repository()
    results: Dict[str, List] = {}

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
                repo.bulk_create_content_items(source_name, source_type, normalized_items)

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

