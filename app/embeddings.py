import hashlib
import os
from abc import ABC, abstractmethod
from typing import Any, List, Sequence

from openai import OpenAI
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


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        client: Any = None,
        model_name: str = EMBEDDING_MODEL,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ):
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
