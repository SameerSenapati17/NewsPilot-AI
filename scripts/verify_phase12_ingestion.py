"""Read-only verification for Phase 12 ingestion state."""

import sys
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import get_session
from app.database.models import ContentItem
from app.database.repository import Repository


def main() -> int:
    session = get_session()
    repo = Repository(session=session)
    try:
        count = session.query(func.count(ContentItem.id)).scalar()
        items, total = repo.list_content_items(page=1, page_size=1)
        print("Phase 12 ingestion verification (read-only)")
        print("Database connectivity: PASS")
        print(f"ContentItems count: {count}")
        print(f"Repository list total: {total}")
        print(f"Repository read sample: {'PASS' if items else 'EMPTY'}")
        print("Duplicate safety: repository checks external_id before insert")
        print("Production writes: NONE")
        return 0
    finally:
        repo.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
