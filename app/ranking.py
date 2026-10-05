import math
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field

from .config import (
    RANKING_ENTITY_WEIGHT,
    RANKING_EXCLUSION_PENALTY,
    RANKING_FRESHNESS_HALF_LIFE_DAYS,
    RANKING_FRESHNESS_WEIGHT,
    RANKING_SEMANTIC_WEIGHT,
    RANKING_SOURCE_QUALITY,
    RANKING_SOURCE_WEIGHT,
    RANKING_TOPIC_WEIGHT,
)
from .profiles.user_profile import UserProfile
from .retrieval import RetrievalResult


class RankingConfig(BaseModel):
    semantic_weight: float = RANKING_SEMANTIC_WEIGHT
    topic_weight: float = RANKING_TOPIC_WEIGHT
    entity_weight: float = RANKING_ENTITY_WEIGHT
    freshness_weight: float = RANKING_FRESHNESS_WEIGHT
    source_weight: float = RANKING_SOURCE_WEIGHT
    exclusion_penalty: float = RANKING_EXCLUSION_PENALTY
    freshness_half_life_days: float = RANKING_FRESHNESS_HALF_LIFE_DAYS
    source_quality: Dict[str, float] = Field(
        default_factory=lambda: dict(RANKING_SOURCE_QUALITY)
    )


class RankingCandidate(BaseModel):
    content_item_id: str
    story_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    similarity: float = 0.0
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    source_name: Optional[str] = None
    source_quality: Optional[float] = None
    content_type: Optional[str] = None

    @classmethod
    def from_retrieval(
        cls,
        result: RetrievalResult,
        topics: Optional[Iterable[str]] = None,
        entities: Optional[Iterable[str]] = None,
        source_name: Optional[str] = None,
        source_quality: Optional[float] = None,
        content_type: Optional[str] = None,
    ):
        return cls(
            content_item_id=result.content_item_id,
            story_id=result.story_id,
            title=result.title,
            url=result.url,
            published_at=result.published_at,
            similarity=result.similarity,
            topics=list(topics or []),
            entities=list(entities or []),
            source_name=source_name,
            source_quality=source_quality,
            content_type=content_type,
        )


class RankingExplanation(BaseModel):
    matched_topics: List[str] = Field(default_factory=list)
    matched_entities: List[str] = Field(default_factory=list)
    semantic_score: float
    topic_score: float
    entity_score: float
    freshness_score: float
    source_score: float
    exclusion_applied: bool = False
    final_score: float
    reasons: List[str] = Field(default_factory=list)


class PersonalizedRankingResult(BaseModel):
    content_item_id: str
    story_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    final_score: float
    explanation: RankingExplanation


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _matches(preferred: Iterable[str], actual: Iterable[str]) -> List[str]:
    actual_values = [_normalise(value) for value in actual]
    matched = []
    for value in preferred:
        normalised = _normalise(value)
        if normalised and any(
            normalised == candidate
            or normalised in candidate
            or candidate in normalised
            for candidate in actual_values
        ):
            matched.append(value)
    return matched


def freshness_score(
    published_at: Optional[datetime],
    now: Optional[datetime] = None,
    half_life_days: float = RANKING_FRESHNESS_HALF_LIFE_DAYS,
) -> float:
    if published_at is None:
        return 0.0
    if half_life_days <= 0:
        raise ValueError("freshness_half_life_days must be positive")
    current = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (current - published_at).total_seconds() / 86400)
    return max(0.0, min(1.0, math.exp(-math.log(2) * age_days / half_life_days)))


class PersonalizedRanker:
    def __init__(
        self,
        config: Optional[RankingConfig] = None,
        now: Optional[datetime] = None,
    ):
        self.config = config or RankingConfig()
        self.now = now

    def rank(
        self,
        candidates: Iterable[RankingCandidate],
        profile: Optional[UserProfile] = None,
    ) -> List[PersonalizedRankingResult]:
        profile = profile or UserProfile()
        scored = [self._score(candidate, profile) for candidate in candidates]
        representatives: Dict[str, PersonalizedRankingResult] = {}
        for result in scored:
            key = result.story_id or f"content:{result.content_item_id}"
            current = representatives.get(key)
            if current is None or (
                result.final_score,
                result.explanation.semantic_score,
                result.content_item_id,
            ) > (
                current.final_score,
                current.explanation.semantic_score,
                current.content_item_id,
            ):
                representatives[key] = result
        return sorted(
            representatives.values(),
            key=lambda item: (-item.final_score, -item.explanation.semantic_score,
                              item.content_item_id),
        )

    def _score(
        self, candidate: RankingCandidate, profile: UserProfile
    ) -> PersonalizedRankingResult:
        matched_topics = _matches(profile.preferred_topics, candidate.topics)
        matched_entities = _matches(profile.preferred_entities, candidate.entities)
        excluded_topics = _matches(profile.excluded_topics, candidate.topics)
        excluded_entities = _matches(profile.excluded_entities, candidate.entities)
        topic_score = len(matched_topics) / max(1, len(profile.preferred_topics))
        entity_score = len(matched_entities) / max(1, len(profile.preferred_entities))
        semantic_score = max(0.0, min(1.0, candidate.similarity))
        freshness = freshness_score(
            candidate.published_at, self.now, self.config.freshness_half_life_days
        )
        source_score = (
            candidate.source_quality
            if candidate.source_quality is not None
            else self.config.source_quality.get(
                _normalise(candidate.source_name or ""), 0.5
            )
        )
        source_score = max(0.0, min(1.0, source_score))
        exclusion_applied = bool(excluded_topics or excluded_entities)
        final_score = (
            self.config.semantic_weight * semantic_score
            + self.config.topic_weight * topic_score
            + self.config.entity_weight * entity_score
            + self.config.freshness_weight * freshness
            + self.config.source_weight * source_score
            - (self.config.exclusion_penalty if exclusion_applied else 0.0)
        )
        reasons = []
        if semantic_score >= 0.75:
            reasons.append("Strong semantic match")
        reasons.extend(f"Matches preferred topic: {item}" for item in matched_topics)
        reasons.extend(f"Matches preferred entity: {item}" for item in matched_entities)
        if freshness >= 0.5:
            reasons.append("Published recently")
        if exclusion_applied:
            reasons.append("Excluded topic or entity matched")
        explanation = RankingExplanation(
            matched_topics=matched_topics,
            matched_entities=matched_entities,
            semantic_score=semantic_score,
            topic_score=topic_score,
            entity_score=entity_score,
            freshness_score=freshness,
            source_score=source_score,
            exclusion_applied=exclusion_applied,
            final_score=final_score,
            reasons=reasons,
        )
        return PersonalizedRankingResult(
            content_item_id=candidate.content_item_id,
            story_id=candidate.story_id,
            title=candidate.title,
            url=candidate.url,
            final_score=final_score,
            explanation=explanation,
        )


rank_candidates = PersonalizedRanker().rank
