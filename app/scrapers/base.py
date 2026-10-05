from abc import ABC, abstractmethod
from typing import List, Dict, Any, Type, Optional
from datetime import datetime
from pydantic import BaseModel

class GenericArticle(BaseModel):
    title: str
    description: str
    url: str
    guid: str
    published_at: datetime
    author: Optional[str] = None
    category: Optional[str] = None

class SourceAdapter(ABC):
    source_name: str
    source_type: str

    @abstractmethod
    def fetch(self, hours: int = 24) -> List[Any]:
        """Fetch items from the source."""
        pass

class SourceRegistry:
    def __init__(self):
        self.adapters: List[SourceAdapter] = []

    def register(self, adapter: SourceAdapter):
        self.adapters.append(adapter)

    def get_all(self) -> List[SourceAdapter]:
        return self.adapters

registry = SourceRegistry()

