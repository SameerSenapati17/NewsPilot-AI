from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ..profiles.user_profile import get_structured_user_profile
from ..config import API_CORS_ORIGINS, API_VERSION
from ..ranking import PersonalizedRanker, RankingCandidate
from ..trends import TrendDetector
from .dependencies import get_rag_service, get_repository, get_retrieval
from .schemas import (
    AskRequest, AskResponse, HealthResponse, NewsItemResponse,
    PaginatedNewsResponse, PaginatedStoriesResponse, PersonalizedResponse,
    SearchResponse, SearchResultResponse, StoryResponse, TrendsResponse,
)


app = FastAPI(
    title="NewsPilotAI API",
    version=API_VERSION,
    description="HTTP API for NewsPilotAI retrieval, RAG, ranking, and trends.",
)
app.add_middleware(
    CORSMiddleware, allow_origins=API_CORS_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "service": "newspilotai-api"}


@app.get("/api/news", response_model=PaginatedNewsResponse)
def news(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = None, content_type: Optional[str] = None,
    repository=Depends(get_repository),
):
    items, total = repository.list_content_items(page, page_size, source, content_type)
    return {
        "items": [
            NewsItemResponse(
                id=item.id, story_id=item.story_content.story_id if item.story_content else None,
                title=item.title, url=item.url, description=item.description,
                published_at=item.published_at, source=item.source.name,
            ) for item in items
        ], "page": page, "page_size": page_size, "total": total,
    }


@app.get("/api/stories", response_model=PaginatedStoriesResponse)
def stories(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    repository=Depends(get_repository),
):
    values, total = repository.list_stories(page, page_size)
    response = []
    for story in values:
        associated = [link.content_item for link in story.story_content]
        representative = max(associated, key=lambda item: item.published_at) if associated else None
        metadata = None
        if representative:
            metadata = NewsItemResponse(
                id=representative.id, story_id=story.id, title=representative.title,
                url=representative.url, description=representative.description,
                published_at=representative.published_at, source=representative.source.name,
            )
        response.append(StoryResponse(
            story_id=story.id, title=story.title, representative=metadata,
            content_item_count=len(associated),
            latest_published_at=representative.published_at if representative else None,
        ))
    return {"items": response, "page": page, "page_size": page_size, "total": total}

@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    min_similarity: Optional[float] = Query(None, ge=0, le=1),
    retrieval=Depends(get_retrieval),
):
    # Reject empty or whitespace-only queries
    if not q.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty"
        )

    # Remove leading/trailing whitespace
    q = q.strip()

    try:
        results = retrieval.retrieve(q, top_k, min_similarity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "query": q,
        "results": [
            SearchResultResponse(**item.model_dump()) for item in results
        ],
    }

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, rag_service=Depends(get_rag_service)):
    try:
        result = rag_service.answer_question(request.query, request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Answer provider unavailable") from exc
    return {"query": request.query, "answer": result.answer, "sources": result.sources}


@app.get("/api/trends", response_model=TrendsResponse)
def trends(
    top_k: int = Query(10, ge=1, le=50),
    recent_days: Optional[int] = Query(None, ge=1, le=90),
    previous_days: Optional[int] = Query(None, ge=1, le=90),
    repository=Depends(get_repository),
):
    results = TrendDetector(repository).detect_trends(
        recent_days=recent_days, previous_days=previous_days, top_k=top_k,
    )
    return {"trends": results}


@app.get("/api/personalized", response_model=PersonalizedResponse)
def personalized(
    user_id: str = Query("default", min_length=1, max_length=100),
    q: str = Query("", max_length=500),
    top_k: int = Query(10, ge=1, le=50),
    retrieval=Depends(get_retrieval),
    repository=Depends(get_repository),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    results = retrieval.retrieve(q, top_k=top_k)
    candidates = []
    for result in results:
        enrichment = repository.get_content_enrichment(result.content_item_id)
        candidates.append(RankingCandidate.from_retrieval(
            result,
            topics=enrichment.topics if enrichment else [],
            entities=enrichment.entities if enrichment else [],
        ))
    ranked = PersonalizedRanker().rank(candidates, get_structured_user_profile(user_id))
    return {"user_id": user_id, "items": ranked}
