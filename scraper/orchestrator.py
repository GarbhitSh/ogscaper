from typing import List, Dict, Type
from .base import BaseScraper, ScraperResult, ContentItem
from .blog_scraper import BlogScraper
from .pdf_scraper import PDFScraper
from .content_crawler import ContentCrawler, ContentType
import asyncio
from tqdm import tqdm
import json
from pathlib import Path
import logging
import re
import os

class ScraperOrchestrator:
    def __init__(self, team_id: str):
        self.team_id = team_id
        self.scrapers: List[BaseScraper] = [
            BlogScraper(team_id),
            PDFScraper(team_id)
        ]
        self.logger = logging.getLogger(__name__)
        self.content_crawler = ContentCrawler()

    async def scrape_urls(self, urls: List[str]) -> ScraperResult:
        """Scrape multiple URLs and return the results."""
        all_items = []
        all_urls_to_scrape = []
        for url in urls:
            # If it's a local PDF file, pass directly to PDFScraper
            if os.path.isfile(url) and url.lower().endswith('.pdf'):
                all_urls_to_scrape.append((url, url))
                continue
            # Crawl for content links
            crawled = await self.content_crawler.crawl(url)
            # Always add the main page as well (in case it's a content page itself)
            all_urls_to_scrape.append((url, url))
            for ct, found_urls in crawled.items():
                for found_url in found_urls:
                    all_urls_to_scrape.append((found_url, url))
        # Remove duplicates
        seen = set()
        unique_urls = []
        for found_url, base_url in all_urls_to_scrape:
            if found_url not in seen:
                unique_urls.append((found_url, base_url))
                seen.add(found_url)
        # Scrape each URL
        for found_url, base_url in tqdm(unique_urls, desc="Scraping URLs"):
            scraper = self._get_scraper_for_url(found_url)
            if scraper:
                try:
                    items = await scraper.scrape(found_url, base_url=base_url)
                    all_items.extend(items)
                except Exception as e:
                    self.logger.error(f"Error scraping {found_url}: {str(e)}")
                    continue
        return ScraperResult(
            team_id=self.team_id,
            items=all_items
        )

    def _get_scraper_for_url(self, url: str) -> BaseScraper:
        """Find the appropriate scraper for a given URL."""
        for scraper in self.scrapers:
            if scraper.can_handle(url):
                return scraper
        return None

    def save_results(self, result: ScraperResult, output_path: str):
        """Save scraping results to a JSON file in the required schema."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Only include required fields in each item
        output = {
            "team_id": result.team_id,
            "items": [
                {
                    "title": item.title,
                    "content": item.content,
                    "content_type": item.content_type,
                    "source_url": item.source_url,
                    "author": item.author,
                    "user_id": item.user_id
                }
                for item in result.items
            ]
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    async def scrape_and_save(self, urls: List[str], output_path: str):
        """Scrape URLs and save results to a file."""
        result = await self.scrape_urls(urls)
        self.save_results(result, output_path)
        return result 