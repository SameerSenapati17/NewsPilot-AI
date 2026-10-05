"""Safe PostgreSQL/pgvector verification for Phase 6."""

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import EMBEDDING_DIMENSIONS
from app.database.connection import get_engine
from app.database.models import ContentEmbedding, ContentItem, Source
from app.database.repository import Repository


PREFIX = f"phase6-verification-{uuid.uuid4().hex}-"


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_pg_integration_phase6() -> bool:
    engine = get_engine()
    repo = Repository()
    session = repo.session
    source_id = None
    item_ids = []
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            available = connection.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            ).first()
            check(available is not None, "pgvector is available")
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        check("content_embeddings" in inspect(engine).get_table_names(),
              "content_embeddings table exists")
        column = ContentEmbedding.__table__.c.embedding
        check(column.type.dim == EMBEDDING_DIMENSIONS,
              f"vector column dimension is {EMBEDDING_DIMENSIONS}")

        source = repo._get_or_create_source(f"{PREFIX}source", "phase6-verification")
        source_id = source.id
        now = datetime.utcnow()
        first = repo.create_content_item(
            source.name, source.source_type, f"{PREFIX}one", "article",
            "Phase 6 one", f"https://example.com/{PREFIX}one", now,
        )
        second = repo.create_content_item(
            source.name, source.source_type, f"{PREFIX}two", "article",
            "Phase 6 two", f"https://example.com/{PREFIX}two", now + timedelta(minutes=1),
        )
        item_ids = [first.id, second.id]
        vector = [0.1] * EMBEDDING_DIMENSIONS
        record = repo.create_content_embedding(
            first.id, vector, "test-model", EMBEDDING_DIMENSIONS, "a" * 64
        )
        check(record is not None and record.id is not None, "embedding creation works")
        check(repo.get_content_embedding(first.id).text_hash == "a" * 64,
              "embedding read-back works")
        updated = repo.upsert_content_embedding(
            first.id, [0.2] * EMBEDDING_DIMENSIONS,
            "test-model", EMBEDDING_DIMENSIONS, "b" * 64,
        )
        check(updated.text_hash == "b" * 64, "embedding upsert works")
        session.add(ContentEmbedding(
            content_item_id=first.id, embedding=vector,
            embedding_model="duplicate", dimensions=EMBEDDING_DIMENSIONS,
            text_hash="c" * 64,
        ))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            print("[PASS] unique ContentItem embedding constraint works")
        else:
            raise AssertionError("duplicate embedding was accepted")
        repo.create_content_embedding(
            second.id, vector, "test-model", EMBEDDING_DIMENSIONS, "d" * 64
        )
        results = repo.find_similar_content(
            vector, limit=10, exclude_content_item_id=first.id
        )
        check(all(row["content_item"].id != first.id for row in results),
              "queried ContentItem is excluded")
        check(results and results[0]["content_item"].id == second.id,
              "similarity search returns ordered results")
        print("[PASS] Phase 6 PostgreSQL verification completed")
        return True
    except Exception as exc:
        session.rollback()
        print(f"[FAIL] Phase 6 PostgreSQL verification: {exc}")
        return False
    finally:
        try:
            if item_ids:
                session.query(ContentEmbedding).filter(
                    ContentEmbedding.content_item_id.in_(item_ids)
                ).delete(synchronize_session=False)
                session.query(ContentItem).filter(
                    ContentItem.id.in_(item_ids)
                ).delete(synchronize_session=False)
            if source_id:
                session.query(Source).filter(
                    Source.id == source_id, Source.name == f"{PREFIX}source"
                ).delete(synchronize_session=False)
            session.commit()
            print("[PASS] temporary Phase 6 records cleaned up")
        except Exception as exc:
            session.rollback()
            print(f"[FAIL] cleanup failed: {exc}")
        finally:
            session.close()


if __name__ == "__main__":
    sys.exit(0 if verify_pg_integration_phase6() else 1)
