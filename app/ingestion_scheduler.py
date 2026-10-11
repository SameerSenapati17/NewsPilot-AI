"""Lightweight repeated ingestion scheduler."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from .config import NEWS_INGESTION_INTERVAL_MINUTES
from .runner import IngestionRunStats
from .automated_pipeline import run_automated_pipeline

logger = logging.getLogger(__name__)


def get_ingestion_interval_minutes(value: Optional[int] = None) -> int:
    interval = (
        NEWS_INGESTION_INTERVAL_MINUTES if value is None else value
    )
    if interval <= 0:
        raise ValueError("NEWS_INGESTION_INTERVAL_MINUTES must be positive")
    return interval


class IngestionScheduler:
    def __init__(
        self,
        interval_minutes: Optional[int] = None,
        run_once: Callable[[], IngestionRunStats] = run_automated_pipeline,
    ):
        self.interval_minutes = get_ingestion_interval_minutes(interval_minutes)
        self._run_once_callable = run_once
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def run_once(self) -> Optional[IngestionRunStats]:
        if not self._run_lock.acquire(blocking=False):
            logger.warning("Ingestion run already in progress; skipping overlap.")
            return None
        try:
            try:
                stats = self._run_once_callable()
            except Exception:
                logger.exception("Ingestion run failed; scheduler will continue.")
                return None
            logger.info(
                "Ingestion run: sources=%s successful=%s fetched=%s new=%s duplicates=%s "
                "failures=%s duration=%.2fs",
                stats.sources_checked,
                stats.successful_sources,
                stats.items_fetched,
                stats.new_items,
                stats.duplicates_skipped,
                stats.failed_items,
                stats.duration_seconds,
            )
            return stats
        finally:
            self._run_lock.release()

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            logger.info(
                "Next ingestion run in %s minutes.", self.interval_minutes
            )
            self._stop_event.wait(self.interval_minutes * 60)

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run_forever,
            name="newspilot-ingestion",
            daemon=False,
        )
        self._thread.start()
        return self._thread

    def stop(self, timeout: Optional[float] = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
