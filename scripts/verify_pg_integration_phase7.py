"""Safe PostgreSQL verification for Phase 7 retrieval and RAG context."""

import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_engine
from app.database.models import ContentEmbedding, ContentItem
from app.database.repository import Repository
from app.embeddings import EmbeddingResult
from app.rag_context import build_context
from app.retrieval import SemanticRetrieval


PREFIX = "phase7_verify_"


class FixedEmbeddingProvider:
    def embed_batch(self, texts):
        vector = [1.0] + [0.0] * 1535
        return [EmbeddingResult(embedding=vector, dimensions=1536) for _ in texts]


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main():
    engine = get_engine()
    session = Repository().session
    repository = Repository(session=session)
    temporary_items = []
    result = 1
    try:
        tables = set(inspect(engine).get_table_names())
        check("content_items table exists", "content_items" in tables)
        check("content_embeddings table exists", "content_embeddings" in tables)
        check("stories table exists", "stories" in tables)
        check("story_content table exists", "story_content" in tables)

        item = repository.create_content_item(
            "Phase 7 Verification",
            "test",
            PREFIX + "item",
            "article",
            "Phase 7 retrieval verification",
            "https://example.invalid/phase7",
            datetime.utcnow(),
            description="Temporary retrieval content",
        )
        temporary_items.append(item)
        repository.create_content_embedding(
            item.id, [1.0] + [0.0] * 1535, "phase7-test", 1536, "0" * 64
        )
        check("temporary embedding created", repository.get_content_embedding(item.id) is not None)

        service = SemanticRetrieval(repository, FixedEmbeddingProvider())
        results = service.retrieve("retrieval verification", top_k=5)
        check("semantic retrieval returns temporary content", any(
            result.content_item_id == item.id for result in results
        ))
        context = build_context("retrieval verification", results, max_items=5, max_chars=2000)
        check("RAG context preserves source attribution", any(
            source.content_item_id == item.id for source in context.sources
        ))
        print("[PASS] Phase 7 PostgreSQL verification")
        result = 0
    except Exception as exc:
        print(f"[FAIL] Phase 7 PostgreSQL verification: {exc}")
        return 1
    finally:
        try:
            for item in temporary_items:
                session.query(ContentEmbedding).filter_by(
                    content_item_id=item.id
                ).delete(synchronize_session=False)
                session.query(ContentItem).filter_by(id=item.id).delete(
                    synchronize_session=False
                )
            session.commit()
            session.close()
            print("[PASS] Cleanup")
        except Exception as exc:
            session.rollback()
            session.close()
            print(f"[FAIL] Cleanup: {exc}")
            result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
