import unittest
from datetime import datetime, timezone
from app.normalizer import normalize
from app.scrapers.youtube import ChannelVideo
from app.scrapers.openai import OpenAIArticle
from app.scrapers.anthropic import AnthropicArticle

class TestNormalizer(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_normalize_youtube_video(self):
        video = ChannelVideo(
            title="Test Video",
            url="http://youtube.com/v1",
            video_id="v1",
            published_at=self.now,
            description="Test Description",
            transcript="Test Transcript"
        )
        normalized = normalize(video)
        
        self.assertEqual(normalized["external_id"], "v1")
        self.assertEqual(normalized["title"], "Test Video")
        self.assertEqual(normalized["url"], "http://youtube.com/v1")
        self.assertEqual(normalized["content_type"], "video")
        self.assertEqual(normalized["published_at"], self.now)
        self.assertEqual(normalized["description"], "Test Description")
        self.assertEqual(normalized["transcript"], "Test Transcript")

    def test_normalize_openai_article(self):
        article = OpenAIArticle(
            title="OpenAI News",
            description="OpenAI Description",
            url="http://openai.com/news1",
            guid="guid1",
            published_at=self.now,
            category="Research"
        )
        normalized = normalize(article)
        
        self.assertEqual(normalized["external_id"], "guid1")
        self.assertEqual(normalized["title"], "OpenAI News")
        self.assertEqual(normalized["url"], "http://openai.com/news1")
        self.assertEqual(normalized["content_type"], "article")
        self.assertEqual(normalized["published_at"], self.now)
        self.assertEqual(normalized["description"], "OpenAI Description")

    def test_normalize_anthropic_article(self):
        article = AnthropicArticle(
            title="Anthropic News",
            description="Anthropic Description",
            url="http://anthropic.com/news1",
            guid="guid2",
            published_at=self.now,
            category="Product"
        )
        normalized = normalize(article)
        
        self.assertEqual(normalized["external_id"], "guid2")
        self.assertEqual(normalized["title"], "Anthropic News")
        self.assertEqual(normalized["url"], "http://anthropic.com/news1")
        self.assertEqual(normalized["content_type"], "article")
        self.assertEqual(normalized["published_at"], self.now)
        self.assertEqual(normalized["description"], "Anthropic Description")

if __name__ == '__main__':
    unittest.main()
