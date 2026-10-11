"""
category_extractor.py - Extract product categories from e-commerce pages.

Extracts categories from:
- Navigation menus (header, sidebar)
- Collection links
- Breadcrumbs
- Footer links
"""

import re
import logging
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CategoryExtractor:
    """
    Extracts product category information from e-commerce pages.
    
    Supports extraction from:
    1. Shopify collection links (/collections/xxx)
    2. Navigation menus (header nav, mega menus)
    3. Sidebar category links
    4. Footer category links
    """
    
    # Words that indicate a category (not a page link)
    CATEGORY_INDICATORS = [
        'shop', 'collection', 'category', 'categories', 'department',
        'products', 'browse', 'all', 'view all'
    ]
    
    # Words to exclude (not real categories)
    EXCLUDE_WORDS = [
        'login', 'account', 'cart', 'checkout', 'wishlist', 'search',
        'blog', 'contact', 'about', 'faq', 'help', 'support', 'terms',
        'privacy', 'policy', 'track', 'order', 'return', 'shipping',
        'my account', 'sign in', 'sign up', 'register', 'home'
    ]
    
    def extract_categories(
        self,
        soup: BeautifulSoup,
        base_url: str
    ) -> Dict:
        """
        Extract all category information from a page.
        
        Args:
            soup: Parsed HTML
            base_url: Base URL for resolving relative links
            
        Returns:
            Dictionary with category data
        """
        result = {
            'categories': [],  # List of category names
            'category_urls': {},  # Map of category name -> URL
            'category_count': 0,
            'has_mega_menu': False,
            'category_structure': [],  # Hierarchical structure
        }
        
        seen_names: Set[str] = set()
        
        # Method 1: Extract from navigation menus
        nav_categories = self._extract_from_navigation(soup, base_url, seen_names)
        result['categories'].extend(nav_categories['names'])
        result['category_urls'].update(nav_categories['urls'])
        result['has_mega_menu'] = nav_categories['has_mega_menu']
        
        # Method 2: Extract from collection/category links
        collection_categories = self._extract_from_collections(soup, base_url, seen_names)
        result['categories'].extend(collection_categories['names'])
        result['category_urls'].update(collection_categories['urls'])
        
        # Method 3: Extract from footer
        footer_categories = self._extract_from_footer(soup, base_url, seen_names)
        result['categories'].extend(footer_categories['names'])
        result['category_urls'].update(footer_categories['urls'])
        
        # Deduplicate and clean
        result['categories'] = list(dict.fromkeys(result['categories']))  # Preserve order
        result['category_count'] = len(result['categories'])
        
        return result
    
    def _extract_from_navigation(
        self,
        soup: BeautifulSoup,
        base_url: str,
        seen: Set[str]
    ) -> Dict:
        """Extract categories from navigation menus."""
        from .url_utils import make_absolute_url
        
        names = []
        urls = {}
        has_mega_menu = False
        
        # Selectors for navigation elements
        nav_selectors = [
            # Main navigation
            'nav', 'header nav', '.nav', '.navigation', '.main-nav',
            '.header-nav', '.primary-nav', '.site-nav',
            # Shopify specific patterns (like Rastaclat)
            '.header__primary-nav', '.header__nav', '.header-sidebar',
            '[class*="header__nav"]', '[class*="primary-nav"]',
            # Mega menu patterns
            '.mega-menu', '.dropdown-menu', '.submenu', '.sub-menu',
            '[class*="mega"]', '[class*="dropdown"]',
            # Mobile menu / sidebar
            '.header-sidebar__linklist', '.mobile-menu', '.sidebar-nav',
        ]
        
        # Check for mega menu
        if soup.select_one('.mega-menu, [class*="mega-menu"], [class*="megamenu"]'):
            has_mega_menu = True
        
        for selector in nav_selectors:
            nav_elements = soup.select(selector)
            for nav in nav_elements:
                links = nav.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # Skip empty or excluded links
                    if not text or len(text) < 2:
                        continue
                    if any(ex in text.lower() for ex in self.EXCLUDE_WORDS):
                        continue
                    
                    # Check if it's a collection/category link
                    if self._is_category_link(href, text):
                        normalized = self._normalize_category_name(text)
                        if normalized and normalized.lower() not in seen:
                            seen.add(normalized.lower())
                            names.append(normalized)
                            urls[normalized] = make_absolute_url(base_url, href)
        
        return {'names': names, 'urls': urls, 'has_mega_menu': has_mega_menu}
    
    def _extract_from_collections(
        self,
        soup: BeautifulSoup,
        base_url: str,
        seen: Set[str]
    ) -> Dict:
        """Extract categories from collection links."""
        from .url_utils import make_absolute_url
        
        names = []
        urls = {}
        
        # Find all collection links (Shopify pattern: /collections/xxx)
        collection_links = soup.find_all('a', href=re.compile(r'/collections/[^/]+/?$'))
        
        for link in collection_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Try to extract category name from URL if text is empty
            if not text or len(text) < 2:
                match = re.search(r'/collections/([^/?]+)', href)
                if match:
                    text = match.group(1).replace('-', ' ').title()
            
            if not text:
                continue
            
            # Skip excluded words
            if any(ex in text.lower() for ex in self.EXCLUDE_WORDS):
                continue
            
            normalized = self._normalize_category_name(text)
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                names.append(normalized)
                urls[normalized] = make_absolute_url(base_url, href)
        
        # Also look for category/product links (other platform patterns)
        category_patterns = [
            r'/category/([^/?]+)',
            r'/shop/([^/?]+)',
            r'/c/([^/?]+)',
            r'/products/category/([^/?]+)',
        ]
        
        for pattern in category_patterns:
            for link in soup.find_all('a', href=re.compile(pattern)):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if not text:
                    match = re.search(pattern, href)
                    if match:
                        text = match.group(1).replace('-', ' ').title()
                
                if text:
                    normalized = self._normalize_category_name(text)
                    if normalized and normalized.lower() not in seen:
                        seen.add(normalized.lower())
                        names.append(normalized)
                        urls[normalized] = make_absolute_url(base_url, href)
        
        return {'names': names, 'urls': urls}
    
    def _extract_from_footer(
        self,
        soup: BeautifulSoup,
        base_url: str,
        seen: Set[str]
    ) -> Dict:
        """Extract categories from footer."""
        from .url_utils import make_absolute_url
        
        names = []
        urls = {}
        
        footer = soup.find('footer')
        if not footer:
            return {'names': names, 'urls': urls}
        
        # Look for "Shop" or "Categories" sections in footer
        shop_sections = footer.find_all(
            ['div', 'section', 'ul'],
            string=re.compile(r'shop|categor|collection|product', re.I)
        )
        
        # Also find by nearby headers
        shop_headers = footer.find_all(
            ['h3', 'h4', 'h5', 'h6', 'p', 'span'],
            string=re.compile(r'shop|categor|collection|product', re.I)
        )
        
        for header in shop_headers:
            # Find the next sibling list or container
            sibling = header.find_next_sibling(['ul', 'div'])
            if sibling:
                links = sibling.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if self._is_category_link(href, text):
                        normalized = self._normalize_category_name(text)
                        if normalized and normalized.lower() not in seen:
                            seen.add(normalized.lower())
                            names.append(normalized)
                            urls[normalized] = make_absolute_url(base_url, href)
        
        return {'names': names, 'urls': urls}
    
    def _is_category_link(self, href: str, text: str) -> bool:
        """Check if a link is a category link."""
        href_lower = href.lower()
        text_lower = text.lower()
        
        # Skip excluded patterns
        if any(ex in href_lower or ex in text_lower for ex in self.EXCLUDE_WORDS):
            return False
        
        # Shopify collection pattern
        if '/collections/' in href_lower:
            return True
        
        # Other common patterns
        category_patterns = [
            '/category/', '/categories/', '/shop/', '/c/',
            '/products/', '/department/'
        ]
        if any(p in href_lower for p in category_patterns):
            return True
        
        # Check text for category indicators
        if any(ind in text_lower for ind in self.CATEGORY_INDICATORS):
            return True
        
        return False
    
    def _normalize_category_name(self, name: str) -> str:
        """Normalize a category name."""
        if not name:
            return ''
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        # Remove common prefixes/suffixes
        prefixes = ['shop ', 'view all ', 'browse ', 'all ']
        for prefix in prefixes:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
        
        suffixes = [' collection', ' category', ' products']
        for suffix in suffixes:
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
        
        # Limit length
        if len(name) > 50:
            name = name[:50]
        
        return name.strip()


def extract_categories(
    soup: BeautifulSoup,
    base_url: str
) -> Dict:
    """
    Convenience function for category extraction.
    
    Args:
        soup: Parsed HTML
        base_url: Base URL for resolving links
        
    Returns:
        Dictionary with category data
    """
    extractor = CategoryExtractor()
    return extractor.extract_categories(soup, base_url)
