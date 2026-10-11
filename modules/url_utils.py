"""
url_utils.py - URL normalization, validation, and manipulation utilities.

Provides functions for cleaning URLs, extracting domains, and detecting
URL patterns common in e-commerce sites.
"""

import re
import logging
from typing import Optional, List, Set, Tuple
from urllib.parse import urlparse, urljoin, urlunparse, parse_qs, urlencode

import tldextract

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent comparison and storage.
    
    - Adds https:// if no scheme
    - Removes trailing slashes
    - Lowercases the domain
    - Removes common tracking parameters
    - Removes fragments
    
    Args:
        url: URL string to normalize
        
    Returns:
        Normalized URL string
    """
    url = url.strip()
    
    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        parsed = urlparse(url)
        
        # Lowercase the domain
        netloc = parsed.netloc.lower()
        
        # Remove www. prefix for consistency (optional - comment out if you want to keep it)
        # if netloc.startswith('www.'):
        #     netloc = netloc[4:]
        
        # Clean path
        path = parsed.path.rstrip('/')
        if not path:
            path = ''
        
        # Remove tracking parameters
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'ref', 'ref_', '_ga', 'mc_cid', 'mc_eid'
        }
        
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        filtered_params = {
            k: v for k, v in query_params.items() 
            if k.lower() not in tracking_params
        }
        
        # Rebuild query string
        query = urlencode(filtered_params, doseq=True) if filtered_params else ''
        
        # Reconstruct URL without fragment
        normalized = urlunparse((
            parsed.scheme,
            netloc,
            path,
            '',  # params
            query,
            ''   # fragment
        ))
        
        return normalized
        
    except Exception as e:
        logger.warning(f"URL normalization failed for {url}: {e}")
        return url


def extract_domain(url: str) -> str:
    """
    Extract the registered domain from a URL.
    
    Uses tldextract to properly handle multi-level TLDs like .co.uk
    
    Args:
        url: URL string
        
    Returns:
        Domain string (e.g., 'example.com')
    """
    try:
        extracted = tldextract.extract(url)
        if extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
        return extracted.domain
    except Exception:
        # Fallback to simple parsing
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')


def extract_full_domain(url: str) -> str:
    """
    Extract the full domain including subdomain from a URL.
    
    Args:
        url: URL string
        
    Returns:
        Full domain string (e.g., 'shop.example.com')
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return url


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs belong to the same registered domain."""
    return extract_domain(url1) == extract_domain(url2)


def is_internal_link(base_url: str, link: str) -> bool:
    """
    Check if a link is internal to the base URL's domain.
    
    Args:
        base_url: The base/source URL
        link: The link to check
        
    Returns:
        True if the link is internal
    """
    if not link:
        return False
    
    # Relative URLs are internal
    if link.startswith('/') and not link.startswith('//'):
        return True
    
    if link.startswith('#'):
        return False
    
    # Check domain match
    return is_same_domain(base_url, link)


def make_absolute_url(base_url: str, relative_url: str) -> str:
    """
    Convert a relative URL to absolute using the base URL.
    
    Args:
        base_url: The base URL
        relative_url: Relative or absolute URL
        
    Returns:
        Absolute URL
    """
    if not relative_url:
        return base_url
    
    # Already absolute
    if relative_url.startswith(('http://', 'https://')):
        return relative_url
    
    # Protocol-relative
    if relative_url.startswith('//'):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{relative_url}"
    
    return urljoin(base_url, relative_url)


def deduplicate_urls(urls: List[str]) -> List[str]:
    """
    Remove duplicate URLs after normalization.
    
    Args:
        urls: List of URL strings
        
    Returns:
        List of unique normalized URLs
    """
    seen: Set[str] = set()
    result: List[str] = []
    
    for url in urls:
        normalized = normalize_url(url)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    
    return result


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid and potentially reachable.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if URL appears valid
    """
    try:
        result = urlparse(url)
        return all([
            result.scheme in ('http', 'https'),
            result.netloc,
            '.' in result.netloc  # Has TLD
        ])
    except Exception:
        return False


