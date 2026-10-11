"""
platform_detector.py - E-commerce platform detection using multiple heuristics.

Detects Shopify, WooCommerce, Magento, BigCommerce, Wix, Squarespace, and others
by analyzing HTML structure, scripts, headers, and metadata.
"""

import re
import logging
from typing import Tuple, List, Dict, Optional
from bs4 import BeautifulSoup

from .models import Platform

logger = logging.getLogger(__name__)


class PlatformDetector:
    """
    Detects e-commerce platform from page HTML and HTTP headers.
    
    Uses multiple heuristic signals for robust detection.
    """
    
    # Platform detection patterns
    PATTERNS: Dict[Platform, Dict[str, List[str]]] = {
        Platform.SHOPIFY: {
            'html': [
                r'cdn\.shopify\.com',
                r'Shopify\.theme',
                r'shopify-section',
                r'data-shopify',
                r'/cdn/shop/',
                r'myshopify\.com',
                r'"Shopify"',
                r'shopify\.loadFeatures',
            ],
            'scripts': [
                r'cdn\.shopify\.com',
                r'/assets/storefront/',
                r'shopify_analytics',
            ],
            'headers': [
                ('x-shopify-stage', ''),
                ('x-shardid', ''),
                ('x-sorting-hat-shopid', ''),
            ],
            'meta': [
                ('generator', r'shopify', False),
            ],
        },
        Platform.WOOCOMMERCE: {
            'html': [
                r'woocommerce',
                r'wc-block',
                r'wp-content.*woocommerce',
                r'add_to_cart_button',
                r'is-woocommerce',
            ],
            'scripts': [
                r'woocommerce',
                r'/wp-content/plugins/woocommerce',
                r'wc-add-to-cart',
            ],
            'headers': [],
            'meta': [
                ('generator', r'wordpress', False),
                ('generator', r'woocommerce', False),
            ],
        },
        Platform.MAGENTO: {
            'html': [
                r'Magento',
                r'mage-',
                r'magento-',
                r'/static/version',
                r'Mage\.Cookies',
                r'data-mage-init',
                r'requirejs-config\.js',
            ],
            'scripts': [
                r'/static/.*magento',
                r'mage/cookies',
                r'requirejs',
            ],
            'headers': [
                ('x-magento-', ''),
            ],
            'meta': [
                ('generator', r'magento', False),
            ],
        },
        Platform.BIGCOMMERCE: {
            'html': [
                r'bigcommerce',
                r'BigCommerce',
                r'cdn\.bcapp',
                r'bcapp\.dev',
                r'stencil-stylesheet',
            ],
            'scripts': [
                r'bigcommerce',
                r'cdn\d*\.bigcommerce\.com',
            ],
            'headers': [
                ('x-bc-', ''),
            ],
            'meta': [
                ('generator', r'bigcommerce', False),
            ],
        },
        Platform.WIX: {
            'html': [
                r'wixsite\.com',
                r'wix\.com',
                r'_wix_browser_sess',
                r'wix-warmup-data',
                r'corvid-runtime',
            ],
            'scripts': [
                r'static\.wixstatic\.com',
                r'parastorage\.com',
            ],
            'headers': [
                ('x-wix-', ''),
            ],
            'meta': [
                ('generator', r'wix', False),
            ],
        },
        Platform.SQUARESPACE: {
            'html': [
                r'squarespace',
                r'sqsp',
                r'static\.squarespace\.com',
                r'sqs-cookie-banner',
                r'sqs-block',
            ],
            'scripts': [
                r'squarespace\.com',
                r'static\d*\.squarespace\.com',
            ],
            'headers': [
                ('x-squarespace', ''),
            ],
            'meta': [
                ('generator', r'squarespace', False),
            ],
        },
        Platform.PRESTASHOP: {
            'html': [
                r'prestashop',
                r'PrestaShop',
                r'/modules/ps_',
                r'prestashop-',
            ],
            'scripts': [
                r'prestashop',
                r'/modules/ps_',
            ],
            'headers': [],
            'meta': [
                ('generator', r'prestashop', False),
            ],
        },
    }
    
    def detect(
        self,
        soup: BeautifulSoup,
        headers: Dict[str, str],
        url: str
    ) -> Tuple[Platform, float, List[str]]:
        """
        Detect the e-commerce platform for a page.
        
        Args:
            soup: Parsed HTML of the page
            headers: HTTP response headers
            url: The page URL
            
        Returns:
            Tuple of (platform, confidence, signals_found)
        """
        scores: Dict[Platform, List[str]] = {p: [] for p in Platform}
        
        html_str = str(soup)
        
        for platform, patterns in self.PATTERNS.items():
            # Check HTML patterns
            for pattern in patterns['html']:
                if re.search(pattern, html_str, re.IGNORECASE):
                    scores[platform].append(f"html:{pattern}")
            
            # Check script sources
            for script in soup.find_all('script', src=True):
                src = script.get('src', '')
                for pattern in patterns['scripts']:
                    if re.search(pattern, src, re.IGNORECASE):
                        scores[platform].append(f"script:{pattern}")
            
            # Check headers
            headers_lower = {k.lower(): v for k, v in headers.items()}
            for header_name, header_pattern in patterns['headers']:
                for key in headers_lower:
                    if key.startswith(header_name.lower()):
                        scores[platform].append(f"header:{header_name}")
                        break
            
            # Check meta tags
            for meta in soup.find_all('meta'):
                meta_name = meta.get('name', '').lower()
                meta_content = meta.get('content', '').lower()
                
                for tag_name, pattern, check_name in patterns['meta']:
                    if tag_name == meta_name or (not check_name):
                        if re.search(pattern, meta_content, re.IGNORECASE):
                            scores[platform].append(f"meta:{tag_name}={pattern}")
        
        # Additional Shopify-specific checks
        if self._check_shopify_specific(soup, headers, url):
            scores[Platform.SHOPIFY].append("shopify_specific_check")
        
        # Find the platform with most signals
        best_platform = Platform.CUSTOM
        best_score = 0
        best_signals: List[str] = []
        
        for platform, signals in scores.items():
            if len(signals) > best_score:
                best_score = len(signals)
                best_platform = platform
                best_signals = signals
        
        # Calculate confidence
        if best_score >= 3:
            confidence = 0.95
        elif best_score == 2:
            confidence = 0.8
        elif best_score == 1:
            confidence = 0.6
        else:
            confidence = 0.0
        
        return best_platform, confidence, best_signals
    
    def _check_shopify_specific(
        self,
        soup: BeautifulSoup,
        headers: Dict[str, str],
        url: str
    ) -> bool:
        """Additional Shopify-specific detection."""
        # Check for Shopify JSON API patterns
        for script in soup.find_all('script', type='application/json'):
            if 'window.ShopifyAnalytics' in str(script):
                return True
            if 'Shopify.checkout' in str(script):
                return True
        
        # Check for Shopify cart form
        cart_form = soup.find('form', action=re.compile(r'/cart/add'))
        if cart_form:
            return True
        
        # Check for typical Shopify data attributes
        if soup.find(attrs={'data-product-id': True}):
            return True
        
        return False


def detect_platform(
    soup: BeautifulSoup,
    headers: Dict[str, str],
    url: str
) -> Tuple[Platform, float, List[str]]:
    """
    Convenience function for platform detection.
    
    Args:
        soup: Parsed HTML of the page
        headers: HTTP response headers
        url: The page URL
        
    Returns:
        Tuple of (platform, confidence, signals_found)
    """
    detector = PlatformDetector()
    return detector.detect(soup, headers, url)
