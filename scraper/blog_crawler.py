import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Set
import re
from urllib.parse import urljoin, urlparse
import logging

class BlogCrawler:
    def __init__(self, max_pages: int = 10):
        self.max_pages = max_pages
        self.logger = logging.getLogger(__name__)
        self.visited_urls: Set[str] = set()
        self.blog_post_urls: Set[str] = set()

    async def crawl(self, start_url: str) -> List[str]:
        """Crawl a blog to find all blog post URLs."""
        try:
            # Normalize the start URL
            if not start_url.endswith('/'):
                start_url += '/'
            
            # Start with the main blog page
            await self._process_page(start_url)
            
            # Find pagination links and process them
            page_num = 2
            while page_num <= self.max_pages:
                next_page = self._get_next_page_url(start_url, page_num)
                if not next_page:
                    break
                
                if not await self._process_page(next_page):
                    break
                
                page_num += 1

            return list(self.blog_post_urls)
        except Exception as e:
            self.logger.error(f"Error crawling {start_url}: {str(e)}")
            return list(self.blog_post_urls)

    async def _process_page(self, url: str) -> bool:
        """Process a single page and extract blog post URLs."""
        if url in self.visited_urls:
            return False
        
        self.visited_urls.add(url)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find all links
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        full_url = urljoin(url, href)
                        
                        # Skip if we've already processed this URL
                        if full_url in self.visited_urls:
                            continue
                        
                        # Check if it's a blog post URL
                        if self._is_blog_post_url(full_url):
                            self.blog_post_urls.add(full_url)
                    
                    return True
        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}")
            return False

    def _is_blog_post_url(self, url: str) -> bool:
        """Check if a URL is likely a blog post URL."""
        # Common blog post URL patterns
        patterns = [
            r'/blog/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
            r'/blog/\d{4}/\d{2}/',        # Month-based URLs
            r'/blog/\d{4}/',              # Year-based URLs
            r'/blog/[^/]+$',              # Simple blog post URLs
            r'/posts/[^/]+$',             # Alternative blog post URLs
            r'/article/[^/]+$',           # Article URLs
        ]
        
        # Check if URL matches any pattern
        return any(re.search(pattern, url) for pattern in patterns)

    def _get_next_page_url(self, base_url: str, page_num: int) -> str:
        """Generate the next page URL based on common pagination patterns."""
        # Common pagination patterns
        patterns = [
            f"{base_url}page/{page_num}/",  # WordPress style
            f"{base_url}?page={page_num}",  # Query parameter style
            f"{base_url}p{page_num}/",      # Simple pagination
        ]
        
        # Return the first pattern that matches the base URL structure
        for pattern in patterns:
            if self._is_valid_url(pattern):
                return pattern
        return ""

    def _is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False 