import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag_context import build_context
from app.retrieval import RetrievalResult, SemanticRetrieval
from app.rag import RAGService


class FakeEmbeddingProvider:
    def __init__(self):
        self.queries = []

    def embed_batch(self, texts):
        self.queries.extend(texts)
        return [Mock(embedding=[0.1, 0.2])]


class TestRetrievalAndRAG(unittest.TestCase):
    def setUp(self):
        self.item = Mock(
            id="item-1",
            title="AI release",
            url="https://example.com/a",
            description="A useful description",
            raw_content="Full article text",
            transcript=None,
            published_at=datetime(2026, 1, 1),
        )
        self.repo = Mock()
        self.repo.find_similar_content.return_value = [
            {"content_item": self.item, "story_id": "story-1", "similarity": 0.9},
            {"content_item": self.item, "story_id": "story-1", "similarity": 0.8},
        ]

    def test_retrieval_validates_query_and_preserves_story(self):
        provider = FakeEmbeddingProvider()
        service = SemanticRetrieval(self.repo, provider)
        with self.assertRaises(ValueError):
            service.retrieve("  ")
        results = service.retrieve("new models", top_k=3)
        self.assertEqual(provider.queries, ["new models"])
        self.assertEqual(results[0].story_id, "story-1")
        self.assertEqual(results[0].content, "Full article text")

    def test_context_deduplicates_stories_and_is_bounded(self):
        first = RetrievalResult(
            content_item_id="a", story_id="story", title="A",
            content="x" * 100,
            similarity=0.9,
        )
        second = first.model_copy(update={"content_item_id": "b"})
        context = build_context("q", [first, second], max_items=8, max_chars=80)
        self.assertEqual(len(context.sources), 1)
        self.assertLessEqual(len(context.context_text), 80)

    def test_empty_context_is_answered_without_provider(self):
        retrieval = Mock()
        retrieval.retrieve.return_value = []
        provider = Mock()
        answer = RAGService(retrieval, provider).answer_question("q")
        self.assertIn("insufficient", answer.answer.lower())
        provider.answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
