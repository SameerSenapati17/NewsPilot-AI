from collections.abc import Generator

from fastapi import Depends

from ..database.repository import Repository
from ..embeddings import OpenAIEmbeddingProvider
from ..rag import OpenAIGroundedAnswerProvider, RAGService
from ..retrieval import SemanticRetrieval


def get_repository() -> Generator[Repository, None, None]:
    repository = Repository()
    try:
        yield repository
    finally:
        repository.session.close()


def get_retrieval(repository: Repository = Depends(get_repository)):
    return SemanticRetrieval(repository, OpenAIEmbeddingProvider())


def get_rag_service(retrieval=Depends(get_retrieval)):
    return RAGService(retrieval, OpenAIGroundedAnswerProvider())
