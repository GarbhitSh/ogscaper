import re
from typing import List, Optional
from newspaper import Article
from newspaper.article import ArticleException
from .base import BaseScraper, ContentItem
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import html2text
from datetime import datetime
import logging
from urllib.parse import urljoin
import html

class BlogScraper(BaseScraper):
    def __init__(self, team_id: str):
        super().__init__(team_id)
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.logger = logging.getLogger(__name__)

    def can_handle(self, url: str) -> bool:
        """Check if the URL is a blog post."""
        blog_post_patterns = [
            r'/blog/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
            r'/blog/\d{4}/\d{2}/',        # Month-based URLs
            r'/blog/\d{4}/',              # Year-based URLs
            r'/blog/[^/]+$',              # Simple blog post URLs
            r'/posts/[^/]+$',             # Alternative blog post URLs
            r'/article/[^/]+$',           # Article URLs
            r'\.substack\.com/p/',        # Substack posts
            r'medium\.com/@[^/]+/[^/]+$', # Medium posts
            r'dev\.to/[^/]+/[^/]+$',      # Dev.to posts
        ]
        return any(re.search(pattern, url.lower()) for pattern in blog_post_patterns)

    async def scrape(self, url: str, base_url: str = None) -> List[ContentItem]:
        """Scrape a blog post and return its content using multiple fallback strategies."""
        try:
            # Normalize URL to absolute
            if base_url:
                url = urljoin(base_url, url)
            elif not url.lower().startswith(('http://', 'https://')):
                url = urljoin('https://', url)
            self.logger.info(f"Scraping blog post: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    html_text = await response.text()
                    soup = BeautifulSoup(html_text, 'html.parser')

            # --- STRATEGY 1: newspaper3k ---
            try:
                article = Article(url)
                article.set_html(html_text)
                article.parse()
                if article.text.strip():
                    title = article.title or self._extract_title(soup) or ""
                    author = ", ".join(article.authors) if article.authors else self._extract_author(soup) or ""
                    date = article.publish_date or self._extract_date(soup)
                    content = article.text
                    content_md = self.h2t.handle(content)
                    content_md = self._clean_content(content_md)
                    content_md = re.sub(r'\n{3,}', '\n\n', content_md.strip())
                    content_md = re.sub(r'<[^>]+>', '', content_md)
                    content_md = html.unescape(content_md.encode('utf-8').decode('unicode_escape'))
                    title_clean = html.unescape(title.encode('utf-8').decode('unicode_escape'))
                    return [ContentItem(
                        title=self.normalize_content(title_clean),
                        content=self.normalize_content(content_md),
                        content_type="blog",
                        source_url=url,
                        author=author,
                        user_id=""
                    )]
            except Exception as e:
                self.logger.warning(f"newspaper3k failed: {str(e)}")

            # --- STRATEGY 2: Manual BeautifulSoup Extraction ---
            try:
                title = self._extract_title(soup) or ""
                author = self._extract_author(soup) or ""
                date = self._extract_date(soup)
                content = self._extract_content_manually(soup)
                if content.strip():
                    content_md = self.h2t.handle(content)
                    content_md = self._clean_content(content_md)
                    content_md = re.sub(r'\n{3,}', '\n\n', content_md.strip())
                    content_md = re.sub(r'<[^>]+>', '', content_md)
                    content_md = html.unescape(content_md.encode('utf-8').decode('unicode_escape'))
                    title_clean = html.unescape(title.encode('utf-8').decode('unicode_escape'))
                    return [ContentItem(
                        title=self.normalize_content(title_clean),
                        content=self.normalize_content(content_md),
                        content_type="blog",
                        source_url=url,
                        author=author,
                        user_id=""
                    )]
            except Exception as e:
                self.logger.warning(f"Manual BeautifulSoup extraction failed: {str(e)}")

            # --- STRATEGY 3: Generic Fallback (all <p> tags) ---
            try:
                title = self._extract_title(soup) or ""
                author = self._extract_author(soup) or ""
                date = self._extract_date(soup)
                content = "\n\n".join([p.get_text() for p in soup.find_all('p')])
                if content.strip():
                    content_md = self.h2t.handle(content)
                    content_md = self._clean_content(content_md)
                    content_md = re.sub(r'\n{3,}', '\n\n', content_md.strip())
                    content_md = re.sub(r'<[^>]+>', '', content_md)
                    content_md = html.unescape(content_md.encode('utf-8').decode('unicode_escape'))
                    title_clean = html.unescape(title.encode('utf-8').decode('unicode_escape'))
                    return [ContentItem(
                        title=self.normalize_content(title_clean),
                        content=self.normalize_content(content_md),
                        content_type="blog",
                        source_url=url,
                        author=author,
                        user_id=""
                    )]
            except Exception as e:
                self.logger.warning(f"Generic <p> tag extraction failed: {str(e)}")

            # If all strategies fail
            self.logger.error(f"All blog scraping strategies failed for {url}")
            return []
        except Exception as e:
            self.logger.error(f"Error scraping {url}: {str(e)}")
            return []

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract title from various meta tags."""
        # Try meta tags first
        for meta in soup.find_all('meta'):
            if meta.get('property') == 'og:title':
                return meta.get('content')
        
        # Try article title
        article_title = soup.find('h1')
        if article_title:
            return article_title.get_text().strip()
        
        # Try page title
        if soup.title:
            return soup.title.string.strip()
        
        return None

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract author from various meta tags and content."""
        # Try meta tags
        for meta in soup.find_all('meta'):
            if meta.get('name') in ['author', 'article:author']:
                return meta.get('content')
        
        # Try common author selectors
        author_selectors = [
            '.author', '.byline', '[rel="author"]',
            '.post-author', '.article-author', '.entry-author'
        ]
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                return author_elem.get_text().strip()
        
        return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract published date from various meta tags and content."""
        # Try meta tags
        for meta in soup.find_all('meta'):
            if meta.get('property') in ['article:published_time', 'og:published_time']:
                try:
                    return datetime.fromisoformat(meta.get('content').replace('Z', '+00:00'))
                except:
                    pass
        
        # Try common date selectors
        date_selectors = [
            '.date', '.published', '.post-date',
            '.article-date', '.entry-date', 'time'
        ]
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                try:
                    # Try to parse the date text
                    date_text = date_elem.get_text().strip()
                    # Add more date parsing patterns as needed
                    return datetime.strptime(date_text, '%B %d, %Y')
                except:
                    pass
        
        return None

    def _extract_content_manually(self, soup: BeautifulSoup) -> str:
        """Extract content manually when newspaper3k fails."""
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Find the main content container
        content_selectors = [
            'article', '.post-content', '.entry-content',
            '.article-content', '.blog-post', '.content'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                return content_elem.get_text()
        
        # If no specific container found, get body text
        return soup.body.get_text() if soup.body else ""

    def _clean_content(self, content: str) -> str:
        """Clean up the extracted content."""
        # Remove multiple newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        # Remove extra spaces
        content = re.sub(r' +', ' ', content)
        # Fix list formatting
        content = re.sub(r'(\n\s*[-*]\s.*?)(\n{1,2})', r'\1\n', content)
        # Fix header formatting
        content = re.sub(r'(#{1,6}\s.*?)(\n{1,2})', r'\1\n\n', content)
        # Remove author and published lines at the start (in any order)
        content = re.sub(r'^(By [^|\n]+\|?\s*)?(Published:.*?)?\n+', '', content, flags=re.IGNORECASE)
        # Remove any remaining 'Published:' at the start of the content
        content = re.sub(r'^Published: ?', '', content, flags=re.IGNORECASE)
        return content.strip()

    def normalize_content(self, content: str) -> str:
        """Normalize blog content to clean markdown."""
        content = super().normalize_content(content)
        
        # Remove multiple newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Ensure proper spacing around headers
        content = re.sub(r'(#{1,6}\s.*?)(\n{1,2})', r'\1\n\n', content)
        
        # Fix list formatting
        content = re.sub(r'(\n\s*[-*]\s.*?)(\n{1,2})', r'\1\n', content)
        
        return content.strip() 