"""
NewsPilotAI — Phase 1 Import + Dependency Verification Script
=============================================================
Run this first to check that all dependencies and internal modules import
correctly without requiring a live PostgreSQL connection.

Usage:
    python scripts/verify_imports.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check(label: str, fn):
    try:
        result = fn()
        status = result if result is not None else "OK"
        print(f"  [PASS] {label}: {status}")
        return True
    except Exception as e:
        print(f"  [FAIL] {label}: {e}")
        return False


def main():
    print("\n=== NewsPilotAI Phase 1 Import Verification ===\n")
    all_ok = True

    # ── Third-party runtime dependencies ──────────────────────────────────
    print("── Third-party packages ──")
    checks = [
        ("feedparser",         lambda: __import__("feedparser") and "feedparser OK"),
        ("psycopg2",           lambda: __import__("psycopg2") and "psycopg2 OK"),
        ("sqlalchemy",         lambda: __import__("sqlalchemy") and "sqlalchemy OK"),
        ("openai",             lambda: __import__("openai") and "openai OK"),
        ("pydantic",           lambda: __import__("pydantic") and "pydantic OK"),
        ("python-dotenv",      lambda: __import__("dotenv") and "dotenv OK"),
        ("requests",           lambda: __import__("requests") and "requests OK"),
        ("beautifulsoup4",     lambda: __import__("bs4") and "bs4 OK"),
        ("markdownify",        lambda: __import__("markdownify") and "markdownify OK"),
        ("markdown",           lambda: __import__("markdown") and "markdown OK"),
        ("youtube-transcript-api", lambda: __import__("youtube_transcript_api") and "OK"),
    ]
    for label, fn in checks:
        if not check(label, fn):
            all_ok = False

    # ── Internal modules (no DB connection) ───────────────────────────────
    print("\n── Internal modules ──")

    def import_models():
        from app.database.models import Source, ContentItem, Digest
        return f"Source, ContentItem, Digest loaded"

    def import_repository():
        from app.database.repository import Repository
        return "Repository class loaded"

    def import_digest_agent():
        from app.agent.digest_agent import DigestAgent
        return "DigestAgent loaded"

    def import_curator_agent():
        from app.agent.curator_agent import CuratorAgent
        return "CuratorAgent loaded"

    def import_email_agent():
        from app.agent.email_agent import EmailAgent
        return "EmailAgent loaded"

    def import_youtube_scraper():
        from app.scrapers.youtube import YouTubeScraper
        return "YouTubeScraper loaded"

    def import_anthropic_scraper():
        from app.scrapers.anthropic import AnthropicScraper
        return "AnthropicScraper loaded"

    def import_openai_scraper():
        from app.scrapers.openai import OpenAIScraper
        return "OpenAIScraper loaded"

    def import_user_profile():
        from app.profiles.user_profile import get_user_profile, USER_PROFILE
        profile = get_user_profile()
        assert isinstance(profile, dict)
        assert "name" in profile
        return f"Profile for '{profile['name']}' loaded"

    def import_connection_nodbc():
        # Importing connection must NOT raise an error even without PostgreSQL
        from app.database.connection import get_database_url
        url = get_database_url()
        # Mask password for safety
        parts = url.split("@")
        safe = "****@" + parts[-1] if len(parts) > 1 else url
        return f"URL built: {safe}"

    internal_checks = [
        ("app.database.models",            import_models),
        ("app.database.repository",        import_repository),
        ("app.database.connection (no-DB)",import_connection_nodbc),
        ("app.agent.digest_agent",         import_digest_agent),
        ("app.agent.curator_agent",        import_curator_agent),
        ("app.agent.email_agent",          import_email_agent),
        ("app.scrapers.youtube",           import_youtube_scraper),
        ("app.scrapers.anthropic",         import_anthropic_scraper),
        ("app.scrapers.openai",            import_openai_scraper),
        ("app.profiles.user_profile",      import_user_profile),
    ]
    for label, fn in internal_checks:
        if not check(label, fn):
            all_ok = False

    # ── Database connectivity (optional — skipped if not configured) ──────
    print("\n── Database connectivity (informational — skipped if not configured) ──")
    try:
        from app.database.connection import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  [PASS] PostgreSQL connection: reachable")
    except Exception as e:
        print(f"  [INFO] PostgreSQL not reachable (safe to ignore for local import tests): {e}")

    # ── Final result ───────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    if all_ok:
        print("All checks passed. Phase 1 imports are healthy.")
    else:
        print("One or more checks FAILED. See [FAIL] lines above.")
    print("=" * 50 + "\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
