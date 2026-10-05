from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .database.repository import Repository
from .embeddings import EmbeddingProvider


class RetrievalResult(BaseModel):
    content_item_id: str
    story_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[datetime] = None
    similarity: float


class SemanticRetrieval:
    def __init__(self, repository: Repository, embedding_provider: EmbeddingProvider):
        self.repository = repository
        self.embedding_provider = embedding_provider

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: Optional[float] = None,
    ) -> List[RetrievalResult]:
        if not query or not query.strip():
            raise ValueError("Retrieval query must not be empty")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        embedding = self.embedding_provider.embed_batch([query.strip()])[0]
        rows = self.repository.find_similar_content(embedding.embedding, limit=top_k)
        results = [
            RetrievalResult(
                content_item_id=row["content_item"].id,
                story_id=row.get("story_id"),
                title=row["content_item"].title,
                url=row["content_item"].url,
                description=row["content_item"].description,
                content=(
                    row["content_item"].raw_content
                    or row["content_item"].transcript
                    or row["content_item"].description
                ),
                published_at=row["content_item"].published_at,
                similarity=row["similarity"],
            )
            for row in rows
        ]
        if min_similarity is not None:
            results = [item for item in results if item.similarity >= min_similarity]
        return results


RetrievalService = SemanticRetrieval
