"""Safe PostgreSQL verification for deterministic Phase 8 ranking."""

import sys
import uuid
from datetime import datetime, timezone
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
from app.embeddings import EmbeddingResult
from app.profiles.user_profile import UserProfile
from app.ranking import PersonalizedRanker, RankingCandidate
from app.retrieval import SemanticRetrieval
from app.database.repository import Repository


PREFIX = f"phase8-verification-{uuid.uuid4().hex}-"


class FixedEmbeddingProvider:
    def embed_batch(self, texts):
        vector = [1.0] + [0.0] * 1535
        return [EmbeddingResult(embedding=vector, dimensions=1536) for _ in texts]


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    engine = get_engine()
    session = Repository().session
    repository = Repository(session=session)
    item_ids = []
    story_ids = []
    source_id = None
    try:
        tables = set(inspect(engine).get_table_names())
        required = {"content_items", "content_enrichments", "content_embeddings",
                    "stories", "story_content"}
        check(required.issubset(tables), "required tables exist")

        source = repository._get_or_create_source(PREFIX + "source", "phase8")
        source_id = source.id
        now = datetime.now(timezone.utc)
        first = repository.create_content_item(
            source.name, source.source_type, PREFIX + "one", "article",
            "Phase 8 preferred AI agents", "https://example.invalid/one", now,
            description="Temporary ranking content",
        )
        second = repository.create_content_item(
            source.name, source.source_type, PREFIX + "two", "article",
            "Phase 8 duplicate story", "https://example.invalid/two", now,
            description="Temporary duplicate content",
        )
        third = repository.create_content_item(
            source.name, source.source_type, PREFIX + "three", "article",
            "Phase 8 excluded topic", "https://example.invalid/three", now,
            description="Temporary excluded content",
        )
        item_ids = [first.id, second.id, third.id]
        check(len(item_ids) == 3, "temporary ContentItems created")

        story = Story(title=PREFIX + "story")
        other_story = Story(title=PREFIX + "other-story")
        session.add_all([story, other_story])
        session.flush()
        story_ids = [story.id, other_story.id]
        session.add_all([
            StoryContent(story_id=story.id, content_item_id=first.id),
            StoryContent(story_id=story.id, content_item_id=second.id),
            StoryContent(story_id=other_story.id, content_item_id=third.id),
        ])
        for item in (first, second, third):
            session.add(ContentEnrichment(
                content_item_id=item.id,
                category="industry",
                topics=["AI Agents"] if item is not third else ["cryptocurrency"],
                entities=["OpenAI"],
                importance=0.8,
                novelty=0.8,
                technical_depth=0.8,
                impact=0.8,
                source_quality=0.9,
                model_name="phase8-test",
                prompt_version="phase8",
            ))
            session.add(ContentEmbedding(
                content_item_id=item.id,
                embedding=[1.0] + [0.0] * 1535,
                embedding_model="phase8-test",
                dimensions=1536,
                text_hash=("a" * 63) + str(len(item_ids)),
            ))
        session.commit()
        check(session.query(StoryContent).filter(
            StoryContent.story_id == story.id
        ).count() == 2, "temporary Stories created")
        check(all(repository.get_content_enrichment(item.id) for item in (first, second, third)),
              "enrichment metadata available")

        retrieved = SemanticRetrieval(
            repository, FixedEmbeddingProvider()
        ).retrieve("AI agents", top_k=20)
        temporary_results = [item for item in retrieved if item.content_item_id in item_ids]
        check(len(temporary_results) == 3, "candidate retrieval works")

        by_id = {item.id: item for item in (first, second, third)}
        candidates = [
            RankingCandidate.from_retrieval(
                item,
                topics=repository.get_content_enrichment(item.content_item_id).topics,
                entities=repository.get_content_enrichment(item.content_item_id).entities,
                source_name=source.name,
                source_quality=0.9,
            )
            for item in temporary_results
        ]
        ranked = PersonalizedRanker(now=now).rank(
            candidates,
            UserProfile(preferred_topics=["AI Agents"], excluded_topics=["cryptocurrency"]),
        )
        check(ranked, "personalized ranking works")
        check(len([item for item in ranked if item.story_id == story.id]) == 1,
              "story-aware ranking works")
        excluded = next(item for item in ranked if item.story_id == other_story.id)
        check(excluded.explanation.exclusion_applied, "exclusions work")
        check(excluded.explanation.reasons, "ranking explanations work")
        print("[PASS] Phase 8 PostgreSQL verification completed")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"[FAIL] Phase 8 PostgreSQL verification: {exc}")
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
            if source_id:
                session.query(Source).filter(
                    Source.id == source_id, Source.name == PREFIX + "source"
                ).delete(synchronize_session=False)
            session.commit()
            print("[PASS] temporary Phase 8 records cleaned up")
        except Exception as exc:
            session.rollback()
            print(f"[FAIL] cleanup failed: {exc}")
        finally:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
