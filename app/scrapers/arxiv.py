import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List
from .base import SourceAdapter, GenericArticle

class ArxivScraper(SourceAdapter):
    source_name = "arXiv AI/ML"
    source_type = "api"
    
    def __init__(self):
        self.api_url = "http://export.arxiv.org/api/query"
        self.search_query = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
        
    def fetch(self, hours: int = 24) -> List[GenericArticle]:
        params = {
            "search_query": self.search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 50
        }
        
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
        except Exception:
            return []
            
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=hours)
        articles = []
        
        for entry in root.findall("atom:entry", ns):
            published_str = entry.find("atom:published", ns).text
            # arXiv uses ISO8601 like 2024-03-12T18:00:00Z
            published_time = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            
            if published_time >= cutoff_time:
                guid = entry.find("atom:id", ns).text
                title = entry.find("atom:title", ns).text.replace("\n", " ").strip()
                summary = entry.find("atom:summary", ns).text.strip()
                link = entry.find("atom:link[@title='pdf']", ns)
                if link is None:
                    link = entry.find("atom:link", ns)
                url = link.attrib.get("href", guid) if link is not None else guid
                
                authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
                author_str = ", ".join(authors) if authors else None
                
                articles.append(GenericArticle(
                    title=title,
                    description=summary,
                    url=url,
                    guid=guid,
                    published_at=published_time,
                    author=author_str
                ))
                
        return articles
