"""Safe PostgreSQL verification for Phase 5 AI enrichment."""

import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.connection import get_engine
from app.database.models import ContentEnrichment, ContentItem, Source
from app.database.repository import Repository


PREFIX = f"phase5-verification-{uuid.uuid4().hex}-"


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_pg_integration_phase5() -> bool:
    repo = Repository()
    session = repo.session
    source_id = None
    item_id = None
    try:
        check(
            "content_enrichments" in inspect(get_engine()).get_table_names(),
            "content_enrichments table exists",
        )
        source = repo._get_or_create_source(
            f"{PREFIX}source", "phase5-verification"
        )
        source_id = source.id
        item = repo.create_content_item(
            source.name,
            source.source_type,
            f"{PREFIX}item",
            "article",
            "Phase 5 integration item",
            f"https://example.com/{PREFIX}item",
            datetime.utcnow(),
        )
        check(item is not None, "Temporary ContentItem created")
        item_id = item.id

        required_columns = {
            "content_item_id",
            "category",
            "topics",
            "entities",
            "importance",
            "novelty",
            "technical_depth",
            "impact",
            "source_quality",
            "model_name",
            "prompt_version",
        }
        check(
            required_columns.issubset(
                {column.name for column in ContentEnrichment.__table__.columns}
            ),
            "ContentEnrichment columns exist",
        )

        enrichment = ContentEnrichment(
            content_item_id=item.id,
            category="research",
            topics=["machine learning"],
            entities=["Temporary Test Entity"],
            importance=0.8,
            novelty=0.7,
            technical_depth=0.6,
            impact=0.5,
            source_quality=0.9,
            model_name="phase5-test-model",
            prompt_version="v1",
        )
        session.add(enrichment)
        session.commit()
        check(enrichment.id is not None, "ContentEnrichment creation works")

        row = session.query(ContentEnrichment).filter_by(
            content_item_id=item.id
        ).first()
        check(row is not None, "ContentEnrichment read-back works")

        duplicate = ContentEnrichment(
            content_item_id=item.id,
            category="other",
            topics=[],
            entities=[],
            importance=0,
            novelty=0,
            technical_depth=0,
            impact=0,
            source_quality=0,
            model_name="duplicate",
            prompt_version="duplicate",
        )
        session.add(duplicate)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            print("[PASS] Unique ContentItem enrichment constraint works")
        else:
            raise AssertionError("Duplicate enrichment row was accepted")

        print("[PASS] PostgreSQL Phase 5 verification completed")
        return True
    except Exception as exc:
        session.rollback()
        print(f"[FAIL] PostgreSQL Phase 5 verification: {exc}")
        return False
    finally:
        try:
            if item_id is not None:
                session.query(ContentEnrichment).filter_by(
                    content_item_id=item_id
                ).delete(synchronize_session=False)
                session.query(ContentItem).filter_by(id=item_id).delete(
                    synchronize_session=False
                )
            if source_id is not None:
                session.query(Source).filter(
                    Source.id == source_id,
                    Source.name == f"{PREFIX}source",
                ).delete(synchronize_session=False)
            session.commit()
            print("[PASS] Temporary Phase 5 records cleaned up")
        except Exception as exc:
            session.rollback()
            print(f"[FAIL] Cleanup failed: {exc}")
        finally:
            session.close()


if __name__ == "__main__":
    sys.exit(0 if verify_pg_integration_phase5() else 1)
