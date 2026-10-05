import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from io import StringIO

from app.scrapers.base import GenericArticle, SourceRegistry
from app.scrapers.rss_generic import GenericRSSScraper
from app.scrapers.arxiv import ArxivScraper
from app.scrapers.hacker_news import HackerNewsScraper
from app.normalizer import normalize


# ---------------------------------------------------------------------------
# feedparser returns FeedParserDict — a dict subclass whose keys are also
# accessible as attributes.  Plain dicts don't support attribute access, so
# any test that mocks feedparser.parse() must return an attribute-accessible
# object.  This minimal stand-in reproduces that contract exactly.
# ---------------------------------------------------------------------------
class _AttrDict(dict):
    """dict whose values are also accessible as attributes (like FeedParserDict)."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _make_feed(entries):
    """Build a FeedParserDict-like object with an entries list."""
    feed = _AttrDict(entries=[_AttrDict(e) for e in entries])
    return feed


# ---------------------------------------------------------------------------
# 1. GenericArticle normalization
# ---------------------------------------------------------------------------
class TestGenericArticleNormalization(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.article = GenericArticle(
            title="Test Post",
            description="Test Description",
            url="http://test.com/post1",
            guid="post1",
            published_at=self.now,
            author="Test Author",
            category="AI"
        )

    def test_normalized_external_id(self):
        self.assertEqual(normalize(self.article)["external_id"], "post1")

    def test_normalized_content_type(self):
        self.assertEqual(normalize(self.article)["content_type"], "article")

    def test_normalized_title(self):
        self.assertEqual(normalize(self.article)["title"], "Test Post")

    def test_normalized_url(self):
        self.assertEqual(normalize(self.article)["url"], "http://test.com/post1")

    def test_normalized_author(self):
        self.assertEqual(normalize(self.article)["author"], "Test Author")

    def test_normalized_description(self):
        self.assertEqual(normalize(self.article)["description"], "Test Description")

    def test_normalized_published_at(self):
        self.assertEqual(normalize(self.article)["published_at"], self.now)

    def test_normalize_raises_for_unknown_type(self):
        with self.assertRaises(ValueError):
            normalize("not_a_known_type")


# ---------------------------------------------------------------------------
# 2. GenericRSSScraper — mocked feedparser
# ---------------------------------------------------------------------------

# Fixture: a single valid entry.  published_parsed must be accessible as an
# attribute because rss_generic.py uses getattr(entry, "published_parsed").
RSS_ENTRY = {
    "id": "http://blog.example.com/post1",
    "title": "Test RSS Article",
    "description": "RSS Description",
    "link": "http://blog.example.com/post1",
    "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 0, 0),
    "author": "RSS Author",
}

RSS_FIXTURE = _make_feed([RSS_ENTRY])
EMPTY_FEED   = _make_feed([])
NO_DATE_FEED = _make_feed([{"id": "x", "title": "no date", "link": "http://x.com"}])


class TestGenericRSSScraper(unittest.TestCase):
    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_returns_articles(self, _mock):
        scraper = GenericRSSScraper(name="Test Source", rss_url="http://fake.rss")
        # hours=87600 (10 years) keeps the 2026 fixture date within the cutoff
        articles = scraper.fetch(hours=87600)
        self.assertEqual(len(articles), 1)

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_correct_external_id(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=87600)
        self.assertEqual(articles[0].guid, "http://blog.example.com/post1")

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_correct_title(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=87600)
        self.assertEqual(articles[0].title, "Test RSS Article")

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_correct_url(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=87600)
        self.assertEqual(articles[0].url, "http://blog.example.com/post1")

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=EMPTY_FEED)
    def test_fetch_empty_feed(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=24)
        self.assertEqual(articles, [])

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_deduplicates_same_guid(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=87600)
        guids = [a.guid for a in articles]
        self.assertEqual(len(guids), len(set(guids)))

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=RSS_FIXTURE)
    def test_fetch_drops_old_entries(self, _mock):
        # hours=0: nothing is recent enough
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=0)
        self.assertEqual(articles, [])

    @patch("app.scrapers.rss_generic.feedparser.parse", return_value=NO_DATE_FEED)
    def test_fetch_skips_entries_without_published_parsed(self, _mock):
        articles = GenericRSSScraper(name="T", rss_url="x").fetch(hours=24)
        self.assertEqual(articles, [])


# ---------------------------------------------------------------------------
# 3. ArxivScraper — mocked requests
# ---------------------------------------------------------------------------
ARXIV_FIXTURE = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <entry>
        <id>http://arxiv.org/abs/2301.00001</id>
        <published>2026-01-01T12:00:00Z</published>
        <title>Test arXiv Paper</title>
        <summary>  Test Summary Text  </summary>
        <author><name>Alice</name></author>
        <author><name>Bob</name></author>
        <link title="pdf" href="http://arxiv.org/pdf/2301.00001" />
    </entry>
</feed>'''


class TestArxivScraper(unittest.TestCase):
    @patch("app.scrapers.arxiv.requests.get")
    def test_fetch_returns_articles(self, mock_get):
        mock_get.return_value = MagicMock(content=ARXIV_FIXTURE)
        articles = ArxivScraper().fetch(hours=87600)
        self.assertEqual(len(articles), 1)

    @patch("app.scrapers.arxiv.requests.get")
    def test_arxiv_external_id(self, mock_get):
        mock_get.return_value = MagicMock(content=ARXIV_FIXTURE)
        articles = ArxivScraper().fetch(hours=87600)
        self.assertEqual(articles[0].guid, "http://arxiv.org/abs/2301.00001")

    @patch("app.scrapers.arxiv.requests.get")
    def test_arxiv_title(self, mock_get):
        mock_get.return_value = MagicMock(content=ARXIV_FIXTURE)
        articles = ArxivScraper().fetch(hours=87600)
        self.assertEqual(articles[0].title, "Test arXiv Paper")

    @patch("app.scrapers.arxiv.requests.get")
    def test_arxiv_authors_joined(self, mock_get):
        mock_get.return_value = MagicMock(content=ARXIV_FIXTURE)
        articles = ArxivScraper().fetch(hours=87600)
        self.assertEqual(articles[0].author, "Alice, Bob")

    @patch("app.scrapers.arxiv.requests.get")
    def test_arxiv_pdf_url(self, mock_get):
        mock_get.return_value = MagicMock(content=ARXIV_FIXTURE)
        articles = ArxivScraper().fetch(hours=87600)
        self.assertEqual(articles[0].url, "http://arxiv.org/pdf/2301.00001")

    @patch("app.scrapers.arxiv.requests.get", side_effect=Exception("timeout"))
    def test_arxiv_network_failure_returns_empty(self, _mock):
        articles = ArxivScraper().fetch(hours=24)
        self.assertEqual(articles, [])


# ---------------------------------------------------------------------------
# 4. HackerNewsScraper — mocked requests
# ---------------------------------------------------------------------------
HN_FIXTURE = {
    "hits": [
        {
            "objectID": "123456",
            "title": "HN AI Story",
            "url": "http://hn.test/story",
            "created_at_i": int(datetime.now(timezone.utc).timestamp()),
            "author": "hn_user",
        },
        {
            "objectID": "654321",
            "title": "Ask HN: AI?",
            "url": None,  # No URL → should fall back to HN thread URL
            "created_at_i": int(datetime.now(timezone.utc).timestamp()),
            "author": "asker",
        },
    ]
}


class TestHackerNewsScraper(unittest.TestCase):
    @patch("app.scrapers.hacker_news.requests.get")
    def test_fetch_returns_articles(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: HN_FIXTURE)
        articles = HackerNewsScraper().fetch(hours=24)
        self.assertEqual(len(articles), 2)

    @patch("app.scrapers.hacker_news.requests.get")
    def test_hn_story_url(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: HN_FIXTURE)
        articles = HackerNewsScraper().fetch(hours=24)
        self.assertEqual(articles[0].url, "http://hn.test/story")

    @patch("app.scrapers.hacker_news.requests.get")
    def test_hn_no_url_falls_back_to_thread(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: HN_FIXTURE)
        articles = HackerNewsScraper().fetch(hours=24)
        self.assertEqual(articles[1].url, "https://news.ycombinator.com/item?id=654321")

    @patch("app.scrapers.hacker_news.requests.get")
    def test_hn_external_id_is_object_id(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: HN_FIXTURE)
        articles = HackerNewsScraper().fetch(hours=24)
        self.assertEqual(articles[0].guid, "123456")

    @patch("app.scrapers.hacker_news.requests.get", side_effect=Exception("timeout"))
    def test_hn_network_failure_returns_empty(self, _mock):
        articles = HackerNewsScraper().fetch(hours=24)
        self.assertEqual(articles, [])


# ---------------------------------------------------------------------------
# 5. SourceRegistry
# ---------------------------------------------------------------------------
class TestSourceRegistry(unittest.TestCase):
    def test_registry_register_and_retrieve(self):
        reg = SourceRegistry()
        scraper = GenericRSSScraper(name="Test", rss_url="http://x.com/feed")
        reg.register(scraper)
        self.assertIn(scraper, reg.get_all())

    def test_registry_multiple_adapters(self):
        reg = SourceRegistry()
        reg.register(GenericRSSScraper(name="A", rss_url="http://a.com"))
        reg.register(GenericRSSScraper(name="B", rss_url="http://b.com"))
        self.assertEqual(len(reg.get_all()), 2)

    def test_global_registry_has_all_sources(self):
        # Import to trigger registration
        from app.scrapers.base import registry
        import app.scrapers  # noqa: F401

        names = {a.source_name for a in registry.get_all()}
        expected = {
            "YouTube", "OpenAI RSS", "Anthropic RSS",
            "Hugging Face", "NVIDIA AI", "Microsoft AI",
            "arXiv AI/ML", "Hacker News AI",
        }
        self.assertEqual(names, expected)


if __name__ == "__main__":
    unittest.main()
