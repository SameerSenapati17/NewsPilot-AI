import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.smoke_test_enrichment_rich_input import _select_rich_arxiv_item


class TestRichEnrichmentSmokeSelection(unittest.TestCase):
    def test_selects_newest_arxiv_item_with_description(self):
        items = [
            SimpleNamespace(
                id="older",
                published_at=datetime(2026, 1, 1),
                description="older abstract",
                source=SimpleNamespace(name="arXiv AI/ML"),
            ),
            SimpleNamespace(
                id="newest",
                published_at=datetime(2026, 2, 1),
                description="newer abstract",
                source=SimpleNamespace(name="arXiv AI/ML"),
            ),
            SimpleNamespace(
                id="title-only",
                published_at=datetime(2026, 3, 1),
                description=" ",
                source=SimpleNamespace(name="arXiv AI/ML"),
            ),
            SimpleNamespace(
                id="other-source",
                published_at=datetime(2026, 4, 1),
                description="content",
                source=SimpleNamespace(name="OpenAI RSS"),
            ),
        ]

        selected = _select_rich_arxiv_item(items)
        self.assertEqual(selected.id, "newest")


if __name__ == "__main__":
    unittest.main()
