"""
NewsPilotAI — Database Initialization
=====================================
Initializes the PostgreSQL database by creating all tables defined in models.py.
This includes the new Source and ContentItem tables, as well as the temporary
legacy tables (YouTubeVideo, OpenAIArticle, AnthropicArticle) required for 
migration compatibility.

Safe to run multiple times (idempotent: uses CREATE TABLE IF NOT EXISTS).

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

# Ensure the project root is on the path regardless of where this is run from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.connection import get_engine
from app.config import EMBEDDING_DIMENSIONS
from app.database.models import Base
from sqlalchemy import text

def init_db():
    print("Initializing NewsPilotAI database...")
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            available = connection.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            ).first()
            if available is None:
                raise RuntimeError(
                    "pgvector is unavailable; install/enable the PostgreSQL vector "
                    "extension before initializing the Phase 6 schema."
                )
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            existing_dimension = connection.execute(text("""
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'content_embeddings'
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
            """)).scalar()
            expected_type = f"vector({EMBEDDING_DIMENSIONS})"
            if existing_dimension and existing_dimension != expected_type:
                print(
                    "Embedding dimension changed; recreating only "
                    "content_embeddings and invalidating old vectors."
                )
                connection.execute(text("DROP TABLE public.content_embeddings"))
    # create_all is safe and idempotent. It will only create tables that do not exist.
    Base.metadata.create_all(engine)
    print("Database initialization complete. All required tables exist.")

if __name__ == "__main__":
    init_db()
