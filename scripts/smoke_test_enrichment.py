"""Run one non-persisting Mistral enrichment smoke test.

This script reads exactly one existing ContentItem, calls the existing
MistralEnrichmentProvider once, and never persists the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import MISTRAL_MODEL
from app.database.connection import get_session
from app.database.models import ContentEnrichment, ContentItem
from app.database.repository import Repository
from app.enrichment import MistralEnrichmentProvider


def main() -> int:
    session = get_session()
    repo = Repository(session=session)
    try:
        count_before = session.query(
            func.count(ContentEnrichment.id)
        ).scalar()
        content_item = session.query(ContentItem).order_by(
            ContentItem.published_at.desc(),
            ContentItem.id.asc(),
        ).first()

        if content_item is None:
            print("Enrichment smoke test failed: no ContentItems found.")
            return 1

        source_name = getattr(content_item.source, "name", "unknown")
        print(f"ContentItem title: {content_item.title}")
        print(f"ContentItem source: {source_name}")
        print(f"Mistral model: {MISTRAL_MODEL}")
        print(f"ContentEnrichment count before: {count_before}")

        try:
            result = MistralEnrichmentProvider().enrich(content_item)
        except Exception as exc:
            count_after = session.query(
                func.count(ContentEnrichment.id)
            ).scalar()
            print("Enrichment: FAILURE")
            print(f"Exception: {exc}")
            print(f"ContentEnrichment count after: {count_after}")
            if count_after != count_before:
                print("ERROR: ContentEnrichment count changed.")
            return 1

        count_after = session.query(
            func.count(ContentEnrichment.id)
        ).scalar()
        print("Enrichment: SUCCESS")
        print(f"Validated category: {result.category.value}")
        print(f"Topics: {result.topics}")
        print(f"Entities: {result.entities}")
        print(f"Importance: {result.importance}")
        print(f"Novelty: {result.novelty}")
        print(f"Technical depth: {result.technical_depth}")
        print(f"Impact: {result.impact}")
        print(f"Source quality: {result.source_quality}")
        print(f"ContentEnrichment count after: {count_after}")

        if count_after != count_before:
            print("ERROR: ContentEnrichment count changed.")
            return 1
        return 0
    finally:
        repo.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
