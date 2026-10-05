"""
NewsPilotAI — Unit Tests for the Repository layer.

Uses an in-memory SQLite database so no PostgreSQL connection is required.
Run with:
    python -m unittest discover -s tests -p "test_*.py"
    python -m unittest tests.test_repository
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Make `app` importable when this file is run directly OR discovered via
# `python -m unittest tests.test_repository` from the project root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database.models import Base, Source, ContentItem, Digest
from app.database.repository import Repository


class TestRepository(unittest.TestCase):
    """Test suite for the unified ContentItem / Source / Digest repository."""

    def setUp(self):
        """Create a fresh in-memory SQLite database for each test."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.repo = Repository(session=self.session)

    def tearDown(self):
        self.session.close()

    # ------------------------------------------------------------------
    # Source helpers
    # ------------------------------------------------------------------
    def test_get_or_create_source_creates_new(self):
        source = self.repo._get_or_create_source("Test Feed", "rss")
        self.assertIsNotNone(source)
        self.assertEqual(source.name, "Test Feed")
        self.assertEqual(source.source_type, "rss")

    def test_get_or_create_source_is_idempotent(self):
        s1 = self.repo._get_or_create_source("Test Feed", "rss")
        s2 = self.repo._get_or_create_source("Test Feed", "rss")
        self.assertEqual(s1.id, s2.id)

    # ------------------------------------------------------------------
    # ContentItem creation
    # ------------------------------------------------------------------
    def test_create_content_item_succeeds(self):
        item = self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="test-001",
            content_type="article",
            title="Test Title",
            url="http://example.com/1",
            published_at=datetime.now(timezone.utc),
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.title, "Test Title")
        self.assertEqual(item.external_id, "test-001")

    def test_create_content_item_links_to_source(self):
        item = self.repo.create_content_item(
            source_name="My Source",
            source_type="youtube",
            external_id="yt-abc",
            content_type="video",
            title="A Video",
            url="http://youtube.com/watch?v=abc",
            published_at=datetime.now(timezone.utc),
        )
        self.assertEqual(item.source.name, "My Source")
        self.assertEqual(item.source.source_type, "youtube")

    # ------------------------------------------------------------------
    # Duplicate external_id prevention
    # ------------------------------------------------------------------
    def test_duplicate_external_id_returns_none(self):
        self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="dup-001",
            content_type="article",
            title="First",
            url="http://example.com/1",
            published_at=datetime.now(timezone.utc),
        )
        result = self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="dup-001",
            content_type="article",
            title="Second — should be ignored",
            url="http://example.com/2",
            published_at=datetime.now(timezone.utc),
        )
        self.assertIsNone(result)

    def test_duplicate_external_id_does_not_overwrite_data(self):
        self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="dup-002",
            content_type="article",
            title="Original Title",
            url="http://example.com/orig",
            published_at=datetime.now(timezone.utc),
        )
        self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="dup-002",
            content_type="article",
            title="Overwrite Attempt",
            url="http://example.com/overwrite",
            published_at=datetime.now(timezone.utc),
        )
        stored = self.session.query(ContentItem).filter_by(external_id="dup-002").first()
        self.assertEqual(stored.title, "Original Title")

    # ------------------------------------------------------------------
    # Digest creation and ContentItem linkage
    # ------------------------------------------------------------------
    def test_create_digest_linked_to_content_item(self):
        item = self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="art-001",
            content_type="article",
            title="Article One",
            url="http://example.com/art1",
            published_at=datetime.now(timezone.utc),
        )
        digest = self.repo.create_digest(
            article_type="web",
            article_id="art-001",
            url="http://example.com/art1",
            title="Digest of Article One",
            summary="A concise summary.",
            content_item_id=item.id,
        )
        self.assertIsNotNone(digest)
        self.assertEqual(digest.content_item_id, item.id)

    def test_create_digest_auto_links_via_external_id(self):
        """Digest without explicit content_item_id should auto-resolve it."""
        item = self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="art-002",
            content_type="article",
            title="Article Two",
            url="http://example.com/art2",
            published_at=datetime.now(timezone.utc),
        )
        digest = self.repo.create_digest(
            article_type="web",
            article_id="art-002",
            url="http://example.com/art2",
            title="Digest of Article Two",
            summary="Another summary.",
            # content_item_id intentionally omitted — should be resolved automatically
        )
        self.assertIsNotNone(digest)
        self.assertEqual(digest.content_item_id, item.id)

    def test_duplicate_digest_returns_none(self):
        self.repo.create_content_item(
            source_name="Test Source",
            source_type="web",
            external_id="art-003",
            content_type="article",
            title="Article Three",
            url="http://example.com/art3",
            published_at=datetime.now(timezone.utc),
        )
        self.repo.create_digest(
            article_type="web", article_id="art-003",
            url="http://example.com/art3",
            title="D1", summary="S1",
        )
        second = self.repo.create_digest(
            article_type="web", article_id="art-003",
            url="http://example.com/art3",
            title="D2", summary="S2",
        )
        self.assertIsNone(second)

    # ------------------------------------------------------------------
    # Bulk legacy wrappers
    # ------------------------------------------------------------------
    def test_bulk_create_youtube_videos(self):
        videos = [
            {
                "video_id": "ytv-1",
                "title": "Video 1",
                "url": "https://youtube.com/watch?v=ytv-1",
                "published_at": datetime.now(timezone.utc),
                "description": "desc",
                "transcript": "transcript text",
            }
        ]
        count = self.repo.bulk_create_youtube_videos(videos)
        self.assertEqual(count, 1)
        item = self.session.query(ContentItem).filter_by(external_id="ytv-1").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.content_type, "video")
        self.assertEqual(item.transcript, "transcript text")

    def test_bulk_create_openai_articles(self):
        articles = [
            {
                "guid": "oa-1",
                "title": "OpenAI Post",
                "url": "https://openai.com/blog/post",
                "published_at": datetime.now(timezone.utc),
                "description": "desc",
            }
        ]
        count = self.repo.bulk_create_openai_articles(articles)
        self.assertEqual(count, 1)
        item = self.session.query(ContentItem).filter_by(external_id="oa-1").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.source.name, "OpenAI RSS")

    def test_bulk_create_anthropic_articles(self):
        articles = [
            {
                "guid": "an-1",
                "title": "Anthropic Post",
                "url": "https://anthropic.com/news/post",
                "published_at": datetime.now(timezone.utc),
                "description": "desc",
            }
        ]
        count = self.repo.bulk_create_anthropic_articles(articles)
        self.assertEqual(count, 1)
        item = self.session.query(ContentItem).filter_by(external_id="an-1").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.source.name, "Anthropic RSS")

    # ------------------------------------------------------------------
    # get_articles_without_digest
    # ------------------------------------------------------------------
    def test_get_articles_without_digest_excludes_digested(self):
        """Once a digest exists for an item it must not appear in the queue."""
        self.repo.create_content_item(
            source_name="OpenAI RSS",
            source_type="rss",
            external_id="oa-ready-1",
            content_type="article",
            title="OpenAI Article",
            url="http://openai.com/1",
            published_at=datetime.now(timezone.utc),
            description="some description",
        )
        undigested = self.repo.get_articles_without_digest()
        self.assertEqual(len(undigested), 1)

        self.repo.create_digest(
            article_type="openai",
            article_id="oa-ready-1",
            url="http://openai.com/1",
            title="D",
            summary="S",
        )
        undigested_after = self.repo.get_articles_without_digest()
        self.assertEqual(len(undigested_after), 0)


if __name__ == "__main__":
    unittest.main()
