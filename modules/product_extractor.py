"""
product_extractor.py - Extract product information from e-commerce pages.

Handles multiple platforms and HTML structures to extract:
- Product titles, URLs, images
- Prices (current, compare-at, sale)
- Categories
- Reviews
- Bundle/subscription indicators
"""

import re
import json
import logging
import statistics
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup

from .models import Product, PriceInfo, Platform
from . import obs

logger = logging.getLogger(__name__)


class ProductExtractor:
    """
    Extracts product information from e-commerce page HTML.
    
    Supports multiple platform-specific patterns as well as
    generic extraction strategies.
    """
    
    # Currency symbols to codes mapping
    CURRENCY_MAP = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
        'C$': 'CAD',
        'A$': 'AUD',
        'HK$': 'HKD',
        'S$': 'SGD',
    }
    
    # Bundle/subscription keywords
    BUNDLE_KEYWORDS = [
        'bundle', 'set', 'kit', 'pack', 'combo', 'collection set',
        '套装', '礼盒', '组合'
    ]
    
    SUBSCRIPTION_KEYWORDS = [
        'subscribe', 'subscription', 'auto-ship', 'recurring',
        'subscribe & save', 'subscribe and save', 'auto delivery',
        'refill', 'membership'
    ]
    
    def __init__(self, platform: Platform = Platform.CUSTOM):
        self.platform = platform
    
    def extract_from_page(
        self,
        soup: BeautifulSoup,
        url: str,
        page_type: str = 'other'
    ) -> List[Product]:
        """
        Extract products from a page.
        
        Args:
            soup: Parsed HTML
            url: Page URL
            page_type: Type of page ('home', 'collection', 'product', etc.)
            
        Returns:
            List of Product objects
        """
        products: List[Product] = []
        
        # Try platform-specific extraction first
        if self.platform == Platform.SHOPIFY:
            products = self._extract_shopify(soup, url)
        elif self.platform == Platform.WOOCOMMERCE:
            products = self._extract_woocommerce(soup, url)
        elif self.platform == Platform.BIGCOMMERCE:
            products = self._extract_bigcommerce(soup, url)
        
        # Fall back to generic extraction
        if not products:
            if self.platform in (Platform.SHOPIFY, Platform.WOOCOMMERCE, Platform.BIGCOMMERCE):
                obs.degraded("product_extractor.py:extract_from_page", "parse",
                             f"{self.platform.value} extractor found no products",
                             fallback="_extract_generic", stage="products", url=url)
            products = self._extract_generic(soup, url)
        
        # Deduplicate by URL
        seen_urls = set()
        unique_products = []
        for p in products:
            if p.url not in seen_urls:
                seen_urls.add(p.url)
                unique_products.append(p)
        
        return unique_products
    
    def _extract_shopify(self, soup: BeautifulSoup, url: str) -> List[Product]:
        """Extract products from Shopify pages."""
        products: List[Product] = []
        html_str = str(soup)
        
        # Method 1: Try to find Shopify JSON data in script tags
        for script in soup.find_all('script', type='application/json'):
            try:
                text = script.string
                if not text:
                    continue
                
                data = json.loads(text)

                # Look for product data in various structures
                if isinstance(data, dict):
                    if 'product' in data:
                        p = self._parse_shopify_product(data['product'], url)
                        if p:
                            products.append(p)
                    elif 'products' in data:
                        for prod_data in data['products'][:50]:
                            p = self._parse_shopify_product(prod_data, url)
                            if p:
                                products.append(p)
                    # Check nested structures
                    for key in ['collection', 'search', 'featured']:
                        if key in data and isinstance(data[key], dict):
                            if 'products' in data[key]:
                                for prod_data in data[key]['products'][:50]:
                                    p = self._parse_shopify_product(prod_data, url)
                                    if p:
                                        products.append(p)

            except (json.JSONDecodeError, Exception):
                obs.swallowed("product_extractor.py:_extract_shopify", error_type="parse",
                              fallback="skip this application/json script", stage="products", url=url)
                continue
        
        # Method 2: Look for inline product JSON in script tags
        for script in soup.find_all('script'):
            if not script.string:
                continue
            text = script.string
            
            # Look for product array assignments
            patterns = [
                r'var\s+products?\s*=\s*(\[[\s\S]*?\]);',
                r'"products?":\s*(\[[\s\S]*?\])',
                r'window\.products?\s*=\s*(\[[\s\S]*?\]);',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        prod_data = json.loads(match.group(1))
                        if isinstance(prod_data, list):
                            for item in prod_data[:50]:
                                p = self._parse_shopify_product(item, url)
                                if p:
                                    products.append(p)
                    except:
                        obs.swallowed("product_extractor.py:_extract_shopify", error_type="parse",
                                      fallback="ignore inline product array", stage="products", url=url,
                                      pattern=pattern)
        
        # Method 3: Extract from Shopify meta tags and structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    p = self._parse_structured_data_product(data, url)
                    if p:
                        products.append(p)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Product':
                            p = self._parse_structured_data_product(item, url)
                            if p:
                                products.append(p)
                elif isinstance(data, dict) and '@graph' in data:
                    obs.degraded("product_extractor.py:_extract_shopify", "parse",
                                 "JSON-LD @graph is not searched for Product nodes",
                                 fallback="ignored", stage="products", event_name="fail", url=url)
            except:
                obs.swallowed("product_extractor.py:_extract_shopify", error_type="parse",
                              fallback="ignore this ld+json script", stage="products", url=url)
        
        # Method 4: Try product card patterns (expanded selectors for modern themes)
        # Modern Shopify themes like Impact use custom elements like <product-card>
        product_cards = soup.select(
            # Custom web components (like Rastaclat's Impact theme)
            'product-card, product-item, product-tile, product-block, '
            # Standard class patterns
            '[data-product-id], [data-product], .product-card, .product-item, '
            '.collection-product, .grid__item[data-product], .product-grid-item, '
            '.product-tile, .product-block, .product-card-wrapper, '
            '.card-product, .grid-product, .product, '
            '[class*="ProductCard"], [class*="product-card"], '
            '.collection__product, .featured-product, '
            # Additional modern patterns
            '[class*="product__card"], .product-list > *, '
            '.products-grid > *, .collection-grid > *, '
            '[handle], [data-handle]'
        )
        
        for card in product_cards:
            product = self._parse_product_card(card, url)
            if product:
                products.append(product)
        
        return products
    
    def _parse_structured_data_product(
        self,
        data: Dict[str, Any],
        base_url: str
    ) -> Optional[Product]:
        """Parse a Schema.org Product JSON-LD object."""
        try:
            from .url_utils import make_absolute_url
            
            title = data.get('name', '')
            if not title:
                return None
            
            product_url = data.get('url', base_url)
            product_url = make_absolute_url(base_url, product_url)
            
            # Get price from offers
            price_info = None
            offers = data.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            if offers:
                price = offers.get('price')
                currency = offers.get('priceCurrency', 'USD')
                
                if price:
                    price_info = PriceInfo(
                        currency=currency,
                        current_price=float(price)
                    )
            
            # Get image
            image_url = data.get('image')
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else None

            product = Product(
                title=title,
                url=product_url,
                price=price_info,
                image_url=image_url
            )
            product._obs = {'source': 'json_ld',
                            'detail': f"JSON-LD Product offers.price={offers.get('price') if offers else None!r} "
                                      f"(compare-at not read)"}
            return product
        except Exception as e:
            obs.swallowed("product_extractor.py:_parse_structured_data_product", error_type="parse",
                          fallback="None", stage="products")
            logger.debug(f"Error parsing structured data product: {e}")
            return None
    
    def _parse_shopify_product(
        self,
        data: Dict[str, Any],
        base_url: str
    ) -> Optional[Product]:
        """Parse a Shopify product JSON object."""
        try:
            title = data.get('title', '')
            handle = data.get('handle', '')
            
            if not title:
                return None
            
            # Build product URL
            product_url = data.get('url', '')
            if handle and not product_url:
                product_url = f"/products/{handle}"
            
            from .url_utils import make_absolute_url
            product_url = make_absolute_url(base_url, product_url)
            
            # Get price from variants
            variants = data.get('variants', [])
            price_info = None
            
            if variants:
                first_variant = variants[0]
                price = first_variant.get('price')
                compare_at = first_variant.get('compare_at_price')
                raw_price, raw_compare = price, compare_at
                
                if price:
                    # Shopify prices are in cents
                    if isinstance(price, (int, float)) and price > 100:
                        price = price / 100
                    
                    price_info = PriceInfo(
                        currency='USD',  # Default, will be overridden if detected
                        current_price=float(price) if price else None,
                        compare_at_price=float(compare_at) / 100 if compare_at and isinstance(compare_at, (int, float)) else None,
                        is_on_sale=bool(compare_at and compare_at > price),
                    )
                    
                    if price_info.is_on_sale and price_info.compare_at_price:
                        price_info.discount_percent = round(
                            (1 - price_info.current_price / price_info.compare_at_price) * 100
                        )
            
            # Get image
            images = data.get('images', [])
            image_url = None
            if images:
                first_img = images[0]
                if isinstance(first_img, str):
                    image_url = first_img
                elif isinstance(first_img, dict):
                    image_url = first_img.get('src', '')
            
            # Check for bundle/subscription in title or tags
            title_lower = title.lower()
            tags = [t.lower() for t in data.get('tags', [])]
            
            is_bundle = any(
                kw in title_lower or kw in ' '.join(tags)
                for kw in self.BUNDLE_KEYWORDS
            )
            is_subscription = any(
                kw in title_lower or kw in ' '.join(tags)
                for kw in self.SUBSCRIPTION_KEYWORDS
            )
            
            product = Product(
                title=title,
                url=product_url,
                price=price_info,
                image_url=image_url,
                category=data.get('product_type', ''),
                is_bundle=is_bundle,
                is_subscription=is_subscription,
            )
            product._obs = {'source': 'json',
                            'detail': (f"Shopify product JSON variants[0] price={raw_price!r} "
                                       f"compare_at_price={raw_compare!r} (int >100 treated as cents; "
                                       f"compare-at only read when int/float)") if variants else
                                      "Shopify product JSON without variants"}
            return product

        except Exception as e:
            obs.swallowed("product_extractor.py:_parse_shopify_product", error_type="parse",
                          fallback="None", stage="products")
            logger.debug(f"Error parsing Shopify product: {e}")
            return None
    
    def _extract_woocommerce(self, soup: BeautifulSoup, url: str) -> List[Product]:
        """Extract products from WooCommerce pages."""
        products: List[Product] = []
        
        # WooCommerce product loop items
        product_items = soup.select(
            '.product, .woocommerce-LoopProduct-link, '
            'li.product, .products .product'
        )
        
        for item in product_items:
            product = self._parse_product_card(item, url)
            if product:
                products.append(product)
        
        return products
    
    def _extract_bigcommerce(self, soup: BeautifulSoup, url: str) -> List[Product]:
        """Extract products from BigCommerce pages."""
        products: List[Product] = []
        
        product_items = soup.select(
            '.product-item, .productCard, [data-product-id]'
        )
        
        for item in product_items:
            product = self._parse_product_card(item, url)
            if product:
                products.append(product)
        
        return products
    
    def _extract_generic(self, soup: BeautifulSoup, url: str) -> List[Product]:
        """Generic product extraction for unknown platforms."""
        products: List[Product] = []
        
        # Common product card patterns
        selectors = [
            '[data-product]',
            '[data-product-id]',
            '.product',
            '.product-card',
            '.product-item',
            '.product-tile',
            '.product-grid-item',
            '.ProductItem',
            '.product-thumbnail',
            'article.product',
        ]
        
        for selector in selectors:
            items = soup.select(selector)
            if items:
                for item in items[:50]:  # Limit per selector
                    product = self._parse_product_card(item, url)
                    if product:
                        products.append(product)
                
                if len(products) >= 10:
                    break
        
        return products
    
    def _parse_product_card(
        self,
        element: BeautifulSoup,
        base_url: str
    ) -> Optional[Product]:
        """Parse a generic product card element."""
        try:
            from .url_utils import make_absolute_url
            
            # Find title - expanded selectors for modern Shopify themes like Rastaclat
            title = None
            title_selectors = [
                # Modern Shopify patterns (like Impact theme)
                '.product-title', '.product-name', '.product__title',
                '.product-card__title', '.card__heading', '.card__title',
                # Link text patterns - common in Rastaclat style
                'a.product-title', '.product-card__info a',
                # Standard patterns
                'h2', 'h3', 'h4', '.title', '.name',
                '[data-product-title]', '.card-title',
                # Additional Shopify patterns
                '.h6', '.product-card__info .h6', 
                '.product__name', '.product-item__title',
            ]
            title_via = None
            for selector in title_selectors:
                title_elem = element.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    title_via = selector
                    if title and len(title) > 2:
                        break
            
            if not title:
                # Try any link text that looks like a product title
                links = element.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    # Check if link goes to a product page
                    if '/products/' in href:
                        link_text = link.get_text(strip=True)
                        if link_text and len(link_text) > 2 and len(link_text) < 200:
                            title = link_text
                            title_via = "a[href*='/products/'] text"
                            break
            
            if not title or len(title) < 2:
                return None
            
            # Find URL - look for product links specifically
            product_url = None
            links = element.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if '/products/' in href:
                    product_url = make_absolute_url(base_url, href)
                    break
            
            # Fallback to first link if no product link found
            if not product_url:
                link = element.find('a', href=True)
                if link:
                    product_url = make_absolute_url(base_url, link['href'])
            
            if not product_url:
                return None
            
            # Find price
            price_info = self._extract_price_from_element(element)
            
            # Find image - check multiple attributes
            image_url = None
            img = element.find('img')
            if img:
                image_url = img.get('src') or img.get('data-src') or img.get('srcset', '').split()[0] if img.get('srcset') else None
                if image_url:
                    # Clean srcset format if present (e.g., "url 200w")
                    if ' ' in image_url:
                        image_url = image_url.split()[0]
                    image_url = make_absolute_url(base_url, image_url)
            
            # Check bundle/subscription
            text = element.get_text().lower()
            is_bundle = any(kw in text for kw in self.BUNDLE_KEYWORDS)
            is_subscription = any(kw in text for kw in self.SUBSCRIPTION_KEYWORDS)
            
            product = Product(
                title=title[:200],  # Limit title length
                url=product_url,
                price=price_info,
                image_url=image_url,
                is_bundle=is_bundle,
                is_subscription=is_subscription,
            )
            product._obs = {'source': 'selector',
                            'detail': f"card <{element.name} class={element.get('class')}>; title via {title_via!r}; "
                                      f"price {getattr(price_info, '_obs', 'none found')}"}
            return product

        except Exception as e:
            obs.swallowed("product_extractor.py:_parse_product_card", error_type="parse",
                          fallback="None", stage="products")
            logger.debug(f"Error parsing product card: {e}")
            return None
    
    def _extract_price_from_element(
        self,
        element: BeautifulSoup
    ) -> Optional[PriceInfo]:
        """Extract price information from an element."""
        try:
            # Extended price selectors - including modern Shopify theme patterns
            # Patterns found in sites like Rastaclat:
            # <sale-price class="h6 text-subdued"><span class="sr-only">Sale price</span>$30.00</sale-price>
            # <price-list class="price-list "><sale-price>...</sale-price></price-list>
            price_selectors = [
                # Modern Shopify custom elements (like Rastaclat)
                'sale-price',
                'regular-price', 
                'price-list sale-price',
                'price-list regular-price',
                # Standard selectors
                '.price', '.product-price', '.price-item',
                '[data-price]', '.money', '.amount',
                '.current-price', '.sale-price', '.regular-price',
                # Additional Shopify patterns
                '.price__current', '.price__sale', '.price-item--sale',
                '[class*="price"]', '[class*="Price"]',
                '.product__price', '.card-price',
                '.h6.text-subdued',  # Rastaclat pattern
            ]
            
            price_text = None
            compare_text = None
            price_via = None
            compare_via = None

            # Look for current price
            for selector in price_selectors:
                price_elem = element.select_one(selector)
                if price_elem:
                    # Get text, excluding screen-reader only text
                    sr_only = price_elem.select_one('.sr-only')
                    if sr_only:
                        sr_only.decompose()
                    price_text = price_elem.get_text(strip=True)
                    price_via = selector
                    if price_text and '$' in price_text:
                        break

            # If still no price, try looking for any element with $ symbol
            if not price_text:
                all_text = element.get_text()
                price_match = re.search(r'\$[\d,.]+', all_text)
                if price_match:
                    price_text = price_match.group()
                    price_via = "first \\$[\\d,.]+ in card text"
            
            # Look for compare-at price
            compare_selectors = [
                # Modern Shopify patterns
                'compare-at-price',
                '.compare-at-price', '.was-price', '.original-price',
                '.price-compare', '.price__compare', '.price-item--regular',
                's', 'del', '.line-through',
                '[class*="compare"]', '[class*="original"]',
            ]
            for selector in compare_selectors:
                compare_elem = element.select_one(selector)
                if compare_elem:
                    compare_text = compare_elem.get_text(strip=True)
                    compare_via = selector
                    break
            
            if not price_text:
                return None
            
            # Parse prices
            current_price, currency = self._parse_price_string(price_text)
            compare_price = None
            
            if compare_text:
                compare_price, _ = self._parse_price_string(compare_text)
            
            if current_price is None:
                return None
            
            is_on_sale = compare_price is not None and compare_price > current_price
            discount_percent = None
            
            if is_on_sale:
                discount_percent = round((1 - current_price / compare_price) * 100)
            
            price_info = PriceInfo(
                currency=currency or 'USD',
                current_price=current_price,
                compare_at_price=compare_price,
                is_on_sale=is_on_sale,
                discount_percent=discount_percent
            )
            price_info._obs = (f"price via {price_via!r} text {price_text[:80]!r} -> {current_price}; "
                               f"compare via {compare_via!r} text {(compare_text or '')[:80]!r} -> {compare_price}")
            return price_info

        except Exception:
            obs.swallowed("product_extractor.py:_extract_price_from_element", error_type="parse",
                          fallback="None (no price)", stage="products")
            return None
    
    def _parse_price_string(
        self,
        text: str
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Parse a price string to extract numeric value and currency.
        
        Returns:
            Tuple of (price_float, currency_code)
        """
        if not text:
            return None, None
        
        # Clean the text
        text = text.strip()
        
        # Detect currency
        currency = None
        for symbol, code in self.CURRENCY_MAP.items():
            if symbol in text:
                currency = code
                break
        
        # Also check for currency codes
        currency_codes = ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD']
        for code in currency_codes:
            if code in text.upper():
                currency = code
                break
        
        # Extract numeric value
        # Handle formats: $19.99, 19,99€, 1,999.00, etc.
        price_match = re.search(
            r'[\d,]+\.?\d*|\d+[,\s]?\d*',
            text.replace(',', '.')
        )
        
        if price_match:
            price_str = price_match.group()
            # Clean up
            price_str = re.sub(r'[^\d.]', '', price_str)
            
            try:
                return float(price_str), currency
            except ValueError:
                obs.swallowed("product_extractor.py:_parse_price_string", error_type="parse", fallback="pass", stage="products")
                pass
        
        return None, currency


def extract_products(
    soup: BeautifulSoup,
    url: str,
    platform: Platform = Platform.CUSTOM,
    page_type: str = 'other'
) -> List[Product]:
    """
    Convenience function for product extraction.
    
    Args:
        soup: Parsed HTML
        url: Page URL
        platform: Detected e-commerce platform
        page_type: Type of page
        
    Returns:
        List of Product objects
    """
    extractor = ProductExtractor(platform)
    return extractor.extract_from_page(soup, url, page_type)


def calculate_price_stats(
    products: List[Product]
) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    """
    Calculate price statistics from a list of products.
    
    Returns:
        Tuple of (min_price, max_price, median_price, currency)
    """
    prices = []
    currency = 'USD'
    
    for p in products:
        if p.price and p.price.current_price:
            prices.append(p.price.current_price)
            if p.price.currency:
                currency = p.price.currency
    
    if not prices:
        return None, None, None, currency
    
    return (
        min(prices),
        max(prices),
        statistics.median(prices),
        currency
    )
