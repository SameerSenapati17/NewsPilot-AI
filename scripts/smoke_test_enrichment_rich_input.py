"""Run one non-persisting enrichment smoke test using a rich arXiv item."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import MISTRAL_MODEL
from app.database.connection import get_session
from app.database.models import ContentEnrichment, ContentItem, Source
from app.database.repository import Repository
from app.enrichment import MistralEnrichmentProvider


def _description_length(item: ContentItem) -> int:
    return len(item.description.strip()) if item.description else 0


def _select_rich_arxiv_item(items):
    eligible = [
        item for item in items
        if "arxiv" in item.source.name.lower()
        and _description_length(item) > 0
    ]
    return min(
        eligible,
        key=lambda item: (-item.published_at.timestamp(), item.id),
        default=None,
    )


def main() -> int:
    session = get_session()
    repo = Repository(session=session)
    try:
        count_before = session.query(
            func.count(ContentEnrichment.id)
        ).scalar()
        arxiv_items = session.query(ContentItem).join(Source).filter(
            Source.name.ilike("%arxiv%"),
            func.length(func.trim(ContentItem.description)) > 0,
        ).all()
        content_item = _select_rich_arxiv_item(arxiv_items)
        if content_item is None:
            print("Enrichment smoke test failed: no rich arXiv ContentItem found.")
            return 1

        print(f"ContentItem title: {content_item.title}")
        print(f"ContentItem source: {content_item.source.name}")
        print(f"Description length: {_description_length(content_item)}")
        print(f"Mistral model: {MISTRAL_MODEL}")
        print(f"ContentEnrichment count before: {count_before}")

        try:
            result = MistralEnrichmentProvider().enrich(content_item)
        except Exception as exc:
            print("Enrichment: FAILURE")
            print(f"Exception: {exc}")
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
