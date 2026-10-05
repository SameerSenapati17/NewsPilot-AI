from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class NewsItemResponse(BaseModel):
    id: str
    story_id: Optional[str] = None
    title: str
    url: str
    description: Optional[str] = None
    published_at: datetime
    source: str


class PaginatedNewsResponse(BaseModel):
    items: List[NewsItemResponse]
    page: int
    page_size: int
    total: int


class StoryResponse(BaseModel):
    story_id: str
    title: str
    representative: Optional[NewsItemResponse] = None
    content_item_count: int
    latest_published_at: Optional[datetime] = None


class PaginatedStoriesResponse(BaseModel):
    items: List[StoryResponse]
    page: int
    page_size: int
    total: int


class SearchResultResponse(BaseModel):
    content_item_id: str
    story_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultResponse]


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: List[Any]


class TrendsResponse(BaseModel):
    trends: List[Any]


class PersonalizedResponse(BaseModel):
    user_id: str
    items: List[Any]
