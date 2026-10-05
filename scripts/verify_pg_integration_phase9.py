"""Safe PostgreSQL verification for deterministic Phase 9 trend detection."""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_engine
from app.database.models import (
    ContentEmbedding,
    ContentEnrichment,
    ContentItem,
    Source,
    Story,
    StoryContent,
)
from app.database.repository import Repository
from app.trends import TrendDetector, TrendConfig


PREFIX = f"phase9-verification-{uuid.uuid4().hex}-"
END = datetime(2026, 1, 15, tzinfo=timezone.utc)


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    engine = get_engine()
    session = Repository().session
    repository = Repository(session=session)
    item_ids, story_ids = [], []
    source_ids = []
    try:
        tables = set(inspect(engine).get_table_names())
        check(
            {"content_items", "content_enrichments", "stories", "story_content"}
            .issubset(tables),
            "required tables exist",
        )
        source_a = repository._get_or_create_source(PREFIX + "source-a", "phase9")
        source_b = repository._get_or_create_source(PREFIX + "source-b", "phase9")
        source_ids = [source_a.id, source_b.id]
        items = []
        for suffix, days, source in (
            ("recent-a", 1, source_a),
            ("recent-b", 2, source_b),
            ("recent-c", 3, source_a),
            ("previous-a", 8, source_a),
        ):
            item = repository.create_content_item(
                source.name, source.source_type, PREFIX + suffix, "article",
                f"Phase 9 {suffix}", f"https://example.invalid/{suffix}",
                END - timedelta(days=days),
            )
            items.append(item)
            item_ids.append(item.id)
        check(len(items) == 4, "temporary ContentItems created")

        stories = [Story(title=PREFIX + "story-a"), Story(title=PREFIX + "story-b")]
        session.add_all(stories)
        session.flush()
        story_ids = [story.id for story in stories]
        session.add_all([
            StoryContent(story_id=stories[0].id, content_item_id=items[0].id),
            StoryContent(story_id=stories[1].id, content_item_id=items[1].id),
            StoryContent(story_id=stories[0].id, content_item_id=items[2].id),
            StoryContent(story_id=stories[0].id, content_item_id=items[3].id),
        ])
        print("[PASS] temporary Stories created")
        print("[PASS] temporary StoryContent associations created")
        for item in items:
            session.add(ContentEnrichment(
                content_item_id=item.id, category="industry",
                topics=["AI Agents"], entities=["OpenAI"], importance=0.8,
                novelty=0.8, technical_depth=0.8, impact=0.8,
                source_quality=0.8, model_name="phase9-test", prompt_version="phase9",
            ))
        session.commit()
        check(
            all(repository.get_content_enrichment(item.id) for item in items),
            "temporary enrichment metadata created",
        )
        records = repository.get_trend_records(
            END - timedelta(days=14), END
        )
        config = TrendConfig(min_recent_content=2, min_recent_stories=1)
        results = TrendDetector(config).detect_trends(records, end_time=END)
        check(results, "recent activity detected")
        result = next(item for item in results if item.topic == "ai agents")
        check(result.metrics.previous_content_count == 1, "previous activity detected")
        check(result.metrics.growth_rate > 0, "topic growth detected")
        check(result.metrics.recent_source_count == 2, "source diversity detected")
        check(result.metrics.recent_story_count == 2, "Story diversity detected")
        check(result.is_emerging, "emerging trend detected")
        check(result.explanation, "deterministic explanation generated")
        check(results == sorted(results, key=lambda item: (-item.score, item.topic)),
              "trend ordering works")
        print("[PASS] Phase 9 PostgreSQL verification completed")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"[FAIL] Phase 9 PostgreSQL verification: {exc}")
        return 1
    finally:
        try:
            if item_ids:
                session.query(StoryContent).filter(
                    StoryContent.content_item_id.in_(item_ids)
                ).delete(synchronize_session=False)
                session.query(ContentEnrichment).filter(
                    ContentEnrichment.content_item_id.in_(item_ids)
                ).delete(synchronize_session=False)
                session.query(ContentEmbedding).filter(
                    ContentEmbedding.content_item_id.in_(item_ids)
                ).delete(synchronize_session=False)
                session.query(ContentItem).filter(
                    ContentItem.id.in_(item_ids)
                ).delete(synchronize_session=False)
            if story_ids:
                session.query(Story).filter(Story.id.in_(story_ids)).delete(
                    synchronize_session=False
                )
            if source_ids:
                session.query(Source).filter(Source.id.in_(source_ids)).delete(
                    synchronize_session=False
                )
            session.commit()
            print("[PASS] temporary Phase 9 records cleaned up")
        except Exception as exc:
            session.rollback()
            print(f"[FAIL] cleanup failed: {exc}")
        finally:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
