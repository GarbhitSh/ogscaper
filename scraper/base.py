from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class ContentItem(BaseModel):
    title: str
    content: str
    content_type: str
    source_url: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    metadata: Dict[str, Any] = {}
    user_id: str = ""

class ScraperResult(BaseModel):
    team_id: str
    items: List[ContentItem]

class BaseScraper(ABC):
    def __init__(self, team_id: str):
        self.team_id = team_id

    @abstractmethod
    async def scrape(self, url: str) -> List[ContentItem]:
        """Scrape content from the given URL and return a list of ContentItems."""
        pass

    def normalize_content(self, content: str) -> str:
        """Normalize content to clean markdown format."""
        # Basic normalization - can be extended
        content = content.strip()
        return content

    def create_result(self, items: List[ContentItem]) -> ScraperResult:
        """Create a ScraperResult from a list of ContentItems."""
        return ScraperResult(
            team_id=self.team_id,
            items=items
        )

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this scraper can handle the given URL."""
        pass 