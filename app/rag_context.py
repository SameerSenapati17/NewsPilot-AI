from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .retrieval import RetrievalResult


class ContextSource(BaseModel):
    content_item_id: str
    story_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    similarity: float
    text: str


class RAGContext(BaseModel):
    query: str
    sources: List[ContextSource]
    context_text: str


def build_context(
    query: str,
    results: List[RetrievalResult],
    max_items: int = 8,
    max_chars: int = 12000,
) -> RAGContext:
    if max_items < 1 or max_chars < 1:
        raise ValueError("Context limits must be positive")
    selected: List[RetrievalResult] = []
    seen_stories = set()
    for result in results:
        story_key = result.story_id
        if story_key is not None and story_key in seen_stories:
            continue
        if story_key is not None:
            seen_stories.add(story_key)
        selected.append(result)
        if len(selected) >= max_items:
            break

    sources: List[ContextSource] = []
    blocks: List[str] = []
    used_chars = 0
    for result in selected:
        text = result.content or result.description or result.title
        source = ContextSource(
            content_item_id=result.content_item_id,
            story_id=result.story_id,
            title=result.title,
            url=result.url,
            published_at=result.published_at,
            similarity=result.similarity,
            text=text,
        )
        block = (
            f"[{result.content_item_id}] {result.title}\n"
            f"URL: {result.url or 'Unavailable'}\n"
            f"Published: {result.published_at.isoformat() if result.published_at else 'Unavailable'}\n"
            f"Relevance: {result.similarity:.4f}\n"
            f"Content: {text}\n"
        )
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
            source.text = source.text[: max(0, remaining)]
        sources.append(source)
        blocks.append(block)
        used_chars += len(block)
    return RAGContext(query=query, sources=sources, context_text="\n".join(blocks))
