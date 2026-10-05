import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.init_db import init_db
from sqlalchemy import create_engine
from app.database.models import Base

class TestInitDB(unittest.TestCase):
    @patch('scripts.init_db.get_engine')
    def test_init_db(self, mock_get_engine):
        # Use an in-memory sqlite engine for testing
        test_engine = create_engine("sqlite:///:memory:")
        mock_get_engine.return_value = test_engine
        
        # Run init_db
        init_db()
        
        # Verify tables were created
        from sqlalchemy import inspect
        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        
        # Check for both new and legacy tables
        expected_tables = {
            'sources', 'content_items', 'digests', 
            'youtube_videos', 'openai_articles', 'anthropic_articles',
            'content_enrichments', 'content_embeddings', 'content_embeddings'
        }
        self.assertTrue(expected_tables.issubset(set(tables)))

if __name__ == "__main__":
    unittest.main()
