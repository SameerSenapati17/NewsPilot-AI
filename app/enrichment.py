import os
import math
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List

try:
    from openai import OpenAI
except ImportError:  # Optional legacy provider dependency.
    OpenAI = None
from pydantic import BaseModel, Field

from .config import (
    ENRICHMENT_MAX_CONTENT_CHARS,
    ENRICHMENT_MODEL,
    ENRICHMENT_PROMPT_VERSION,
)
from .database.models import ContentItem
from .mistral import MistralLLMProvider


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


ENRICHMENT_PROMPT = f"""You classify and enrich one piece of AI-related source content.
Use only the supplied content and source metadata. Return JSON only, with exactly
these keys and no extra keys: category, topics, entities, importance, novelty,
technical_depth, impact, source_quality.
category must be exactly one of: {", ".join(category.value for category in EnrichmentCategory)}.
topics and entities must be JSON arrays of strings. importance, novelty,
technical_depth, impact, and source_quality must each be decimal numbers from
0.0 to 1.0 inclusive. Do not use a 1-10 scale or the plural key "categories".
Do not invent entities or topics. Use "other" when no controlled category fits.
Do not summarize a Story, personalize the result, or make recommendations."""

_SCORE_FIELDS = (
    "importance", "novelty", "technical_depth", "impact", "source_quality"
)
_CATEGORY_ALIASES = {
    "ai": EnrichmentCategory.INDUSTRY.value,
    "artificial intelligence": EnrichmentCategory.INDUSTRY.value,
    "nlp": EnrichmentCategory.RESEARCH.value,
    "natural language processing": EnrichmentCategory.RESEARCH.value,
}


def _normalize_category(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("enrichment category must be a string")
    normalized = value.strip().lower().replace(" ", "_")
    valid = {category.value for category in EnrichmentCategory}
    if normalized in valid:
        return normalized
    alias = _CATEGORY_ALIASES.get(value.strip().lower())
    if alias is not None:
        return alias
    raise ValueError(f"unsupported enrichment category: {value!r}")


def _normalize_score(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    if 0.0 <= value <= 1.0:
        return float(value)
    if 1.0 < value <= 10.0:
        return float(value) / 10.0
    raise ValueError(f"{field} must be between 0 and 1 or a 1-10 score")


def normalize_mistral_enrichment_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Mistral enrichment must be a JSON object")
    allowed = {"category", "categories", "topics", "entities", *_SCORE_FIELDS}
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError(f"unexpected enrichment keys: {sorted(unexpected)}")
    normalized = dict(payload)
    if "category" not in normalized:
        categories = normalized.pop("categories", None)
        if not isinstance(categories, list) or not categories:
            raise ValueError("enrichment requires a singular category")
        mapped = []
        for category in categories:
            try:
                mapped.append(_normalize_category(category))
            except ValueError:
                continue
        if not mapped:
            raise ValueError("categories contain no supported enrichment category")
        normalized["category"] = mapped[0]
    elif "categories" in normalized:
        raise ValueError("use category instead of categories")
    else:
        normalized["category"] = _normalize_category(normalized["category"])
    for field in _SCORE_FIELDS:
        if field not in normalized:
            raise ValueError(f"missing enrichment field: {field}")
        normalized[field] = _normalize_score(normalized[field], field)
    return normalized


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
        if client is None and OpenAI is None:
            raise RuntimeError("openai is only required for the legacy provider")
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


class MistralEnrichmentProvider(EnrichmentProvider):
    def __init__(
        self,
        client: MistralLLMProvider | None = None,
        model_name: str | None = None,
        prompt_version: str = ENRICHMENT_PROMPT_VERSION,
    ):
        self.client = client or (
            MistralLLMProvider(model=model_name)
            if model_name
            else MistralLLMProvider()
        )
        self.model_name = model_name or self.client.model
        self.prompt_version = prompt_version

    def enrich(self, content_item: ContentItem) -> ContentEnrichmentResult:
        payload = self.client.complete_json(
            ENRICHMENT_PROMPT
            + "\nReturn only a JSON object matching the enrichment fields.",
            build_enrichment_input(content_item),
        )
        try:
            normalized = normalize_mistral_enrichment_payload(payload)
            return ContentEnrichmentResult.model_validate(normalized)
        except Exception as exc:
            raise RuntimeError("Mistral enrichment did not match the schema") from exc
