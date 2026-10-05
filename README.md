# NewsPilotAI
> Your AI-powered navigator through the world of artificial intelligence.

NewsPilotAI is a daily AI-powered news aggregator pipeline. It ingests content from multiple AI sources, generates summaries using LLMs, curates and ranks them using a personalized profile, and delivers a digest email every day.

---

## Architecture Overview

```
Source Adapters (scrapers/)
        ↓
  Normalization Layer (normalizer.py)
        ↓
  ContentItem → AI enrichment → PostgreSQL (repository.py)
        ↓
  Enrichment (process_anthropic, process_youtube)
        ↓
  Digest Generation (DigestAgent / gpt-4o-mini)
        ↓
  Curation & Ranking (CuratorAgent / gpt-4.1)
        ↓
  Email Digest (EmailAgent / gpt-4o-mini → SMTP)
```

---

## Supported Sources

| Source          | Type    | Mechanism                   | Auth Required | Status      |
|-----------------|---------|-----------------------------|---------------|-------------|
| YouTube         | youtube | feedparser + RSS            | No            | ✅ Active   |
| OpenAI RSS      | rss     | feedparser + RSS            | No            | ✅ Active   |
| Anthropic RSS   | rss     | feedparser + RSS (3 feeds)  | No            | ✅ Active   |
| Hugging Face    | rss     | feedparser + RSS            | No            | ✅ Active   |
| NVIDIA AI       | rss     | feedparser + RSS            | No            | ✅ Active   |
| Microsoft AI    | rss     | feedparser + RSS            | No            | ✅ Active   |
| arXiv AI/ML     | api     | arXiv Atom API              | No            | ✅ Active   |
| Hacker News AI  | api     | Algolia HN Search API       | No            | ✅ Active   |

### Deferred Sources

| Source          | Reason Deferred                                                      |
|-----------------|----------------------------------------------------------------------|
| Google DeepMind | No official RSS or public API. Fragile HTML scraping rejected.       |
| Meta AI (blog)  | No official RSS feed at ai.meta.com/blog. Community feeds only.      |

---

## Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 18+
- [`uv`](https://docs.astral.sh/uv/) package manager

### Installation

```bash
git clone <repo>
cd ai-news-aggregator

# Install all dependencies
uv sync

# Copy environment template and fill in your values
cp .env.example .env
```

### Environment Variables (`.env`)

```env
# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=yourpassword
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_news_aggregator

# OpenAI API key (for digest + curation + email agents)
OPENAI_API_KEY=sk-...

# Gmail SMTP for sending digest email
MY_EMAIL=you@gmail.com
APP_PASSWORD=your-gmail-app-password

# Optional: YouTube proxy (for transcript access in restricted regions)
# PROXY_USERNAME=...
# PROXY_PASSWORD=...
```

### Database Initialization

```bash
# Create all tables (idempotent — safe to run multiple times)
python scripts/init_db.py

# Verify tables
python -c "from app.database.connection import get_engine; from sqlalchemy import inspect; print(inspect(get_engine()).get_table_names())"
```

### Running the Pipeline

```bash
# Run the full daily pipeline
python main.py
```

---

## Testing

```bash
# Run all tests (no live network or database required)
python -m unittest discover -s tests -p "test_*.py"
```

---

## Project Structure

```
app/
├── scrapers/
│   ├── base.py          # SourceAdapter ABC, GenericArticle, SourceRegistry
│   ├── __init__.py      # Registers all adapters into the global registry
│   ├── youtube.py       # YouTube channel RSS + transcript fetching
│   ├── openai.py        # OpenAI RSS feed
│   ├── anthropic.py     # Anthropic RSS feeds (news + research + engineering)
│   ├── rss_generic.py   # Reusable generic RSS adapter (Hugging Face, NVIDIA, Microsoft)
│   ├── arxiv.py         # arXiv AI/ML via Atom API
│   └── hacker_news.py   # Hacker News via Algolia Search API
├── database/
│   ├── models.py        # Source, ContentItem, Digest + legacy models
│   ├── connection.py    # Lazy SQLAlchemy engine / session
│   └── repository.py    # All DB access (Repository class)
├── services/
│   ├── process_anthropic.py  # Docling markdown extraction
│   ├── process_youtube.py    # YouTube transcript extraction
│   ├── process_digest.py     # LLM digest generation
│   └── process_email.py      # LLM email composition + SMTP send
├── agent/
│   ├── digest_agent.py       # gpt-4o-mini structured digest
│   ├── curator_agent.py      # gpt-4.1 ranking
│   └── email_agent.py        # gpt-4o-mini email composition
├── profiles/
│   └── user_profile.py       # User interest profile
├── normalizer.py             # Source-agnostic ContentItem dict conversion
├── enrichment.py             # Structured AI enrichment provider and schema
├── runner.py                 # Ingestion loop with failure isolation
├── daily_runner.py           # Full pipeline orchestration
└── config.py                 # Static config (YouTube channel IDs)

scripts/
├── init_db.py               # Idempotent DB schema creation
├── migrate_data.py          # Phase 1 data migration (legacy → ContentItem)
└── verify_pg_integration*.py # PostgreSQL integration checks

tests/
├── test_repository.py       # Repository + SQLite unit tests
├── test_normalizer.py       # Phase 2 normalization tests
├── test_scrapers_phase3.py  # Phase 3 scrapers + registry tests
└── test_init_db.py          # DB initialization test
```

---

## Data Model

```
Source
  id, name, source_type, base_url, reliability_score, is_active, created_at
    ↓ (1-to-many)
ContentItem
  id, source_id, external_id (unique), content_type, title, url,
  description, author, raw_content, transcript, published_at, created_at, updated_at
    ↓ (1-to-many)
Digest
  id, content_item_id, article_type, article_id, url, title, summary, created_at
```

`ContentItem` represents one piece of source content (a video, article, or paper).
Phase 5 adds one `ContentEnrichment` record per ContentItem. It contains a
controlled category, JSON topic/entity lists, and model-generated scores from
0 to 1 for importance, novelty, technical depth, impact, and source quality.
These scores are heuristics, not ground-truth measurements.

The enrichment provider is isolated behind `EnrichmentProvider`, with the
existing OpenAI structured-output client used by the default implementation.
Input is metadata-first and capped at `ENRICHMENT_MAX_CONTENT_CHARS` (12,000
characters by default), with deterministic body truncation. Provider failures
are logged without deleting the ContentItem, and existing enrichment records
are skipped so ingestion is idempotent.