import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import EMBEDDING_DIMENSIONS
from app.embeddings import LocalSentenceTransformerEmbeddingProvider
from app.enrichment import (
    ContentEnrichmentResult,
    EnrichmentCategory,
    MistralEnrichmentProvider,
)
from app.mistral import MistralLLMProvider
from app.rag import MistralGroundedAnswerProvider
from app.rag_context import ContextSource, RAGContext


class TestLocalProviders(unittest.TestCase):
    def test_local_embedding_is_batched_and_reused(self):
        model = Mock()
        model.encode.return_value = [[0.1] * EMBEDDING_DIMENSIONS] * 2
        provider = LocalSentenceTransformerEmbeddingProvider(model=model)
        results = provider.embed_texts(["one", "two"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].dimensions, EMBEDDING_DIMENSIONS)
        model.encode.assert_called_once()

    def test_empty_embedding_input(self):
        provider = LocalSentenceTransformerEmbeddingProvider(model=Mock())
        self.assertEqual(provider.embed_texts([]), [])

    def test_mistral_requires_key_without_network(self):
        session = Mock()
        provider = MistralLLMProvider(api_key="", session=session)
        with self.assertRaises(RuntimeError):
            provider.complete_json("system", "user")
        session.post.assert_not_called()

    def test_mistral_sends_bearer_authorization_header(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '{"answer": "ok"}'}}]
        }
        session = Mock()
        session.post.return_value = response
        provider = MistralLLMProvider(api_key="test-key", session=session)

        self.assertEqual(provider.complete_json("system", "user"), {"answer": "ok"})
        request = session.post.call_args
        self.assertEqual(
            request.kwargs["headers"]["Authorization"], "Bearer test-key"
        )
        self.assertNotIn("test-key", repr(request.kwargs["json"]))

    def test_mistral_json_parsing_and_enrichment_validation(self):
        llm = Mock()
        llm.model = "test-model"
        llm.complete_json.return_value = {
            "category": "research",
            "topics": ["AI"],
            "entities": ["OpenAI"],
            "importance": 0.8,
            "novelty": 0.7,
            "technical_depth": 0.6,
            "impact": 0.5,
            "source_quality": 0.9,
        }
        item = Mock(
            title="Title",
            source=Mock(name="Source", reliability_score=0.9),
            content_type="article",
            published_at=datetime(2026, 1, 1),
            raw_content="Body",
            transcript=None,
            description="Description",
        )
        result = MistralEnrichmentProvider(client=llm).enrich(item)
        self.assertIsInstance(result, ContentEnrichmentResult)
        self.assertEqual(result.category, EnrichmentCategory.RESEARCH)

    def test_mistral_codestral_payload_is_normalized(self):
        llm = Mock()
        llm.model = "codestral-2508"
        llm.complete_json.return_value = {
            "categories": ["AI", "Natural Language Processing"],
            "topics": ["NLP"],
            "entities": ["Codestral"],
            "importance": 8,
            "novelty": 7,
            "technical_depth": 9,
            "impact": 7,
            "source_quality": 10,
        }
        item = Mock(
            title="Title",
            source=Mock(name="Source", reliability_score=0.9),
            content_type="article",
            published_at=datetime(2026, 1, 1),
            raw_content="Body",
            transcript=None,
            description="Description",
        )
        result = MistralEnrichmentProvider(client=llm).enrich(item)
        self.assertEqual(result.category, EnrichmentCategory.INDUSTRY)
        self.assertEqual(result.impact, 0.7)

    def test_mistral_grounded_answer_preserves_sources(self):
        source = ContextSource(
            content_item_id="item", title="Source title", similarity=0.9, text="text"
        )
        context = RAGContext(query="q", sources=[source], context_text="context")
        llm = Mock()
        llm.complete_json.return_value = {"answer": "Grounded"}
        result = MistralGroundedAnswerProvider(client=llm).answer("q", context)
        self.assertEqual(result.answer, "Grounded")
        self.assertEqual(result.sources, [source])


if __name__ == "__main__":
    unittest.main()
