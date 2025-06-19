import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Set, Dict, Optional, Tuple
import re
from urllib.parse import urljoin, urlparse, urlunparse
import logging
from dataclasses import dataclass
from enum import Enum
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
from newspaper import Article
import requests
from playwright.async_api import async_playwright
import cloudscraper
from fake_useragent import UserAgent
import undetected_chromedriver as uc
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import random
import feedparser
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
import os

class ContentType(Enum):
    BLOG = "blog"
    GUIDE = "guide"
    TOPIC = "topic"
    SUBSTACK = "substack"
    CATEGORY = "category"
    UNKNOWN = "unknown"

@dataclass
class SiteConfig:
    domain: str
    content_selectors: List[str]
    pagination_selectors: List[str]
    content_patterns: List[str]
    requires_js: bool = False
    infinite_scroll: bool = False
    api_endpoints: List[str] = None
    custom_extractors: Dict[str, str] = None
    use_playwright: bool = False
    use_cloudscraper: bool = False
    use_undetected: bool = False
    scroll_pause_time: float = 2.0
    max_scroll_attempts: int = 10
    wait_for_selectors: List[str] = None
    click_selectors: List[str] = None
    custom_headers: Dict[str, str] = None
    feed_urls: List[str] = None

class ContentCrawler:
    def __init__(self, max_pages: int = 10):
        self.max_pages = max_pages
        self.logger = logging.getLogger(__name__)
        self.visited_urls: Set[str] = set()
        self.content_urls: Dict[ContentType, Set[str]] = {ct: set() for ct in ContentType}
        
        # Site-specific configurations
        self.site_configs = {
            'quill.co': SiteConfig(
                domain='quill.co',
                content_selectors=[
                    'article a', '.blog-post a', '.post-title a',
                    'a[href*="/blog/"]', '.blog-list a',
                    '.post-preview a', '.entry-title a',
                    '[data-testid="blog-post-link"]',
                    '.blog-grid a', '.post-grid a'
                ],
                pagination_selectors=['.pagination a', '.next-page', 'a[rel="next"]'],
                content_patterns=[r'/blog/[^/]+$'],
                requires_js=True,
                infinite_scroll=True,
                use_playwright=True,
                wait_for_selectors=['.blog-list', '.post-list', 'article'],
                scroll_pause_time=3.0,
                max_scroll_attempts=15,
                feed_urls=[
                    '/feed',
                    '/feed.xml',
                    '/rss',
                    '/rss.xml',
                    '/atom.xml',
                    '/feed/atom',
                    '/feed/rss',
                    '/blog/feed',
                    '/blog/feed.xml',
                    '/blog/rss',
                    '/blog/rss.xml'
                ],
                custom_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                }
            ),
            'substack.com': SiteConfig(
                domain='substack.com',
                content_selectors=[
                    '.post-preview a', '.post-title a',
                    'article a', '.entry-title a',
                    '.post-list a', '.archive-item a',
                    'a[href*="/p/"]', '.post a',
                    '[data-testid="post-link"]',
                    '.post-grid a'
                ],
                pagination_selectors=['.pagination a', '.next-page'],
                content_patterns=[r'/p/[^/]+$'],
                requires_js=True,
                infinite_scroll=True,
                use_undetected=True,
                wait_for_selectors=['.post-list', '.archive-list', 'article'],
                scroll_pause_time=2.5,
                max_scroll_attempts=20,
                feed_urls=[
                    '/feed',
                    '/feed.xml',
                    '/rss',
                    '/rss.xml',
                    '/atom.xml',
                    '/feed/atom',
                    '/feed/rss',
                    '/archive/feed',
                    '/archive/feed.xml',
                    '/archive/rss',
                    '/archive/rss.xml'
                ],
                custom_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                }
            ),
            'interviewing.io': SiteConfig(
                domain='interviewing.io',
                content_selectors=[
                    '.blog-list a', '.blog-entry a', '.post-list a',
                    'article a', '.blog-item a', '.post-title a',
                    'a[href*="/blog/"]', '.entry-title a',
                    '[data-testid="blog-link"]',
                    '.blog-grid a',
                    'a[href^="/topics/"]',
                    'a[href^="/learn/"]',
                ],
                pagination_selectors=['.pagination a', '.next-page'],
                content_patterns=[r'/blog/[^/]+$', r'/learn/[^/]+$', r'/topics/[^#]+$'],
                requires_js=True,
                api_endpoints=['/api/blog/posts'],
                use_playwright=True,
                wait_for_selectors=['.blog-list', '.post-list', 'article'],
                feed_urls=[
                    '/feed',
                    '/feed.xml',
                    '/rss',
                    '/rss.xml',
                    '/atom.xml',
                    '/feed/atom',
                    '/feed/rss',
                    '/blog/feed',
                    '/blog/feed.xml',
                    '/blog/rss',
                    '/blog/rss.xml'
                ],
                custom_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                }
            )
        }
        
        # Initialize tools
        self.driver = None
        self.playwright = None
        self.scraper = cloudscraper.create_scraper()
        self.ua = UserAgent()

    async def crawl(self, start_url: str) -> Dict[ContentType, List[str]]:
        """Crawl a website to find all content URLs using multiple strategies, with a fallback to all-links extraction."""
        try:
            domain = urlparse(start_url).netloc
            site_config = self._get_site_config(domain)
            self.logger.info(f"Crawling {domain} with {len(site_config.content_selectors)} selectors")
            # Try multiple crawling strategies in order of preference
            strategies = []
            if 'quill.co' in domain:
                strategies = [self._crawl_with_quill_api, self._crawl_with_playwright, self._crawl_with_quill_bs]
            else:
                strategies = [
                    self._crawl_with_feed,
                    self._crawl_with_playwright if site_config.use_playwright else None,
                    self._crawl_with_undetected if site_config.use_undetected else None,
                    self._crawl_with_selenium,
                    self._crawl_with_cloudscraper if site_config.use_cloudscraper else None,
                    self._crawl_with_api,
                    self._crawl_with_requests,
                    self._crawl_with_aggressive_selenium  # Aggressive fallback
                ]
                strategies = [s for s in strategies if s is not None]
            found_urls = set()
            for strategy in strategies:
                try:
                    urls = await strategy(start_url, site_config)
                    if urls:
                        found_urls.update(urls)
                        content_type = self._determine_content_type(start_url)
                        self.content_urls[content_type].update(urls)
                        break
                except Exception as e:
                    self.logger.warning(f"Strategy {strategy.__name__} failed: {str(e)}")
                    continue
            # Fallback: extract all links if nothing found
            if not found_urls:
                try:
                    resp = requests.get(start_url, headers={'User-Agent': self.ua.random}, timeout=10)
                    if resp.status_code == 200:
                        all_links = self._extract_all_links(resp.text, start_url)
                        # Optionally filter links by domain
                        all_links = {l for l in all_links if urlparse(l).netloc == domain}
                        if all_links:
                            self.logger.info(f"Fallback: extracted {len(all_links)} links from {start_url}")
                            content_type = self._determine_content_type(start_url)
                            self.content_urls[content_type].update(all_links)
                except Exception as e:
                    self.logger.error(f"Fallback all-links extraction failed: {str(e)}")
            return {ct: list(urls) for ct, urls in self.content_urls.items() if urls}
        except Exception as e:
            self.logger.error(f"Error crawling {start_url}: {str(e)}")
            return {ct: list(urls) for ct, urls in self.content_urls.items() if urls}
        finally:
            await self._cleanup()

    async def _crawl_with_feed(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using RSS/XML feeds."""
        urls = set()
        domain = urlparse(url).netloc
        
        try:
            # Try to find feed URL in HTML first
            feed_urls = await self._discover_feed_urls(url)
            
            # Add site-specific feed URLs
            if site_config.feed_urls:
                base_url = f"https://{domain}"
                feed_urls.extend([urljoin(base_url, feed_path) for feed_path in site_config.feed_urls])
            
            # Try each feed URL
            for feed_url in feed_urls:
                try:
                    self.logger.debug(f"Trying feed URL: {feed_url}")
                    
                    # Try parsing as RSS/Atom feed
                    feed = feedparser.parse(feed_url)
                    if feed.entries:
                        for entry in feed.entries:
                            if 'link' in entry:
                                urls.add(entry.link)
                            elif 'id' in entry:
                                urls.add(entry.id)
                    
                    # Try parsing as XML
                    response = requests.get(feed_url, headers={'User-Agent': self.ua.random})
                    if response.status_code == 200:
                        try:
                            root = ET.fromstring(response.content)
                            # Look for common feed item elements
                            for item in root.findall('.//{*}item') + root.findall('.//{*}entry'):
                                link = item.find('.//{*}link')
                                if link is not None and link.text:
                                    urls.add(link.text)
                                elif link is not None and 'href' in link.attrib:
                                    urls.add(link.attrib['href'])
                        except ET.ParseError:
                            continue
                    
                    if urls:
                        self.logger.info(f"Found {len(urls)} URLs in feed: {feed_url}")
                        break
                        
                except Exception as e:
                    self.logger.debug(f"Failed to parse feed {feed_url}: {str(e)}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Feed crawl error: {str(e)}")
        
        return urls

    async def _discover_feed_urls(self, url: str) -> List[str]:
        """Discover feed URLs from HTML page."""
        feed_urls = []
        
        try:
            response = requests.get(url, headers={'User-Agent': self.ua.random})
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for feed links in HTML
                feed_links = soup.find_all('link', type=lambda t: t and ('rss' in t.lower() or 'atom' in t.lower()))
                feed_links.extend(soup.find_all('a', href=lambda h: h and ('feed' in h.lower() or 'rss' in h.lower() or 'atom' in h.lower())))
                
                for link in feed_links:
                    href = link.get('href')
                    if href:
                        feed_urls.append(urljoin(url, href))
                
                # Look for feed URLs in meta tags
                meta_links = soup.find_all('meta', attrs={'name': ['alternate', 'feed']})
                for meta in meta_links:
                    href = meta.get('href') or meta.get('content')
                    if href:
                        feed_urls.append(urljoin(url, href))
                
        except Exception as e:
            self.logger.debug(f"Error discovering feed URLs: {str(e)}")
        
        return feed_urls

    async def _crawl_with_playwright(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using Playwright for better JavaScript handling, with Quill-specific logic for network interception and button-based navigation."""
        urls = set()
        domain = urlparse(url).netloc
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.ua.random,
                    viewport={'width': 1920, 'height': 1080}
                )
                if site_config.custom_headers:
                    await context.set_extra_http_headers(site_config.custom_headers)
                page = await context.new_page()
                await page.goto(url, wait_until='networkidle')
                if 'quill.co' in domain:
                    intercepted_urls = set()
                    def handle_request(request):
                        req_url = request.url
                        if '/blog/' in req_url and req_url not in [url, url + '/']:
                            intercepted_urls.add(req_url)
                    page.on('request', handle_request)
                    try:
                        await page.wait_for_selector('.bg-white.p-\\[30px\\]', timeout=20000)
                    except:
                        pass
                    for _ in range(15):
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(1)
                    cards = await page.query_selector_all('.bg-white.p-\\[30px\\]')
                    for i, card in enumerate(cards):
                        try:
                            button = await card.query_selector('button')
                            if button:
                                async with context.expect_page() as new_page_info:
                                    await button.click(button="left", modifiers=[], force=True)
                                new_page = await new_page_info.value
                                await new_page.wait_for_load_state('networkidle')
                                post_url = new_page.url
                                if post_url and '/blog/' in post_url and post_url not in [url, url + '/']:
                                    urls.add(post_url)
                                await new_page.close()
                        except Exception as e:
                            self.logger.debug(f"[Playwright][Quill] Error clicking blog card {i}: {str(e)}")
                    urls.update(intercepted_urls)
                else:
                    # Default logic for other sites
                    if site_config.wait_for_selectors:
                        for selector in site_config.wait_for_selectors:
                            try:
                                await page.wait_for_selector(selector, timeout=10000)
                            except:
                                continue
                    if site_config.infinite_scroll:
                        await self._handle_playwright_infinite_scroll(page, site_config)
                    for selector in site_config.content_selectors:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            href = await element.get_attribute('href')
                            if href and self._is_valid_content_url(href, site_config):
                                urls.add(href)
                    page_num = 1
                    while page_num < self.max_pages:
                        next_page = self._get_next_page_url(url, page_num, site_config)
                        if not next_page:
                            break
                        await page.goto(next_page, wait_until='networkidle')
                        await asyncio.sleep(site_config.scroll_pause_time)
                        for selector in site_config.content_selectors:
                            elements = await page.query_selector_all(selector)
                            for element in elements:
                                href = await element.get_attribute('href')
                                if href and self._is_valid_content_url(href, site_config):
                                    urls.add(href)
                        page_num += 1
                await browser.close()
        except Exception as e:
            self.logger.error(f"Playwright crawl error: {str(e)}")
        return urls

    async def _crawl_with_undetected(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using undetected-chromedriver to bypass anti-bot measures."""
        urls = set()
        
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument(f'user-agent={self.ua.random}')
            
            if site_config.custom_headers:
                for key, value in site_config.custom_headers.items():
                    options.add_argument(f'--header={key}: {value}')
            
            driver = uc.Chrome(options=options)
            
            try:
                driver.get(url)
                time.sleep(site_config.scroll_pause_time)
                
                # Wait for content to load
                if site_config.wait_for_selectors:
                    for selector in site_config.wait_for_selectors:
                        try:
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                        except:
                            continue
                
                # Handle infinite scroll
                if site_config.infinite_scroll:
                    self._handle_infinite_scroll(driver, site_config)
                
                # Extract URLs
                for selector in site_config.content_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        href = element.get_attribute('href')
                        if href and self._is_valid_content_url(href, site_config):
                            urls.add(href)
                
                # Handle pagination
                page_num = 1
                while page_num < self.max_pages:
                    next_page = self._get_next_page_url(url, page_num, site_config)
                    if not next_page:
                        break
                    
                    driver.get(next_page)
                    time.sleep(site_config.scroll_pause_time)
                    
                    for selector in site_config.content_selectors:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            href = element.get_attribute('href')
                            if href and self._is_valid_content_url(href, site_config):
                                urls.add(href)
                    
                    page_num += 1
                
            finally:
                driver.quit()
                
        except Exception as e:
            self.logger.error(f"Undetected Chrome crawl error: {str(e)}")
        
        return urls

    async def _crawl_with_cloudscraper(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using cloudscraper to bypass Cloudflare protection."""
        urls = set()
        
        try:
            headers = site_config.custom_headers or {}
            headers['User-Agent'] = self.ua.random
            
            response = self.scraper.get(url, headers=headers)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract URLs using selectors
                for selector in site_config.content_selectors:
                    for element in soup.select(selector):
                        href = element.get('href')
                        if href and self._is_valid_content_url(href, site_config):
                            urls.add(href)
                
                # Handle pagination
                page_num = 1
                while page_num < self.max_pages:
                    next_page = self._get_next_page_url(url, page_num, site_config)
                    if not next_page:
                        break
                    
                    response = self.scraper.get(next_page, headers=headers)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        for selector in site_config.content_selectors:
                            for element in soup.select(selector):
                                href = element.get('href')
                                if href and self._is_valid_content_url(href, site_config):
                                    urls.add(href)
                    page_num += 1
                    
        except Exception as e:
            self.logger.error(f"Cloudscraper crawl error: {str(e)}")
        
        return urls

    async def _handle_playwright_infinite_scroll(self, page, site_config: SiteConfig):
        """Handle infinite scroll using Playwright."""
        last_height = await page.evaluate('document.body.scrollHeight')
        attempts = 0
        
        while attempts < site_config.max_scroll_attempts:
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(site_config.scroll_pause_time)
            
            new_height = await page.evaluate('document.body.scrollHeight')
            if new_height == last_height:
                break
                
            last_height = new_height
            attempts += 1

    def _handle_infinite_scroll(self, driver, site_config: SiteConfig):
        """Handle infinite scroll using Selenium."""
        last_height = driver.execute_script("return document.body.scrollHeight")
        attempts = 0
        
        while attempts < site_config.max_scroll_attempts:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(site_config.scroll_pause_time)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
                
            last_height = new_height
            attempts += 1

    async def _cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            self.driver = None
        if self.playwright:
            await self.playwright.close()
            self.playwright = None

    def _init_browser(self):
        """Initialize the browser if not already initialized."""
        if not self.driver:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            # Use WebDriverManager to get the path, but ensure we use chromedriver.exe, not a text file
            driver_path = ChromeDriverManager().install()
            # On Windows, ensure we use chromedriver.exe
            if os.name == 'nt' and not driver_path.endswith('chromedriver.exe'):
                # Look for chromedriver.exe in the same directory
                exe_path = os.path.join(os.path.dirname(driver_path), 'chromedriver.exe')
                if os.path.exists(exe_path):
                    driver_path = exe_path
            self.driver = webdriver.Chrome(
                service=Service(driver_path),
                options=chrome_options
            )

    async def _crawl_with_selenium(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using Selenium for JavaScript-heavy sites."""
        if not site_config.requires_js:
            return set()
            
        self._init_browser()
        urls = set()
        
        try:
            self.driver.get(url)
            time.sleep(2)  # Initial load wait
            
            # Handle infinite scroll
            if site_config.infinite_scroll:
                self._handle_infinite_scroll()
            
            # Extract URLs using selectors
            for selector in site_config.content_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    href = element.get_attribute('href')
                    if href and self._is_valid_content_url(href, site_config):
                        urls.add(href)
            
            # Handle pagination
            page = 1
            while page < self.max_pages:
                next_page = self._get_next_page_url(url, page, site_config)
                if not next_page:
                    break
                    
                self.driver.get(next_page)
                time.sleep(2)
                
                for selector in site_config.content_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        href = element.get_attribute('href')
                        if href and self._is_valid_content_url(href, site_config):
                            urls.add(href)
                
                page += 1
                
        except Exception as e:
            self.logger.error(f"Selenium crawl error: {str(e)}")
            
        return urls

    async def _crawl_with_api(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using API endpoints if available."""
        if not site_config.api_endpoints:
            return set()
            
        urls = set()
        domain = urlparse(url).netloc
        
        try:
            for endpoint in site_config.api_endpoints:
                api_url = f"https://{domain}{endpoint}"
                response = requests.get(api_url)
                if response.status_code == 200:
                    data = response.json()
                    urls.update(self._extract_urls_from_api_response(data, site_config))
        except Exception as e:
            self.logger.error(f"API crawl error: {str(e)}")
            
        return urls

    async def _crawl_with_requests(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Crawl using simple HTTP requests for static sites."""
        urls = set()
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract URLs using selectors
                for selector in site_config.content_selectors:
                    for element in soup.select(selector):
                        href = element.get('href')
                        if href and self._is_valid_content_url(href, site_config):
                            urls.add(href)
                            
                # Handle pagination
                page = 1
                while page < self.max_pages:
                    next_page = self._get_next_page_url(url, page, site_config)
                    if not next_page:
                        break
                        
                    response = requests.get(next_page)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        for selector in site_config.content_selectors:
                            for element in soup.select(selector):
                                href = element.get('href')
                                if href and self._is_valid_content_url(href, site_config):
                                    urls.add(href)
                    page += 1
                    
        except Exception as e:
            self.logger.error(f"Requests crawl error: {str(e)}")
            
        return urls

    def _get_site_config(self, domain: str) -> SiteConfig:
        """Get site-specific configuration."""
        for config in self.site_configs.values():
            if config.domain in domain:
                return config
        return SiteConfig(
            domain=domain,
            content_selectors=['article a', '.post a', '.blog-post a'],
            pagination_selectors=['.pagination a', '.next-page'],
            content_patterns=[r'/blog/[^/]+$', r'/post/[^/]+$']
        )

    def _is_valid_content_url(self, url: str, site_config: SiteConfig) -> bool:
        """Check if URL is a valid content URL based on site configuration."""
        if not url or url in self.visited_urls:
            return False
            
        self.visited_urls.add(url)
        
        # Check against content patterns
        for pattern in site_config.content_patterns:
            if re.search(pattern, url):
                return True
                
        return False

    def _get_next_page_url(self, base_url: str, page: int, site_config: SiteConfig) -> Optional[str]:
        """Get the next page URL based on site configuration."""
        for pattern in site_config.pagination_selectors:
            if '{page}' in pattern:
                return urljoin(base_url, pattern.format(page=page))
        return None

    def _extract_urls_from_api_response(self, data: dict, site_config: SiteConfig) -> Set[str]:
        """Extract URLs from API response data."""
        urls = set()
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and self._is_valid_content_url(value, site_config):
                    urls.add(value)
                elif isinstance(value, (dict, list)):
                    urls.update(self._extract_urls_from_api_response(value, site_config))
        elif isinstance(data, list):
            for item in data:
                urls.update(self._extract_urls_from_api_response(item, site_config))
        return urls

    def _determine_content_type(self, url: str) -> ContentType:
        """Determine the content type based on URL patterns."""
        url_lower = url.lower()
        
        for content_type, pattern in self.site_configs.items():
            if any(re.search(p, url_lower) for p in pattern.content_patterns):
                return content_type
        
        # Check for common blog indicators
        if 'blog' in url_lower or 'posts' in url_lower:
            return ContentType.BLOG
        
        return ContentType.UNKNOWN

    async def _crawl_with_quill_api(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Try to find and call Quill's API endpoints to extract blog post URLs."""
        urls = set()
        domain = urlparse(url).netloc
        api_candidates = [
            f'https://{domain}/api/blog',
            f'https://{domain}/api/posts',
            f'https://{domain}/api/blog/posts',
            f'https://{domain}/api/articles',
            f'https://{domain}/api/blog-articles',
        ]
        headers = site_config.custom_headers or {}
        headers['User-Agent'] = self.ua.random
        for api_url in api_candidates:
            try:
                resp = requests.get(api_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    # Recursively extract all URLs containing '/blog/'
                    def extract_blog_urls(obj):
                        if isinstance(obj, dict):
                            for v in obj.values():
                                extract_blog_urls(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_blog_urls(item)
                        elif isinstance(obj, str):
                            if '/blog/' in obj:
                                urls.add(obj)
                    extract_blog_urls(data)
            except Exception as e:
                self.logger.debug(f"[Quill API] Failed to fetch {api_url}: {str(e)}")
        return urls

    async def _crawl_with_quill_bs(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Try to extract blog post URLs from static HTML using BeautifulSoup heuristics for Quill."""
        urls = set()
        domain = urlparse(url).netloc
        try:
            headers = site_config.custom_headers or {}
            headers['User-Agent'] = self.ua.random
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Find all blog post cards (improved: handle both class and main content area)
                cards = soup.find_all('div', class_='bg-white')
                for card in cards:
                    # Try to find the title
                    h = card.find(['h1', 'h2', 'h3', 'h4'])
                    title = h.get_text(strip=True) if h else None
                    # Try to find a button with 'Read more' text
                    button = card.find('button', string=lambda s: s and 'read more' in s.lower())
                    # Try to find a data attribute or reconstruct a slug
                    if title:
                        slug = title.lower().replace(' ', '-').replace('?', '').replace('.', '').replace(',', '').replace("'", "")
                        candidate_url = f'https://{domain}/blog/{slug}'
                        urls.add(candidate_url)
                # Also look for all headings in the main content area
                main = soup.find('main') or soup
                for h in main.find_all(['h1', 'h2', 'h3', 'h4']):
                    title = h.get_text(strip=True)
                    if title:
                        slug = title.lower().replace(' ', '-').replace('?', '').replace('.', '').replace(',', '').replace("'", "")
                        candidate_url = f'https://{domain}/blog/{slug}'
                        urls.add(candidate_url)
        except Exception as e:
            self.logger.debug(f"[Quill BeautifulSoup] Failed to parse static HTML: {str(e)}")
        # Try sitemap.xml as a last fallback
        try:
            sitemap_url = f'https://{domain}/sitemap.xml'
            resp = requests.get(sitemap_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'xml')
                for loc in soup.find_all('loc'):
                    loc_url = loc.get_text()
                    if '/blog/' in loc_url:
                        urls.add(loc_url)
        except Exception as e:
            self.logger.debug(f"[Quill BeautifulSoup] Failed to parse sitemap.xml: {str(e)}")
        return urls

    async def _crawl_with_aggressive_selenium(self, url: str, site_config: SiteConfig) -> Set[str]:
        """Aggressive Selenium fallback: render, scroll, and extract all <a> tags as content URLs."""
        urls = set()
        try:
            self._init_browser()
            self.driver.get(url)
            for _ in range(15):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            anchors = self.driver.find_elements(By.TAG_NAME, "a")
            for a in anchors:
                href = a.get_attribute('href')
                if href and self._is_valid_content_url(href, site_config):
                    urls.add(href)
            self.driver.quit()
        except Exception as e:
            self.logger.error(f"Aggressive Selenium crawl error: {str(e)}")
        return urls

    def _extract_all_links(self, html, base_url):
        """Extract all <a href> links from the page."""
        soup = BeautifulSoup(html, 'html.parser')
        links = set()
        for tag in soup.find_all('a', href=True):
            full_url = urljoin(base_url, tag['href'])
            if full_url.startswith('http'):
                links.add(full_url)
        return links