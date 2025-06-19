from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import uvicorn
import logging

from scraper.content_crawler import ContentCrawler, ContentType
from scraper.orchestrator import ScraperOrchestrator
from scraper.blog_scraper import BlogScraper
from scraper.pdf_scraper import PDFScraper

app = FastAPI()

class CrawlRequest(BaseModel):
    start_url: str
    max_pages: int = 10

class CrawlResponse(BaseModel):
    results: Dict[str, List[str]]

class ScrapeRequest(BaseModel):
    url: str
    base_url: Optional[str] = None

class ScrapeResponse(BaseModel):
    items: List[dict]

class CrawlAndScrapeRequest(BaseModel):
    team_id: str
    start_url: str
    max_pages: int = 10

class CrawlAndScrapeResponse(BaseModel):
    team_id: str
    items: List[dict]

@app.post("/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest):
    crawler = ContentCrawler(max_pages=request.max_pages)
    results = await crawler.crawl(request.start_url)
    # Convert ContentType keys to string for JSON serialization
    results_str = {ct.value if isinstance(ct, ContentType) else str(ct): urls for ct, urls in results.items()}
    return CrawlResponse(results=results_str)

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    # Try BlogScraper first, then PDFScraper
    blog_scraper = BlogScraper(team_id="api")
    pdf_scraper = PDFScraper(team_id="api")
    items = []
    if blog_scraper.can_handle(request.url):
        items = await blog_scraper.scrape(request.url, base_url=request.base_url)
    elif pdf_scraper.can_handle(request.url):
        items = await pdf_scraper.scrape(request.url, base_url=request.base_url)
    return ScrapeResponse(items=[item.dict() for item in items])

@app.post("/crawl-and-scrape", response_model=CrawlAndScrapeResponse)
async def crawl_and_scrape(request: CrawlAndScrapeRequest):
    orchestrator = ScraperOrchestrator(request.team_id)
    # Crawl for all URLs
    crawler = ContentCrawler(max_pages=request.max_pages)
    crawled = await crawler.crawl(request.start_url)
    # Collect all URLs to scrape (including the main page)
    all_urls = [request.start_url]
    for urls in crawled.values():
        all_urls.extend(urls)
    # Remove duplicates
    all_urls = list(dict.fromkeys(all_urls))
    # Scrape all URLs
    result = await orchestrator.scrape_urls(all_urls)
    return CrawlAndScrapeResponse(
        team_id=request.team_id,
        items=[item.dict() for item in result.items]
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("fastapi_server:app", host="0.0.0.0", port=8000, reload=True) 