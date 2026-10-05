"""In-process API verification using dependency overrides and temporary data."""

import sys
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import get_rag_service, get_repository, get_retrieval
from app.api.main import app


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main():
    repository = Mock()
    repository.list_content_items.return_value = ([], 0)
    repository.list_stories.return_value = ([], 0)
    repository.get_trend_records.return_value = []
    retrieval = Mock()
    retrieval.retrieve.return_value = []
    rag = Mock()
    rag.answer_question.return_value = Mock(answer="Insufficient context.", sources=[])
    app.dependency_overrides.update({
        get_repository: lambda: repository,
        get_retrieval: lambda: retrieval,
        get_rag_service: lambda: rag,
    })
    try:
        with TestClient(app) as client:
            check(client.get("/api/health").status_code == 200, "health endpoint")
            openapi = client.get("/openapi.json").json()
            for path in ("/api/news", "/api/stories", "/api/search",
                         "/api/ask", "/api/trends", "/api/personalized"):
                check(path in openapi["paths"], f"route exists: {path}")
            check(client.get("/api/search?q=anything").json()["results"] == [],
                  "search zero results")
            check(client.get("/api/trends").status_code == 200, "trends endpoint")
            check(client.get("/api/news").status_code == 200, "news endpoint")
            check(client.get("/api/stories").status_code == 200, "stories endpoint")
            ask = client.post("/api/ask", json={"query": "anything"})
            check(ask.status_code == 200 and "sources" in ask.json(),
                  "RAG response source structure")
            check(client.get("/api/personalized").status_code == 400,
                  "personalized validation")
        print("[PASS] Phase 10 API verification completed")
        return 0
    except Exception as exc:
        print(f"[FAIL] Phase 10 API verification: {exc}")
        return 1
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    raise SystemExit(main())
