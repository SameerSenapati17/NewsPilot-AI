import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import backfill_enrichment


def item(item_id: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=item_id,
        title=title,
        published_at=datetime(2026, 1, 1),
        source=SimpleNamespace(name="Test Source"),
    )


class TestBackfillEnrichment(unittest.TestCase):
    def repo(self, items, enriched=()):
        repo = Mock()
        repo.session.query.return_value.order_by.return_value.all.return_value = items
        repo.get_content_enrichment.side_effect = (
            lambda content_item_id: object() if content_item_id in enriched else None
        )
        return repo

    def test_dry_run_makes_no_provider_calls(self):
        repo = self.repo([item("1", "Pending")])
        with patch.object(backfill_enrichment, "MistralEnrichmentProvider") as provider:
            summary = backfill_enrichment.run_backfill(repo, dry_run=True)
        provider.assert_not_called()
        self.assertEqual(summary.calls_attempted, 0)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(summary.scanned, 1)

    def test_already_enriched_items_are_skipped(self):
        repo = self.repo([item("1", "Done")], enriched={"1"})
        provider = Mock()
        with patch.object(backfill_enrichment, "enrich_content_item") as helper:
            summary = backfill_enrichment.run_backfill(repo, provider=provider)
        helper.assert_not_called()
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.enriched, 0)

    def test_pending_items_use_existing_helper(self):
        first, second = item("1", "First"), item("2", "Second")
        repo = self.repo([first, second])
        provider = Mock()
        with patch.object(
            backfill_enrichment, "enrich_content_item", return_value=True
        ) as helper:
            summary = backfill_enrichment.run_backfill(repo, provider=provider)
        self.assertEqual(helper.call_count, 2)
        helper.assert_any_call(repo, first, provider)
        helper.assert_any_call(repo, second, provider)
        self.assertEqual(summary.enriched, 2)
        self.assertEqual(summary.calls_attempted, 2)

    def test_failed_item_does_not_stop_later_items(self):
        first, second = item("1", "First"), item("2", "Second")
        repo = self.repo([first, second])
        provider = Mock()
        with patch.object(
            backfill_enrichment,
            "enrich_content_item",
            side_effect=[False, True],
        ) as helper:
            summary = backfill_enrichment.run_backfill(repo, provider=provider)
        self.assertEqual(helper.call_count, 2)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.enriched, 1)

    def test_missing_key_fails_before_processing(self):
        repo = self.repo([item("1", "Pending")])
        with patch.object(backfill_enrichment, "MISTRAL_API_KEY", ""):
            with self.assertRaisesRegex(RuntimeError, "MISTRAL_API_KEY"):
                backfill_enrichment.run_backfill(repo)


if __name__ == "__main__":
    unittest.main()
