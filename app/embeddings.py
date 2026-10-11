import hashlib
import os
from abc import ABC, abstractmethod
from typing import Any, List, Sequence

try:
    from openai import OpenAI
except ImportError:  # Optional legacy provider dependency.
    OpenAI = None
from pydantic import BaseModel, field_validator

from .config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MAX_CONTENT_CHARS,
    EMBEDDING_MODEL,
)
from .database.models import ContentItem


class EmbeddingResult(BaseModel):
    embedding: List[float]
    dimensions: int

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, value):
        if len(value) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS} embedding dimensions, got {len(value)}"
            )
        return value

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, value):
        if value != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected configured embedding dimensions {EMBEDDING_DIMENSIONS}, got {value}"
            )
        return value


def prepare_embedding_text(
    content_item: ContentItem, max_chars: int = EMBEDDING_MAX_CONTENT_CHARS
) -> str:
    body = content_item.raw_content or content_item.transcript or content_item.description or ""
    metadata = (
        f"Title: {content_item.title}\n"
        f"Source: {content_item.source.name}\n"
        f"Content type: {content_item.content_type}\n"
        "Content:\n"
    )
    if max_chars <= 0:
        return ""
    return (metadata + body)[:max_chars]


def embedding_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingProvider(ABC):
    model_name: str
    dimensions: int
    batch_size: int

    @abstractmethod
    def embed_batch(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        raise NotImplementedError

    def embed_text(self, text: str) -> EmbeddingResult:
        results = self.embed_texts([text])
        return results[0]

    def embed_texts(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        return self.embed_batch(texts)


class LocalSentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """CPU-friendly local embeddings with one reusable lazy model instance."""

    _model_cache = {}

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = EMBEDDING_BATCH_SIZE,
        model: Any = None,
    ):
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._model = model

    def _get_model(self):
        if self._model is None:
            if self.model_name not in self._model_cache:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError(
                        "sentence-transformers is required for local embeddings"
                    ) from exc
                self._model_cache[self.model_name] = SentenceTransformer(
                    self.model_name, device="cpu"
                )
            self._model = self._model_cache[self.model_name]
        return self._model

    def embed_batch(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        model = self._get_model()
        vectors = model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if len(texts) == 1 and getattr(vectors, "ndim", None) == 1:
            vectors = [vectors]
        results = []
        for vector in vectors:
            values = [float(value) for value in vector]
            results.append(EmbeddingResult(
                embedding=values,
                dimensions=len(values),
            ))
        return results


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        client: Any = None,
        model_name: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ):
        if client is None and OpenAI is None:
            raise RuntimeError("openai is only required for the legacy provider")
        self.client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size

    def embed_batch(self, texts: Sequence[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.model_name,
            input=list(texts),
            dimensions=self.dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [
            EmbeddingResult(embedding=list(item.embedding), dimensions=self.dimensions)
            for item in ordered
        ]
