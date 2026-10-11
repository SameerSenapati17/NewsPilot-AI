"""Process missing enrichment and embeddings for existing ContentItems."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.repository import Repository
from app.embeddings import LocalSentenceTransformerEmbeddingProvider
from app.config import MISTRAL_API_KEY
from app.intelligence_processing import process_pending_intelligence
from app.runner import initialize_enrichment_provider


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process missing enrichment and embeddings."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report pending work without providers or database writes.",
    )
    return parser.parse_args()


def _print_summary(summary) -> None:
    print(f"Items examined: {summary.items_examined}")
    print(f"Items with enrichment already present: {summary.enrichment_present}")
    print(f"Pending enrichments: {summary.enrichments_pending}")
    print(f"Enrichments successfully created: {summary.enrichments_created}")
    print(f"Enrichment failures: {summary.enrichment_failures}")
    print(f"Items with embeddings already present: {summary.embeddings_present}")
    print(f"Pending embeddings: {summary.embeddings_pending}")
    print(f"Embeddings successfully created: {summary.embeddings_created}")
    print(f"Embedding failures: {summary.embedding_failures}")
    print(f"Items skipped: {summary.items_skipped}")
    for reason, count in sorted(summary.skip_reasons.items()):
        print(f"  skipped ({reason}): {count}")


def main() -> int:
    args = _args()
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    repo = Repository()
    try:
        if args.dry_run:
            summary = process_pending_intelligence(repo, dry_run=True)
            _print_summary(summary)
            return 0

        enrichment_provider = initialize_enrichment_provider()
        embedding_provider = None
        embedding_provider_error = None
        try:
            embedding_provider = LocalSentenceTransformerEmbeddingProvider()
        except Exception as exc:
            embedding_provider_error = exc
            print(
                "Embedding provider could not be initialized; embeddings "
                "will remain pending.",
                file=sys.stderr,
            )
        if enrichment_provider is None and MISTRAL_API_KEY:
            print(
                "Mistral enrichment provider could not be initialized; "
                "enrichment will remain pending.",
                file=sys.stderr,
            )
        summary = process_pending_intelligence(
            repo,
            enrichment_provider=enrichment_provider,
            embedding_provider=embedding_provider,
        )
        _print_summary(summary)
        if (
            summary.enrichment_failures
            or summary.embedding_failures
            or summary.skip_reasons.get("enrichment provider unavailable", 0) > 0
            or summary.skip_reasons.get("embedding provider unavailable", 0) > 0
            or embedding_provider_error is not None
        ):
            return 1
        return 0
    finally:
        repo.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
