import os
from abc import ABC, abstractmethod
from typing import Any, List

try:
    from openai import OpenAI
except ImportError:  # Optional legacy provider dependency.
    OpenAI = None
from pydantic import BaseModel

from .rag_context import ContextSource, RAGContext, build_context
from .retrieval import SemanticRetrieval
from .config import RAG_MODEL, RAG_MAX_CONTEXT_ITEMS, RAG_MAX_CONTEXT_CHARS
from .mistral import MistralLLMProvider


class RAGAnswer(BaseModel):
    answer: str
    sources: List[ContextSource]


GROUNDED_ANSWER_PROMPT = """Answer the user's question using only the supplied
retrieved context. Do not invent facts, URLs, citations, or knowledge outside
the context. If the context is insufficient, say so clearly. Cite sources
using the provided content item identifiers."""


class GroundedAnswerProvider(ABC):
    @abstractmethod
    def answer(self, query: str, context: RAGContext) -> RAGAnswer:
        raise NotImplementedError


class OpenAIGroundedAnswerProvider(GroundedAnswerProvider):
    def __init__(self, client: Any = None, model: str = RAG_MODEL):
        if client is None and OpenAI is None:
            raise RuntimeError("openai is only required for the legacy provider")
        self.client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def answer(self, query: str, context: RAGContext) -> RAGAnswer:
        response = self.client.responses.parse(
            model=self.model,
            instructions=GROUNDED_ANSWER_PROMPT,
            temperature=0,
            input=f"Question: {query}\n\nRetrieved context:\n{context.context_text}",
            text_format=RAGAnswer,
        )
        result = response.output_parsed
        if result is None:
            raise RuntimeError("Answer provider returned no structured answer")
        return RAGAnswer(answer=result.answer, sources=context.sources)


class MistralGroundedAnswerProvider(GroundedAnswerProvider):
    def __init__(self, client: MistralLLMProvider | None = None):
        self.client = client or MistralLLMProvider()

    def answer(self, query: str, context: RAGContext) -> RAGAnswer:
        payload = self.client.complete_json(
            GROUNDED_ANSWER_PROMPT
            + '\nReturn a JSON object with one string field named "answer".',
            f"Question: {query}\n\nRetrieved context:\n{context.context_text}",
        )
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Mistral returned no grounded answer")
        return RAGAnswer(answer=answer, sources=context.sources)


class RAGService:
    def __init__(
        self,
        retrieval: SemanticRetrieval,
        answer_provider: GroundedAnswerProvider,
        max_context_items: int = RAG_MAX_CONTEXT_ITEMS,
        max_context_chars: int = RAG_MAX_CONTEXT_CHARS,
    ):
        self.retrieval = retrieval
        self.answer_provider = answer_provider
        self.max_context_items = max_context_items
        self.max_context_chars = max_context_chars

    def answer_question(self, query: str, top_k: int = 8) -> RAGAnswer:
        if not query or not query.strip():
            raise ValueError("Question must not be empty")
        results = self.retrieval.retrieve(query, top_k=top_k)
        context = build_context(
            query, results, self.max_context_items, self.max_context_chars
        )
        if not context.sources:
            return RAGAnswer(
                answer="The available context is insufficient to answer this question.",
                sources=[],
            )
        return self.answer_provider.answer(query, context)
