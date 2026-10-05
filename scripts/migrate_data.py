"""
NewsPilotAI — Phase 1 Data Migration
=====================================
Migrates data from the legacy per-source tables (youtube_videos, openai_articles,
anthropic_articles) into the unified ContentItem / Source tables.

This script is idempotent: running it multiple times will NOT create duplicate rows.

Usage:
    # Dry-run — see what would be migrated without touching the database
    python scripts/migrate_data.py --dry-run

    # Live run — apply the migration
    python scripts/migrate_data.py

Requirements:
    - POSTGRES_* environment variables must be set (or a .env file present)
    - psycopg2-binary must be installed
"""

import sys
import argparse
from pathlib import Path

# Ensure the project root is on the path regardless of where this is run from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import get_database_url
from app.database.models import (
    Base, Source, ContentItem, YouTubeVideo, OpenAIArticle, AnthropicArticle, Digest
)


def _count_legacy(session) -> dict:
    """Return counts of rows in legacy tables."""
    return {
        "youtube_videos": session.query(YouTubeVideo).count(),
        "openai_articles": session.query(OpenAIArticle).count(),
        "anthropic_articles": session.query(AnthropicArticle).count(),
        "digests_unlinked": session.query(Digest).filter(Digest.content_item_id.is_(None)).count(),
    }


def run_migration(dry_run: bool = False) -> None:
    url = get_database_url()
    engine = create_engine(url)

    # Create new tables if they don't exist yet (safe: CREATE TABLE IF NOT EXISTS)
    if not dry_run:
        Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # ---------------------------------------------------------------
        # Report legacy counts
        # ---------------------------------------------------------------
        counts = _count_legacy(session)
        print("\n=== NewsPilotAI Phase 1 Migration ===")
        print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE'}")
        print(f"\nLegacy rows found:")
        for table, n in counts.items():
            print(f"  {table}: {n}")

        # ---------------------------------------------------------------
        # 1. Ensure canonical Source rows exist
        # ---------------------------------------------------------------
        source_defs = [
            ("YouTube", "youtube"),
            ("OpenAI RSS", "rss"),
            ("Anthropic RSS", "rss"),
        ]
        sources: dict[str, Source] = {}
        for name, stype in source_defs:
            existing = session.query(Source).filter_by(name=name, source_type=stype).first()
            if existing:
                sources[name] = existing
                print(f"\n[Source] '{name}' already exists — skipping creation.")
            else:
                src = Source(name=name, source_type=stype)
                sources[name] = src
                if not dry_run:
                    session.add(src)
                print(f"\n[Source] Would create → '{name}' (type={stype})" if dry_run
                      else f"\n[Source] Created → '{name}' (type={stype})")

        if not dry_run:
            session.commit()

        # ---------------------------------------------------------------
        # 2. Migrate YouTubeVideo → ContentItem
        # ---------------------------------------------------------------
        videos = session.query(YouTubeVideo).all()
        yt_new = 0
        yt_skip = 0
        for v in videos:
            existing = session.query(ContentItem).filter_by(external_id=v.video_id).first()
            if existing:
                yt_skip += 1
                continue
            yt_new += 1
            if not dry_run:
                item = ContentItem(
                    source_id=sources["YouTube"].id,
                    external_id=v.video_id,
                    content_type="video",
                    title=v.title,
                    url=v.url,
                    description=v.description,
                    transcript=v.transcript,
                    published_at=v.published_at,
                    created_at=v.created_at,
                )
                session.add(item)

        print(f"\n[YouTube] Would migrate {yt_new} new videos, skip {yt_skip} already migrated."
              if dry_run
              else f"\n[YouTube] Migrated {yt_new} videos, skipped {yt_skip}.")

        # ---------------------------------------------------------------
        # 3. Migrate OpenAIArticle → ContentItem
        # ---------------------------------------------------------------
        openai_articles = session.query(OpenAIArticle).all()
        oa_new = 0
        oa_skip = 0
        for a in openai_articles:
            existing = session.query(ContentItem).filter_by(external_id=a.guid).first()
            if existing:
                oa_skip += 1
                continue
            oa_new += 1
            if not dry_run:
                item = ContentItem(
                    source_id=sources["OpenAI RSS"].id,
                    external_id=a.guid,
                    content_type="article",
                    title=a.title,
                    url=a.url,
                    description=a.description,
                    published_at=a.published_at,
                    created_at=a.created_at,
                )
                session.add(item)

        print(f"\n[OpenAI] Would migrate {oa_new} new articles, skip {oa_skip} already migrated."
              if dry_run
              else f"\n[OpenAI] Migrated {oa_new} articles, skipped {oa_skip}.")

        # ---------------------------------------------------------------
        # 4. Migrate AnthropicArticle → ContentItem
        # ---------------------------------------------------------------
        anthropic_articles = session.query(AnthropicArticle).all()
        an_new = 0
        an_skip = 0
        for a in anthropic_articles:
            existing = session.query(ContentItem).filter_by(external_id=a.guid).first()
            if existing:
                an_skip += 1
                continue
            an_new += 1
            if not dry_run:
                item = ContentItem(
                    source_id=sources["Anthropic RSS"].id,
                    external_id=a.guid,
                    content_type="article",
                    title=a.title,
                    url=a.url,
                    description=a.description,
                    raw_content=a.markdown,   # markdown → raw_content in new schema
                    published_at=a.published_at,
                    created_at=a.created_at,
                )
                session.add(item)

        print(f"\n[Anthropic] Would migrate {an_new} new articles, skip {an_skip} already migrated."
              if dry_run
              else f"\n[Anthropic] Migrated {an_new} articles, skipped {an_skip}.")

        if not dry_run:
            session.commit()

        # ---------------------------------------------------------------
        # 5. Link existing Digests to their ContentItem
        # ---------------------------------------------------------------
        unlinked_digests = session.query(Digest).filter(Digest.content_item_id.is_(None)).all()
        linked = 0
        not_found = 0
        for d in unlinked_digests:
            content_item = session.query(ContentItem).filter_by(external_id=d.article_id).first()
            if content_item:
                linked += 1
                if not dry_run:
                    d.content_item_id = content_item.id
            else:
                not_found += 1

        print(f"\n[Digests] Would link {linked} digests to ContentItems, {not_found} article_ids not found in ContentItems."
              if dry_run
              else f"\n[Digests] Linked {linked} digests, {not_found} could not be matched.")

        if not dry_run:
            session.commit()

        # ---------------------------------------------------------------
        # Summary
        # ---------------------------------------------------------------
        print("\n=== Summary ===")
        if dry_run:
            print(f"  YouTube videos to migrate : {yt_new}")
            print(f"  OpenAI articles to migrate: {oa_new}")
            print(f"  Anthropic articles to migrate: {an_new}")
            print(f"  Digests to link           : {linked}")
            print("\nDRY RUN complete. No data was changed.")
        else:
            print("Migration completed successfully!")

    except Exception as e:
        if not dry_run:
            session.rollback()
        print(f"\nMigration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NewsPilotAI Phase 1 migration: legacy tables → ContentItem"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what WOULD be migrated without changing any data.",
    )
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
