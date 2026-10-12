"""
page_discovery.py - Find the pages worth fetching on an e-commerce site.

Order of sources:
1. Links on the homepage (collection, product and policy pages), within robots.txt.
2. For page kinds the homepage did not link to: platform-known paths
   (Shopify /collections/all, /policies/*; WooCommerce /shop, /refund_returns).
3. If no product page was found: sitemaps declared in robots.txt, else the
   platform's own sitemap location.

Nothing is guessed for a page kind that is already found, and nothing at all
for a platform this module does not know.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin, urlunparse

from .models import Config, Platform
from .http_client import HttpClient
from .robots_checker import RobotsChecker
from .url_utils import normalize_url, categorize_page_type, extract_links_from_soup
from . import obs

logger = logging.getLogger(__name__)

# (path, page_type, kind) per platform; tried only for kinds the crawl did not find
PLATFORM_PATHS = {
    Platform.SHOPIFY: [
        ('/collections/all', 'collection', 'collection'),
        ('/policies/shipping-policy', 'policy', 'shipping'),
        ('/policies/refund-policy', 'policy', 'returns'),
    ],
    Platform.WOOCOMMERCE: [
        ('/shop', 'collection', 'collection'),
        ('/refund_returns', 'policy', 'returns'),
    ],
}
PLATFORM_SITEMAPS = {
    Platform.SHOPIFY: '/sitemap.xml',
    Platform.WOOCOMMERCE: '/wp-sitemap.xml',
}
CRAWLED_TYPES = ('collection', 'product', 'policy')


def page_kind(url: str, page_type: str) -> Optional[str]:
    """collection / product / shipping / returns, or None for other pages."""
    if page_type in ('collection', 'product'):
        return page_type
    if page_type == 'policy':
        path = urlparse(url.lower()).path
        if 'shipping' in path or 'delivery' in path:
            return 'shipping'
        if 'return' in path or 'refund' in path:
            return 'returns'
    return None


# Inside max_pages every kind gets a share: a store's menu can link dozens of collections, which
# used to fill the whole budget before any policy or product page.
FIRST_COLLECTIONS = 2
FIRST_PRODUCTS = 5


def order_pages(pages: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Fetch order: the first collections, shipping/returns policies, the first products, the
    remaining collections, the remaining products, other policies. Stable within each tier."""
    seen = {'collection': 0, 'product': 0}

    def tier(page):
        kind = page_kind(*page)
        if kind in ('shipping', 'returns'):
            return 1
        if kind in seen:
            seen[kind] += 1
            first = FIRST_COLLECTIONS if kind == 'collection' else FIRST_PRODUCTS
            if seen[kind] <= first:
                return 0 if kind == 'collection' else 2
            return 3 if kind == 'collection' else 4
        return 5

    tiers = [tier(p) for p in pages]
    return [p for _, _, p in sorted(zip(tiers, range(len(pages)), pages))]


