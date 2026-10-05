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
from app.database.models import Base

def init_db():
    print("Initializing NewsPilotAI database...")
    engine = get_engine()
    # create_all is safe and idempotent. It will only create tables that do not exist.
    Base.metadata.create_all(engine)
    print("Database initialization complete. All required tables exist.")

if __name__ == "__main__":
    init_db()
