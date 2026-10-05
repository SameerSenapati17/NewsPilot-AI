import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field, model_validator

from .config import (
    TREND_ACTIVITY_WEIGHT,
    TREND_EMERGING_THRESHOLD,
    TREND_GROWTH_WEIGHT,
    TREND_MIN_RECENT_CONTENT,
    TREND_MIN_RECENT_STORIES,
    TREND_PREVIOUS_DAYS,
    TREND_RECENCY_WEIGHT,
    TREND_RECENT_DAYS,
    TREND_SOURCE_DIVERSITY_WEIGHT,
    TREND_STORY_DIVERSITY_WEIGHT,
)


class TrendConfig(BaseModel):
    recent_days: int = TREND_RECENT_DAYS
    previous_days: int = TREND_PREVIOUS_DAYS
    min_recent_content: int = TREND_MIN_RECENT_CONTENT
    min_recent_stories: int = TREND_MIN_RECENT_STORIES
    growth_weight: float = TREND_GROWTH_WEIGHT
    activity_weight: float = TREND_ACTIVITY_WEIGHT
    story_diversity_weight: float = TREND_STORY_DIVERSITY_WEIGHT
    source_diversity_weight: float = TREND_SOURCE_DIVERSITY_WEIGHT
    recency_weight: float = TREND_RECENCY_WEIGHT
    emerging_threshold: float = TREND_EMERGING_THRESHOLD

    @model_validator(mode="after")
    def validate_values(self):
        if self.recent_days <= 0 or self.previous_days <= 0:
            raise ValueError("trend windows must be positive")
        if self.min_recent_content < 0 or self.min_recent_stories < 0:
            raise ValueError("minimum activity must not be negative")
        weights = (
            self.growth_weight,
            self.activity_weight,
            self.story_diversity_weight,
            self.source_diversity_weight,
            self.recency_weight,
        )
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError("trend weights must be non-negative and non-zero")
        if not 0 <= self.emerging_threshold <= 1:
            raise ValueError("emerging threshold must be between 0 and 1")
        return self


class TrendMetrics(BaseModel):
    recent_content_count: int
    previous_content_count: int
    recent_story_count: int
    previous_story_count: int
    recent_source_count: int
    previous_source_count: int
    growth_rate: float
    growth_score: float
    activity_score: float
    story_diversity_score: float
    source_diversity_score: float
    recency_score: float
    recent_window_start: datetime
    recent_window_end: datetime
    previous_window_start: datetime
    previous_window_end: datetime


class TrendResult(BaseModel):
    topic: str
    score: float
    is_emerging: bool
    metrics: TrendMetrics
    explanation: str


def normalize_topic(topic: str) -> str:
    return " ".join(re.sub(r"\s+", " ", topic.strip().lower()).split())


def calculate_growth(previous_count: int, recent_count: int) -> float:
    if previous_count <= 0:
        return 1.0 if recent_count > 0 else 0.0
    if recent_count <= 0:
        return 0.0
    return max(0.0, min(1.0, (recent_count - previous_count) / previous_count))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _story_key(record: Dict[str, Any]) -> str:
    return record.get("story_id") or f"content:{record['content_item_id']}"


def _activity_score(count: int) -> float:
    return count / (count + 10.0)


def _diversity_score(distinct_count: int, content_count: int) -> float:
    if content_count <= 0:
        return 0.0
    return max(0.0, min(1.0, distinct_count / content_count))


def _recency_score(records: Sequence[Dict[str, Any]], end_time: datetime, days: int) -> float:
    if not records:
        return 0.0
    values = []
    for record in records:
        age = max(0.0, (end_time - _aware(record["published_at"])).total_seconds() / 86400)
        values.append(math.exp(-math.log(2) * age / max(1, days)))
    return sum(values) / len(values)


