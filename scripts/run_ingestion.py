"""Run one ingestion pass."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runner import run_ingestion


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = run_ingestion()
    print(stats)
    return 1 if stats.failed_sources else 0


if __name__ == "__main__":
    raise SystemExit(main())
