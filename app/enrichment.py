import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, List

from openai import OpenAI
from pydantic import BaseModel, Field

from .config import (
    ENRICHMENT_MAX_CONTENT_CHARS,
    ENRICHMENT_MODEL,
    ENRICHMENT_PROMPT_VERSION,
)
from .database.models import ContentItem


class EnrichmentCategory(str, Enum):
    RESEARCH = "research"
    PRODUCT = "product"
    MODEL_RELEASE = "model_release"
    COMPANY = "company"
    FUNDING = "funding"
    POLICY = "policy"
    TUTORIAL = "tutorial"
    BENCHMARK = "benchmark"
    PAPER = "paper"
    SECURITY = "security"
    INDUSTRY = "industry"
    OTHER = "other"


class ContentEnrichmentResult(BaseModel):
    category: EnrichmentCategory
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    importance: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    technical_depth: float = Field(ge=0.0, le=1.0)
    impact: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)


ENRICHMENT_PROMPT = """You classify and enrich one piece of AI-related source content.
Use only the supplied content and source metadata. Return structured data only.
Do not invent entities or topics. Use "other" when no category fits.
Score importance by likely significance, novelty by how new or distinct the
development appears from the supplied content, technical_depth by technical
complexity, impact by potential effect on AI/ML/software/industry, and
source_quality by the supplied source information. Do not summarize a Story,
personalize the result, or make recommendations."""


def build_enrichment_input(
    content_item: ContentItem, max_chars: int = ENRICHMENT_MAX_CONTENT_CHARS
) -> str:
    body = content_item.raw_content or content_item.transcript or content_item.description or ""
    metadata = (
        f"Title: {content_item.title}\n"
        f"Source: {content_item.source.name}\n"
        f"Source reliability: {content_item.source.reliability_score}\n"
        f"Content type: {content_item.content_type}\n"
        f"Published at: {content_item.published_at.isoformat()}\n"
        f"Description/body:\n"
    )
    if max_chars <= 0:
        return ""
    if len(metadata) >= max_chars:
        return metadata[:max_chars]
    return metadata + body[: max_chars - len(metadata)]


class EnrichmentProvider(ABC):
    model_name: str
    prompt_version: str

    @abstractmethod
    def enrich(self, content_item: ContentItem) -> ContentEnrichmentResult:
        raise NotImplementedError


class OpenAIEnrichmentProvider(EnrichmentProvider):
    def __init__(
        self,
        client: Any = None,
        model_name: str = ENRICHMENT_MODEL,
        prompt_version: str = ENRICHMENT_PROMPT_VERSION,
    ):
        self.client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model_name = model_name
        self.prompt_version = prompt_version

    def enrich(self, content_item: ContentItem) -> ContentEnrichmentResult:
        response = self.client.responses.parse(
            model=self.model_name,
            instructions=ENRICHMENT_PROMPT,
            temperature=0,
            input=build_enrichment_input(content_item),
            text_format=ContentEnrichmentResult,
        )
        result = response.output_parsed
        if result is None:
            raise RuntimeError("OpenAI returned no structured enrichment result")
        return result
