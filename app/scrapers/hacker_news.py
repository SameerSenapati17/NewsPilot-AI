import requests
from datetime import datetime, timedelta, timezone
from typing import List
from .base import SourceAdapter, GenericArticle

class HackerNewsScraper(SourceAdapter):
    source_name = "Hacker News AI"
    source_type = "api"
    
    def __init__(self):
        self.api_url = "https://hn.algolia.com/api/v1/search_by_date"
        self.query = "AI OR \"Artificial Intelligence\" OR LLM OR ChatGPT"
        
    def fetch(self, hours: int = 24) -> List[GenericArticle]:
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        numeric_cutoff = int(cutoff_time.timestamp())
        
        params = {
            "query": self.query,
            "tags": "story",
            "numericFilters": f"created_at_i>{numeric_cutoff}",
            "hitsPerPage": 50
        }
        
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []
            
        articles = []
        
        for hit in data.get("hits", []):
            guid = str(hit.get("objectID"))
            title = hit.get("title", "")
            url = hit.get("url")
            # If HN post has no URL (e.g. Ask HN), link to the HN thread
            if not url:
                url = f"https://news.ycombinator.com/item?id={guid}"
                
            published_time = datetime.fromtimestamp(hit.get("created_at_i"), tz=timezone.utc)
            author = hit.get("author")
            
            # Simple score filtering to ensure quality? The prompt asks for reliable ingestion. 
            # We'll just fetch whatever matched the date filter.
            
            articles.append(GenericArticle(
                title=title,
                description="", # HN Algolia doesn't return full text reliably for stories, usually just title
                url=url,
                guid=guid,
                published_at=published_time,
                author=author
            ))
            
        return articles