class PageDiscovery:
    """Discovers the pages of one site to analyse (homepage excluded)."""

    def __init__(
        self,
        client: HttpClient,
        robots_checker: RobotsChecker,
        config: Config
    ):
        self.client = client
        self.robots_checker = robots_checker
        self.config = config

    def discover(self, base_url: str, platform: Optional[Platform] = None,
                 homepage_soup=None) -> List[Tuple[str, str]]:
        """
        Args:
            base_url: The site's home page URL
            platform: detected platform; decides which paths may be guessed
            homepage_soup: the already-fetched homepage (fetched here if None)

        Returns:
            List of (url, page_type) tuples, at most max_pages - 1 (the homepage
            counts as one page), homepage not included.
        """
        base_url = normalize_url(base_url)
        found: List[Tuple[str, str]] = []
        origin: Dict[str, str] = {}
        seen: Set[str] = {base_url}

        for url, page_type in self._crawl_links(base_url, homepage_soup):
            if url not in seen:
                seen.add(url)
                found.append((url, page_type))
                origin[url] = 'homepage_link'
        kinds = {page_kind(u, t) for u, t in found} - {None}
        obs.event("discovery", "success", kind="homepage_links", pages=len(found), kinds=sorted(kinds))

        guessed = []
        for path, page_type, kind in PLATFORM_PATHS.get(platform, []):
            url = normalize_url(urljoin(base_url, path))
            if kind in kinds or url in seen:
                continue
            if self.robots_checker.is_allowed(url):
                seen.add(url)
                found.append((url, page_type))
                origin[url] = 'guessed_platform_path'
                guessed.append(path)
        obs.event("discovery", "success" if guessed else "skip", kind="platform_paths",
                  platform=platform.value if platform else None, guessed=guessed,
                  reason=None if guessed else "every kind found by the crawl, or no known paths for this platform")

        if 'product' not in kinds:
            for url, page_type in self._parse_sitemap(base_url, platform):
                if url not in seen and self.robots_checker.is_allowed(url):
                    seen.add(url)
                    found.append((url, page_type))
                    origin[url] = 'sitemap'
        else:
            obs.skip("discovery", "product pages linked from the homepage; sitemaps not needed")

        found = order_pages(found)
        limit = max(self.config.max_pages - 1, 0)
        dropped = found[limit:]
        found = found[:limit]

        logger.info(f"Discovered {len(found)} pages for {base_url}")
        obs.event("discovery", "success", kind="page_list", count=len(found),
                  pages=[{"url": u, "type": t, "origin": origin.get(u)} for u, t in found],
                  dropped_by_max_pages=[u for u, _ in dropped])
        return found

    def _parse_sitemap(self, base_url: str, platform: Optional[Platform]) -> List[Tuple[str, str]]:
        """Sitemaps declared in robots.txt, else the platform's own sitemap location."""
        pages: List[Tuple[str, str]] = []
        sitemap_urls = list(dict.fromkeys(self.robots_checker.get_sitemaps(base_url)))
        if not sitemap_urls and platform in PLATFORM_SITEMAPS:
            parsed = urlparse(base_url)
            sitemap_urls = [urlunparse((parsed.scheme, parsed.netloc, PLATFORM_SITEMAPS[platform], '', '', ''))]
        for sitemap_url in sitemap_urls:
            pages.extend(self._fetch_sitemap(sitemap_url))
            if len(pages) >= self.config.max_pages * 2:
                break
        return pages

    def _fetch_sitemap(self, sitemap_url: str) -> List[Tuple[str, str]]:
        """Fetch and parse a single sitemap."""
        pages: List[Tuple[str, str]] = []

        if not sitemap_url or not sitemap_url.startswith('http'):
            obs.degraded("page_discovery.py:_fetch_sitemap", "input_invalid", "invalid sitemap URL",
                         fallback="[]", stage="discovery", url=sitemap_url)
            return pages

        try:
            html, status, headers, error = self.client.fetch(sitemap_url)

            if error or not html:
                obs.degraded("page_discovery.py:_fetch_sitemap", obs.classify_fetch(status, error) or "http",
                             error or "empty sitemap body", fallback="[]", stage="discovery", url=sitemap_url)
                return pages

            root = ET.fromstring(html)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            # Sitemap index: follow the first three child sitemaps
            for ref in root.findall('.//ns:sitemap/ns:loc', ns)[:3]:
                child_url = ref.text.strip() if ref.text else ""
                if child_url.startswith('http'):
                    pages.extend(self._fetch_sitemap(child_url))

            for url_elem in root.findall('.//ns:url/ns:loc', ns):
                if url_elem.text:
                    url = normalize_url(url_elem.text.strip())
                    page_type = categorize_page_type(url)
                    if page_type in CRAWLED_TYPES:
                        pages.append((url, page_type))

        except ET.ParseError:
            obs.swallowed("page_discovery.py:_fetch_sitemap", error_type="parse", fallback="pages so far",
                          stage="discovery", url=sitemap_url)
        except Exception as e:
            obs.swallowed("page_discovery.py:_fetch_sitemap", fallback="pages so far",
                          stage="discovery", url=sitemap_url)
            logger.debug(f"Sitemap fetch error for {sitemap_url}: {e}")

        return pages

    def _crawl_links(self, base_url: str, homepage_soup=None) -> List[Tuple[str, str]]:
        """Collection, product and policy links on the homepage, query strings dropped."""
        soup = homepage_soup
        if soup is None:
            soup, status, error = self.client.fetch_and_parse(base_url)
            if error or not soup:
                obs.degraded("page_discovery.py:_crawl_links", obs.classify_fetch(status, error) or "http",
                             error or "no soup", fallback="no crawled links", stage="discovery", url=base_url)
                return []

        pages: List[Tuple[str, str]] = []
        skipped_robots = []
        for url, _text in extract_links_from_soup(soup, base_url):
            parsed = urlparse(url)
            url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
            page_type = categorize_page_type(url)
            if page_type not in CRAWLED_TYPES:
                continue
            if not self.robots_checker.is_allowed(url):
                skipped_robots.append(url)
                continue
            pages.append((url, page_type))
        if skipped_robots:
            obs.event("discovery", "skip", kind="robots_disallowed_links", urls=skipped_robots)
        return pages


def discover_pages(
    base_url: str,
    client: HttpClient,
    robots_checker: RobotsChecker,
    config: Config,
    platform: Optional[Platform] = None,
    homepage_soup=None,
) -> List[Tuple[str, str]]:
    """
    Convenience function for page discovery.

    Returns:
        List of (url, page_type) tuples (homepage not included)
    """
    discovery = PageDiscovery(client, robots_checker, config)
    return discovery.discover(base_url, platform=platform, homepage_soup=homepage_soup)
