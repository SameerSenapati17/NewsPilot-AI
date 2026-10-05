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
  ContentItem → AI enrichment → semantic embeddings → PostgreSQL (repository.py)
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
├── embeddings.py             # pgvector embedding provider and text hashing
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
├── test_embeddings.py       # Phase 6 embedding tests
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
    ↓ (one-to-one)
ContentEnrichment
  id, content_item_id, category, topics, entities, scores, model_name,
  prompt_version, created_at, updated_at
    ↓ (one-to-one)
ContentEmbedding
  id, content_item_id, embedding, embedding_model, dimensions, text_hash,
  created_at, updated_at
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

### Semantic embeddings

Phase 6 stores one numerical semantic representation per `ContentItem` in the
PostgreSQL `vector` type supplied by `pgvector`. The default provider uses
OpenAI `text-embedding-3-small` with 1,536 dimensions; model, dimensions,
batch size, and the 12,000-character deterministic input limit are configurable
through environment variables. Input contains stable title, source, content
type, and body fields and does not include timestamps, summaries, or user data.

The SHA-256 hash of that prepared input is stored in `text_hash`; unchanged
content skips the provider, while changed content is regenerated. Similarity
search uses pgvector cosine distance and performs ordering in PostgreSQL rather
than loading vectors into Python. The current dataset does not justify an ANN
index, so the schema is ready for one later without adding unnecessary
infrastructure. Embedding failures are logged and isolated after the
ContentItem and enrichment have already been persisted. pgvector must be
available in PostgreSQL; this phase does not fake vector storage with JSON or
text.

### Semantic retrieval and grounded RAG

Phase 7 embeds a user query with the same configured embedding provider and
retrieves ContentItems through PostgreSQL pgvector. Results retain source
metadata and Story IDs. Story duplicates are removed after database retrieval,
so database similarity ordering remains authoritative.

RAG context is deterministic and bounded by `RAG_MAX_CONTEXT_ITEMS` and
`RAG_MAX_CONTEXT_CHARS`. It prefers raw content or transcripts, then
descriptions, then titles, and never fabricates missing URLs, dates, or text.
The grounded answer provider receives only retrieved context, returns
structured answers with source attribution, and must explicitly acknowledge
insufficient context. `RAG_MODEL` selects the provider model.

Retrieval and answer generation are provider abstractions and are tested with
mocks; this phase adds no API, frontend, personalization, recommendations, or
agent workflows.