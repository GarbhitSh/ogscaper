from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Dict, List
import asyncio
import uvicorn
import logging

from scraper.content_crawler import ContentCrawler, ContentType

app = FastAPI()

class CrawlRequest(BaseModel):
    start_url: str
    max_pages: int = 10

class CrawlResponse(BaseModel):
    results: Dict[str, List[str]]

@app.post("/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest):
    crawler = ContentCrawler(max_pages=request.max_pages)
    results = await crawler.crawl(request.start_url)
    # Convert ContentType keys to string for JSON serialization
    results_str = {ct.value if isinstance(ct, ContentType) else str(ct): urls for ct, urls in results.items()}
    return CrawlResponse(results=results_str)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("fastapi_server:app", host="0.0.0.0", port=8000, reload=True) 