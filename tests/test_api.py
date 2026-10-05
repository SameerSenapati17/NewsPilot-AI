import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient
    from app.api.main import app
    from app.api.dependencies import get_rag_service, get_repository, get_retrieval
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed")
class TestAPI(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.repository.list_content_items.return_value = ([], 0)
        self.repository.list_stories.return_value = ([], 0)
        self.repository.get_trend_records.return_value = []
        self.retrieval = Mock()
        self.retrieval.retrieve.return_value = []
        self.rag = Mock()
        self.rag.answer_question.return_value = Mock(
            answer="Grounded answer", sources=[]
        )
        app.dependency_overrides[get_repository] = lambda: self.repository
        app.dependency_overrides[get_retrieval] = lambda: self.retrieval
        app.dependency_overrides[get_rag_service] = lambda: self.rag
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "newspilotai-api")

    def test_news_and_pagination(self):
        response = self.client.get("/api/news?page=2&page_size=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page"], 2)
        self.repository.list_content_items.assert_called_once_with(2, 5, None, None)

    def test_stories(self):
        self.assertEqual(self.client.get("/api/stories").status_code, 200)

    def test_search_validation_and_zero_results(self):
        self.assertEqual(self.client.get("/api/search?q=   ").status_code, 400)
        self.assertEqual(self.client.get("/api/search?q=x&top_k=51").status_code, 422)
        self.assertEqual(self.client.get("/api/search?q=x").json()["results"], [])

    def test_ask_and_validation(self):
        response = self.client.post("/api/ask", json={"query": "question"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Grounded answer")
        self.assertEqual(self.client.post("/api/ask", json={"query": ""}).status_code, 422)

    def test_trends_and_personalized_validation(self):
        self.assertEqual(self.client.get("/api/trends").status_code, 200)
        self.assertEqual(self.client.get("/api/personalized").status_code, 400)

    def test_openapi_and_cors(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/search", schema["paths"])
        response = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
