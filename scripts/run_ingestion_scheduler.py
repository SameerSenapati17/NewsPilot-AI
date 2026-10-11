"""Run ingestion repeatedly until interrupted."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion_scheduler import IngestionScheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scheduler = IngestionScheduler()
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopping ingestion scheduler.")
        scheduler.stop()
