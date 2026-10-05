import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

_engine = None
_SessionLocal = None

# Exported so migrate_data.py can import it; populated on first get_engine() call.
DATABASE_URL: Optional[str] = None


def get_database_url() -> str:
    """Build the PostgreSQL connection URL from environment variables."""
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "ai_news_aggregator")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def get_engine():
    """Return (and lazily create) the SQLAlchemy engine for PostgreSQL."""
    global _engine, DATABASE_URL
    if _engine is None:
        DATABASE_URL = get_database_url()
        _engine = create_engine(DATABASE_URL)
    return _engine


def get_session() -> Session:
    """Return a new database session backed by the PostgreSQL engine."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()