def categorize_page_type(url: str) -> str:
    """
    Categorize a URL by its likely page type based on path patterns.
    
    Args:
        url: URL to categorize
        
    Returns:
        Page type string: 'home', 'product', 'collection', 'policy', 'about', 'other'
    """
    parsed = urlparse(url.lower())
    path = parsed.path
    
    # Home page
    if path in ('', '/', '/index', '/index.html'):
        return 'home'
    
    # Product pages
    product_patterns = [
        r'/products?/',
        r'/p/',
        r'/item/',
        r'/goods/',
        r'-p-\d+',
        r'/pd/',
    ]
    for pattern in product_patterns:
        if re.search(pattern, path):
            return 'product'
    
    # Collection/category pages
    collection_patterns = [
        r'/collections?/',
        r'/categories?/',
        r'/c/',
        r'/shop/',
        r'/catalog/',
    ]
    for pattern in collection_patterns:
        if re.search(pattern, path):
            return 'collection'
    
    # Policy pages
    policy_patterns = [
        r'/polic(y|ies)',
        r'/shipping',
        r'/return',
        r'/refund',
        r'/terms',
        r'/privacy',
        r'/legal',
        r'/faq',
    ]
    for pattern in policy_patterns:
        if re.search(pattern, path):
            return 'policy'
    
    # About pages
    about_patterns = [
        r'/about',
        r'/our-story',
        r'/who-we-are',
        r'/company',
        r'/mission',
    ]
    for pattern in about_patterns:
        if re.search(pattern, path):
            return 'about'
    
    # Contact
    if '/contact' in path:
        return 'contact'
    
    # Blog
    if '/blog' in path or '/news' in path or '/articles' in path:
        return 'blog'
    
    return 'other'


def get_priority_pages(base_url: str) -> List[Tuple[str, str]]:
    """
    Get a prioritized list of pages to crawl for an e-commerce site.
    
    Args:
        base_url: The site's base URL
        
    Returns:
        List of (url, page_type) tuples in priority order
    """
    # Common e-commerce page paths to check
    paths = [
        ('/', 'home'),
        ('/collections', 'collection'),
        ('/collections/all', 'collection'),
        ('/products', 'collection'),
        ('/shop', 'collection'),
        ('/catalog', 'collection'),
        ('/pages/about', 'about'),
        ('/pages/about-us', 'about'),
        ('/about', 'about'),
        ('/about-us', 'about'),
        ('/policies/shipping-policy', 'policy'),
        ('/pages/shipping', 'policy'),
        ('/shipping', 'policy'),
        ('/policies/refund-policy', 'policy'),
        ('/pages/returns', 'policy'),
        ('/returns', 'policy'),
        ('/pages/return-policy', 'policy'),
        ('/policies/privacy-policy', 'policy'),
        ('/pages/faq', 'policy'),
        ('/faq', 'policy'),
        ('/pages/contact', 'contact'),
        ('/contact', 'contact'),
    ]
    
    result = []
    seen = set()
    
    for path, page_type in paths:
        url = normalize_url(urljoin(base_url, path))
        if url not in seen:
            seen.add(url)
            result.append((url, page_type))
    
    return result


def extract_links_from_soup(soup, base_url: str) -> List[Tuple[str, str]]:
    """
    Extract all internal links from a BeautifulSoup object.
    
    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative links
        
    Returns:
        List of (absolute_url, link_text) tuples
    """
    links = []
    seen = set()
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        
        # Skip common non-content links
        skip_patterns = [
            '/cart', '/checkout', '/account', '/login', '/register',
            '/wishlist', '/compare', '/search', '.pdf', '.jpg', '.png'
        ]
        if any(pattern in href.lower() for pattern in skip_patterns):
            continue
        
        absolute_url = make_absolute_url(base_url, href)
        
        if not is_internal_link(base_url, absolute_url):
            continue
        
        normalized = normalize_url(absolute_url)
        
        if normalized not in seen:
            seen.add(normalized)
            link_text = a_tag.get_text(strip=True)[:100]
            links.append((normalized, link_text))
    
    return links
