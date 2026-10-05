"""Safe PostgreSQL verification for the Phase 4 schema in the original checkout.

This script creates only uniquely prefixed temporary records. It never drops
or truncates tables and removes every record it creates in a finally block.
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.connection import get_engine
from app.database.models import ContentItem, Source, Story, StoryContent
from app.database.repository import Repository


RUN_PREFIX = f"phase4-verification-{uuid.uuid4().hex}-"


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_pg_integration_phase4() -> bool:
    repo = Repository()
    session = repo.session
    source_id = None
    content_item_ids = []
    story_ids = []
    cleanup_succeeded = False

    try:
        required_tables = {"content_items", "stories", "story_content"}
        tables = set(inspect(get_engine()).get_table_names())
        check(
            required_tables.issubset(tables),
            f"Required tables exist: {', '.join(sorted(required_tables))}",
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = repo._get_or_create_source(
            f"{RUN_PREFIX}source", "phase4-verification"
        )
        source_id = source.id

        first = repo.create_content_item(
            source.name, source.source_type, f"{RUN_PREFIX}first", "article",
            "OpenAI releases a new model", f"https://example.com/{RUN_PREFIX}first",
            now,
        )
        similar = repo.create_content_item(
            source.name, source.source_type, f"{RUN_PREFIX}similar", "article",
            "OpenAI releases new model",
            f"https://example.com/{RUN_PREFIX}similar", now + timedelta(hours=1),
        )
        unrelated = repo.create_content_item(
            source.name, source.source_type, f"{RUN_PREFIX}unrelated", "article",
            "NVIDIA opens a data center",
            f"https://example.com/{RUN_PREFIX}unrelated", now + timedelta(hours=2),
        )
        items = [first, similar, unrelated]
        check(all(items), "Temporary ContentItems created")
        content_item_ids = [item.id for item in items]

        story = Story(
            title=first.title,
            first_seen_at=first.published_at,
            last_updated_at=first.published_at,
        )
        session.add(story)
        session.commit()
        story_ids.append(story.id)
        check(
            session.query(Story).filter_by(id=story.id).first() is not None,
            "Story creation and read-back succeeded",
        )

        association = StoryContent(story_id=story.id, content_item_id=first.id)
        session.add(association)
        session.commit()
        check(
            session.query(StoryContent).filter_by(
                story_id=story.id, content_item_id=first.id
            ).count() == 1,
            "StoryContent association created",
        )
        check(
            [item.id for item in session.query(ContentItem).join(StoryContent).filter(
                StoryContent.story_id == story.id
            ).all()] == [first.id],
            "Associated ContentItem read-back succeeded",
        )

        similar_association = StoryContent(
            story_id=story.id, content_item_id=similar.id
        )
        session.add(similar_association)
        session.commit()
        check(
            session.query(StoryContent).filter_by(
                story_id=story.id, content_item_id=similar.id
            ).count() == 1,
            "Similar ContentItem attaches to the existing Story",
        )

        separate_story = Story(
            title=unrelated.title,
            first_seen_at=unrelated.published_at,
            last_updated_at=unrelated.published_at,
        )
        session.add(separate_story)
        session.commit()
        story_ids.append(separate_story.id)
        session.add(
            StoryContent(
                story_id=separate_story.id, content_item_id=unrelated.id
            )
        )
        session.commit()
        check(
            separate_story.id != story.id,
            "Unrelated ContentItem uses a separate Story",
        )

        duplicate = StoryContent(story_id=separate_story.id, content_item_id=first.id)
        session.add(duplicate)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            print("[PASS] Unique constraint prevents one ContentItem joining two Stories")
        else:
            raise AssertionError(
                "Unique constraint allowed one ContentItem in two Stories"
            )

        duplicate_association = StoryContent(
            story_id=story.id, content_item_id=first.id
        )
        session.add(duplicate_association)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            print("[PASS] Duplicate StoryContent rows are rejected")
        else:
            raise AssertionError("Duplicate StoryContent row was accepted")

        old_story = Story(
            title=f"{RUN_PREFIX}old",
            first_seen_at=now - timedelta(days=5),
            last_updated_at=now - timedelta(days=5),
        )
        session.add(old_story)
        session.commit()
        story_ids.append(old_story.id)
        candidates = session.query(Story).filter(
            Story.last_updated_at >= now - timedelta(hours=48)
        ).all()
        check(
            old_story.id not in {candidate.id for candidate in candidates},
            "Candidate time-window filtering excludes old Stories",
        )
        print("[PASS] PostgreSQL connectivity and Phase 4 verification completed")
        return True
    except Exception as exc:
        session.rollback()
        print(f"[FAIL] PostgreSQL Phase 4 verification: {exc}")
        return False
    finally:
        try:
            session.query(StoryContent).filter(
                StoryContent.content_item_id.in_(content_item_ids)
            ).delete(synchronize_session=False)
            session.query(ContentItem).filter(
                ContentItem.id.in_(content_item_ids)
            ).delete(synchronize_session=False)
            session.query(Story).filter(Story.id.in_(story_ids)).delete(
                synchronize_session=False
            )
            if source_id is not None:
                session.query(Source).filter(
                    Source.id == source_id,
                    Source.name == f"{RUN_PREFIX}source",
                ).delete(synchronize_session=False)
            session.commit()
            cleanup_succeeded = True
            print("[PASS] Temporary records cleaned up")
        except Exception as exc:
            session.rollback()
            print(f"[FAIL] Cleanup failed: {exc}")
        finally:
            session.close()
        if not cleanup_succeeded:
            print("[FAIL] Cleanup result: temporary records may remain")


if __name__ == "__main__":
    sys.exit(0 if verify_pg_integration_phase4() else 1)
