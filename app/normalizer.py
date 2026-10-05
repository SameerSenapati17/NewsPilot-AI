from typing import Dict, Any, Union
from app.scrapers.youtube import ChannelVideo
from app.scrapers.openai import OpenAIArticle
from app.scrapers.anthropic import AnthropicArticle

def normalize_youtube_video(video: ChannelVideo) -> Dict[str, Any]:
    return {
        "external_id": video.video_id,
        "content_type": "video",
        "title": video.title,
        "url": video.url,
        "published_at": video.published_at,
        "description": video.description,
        "transcript": video.transcript
    }

def normalize_openai_article(article: OpenAIArticle) -> Dict[str, Any]:
    return {
        "external_id": article.guid,
        "content_type": "article",
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at,
        "description": article.description,
    }

def normalize_anthropic_article(article: AnthropicArticle) -> Dict[str, Any]:
    return {
        "external_id": article.guid,
        "content_type": "article",
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at,
        "description": article.description,
    }

def normalize(item: Union[ChannelVideo, OpenAIArticle, AnthropicArticle]) -> Dict[str, Any]:
    if isinstance(item, ChannelVideo):
        return normalize_youtube_video(item)
    elif isinstance(item, OpenAIArticle):
        return normalize_openai_article(item)
    elif isinstance(item, AnthropicArticle):
        return normalize_anthropic_article(item)
    else:
        raise ValueError(f"Unknown item type: {type(item)}")
