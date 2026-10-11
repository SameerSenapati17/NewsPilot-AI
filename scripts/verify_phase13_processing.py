"""Read-only verification of Phase 13 processing state."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import get_session
from app.database.models import (
    ContentEmbedding,
    ContentEnrichment,
    ContentItem,
    Story,
    StoryContent,
)


def main() -> int:
    session = get_session()
    try:
        content_ids = {row[0] for row in session.query(ContentItem.id).all()}
        enrichment_ids = {
            row[0] for row in session.query(ContentEnrichment.content_item_id).all()
        }
        embedding_ids = {
            row[0] for row in session.query(ContentEmbedding.content_item_id).all()
        }
        story_ids = {
            row[0] for row in session.query(StoryContent.content_item_id).all()
        }
        embedding_summary = session.query(
            ContentEmbedding.dimensions,
            ContentEmbedding.embedding_model,
            func.count(ContentEmbedding.id),
        ).group_by(
            ContentEmbedding.dimensions,
            ContentEmbedding.embedding_model,
        ).all()
        duplicate_external_ids = [
            value for value, count in session.query(
                ContentItem.external_id,
                func.count(ContentItem.id),
            ).group_by(ContentItem.external_id).all()
            if count > 1
        ]
        duplicate_story_content = [
            value for value, count in session.query(
                StoryContent.content_item_id,
                func.count(StoryContent.id),
            ).group_by(StoryContent.content_item_id).all()
            if count > 1
        ]

        print("Phase 13 processing verification (read-only)")
        print(f"ContentItems: {len(content_ids)}")
        print(f"Stories: {session.query(func.count(Story.id)).scalar()}")
        print(f"StoryContent: {session.query(func.count(StoryContent.id)).scalar()}")
        print(f"ContentEnrichment: {session.query(func.count(ContentEnrichment.id)).scalar()}")
        print(f"ContentEmbedding: {session.query(func.count(ContentEmbedding.id)).scalar()}")
        print(f"Missing StoryContent: {len(content_ids - story_ids)}")
        print(f"Missing enrichment: {len(content_ids - enrichment_ids)}")
        print(f"Missing embeddings: {len(content_ids - embedding_ids)}")
        print(f"Duplicate external IDs: {len(duplicate_external_ids)}")
        print(f"Duplicate StoryContent associations: {len(duplicate_story_content)}")
        print("Embedding dimensions/models:")
        for dimensions, model, count in embedding_summary:
            print(f"  dimensions={dimensions} model={model} count={count}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