class TrendDetector:
    def __init__(self, repository: Any = None, config: Optional[TrendConfig] = None):
        self.repository = repository
        self.config = config or TrendConfig()

    def detect_trends(
        self,
        records: Optional[Iterable[Dict[str, Any]]] = None,
        end_time: Optional[datetime] = None,
        recent_days: Optional[int] = None,
        previous_days: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> List[TrendResult]:
        config = self.config.model_copy(
            update={
                "recent_days": recent_days or self.config.recent_days,
                "previous_days": previous_days or self.config.previous_days,
            }
        )
        end = _aware(end_time or datetime.now(timezone.utc))
        recent_start = end - timedelta(days=config.recent_days)
        previous_start = recent_start - timedelta(days=config.previous_days)
        if records is None:
            if self.repository is None:
                raise ValueError("repository is required when records are not supplied")
            records = self.repository.get_trend_records(previous_start, end)
        records = list(records)
        recent = [r for r in records if recent_start <= _aware(r["published_at"]) < end]
        previous = [
            r for r in records
            if previous_start <= _aware(r["published_at"]) < recent_start
        ]
        topics: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for period, period_records in (("recent", recent), ("previous", previous)):
            for record in period_records:
                for raw_topic in record.get("topics") or []:
                    topic = normalize_topic(raw_topic)
                    if topic:
                        topics.setdefault(topic, {}).setdefault(period, []).append(record)

        results = []
        for topic, periods in topics.items():
            recent_records = periods.get("recent", [])
            previous_records = periods.get("previous", [])
            recent_story_count = len({_story_key(r) for r in recent_records})
            previous_story_count = len({_story_key(r) for r in previous_records})
            recent_sources = {r.get("source_id") or r.get("source_name") for r in recent_records}
            previous_sources = {r.get("source_id") or r.get("source_name") for r in previous_records}
            growth_rate = calculate_growth(len(previous_records), len(recent_records))
            story_diversity = _diversity_score(recent_story_count, len(recent_records))
            source_diversity = _diversity_score(len(recent_sources), len(recent_records))
            metrics = TrendMetrics(
                recent_content_count=len(recent_records),
                previous_content_count=len(previous_records),
                recent_story_count=recent_story_count,
                previous_story_count=previous_story_count,
                recent_source_count=len(recent_sources),
                previous_source_count=len(previous_sources),
                growth_rate=growth_rate,
                growth_score=growth_rate,
                activity_score=_activity_score(len(recent_records)),
                story_diversity_score=story_diversity,
                source_diversity_score=source_diversity,
                recency_score=_recency_score(recent_records, end, config.recent_days),
                recent_window_start=recent_start,
                recent_window_end=end,
                previous_window_start=previous_start,
                previous_window_end=recent_start,
            )
            score = (
                config.growth_weight * metrics.growth_score
                + config.activity_weight * metrics.activity_score
                + config.story_diversity_weight * metrics.story_diversity_score
                + config.source_diversity_weight * metrics.source_diversity_score
                + config.recency_weight * metrics.recency_score
            ) / sum(
                (
                    config.growth_weight,
                    config.activity_weight,
                    config.story_diversity_weight,
                    config.source_diversity_weight,
                    config.recency_weight,
                )
            )
            score = max(0.0, min(1.0, score))
            is_emerging = (
                len(recent_records) >= config.min_recent_content
                and recent_story_count >= config.min_recent_stories
                and score >= config.emerging_threshold
                and growth_rate > 0
            )
            explanation = (
                f"{topic} activity changed from {len(previous_records)} to "
                f"{len(recent_records)} content items across "
                f"{len(recent_sources)} sources and {recent_story_count} stories "
                f"in the recent {config.recent_days}-day window."
            )
            results.append(TrendResult(
                topic=topic,
                score=score,
                is_emerging=is_emerging,
                metrics=metrics,
                explanation=explanation,
            ))
        results.sort(key=lambda result: (-result.score, result.topic))
        return results[:top_k] if top_k is not None else results


def detect_trends(*args, **kwargs) -> List[TrendResult]:
    return TrendDetector().detect_trends(*args, **kwargs)
