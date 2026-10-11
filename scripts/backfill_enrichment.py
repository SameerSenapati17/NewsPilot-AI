"""Safely backfill missing ContentEnrichment records.

This script only reads existing ContentItems and writes new enrichment rows.
It never runs source adapters, changes ContentItems, or invokes embeddings.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import MISTRAL_API_KEY, MISTRAL_MODEL
from app.database.models import ContentItem
from app.database.repository import Repository
from app.enrichment import EnrichmentProvider, MistralEnrichmentProvider
from app.runner import enrich_content_item

logger = logging.getLogger(__name__)


@dataclass
class BackfillSummary:
    scanned: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    calls_attempted: int = 0


def _items(repo: Repository):
    return repo.session.query(ContentItem).order_by(
        ContentItem.published_at.desc(),
        ContentItem.id.asc(),
    ).all()


def _item_label(item: ContentItem) -> str:
    source = getattr(getattr(item, "source", None), "name", "unknown source")
    return f"{item.title} [{item.id}] ({source})"


def run_backfill(
    repo: Repository,
    *,
    dry_run: bool = False,
    provider: Optional[EnrichmentProvider] = None,
) -> BackfillSummary:
    items = _items(repo)
    summary = BackfillSummary(scanned=len(items))
    pending = [
        item for item in items
        if repo.get_content_enrichment(item.id) is None
    ]
    summary.skipped = len(items) - len(pending)

    print(f"ContentItems scanned: {summary.scanned}")
    print(f"Already enriched: {summary.skipped}")
    print(f"Pending enrichment: {len(pending)}")
    print(f"Mistral calls planned: {len(pending)}")

    if dry_run:
        return summary

    if not MISTRAL_API_KEY or not MISTRAL_API_KEY.strip():
        raise RuntimeError(
            "MISTRAL_API_KEY is not configured; refusing to start enrichment backfill."
        )

    active_provider = provider or MistralEnrichmentProvider()
    for index, item in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] Enriching: {_item_label(item)}")
        summary.calls_attempted += 1
        try:
            if enrich_content_item(repo, item, active_provider):
                summary.enriched += 1
            else:
                summary.failed += 1
                logger.error("Enrichment failed for %s", _item_label(item))
        except Exception as exc:
            summary.failed += 1
            logger.error(
                "Enrichment failed for %s: %s",
                _item_label(item),
                exc,
            )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing AI enrichment for existing ContentItems."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect pending items without creating a provider or writing data.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    args = _parse_args()
    started = time.monotonic()
    summary: Optional[BackfillSummary] = None
    try:
        repo = Repository()
        summary = run_backfill(repo, dry_run=args.dry_run)
        if args.dry_run:
            return 0
        print(f"Enriched successfully: {summary.enriched}")
        print(f"Already enriched / skipped: {summary.skipped}")
        print(f"Failed: {summary.failed}")
        print(f"Mistral calls attempted: {summary.calls_attempted}")
        print(f"Mistral model: {MISTRAL_MODEL}")
        print(f"Elapsed time: {time.monotonic() - started:.2f}s")
        return 0 if summary.failed == 0 else 1
    except Exception as exc:
        print(f"Backfill aborted: {exc}", file=sys.stderr)
        if summary is not None:
            print(f"Mistral model: {MISTRAL_MODEL}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
