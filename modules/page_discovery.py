"""
page_discovery.py - Intelligent page discovery for e-commerce sites.

Discovers relevant pages via sitemaps, priority paths, and link crawling.
Prioritizes pages most useful for competitive intelligence.
"""

import re
import logging
import xml.etree.ElementTree as ET
from typing import List, Set, Optional, Tuple
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from .models import Config
from .http_client import HttpClient
from .robots_checker import RobotsChecker
from .url_utils import (
    normalize_url, categorize_page_type, get_priority_pages,
    extract_links_from_soup, is_internal_link
)
from . import obs

logger = logging.getLogger(__name__)


class PageDiscovery:
    """
    Discovers pages on an e-commerce site for analysis.
    
    Uses multiple strategies:
    1. Priority paths (known e-commerce page patterns)
    2. Sitemap.xml parsing
    3. Link crawling with limits
    """
    
    def __init__(
        self,
        client: HttpClient,
        robots_checker: RobotsChecker,
        config: Config
    ):
        self.client = client
        self.robots_checker = robots_checker
        self.config = config
    
    def discover(self, base_url: str) -> List[Tuple[str, str]]:
        """
        Discover pages on the site.
        
        Args:
            base_url: The site's home page URL
            
        Returns:
            List of (url, page_type) tuples
        """
        discovered: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        
        # Normalize base URL
        base_url = normalize_url(base_url)
        
        origin = {}

        # 1. Add priority pages first
        priority = get_priority_pages(base_url)
        for url, page_type in priority:
            if url not in seen and self.robots_checker.is_allowed(url):
                seen.add(url)
                discovered.append((url, page_type))
                origin[url] = 'guessed_priority_path'

        logger.info(f"Added {len(discovered)} priority pages for {base_url}")
        obs.event("discovery", "success", kind="priority_paths", candidates=len(priority),
                  added=len(discovered))

        # 2. Try to parse sitemap
        sitemap_pages = self._parse_sitemap(base_url)
        for url, page_type in sitemap_pages:
            if url not in seen and self.robots_checker.is_allowed(url):
                seen.add(url)
                discovered.append((url, page_type))
                origin[url] = 'sitemap'

        logger.info(f"Added {len(sitemap_pages)} pages from sitemap")
        obs.event("discovery", "success", kind="sitemap", found=len(sitemap_pages))

        # 3. Crawl links from home page if we don't have enough pages
        if len(discovered) < self.config.max_pages:
            crawled = self._crawl_links(base_url, seen)
            for url, page_type in crawled:
                if len(discovered) >= self.config.max_pages:
                    break
                discovered.append((url, page_type))
                origin[url] = 'homepage_link'
        else:
            obs.degraded("page_discovery.py:discover", "unknown",
                         f"{len(discovered)} guessed/sitemap pages already >= max_pages={self.config.max_pages}",
                         fallback="homepage links are never crawled", stage="discovery")
        
        # Sort by priority: home first, then collections, products, policies
        priority_order = {
            'home': 0,
            'collection': 1,
            'product': 2,
            'policy': 3,
            'about': 4,
            'contact': 5,
            'other': 6,
        }
        discovered.sort(key=lambda x: priority_order.get(x[1], 9))
        
        # Limit to max pages
        dropped = discovered[self.config.max_pages:]
        discovered = discovered[:self.config.max_pages]

        logger.info(f"Discovered {len(discovered)} total pages for {base_url}")
        obs.event("discovery", "success", kind="page_list", count=len(discovered),
                  pages=[{"url": u, "type": t, "origin": origin.get(u)} for u, t in discovered],
                  dropped_by_max_pages=[u for u, _ in dropped])
        return discovered
    
    def _parse_sitemap(self, base_url: str) -> List[Tuple[str, str]]:
        """Parse sitemap.xml to find pages."""
        pages: List[Tuple[str, str]] = []
        
        # Get sitemap URLs from robots.txt
        sitemap_urls = self.robots_checker.get_sitemaps(base_url)
        
        # Also try common locations
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        common_sitemaps = [
            f"{base}/sitemap.xml",
            f"{base}/sitemap_index.xml",
            f"{base}/sitemap-products.xml",
        ]
        
        for sitemap_url in list(set(sitemap_urls + common_sitemaps)):
            pages.extend(self._fetch_sitemap(sitemap_url))
            
            # Stop if we have enough pages
            if len(pages) >= self.config.max_pages * 2:
                break
        
        return pages
    
    def _fetch_sitemap(self, sitemap_url: str) -> List[Tuple[str, str]]:
        """Fetch and parse a single sitemap."""
        pages: List[Tuple[str, str]] = []
        
        # Validate URL
        if not sitemap_url or not sitemap_url.startswith('http'):
            obs.degraded("page_discovery.py:_fetch_sitemap", "input_invalid", "invalid sitemap URL",
                         fallback="[]", stage="discovery", url=sitemap_url)
            logger.debug(f"Invalid sitemap URL: {sitemap_url}")
            return pages

        try:
            html, status, headers, error = self.client.fetch(sitemap_url)

            if error or not html:
                obs.degraded("page_discovery.py:_fetch_sitemap", obs.classify_fetch(status, error) or "http",
                             error or "empty sitemap body", fallback="[]", stage="discovery", url=sitemap_url)
                return pages
            
            # Try to parse as XML
            root = ET.fromstring(html)
            
            # Remove namespace for easier parsing
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Check if this is a sitemap index
            sitemap_refs = root.findall('.//ns:sitemap/ns:loc', ns)
            if sitemap_refs:
                # This is a sitemap index, fetch child sitemaps
                for ref in sitemap_refs[:3]:  # Limit to first 3 sub-sitemaps
                    child_url = ref.text.strip() if ref.text else ""
                    if child_url.startswith('http'):
                        pages.extend(self._fetch_sitemap(child_url))
            
            # Parse URL entries
            urls = root.findall('.//ns:url/ns:loc', ns)
            for url_elem in urls:
                if url_elem.text:
                    url = url_elem.text.strip()
                    page_type = categorize_page_type(url)
                    
                    # Only include relevant page types
                    if page_type in ('home', 'product', 'collection', 'policy', 'about'):
                        pages.append((normalize_url(url), page_type))
            
            logger.debug(f"Found {len(urls)} URLs in {sitemap_url}")
            
        except ET.ParseError:
            obs.swallowed("page_discovery.py:_fetch_sitemap", error_type="parse", fallback="pages so far",
                          stage="discovery", url=sitemap_url)
            logger.debug(f"Could not parse sitemap XML: {sitemap_url}")
        except Exception as e:
            obs.swallowed("page_discovery.py:_fetch_sitemap", fallback="pages so far",
                          stage="discovery", url=sitemap_url)
            logger.debug(f"Sitemap fetch error for {sitemap_url}: {e}")
        
        return pages
    
    def _crawl_links(
        self,
        base_url: str,
        seen: Set[str]
    ) -> List[Tuple[str, str]]:
        """Crawl links from the home page."""
        pages: List[Tuple[str, str]] = []
        
        # Fetch home page
        soup, status, error = self.client.fetch_and_parse(base_url)

        if error or not soup:
            obs.degraded("page_discovery.py:_crawl_links", obs.classify_fetch(status, error) or "http",
                         error or "no soup", fallback="no crawled links", stage="discovery", url=base_url)
            return pages
        
        # Extract links
        links = extract_links_from_soup(soup, base_url)
        
        for url, link_text in links:
            if url in seen:
                continue
            
            if not self.robots_checker.is_allowed(url):
                continue
            
            page_type = categorize_page_type(url)
            
            # Filter out blog, cart, account pages
            if page_type in ('blog', 'other'):
                # Check if link text suggests relevance
                relevant_keywords = [
                    'shop', 'product', 'collection', 'about', 'shipping',
                    'return', 'policy', 'sale', 'new', 'men', 'women',
                    'category', 'best seller'
                ]
                if not any(kw in link_text.lower() for kw in relevant_keywords):
                    continue
            
            seen.add(url)
            pages.append((url, page_type))
            
            if len(pages) >= self.config.max_pages:
                break
        
        return pages


def discover_pages(
    base_url: str,
    client: HttpClient,
    robots_checker: RobotsChecker,
    config: Config
) -> List[Tuple[str, str]]:
    """
    Convenience function for page discovery.
    
    Args:
        base_url: The site's home page URL
        client: HTTP client instance
        robots_checker: Robots.txt checker instance
        config: Application configuration
        
    Returns:
        List of (url, page_type) tuples
    """
    discovery = PageDiscovery(client, robots_checker, config)
    return discovery.discover(base_url)
