import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import EMBEDDING_DIMENSIONS
from app.embeddings import (
    EmbeddingResult,
    OpenAIEmbeddingProvider,
    embedding_text_hash,
    prepare_embedding_text,
)
from app.database.models import Base
from app.database.repository import Repository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestEmbeddings(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.repo = Repository(session=self.session)
        self.item = self.repo.create_content_item(
            "Test Source", "web", "embedding-test", "article",
            "Embedding title", "https://example.com/embedding",
            datetime(2026, 1, 1), description="Embedding description",
        )

    def tearDown(self):
        self.session.close()

    def test_input_and_hash_are_deterministic(self):
        text = prepare_embedding_text(self.item)
        self.assertEqual(text, prepare_embedding_text(self.item))
        self.assertEqual(embedding_text_hash(text), embedding_text_hash(text))
        self.item.description = "Changed"
        self.assertNotEqual(text, prepare_embedding_text(self.item))

    def test_large_content_is_truncated(self):
        self.item.raw_content = "x" * 10000
        text = prepare_embedding_text(self.item, max_chars=100)
        self.assertEqual(len(text), 100)
        self.assertEqual(text, prepare_embedding_text(self.item, max_chars=100))

    def test_embedding_dimensions_are_validated(self):
        with self.assertRaises(ValidationError):
            EmbeddingResult(embedding=[0.1], dimensions=1)

    def test_provider_batches_and_orders_results(self):
        client = Mock()
        client.embeddings.create.return_value = Mock(
            data=[
                Mock(index=1, embedding=[0.2] * EMBEDDING_DIMENSIONS),
                Mock(index=0, embedding=[0.1] * EMBEDDING_DIMENSIONS),
            ]
        )
        provider = OpenAIEmbeddingProvider(client=client)
        results = provider.embed_batch(["one", "two"])
        self.assertEqual(results[0].embedding[0], 0.1)
        client.embeddings.create.assert_called_once()

    def test_repository_embedding_upsert_is_idempotent(self):
        vector = [0.1] * EMBEDDING_DIMENSIONS
        created = self.repo.create_content_embedding(
            self.item.id, vector, "test-model", EMBEDDING_DIMENSIONS, "a" * 64
        )
        self.assertIsNotNone(created)
        self.assertIsNone(
            self.repo.create_content_embedding(
                self.item.id, vector, "test-model", EMBEDDING_DIMENSIONS, "a" * 64
            )
        )
        updated = self.repo.upsert_content_embedding(
            self.item.id, [0.2] * EMBEDDING_DIMENSIONS,
            "test-model", EMBEDDING_DIMENSIONS, "b" * 64,
        )
        self.assertEqual(updated.text_hash, "b" * 64)


if __name__ == "__main__":
    unittest.main()
