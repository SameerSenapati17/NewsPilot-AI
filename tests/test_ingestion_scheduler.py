import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion_scheduler import IngestionScheduler, get_ingestion_interval_minutes
from app.runner import IngestionRunStats, _run_ingestion


class TestIngestionScheduler(unittest.TestCase):
    def test_interval_configuration_and_validation(self):
        self.assertEqual(get_ingestion_interval_minutes(15), 15)
        with self.assertRaises(ValueError):
            get_ingestion_interval_minutes(0)
        with self.assertRaises(ValueError):
            get_ingestion_interval_minutes(-1)

    def test_run_once_returns_stats(self):
        expected = IngestionRunStats(sources_checked=8, new_items=3)
        scheduler = IngestionScheduler(
            interval_minutes=1, run_once=Mock(return_value=expected)
        )
        self.assertIs(scheduler.run_once(), expected)

    def test_overlapping_runs_are_skipped(self):
        entered = threading.Event()
        release = threading.Event()

        def blocking_run():
            entered.set()
            release.wait(1)
            return IngestionRunStats()

        scheduler = IngestionScheduler(interval_minutes=1, run_once=blocking_run)
        thread = threading.Thread(target=scheduler.run_once)
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertIsNone(scheduler.run_once())
        release.set()
        thread.join(1)

    def test_scheduler_stops_cleanly(self):
        scheduler = IngestionScheduler(
            interval_minutes=1,
            run_once=Mock(return_value=IngestionRunStats()),
        )
        with patch.object(
            scheduler._stop_event,
            "wait",
            side_effect=lambda _timeout: scheduler._stop_event.set(),
        ):
            thread = scheduler.start()
            scheduler.stop(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_scheduler_repeats_until_shutdown(self):
        calls = []
        scheduler = IngestionScheduler(
            interval_minutes=1,
            run_once=lambda: (calls.append(1) or IngestionRunStats()),
        )

        def wait_then_stop(_timeout):
            if len(calls) >= 2:
                scheduler._stop_event.set()

        with patch.object(scheduler._stop_event, "wait", side_effect=wait_then_stop):
            scheduler.run_forever()
        self.assertEqual(len(calls), 2)

    def test_one_shot_script_uses_reusable_ingestion_callable(self):
        from scripts import run_ingestion as script

        with patch.object(script, "run_ingestion") as run, patch("builtins.print"):
            run.return_value = IngestionRunStats()
            self.assertEqual(script.main(), 0)
        run.assert_called_once_with()

    def test_source_failure_isolated_and_stats_are_reported(self):
        good_a = Mock(source_name="Source A", source_type="rss")
        good_a.fetch.return_value = [Mock()]
        bad = Mock(source_name="Source B", source_type="rss")
        bad.fetch.side_effect = RuntimeError("network")
        good_c = Mock(source_name="Source C", source_type="rss")
        good_c.fetch.return_value = [Mock(), Mock()]
        repo = Mock()
        repo.session = Mock()
        repo.get_content_item_by_external_id.return_value = Mock()

        with patch("app.runner.Repository", return_value=repo), patch(
            "app.runner.registry.get_all",
            return_value=[good_a, bad, good_c],
        ), patch("app.runner.normalize", side_effect=lambda item: {"external_id": str(id(item))}):
            _, stats = _run_ingestion(process_ai=False)

        self.assertEqual(stats.sources_checked, 3)
        self.assertEqual(stats.items_fetched, 3)
        self.assertEqual(stats.failed_sources, 1)
        self.assertEqual(stats.failed_items, 1)
        self.assertEqual(stats.duplicates_skipped, 3)

    def test_repeated_existing_items_are_counted_as_duplicates(self):
        adapter = Mock(source_name="Source", source_type="rss")
        adapter.fetch.return_value = [Mock(), Mock()]
        repo = Mock()
        repo.session = Mock()
        repo.get_content_item_by_external_id.return_value = Mock()

        with patch("app.runner.Repository", return_value=repo), patch(
            "app.runner.registry.get_all", return_value=[adapter]
        ), patch(
            "app.runner.normalize",
            side_effect=lambda item: {"external_id": str(id(item))},
        ):
            _, first = _run_ingestion(process_ai=False)
            _, second = _run_ingestion(process_ai=False)

        self.assertEqual(first.new_items, 0)
        self.assertEqual(first.duplicates_skipped, 2)
        self.assertEqual(second.new_items, 0)
        self.assertEqual(second.duplicates_skipped, 2)


if __name__ == "__main__":
    unittest.main()
