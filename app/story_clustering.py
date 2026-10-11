import re
from datetime import datetime
from typing import Iterable, Set

from .config import (
    STORY_MATCHING_HIGH_THRESHOLD,
    STORY_MATCHING_WINDOW_HOURS,
)
from .database.models import ContentItem, Story
from .database.repository import Repository

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "for", "from", "in", "is", "of",
    "on", "or", "the", "to", "with",
}


def normalize_title(title: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {token for token in tokens if token not in STOPWORDS}


def title_similarity(left: str, right: str) -> float:
    left_tokens = normalize_title(left)
    right_tokens = normalize_title(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _story_title(story: Story, content_items: Iterable[ContentItem]) -> str:
    return story.title or next(iter(content_items)).title


def cluster_content_item(
    repo: Repository,
    content_item: ContentItem,
    window_hours: int = STORY_MATCHING_WINDOW_HOURS,
    high_threshold: float = STORY_MATCHING_HIGH_THRESHOLD,
) -> Story:
    existing = getattr(content_item, "story_content", None)
    if existing is not None:
        story = repo.get_story(existing.story_id)
        if story is None:
            raise ValueError("ContentItem references a missing Story")
        return story

    candidates = repo.find_candidate_stories(content_item.published_at, window_hours)
    best_story = None
    best_score = 0.0
    for candidate in candidates:
        candidate_items = repo.get_story_content_items(candidate.id)
        if not candidate_items:
            continue
        score = max(
            title_similarity(content_item.title, item.title)
            for item in candidate_items
        )
        if score > best_score:
            best_story, best_score = candidate, score

    story = best_story if best_story is not None and best_score >= high_threshold else repo.create_story(
        content_item.title, content_item.published_at
    )
    repo.attach_content_item_to_story(story.id, content_item.id)
    story.last_updated_at = max(story.last_updated_at, content_item.published_at)
    repo.session.commit()
    return story
