from datetime import datetime, timedelta, timezone
from typing import List, Optional
import feedparser
from .base import SourceAdapter, GenericArticle

class GenericRSSScraper(SourceAdapter):
    def __init__(self, name: str, rss_url: str):
        self.source_name = name
        self.source_type = "rss"
        self.rss_url = rss_url

    def fetch(self, hours: int = 24) -> List[GenericArticle]:
        feed = feedparser.parse(self.rss_url)
        if not feed.entries:
            return []
        
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        articles = []
        seen_guids = set()
        
        for entry in feed.entries:
            published_parsed = getattr(entry, "published_parsed", None)
            if not published_parsed:
                continue
            
            published_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)
            if published_time >= cutoff_time:
                guid = entry.get("id", entry.get("link", ""))
                if guid not in seen_guids:
                    seen_guids.add(guid)
                    articles.append(GenericArticle(
                        title=entry.get("title", ""),
                        description=entry.get("description", entry.get("summary", "")),
                        url=entry.get("link", ""),
                        guid=guid,
                        published_at=published_time,
                        author=entry.get("author", None),
                        category=entry.get("tags", [{}])[0].get("term") if entry.get("tags") else None
                    ))
        
        return articles
