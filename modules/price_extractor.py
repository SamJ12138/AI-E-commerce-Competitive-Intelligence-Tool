"""
price_extractor.py - Extract pricing information from JavaScript/HTML on e-commerce pages.

This module provides fallback price extraction when standard product extraction fails.
It looks for prices embedded in JavaScript objects, data attributes, and common patterns.

UNIVERSAL PATTERNS FOR FUTURE SITES:
=====================================
1. Shopify searchSettings.suggestedProducts - contains price, priceFormatted, list_price
2. JSON-LD structured data (@type: Product) - contains offers.price
3. Data attributes (data-price, data-product-price)
4. JavaScript window objects (window.products, window.productData)
5. Meta tags (og:price:amount)
6. Microdata (itemprop="price")
7. Price text patterns in HTML ($XX.XX, £XX.XX, €XX.XX)

SITE-SPECIFIC PATTERNS DISCOVERED:
==================================
- Alo Yoga: searchSettings.suggestedProducts[].price (lines 6004-6039)
- Shopify general: window.products, Shopify.products, featured_products
- WooCommerce: wc_price, product-price data attributes
- Magento: Magento_Catalog/js/price-box, data-price-amount
"""

import re
import json
import logging
import statistics
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def extract_prices_from_js(html_str: str) -> Dict[str, Any]:
    """
    Extract pricing information from JavaScript embedded in HTML.
    
    This is a fallback method when standard product extraction fails.
    It looks for common JavaScript patterns that contain price data.
    
    Args:
        html_str: Raw HTML string from the page
        
    Returns:
        Dictionary with keys:
        - prices: List of float prices found
        - currency: Detected currency code
        - price_min: Minimum price
        - price_max: Maximum price
        - price_median: Median price
        - source: Where the prices were found
    """
    result = {
        'prices': [],
        'currency': 'USD',
        'price_min': None,
        'price_max': None,
        'price_median': None,
        'source': None
    }
    
    prices = []
    currency = 'USD'
    source = None
    
    # Method 1: Shopify searchSettings.suggestedProducts
    # Pattern: searchSettings.suggestedProducts.push({ price: 138.0, priceFormatted: "$138.00" })
    suggested_products_prices = _extract_shopify_search_settings(html_str)
    if suggested_products_prices:
        prices.extend(suggested_products_prices)
        source = 'shopify_searchSettings'
        logger.info(f"Found {len(suggested_products_prices)} prices from Shopify searchSettings")
    
    # Method 2: Window-based product arrays
    # Pattern: window.products = [...], var products = [...]
    if not prices:
        window_prices = _extract_window_products(html_str)
        if window_prices:
            prices.extend(window_prices)
            source = 'window_products'
            logger.info(f"Found {len(window_prices)} prices from window products")
    
    # Method 3: JSON-LD structured data
    # Pattern: <script type="application/ld+json">{"@type":"Product","offers":{"price":"..."}}
    if not prices:
        jsonld_prices, jsonld_currency = _extract_jsonld_prices(html_str)
        if jsonld_prices:
            prices.extend(jsonld_prices)
            if jsonld_currency:
                currency = jsonld_currency
            source = 'json_ld'
            logger.info(f"Found {len(jsonld_prices)} prices from JSON-LD")
    
    # Method 4: Data attributes
    # Pattern: data-price="99.99", data-product-price="99.99"
    if not prices:
        data_attr_prices = _extract_data_attribute_prices(html_str)
        if data_attr_prices:
            prices.extend(data_attr_prices)
            source = 'data_attributes'
            logger.info(f"Found {len(data_attr_prices)} prices from data attributes")
    
    # Method 5: Inline JavaScript price variables
    # Pattern: "price": 99.99, price: 99.99
    if not prices:
        inline_prices = _extract_inline_js_prices(html_str)
        if inline_prices:
            prices.extend(inline_prices)
            source = 'inline_js'
            logger.info(f"Found {len(inline_prices)} prices from inline JavaScript")
    
    # Method 6: Meta tags
    # Pattern: <meta property="og:price:amount" content="99.99">
    if not prices:
        meta_prices, meta_currency = _extract_meta_prices(html_str)
        if meta_prices:
            prices.extend(meta_prices)
            if meta_currency:
                currency = meta_currency
            source = 'meta_tags'
            logger.info(f"Found {len(meta_prices)} prices from meta tags")
    
    # Method 7: HTML price text patterns (last resort)
    if not prices:
        html_prices, html_currency = _extract_html_price_text(html_str)
        if html_prices:
            # Filter out obviously wrong prices (shipping costs, etc.)
            valid_prices = [p for p in html_prices if 5.0 <= p <= 10000.0]
            if valid_prices:
                prices.extend(valid_prices[:20])  # Limit to first 20
                if html_currency:
                    currency = html_currency
                source = 'html_text'
                logger.info(f"Found {len(valid_prices)} prices from HTML text")
    
    # Detect currency from content
    detected_currency = _detect_currency(html_str)
    if detected_currency:
        currency = detected_currency
    
    # Calculate statistics
    if prices:
        # Remove duplicates and sort
        unique_prices = sorted(set(prices))
        result['prices'] = unique_prices
        result['price_min'] = min(unique_prices)
        result['price_max'] = max(unique_prices)
        result['price_median'] = statistics.median(unique_prices)
        result['currency'] = currency
        result['source'] = source
        
        logger.info(f"Price extraction result: min=${result['price_min']}, max=${result['price_max']}, median=${result['price_median']}, currency={currency}")
    
    return result


def _extract_shopify_search_settings(html_str: str) -> List[float]:
    """
    Extract prices from Shopify searchSettings.suggestedProducts.
    
    Pattern found in Alo Yoga and many Shopify sites:
    searchSettings.suggestedProducts.push({
        title: "Product Name",
        price: 138.0,
        priceFormatted: "$138.00",
        list_price: 0,
        ...
    });
    """
    prices = []
    
    # Pattern 1: Individual .push() calls with price field
    # Matches: price: 138.0, or price: 138, or "price": 138.0
    push_pattern = r'suggestedProducts\.push\s*\(\s*\{[^}]*?["\']?price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)[^}]*?\}\s*\)'
    matches = re.findall(push_pattern, html_str, re.IGNORECASE | re.DOTALL)
    for match in matches:
        try:
            price = float(match)
            if price > 0:  # Exclude list_price:0
                prices.append(price)
        except ValueError:
            continue
    
    # Pattern 2: Try to find the entire suggestedProducts array
    array_pattern = r'suggestedProducts\s*=\s*\[(.*?)\]'
    array_match = re.search(array_pattern, html_str, re.DOTALL)
    if array_match:
        array_content = array_match.group(1)
        # Find all price values in the array
        price_pattern = r'["\']?price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)'
        price_matches = re.findall(price_pattern, array_content)
        for pm in price_matches:
            try:
                price = float(pm)
                if price > 0:
                    prices.append(price)
            except ValueError:
                continue
    
    # Pattern 3: Also check for window.AloSearchSettings or similar
    alo_pattern = r'window\.AloSearchSettings\s*=\s*(\{.*?\});'
    alo_match = re.search(alo_pattern, html_str, re.DOTALL)
    if alo_match:
        # Already captured above, but can add additional parsing if needed
        pass
    
    return prices


def _extract_window_products(html_str: str) -> List[float]:
    """
    Extract prices from window.products or similar JavaScript variables.
    
    Common patterns:
    - window.products = [{...}]
    - var products = [{...}]
    - window.productData = {...}
    - Shopify.products = [...]
    """
    prices = []
    
    patterns = [
        r'window\.products?\s*=\s*(\[[\s\S]*?\]);',
        r'var\s+products?\s*=\s*(\[[\s\S]*?\]);',
        r'Shopify\.products?\s*=\s*(\[[\s\S]*?\]);',
        r'featured_products\s*=\s*(\[[\s\S]*?\]);',
        r'window\.productData\s*=\s*(\{[\s\S]*?\});',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_str)
        if match:
            try:
                data_str = match.group(1)
                # Try to parse as JSON (may fail due to JS syntax)
                try:
                    data = json.loads(data_str)
                    prices.extend(_extract_prices_from_data(data))
                except json.JSONDecodeError:
                    # Fall back to regex extraction
                    price_pattern = r'["\']?price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)'
                    for pm in re.findall(price_pattern, data_str):
                        try:
                            prices.append(float(pm))
                        except ValueError:
                            continue
            except Exception:
                continue
    
    return prices


def _extract_prices_from_data(data: Any) -> List[float]:
    """Recursively extract price values from parsed JSON/dict data."""
    prices = []
    
    if isinstance(data, dict):
        # Look for price-related keys
        for key in ['price', 'current_price', 'sale_price', 'regular_price', 
                    'amount', 'value', 'priceV2', 'priceRange']:
            if key in data:
                val = data[key]
                if isinstance(val, (int, float)) and val > 0:
                    prices.append(float(val))
                elif isinstance(val, str):
                    try:
                        clean = re.sub(r'[^\d.]', '', val)
                        if clean:
                            prices.append(float(clean))
                    except ValueError:
                        pass
                elif isinstance(val, dict):
                    prices.extend(_extract_prices_from_data(val))
        
        # Recursively check all values
        for v in data.values():
            if isinstance(v, (dict, list)):
                prices.extend(_extract_prices_from_data(v))
    
    elif isinstance(data, list):
        for item in data:
            prices.extend(_extract_prices_from_data(item))
    
    return prices


def _extract_jsonld_prices(html_str: str) -> Tuple[List[float], Optional[str]]:
    """
    Extract prices from JSON-LD structured data.
    
    Pattern:
    <script type="application/ld+json">
    {"@type":"Product","offers":{"price":"99.99","priceCurrency":"USD"}}
    </script>
    """
    prices = []
    currency = None
    
    # Find all JSON-LD scripts
    pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>'
    matches = re.findall(pattern, html_str, re.IGNORECASE)
    
    for match in matches:
        try:
            data = json.loads(match)
            
            # Handle @graph arrays
            if isinstance(data, dict) and '@graph' in data:
                items = data['@graph']
            elif isinstance(data, list):
                items = data
            else:
                items = [data]
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                    
                item_type = item.get('@type', '')
                if 'Product' in str(item_type):
                    offers = item.get('offers', {})
                    if isinstance(offers, list):
                        for offer in offers:
                            price = _parse_offer_price(offer)
                            if price:
                                prices.append(price)
                            if not currency and 'priceCurrency' in offer:
                                currency = offer['priceCurrency']
                    elif isinstance(offers, dict):
                        price = _parse_offer_price(offers)
                        if price:
                            prices.append(price)
                        if not currency and 'priceCurrency' in offers:
                            currency = offers['priceCurrency']
                            
        except (json.JSONDecodeError, Exception):
            continue
    
    return prices, currency


def _parse_offer_price(offer: Dict) -> Optional[float]:
    """Parse price from a JSON-LD Offer object."""
    price_val = offer.get('price') or offer.get('lowPrice') or offer.get('highPrice')
    if price_val:
        if isinstance(price_val, (int, float)):
            return float(price_val) if float(price_val) > 0 else None
        elif isinstance(price_val, str):
            try:
                clean = re.sub(r'[^\d.]', '', price_val)
                if clean:
                    val = float(clean)
                    return val if val > 0 else None
            except ValueError:
                pass
    return None


def _extract_data_attribute_prices(html_str: str) -> List[float]:
    """
    Extract prices from HTML data attributes.
    
    Patterns:
    - data-price="99.99"
    - data-product-price="99.99"
    - data-price-amount="99.99"
    """
    prices = []
    
    patterns = [
        r'data-price=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        r'data-product-price=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        r'data-price-amount=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        r'data-regular-price=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        r'data-sale-price=["\']([0-9]+(?:\.[0-9]+)?)["\']',
    ]
    
    for pattern in patterns:
        for match in re.findall(pattern, html_str, re.IGNORECASE):
            try:
                price = float(match)
                if price > 0:
                    prices.append(price)
            except ValueError:
                continue
    
    return prices


def _extract_inline_js_prices(html_str: str) -> List[float]:
    """
    Extract prices from inline JavaScript price variables.
    
    Patterns:
    - "price": 99.99
    - price: 99.99
    - "amount": 99.99
    """
    prices = []
    
    # Look for price assignments in script tags
    script_pattern = r'<script[^>]*>([\s\S]*?)</script>'
    scripts = re.findall(script_pattern, html_str, re.IGNORECASE)
    
    for script in scripts:
        # Skip minified analytics/tracking scripts
        if len(script) > 50000:
            continue
            
        # Find price-like patterns
        patterns = [
            r'["\']price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'["\']amount["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'["\']current_price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'["\']sale_price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        ]
        
        for pattern in patterns:
            for match in re.findall(pattern, script, re.IGNORECASE):
                try:
                    price = float(match)
                    # Filter out likely non-product prices (very small or very large)
                    if 1.0 <= price <= 50000.0:
                        prices.append(price)
                except ValueError:
                    continue
    
    return prices


def _extract_meta_prices(html_str: str) -> Tuple[List[float], Optional[str]]:
    """
    Extract prices from meta tags.
    
    Patterns:
    - <meta property="og:price:amount" content="99.99">
    - <meta property="product:price:amount" content="99.99">
    """
    prices = []
    currency = None
    
    patterns = [
        r'<meta[^>]*property=["\']og:price:amount["\'][^>]*content=["\']([0-9]+(?:\.[0-9]+)?)["\']',
        r'<meta[^>]*content=["\']([0-9]+(?:\.[0-9]+)?)["\'][^>]*property=["\']og:price:amount["\']',
        r'<meta[^>]*property=["\']product:price:amount["\'][^>]*content=["\']([0-9]+(?:\.[0-9]+)?)["\']',
    ]
    
    for pattern in patterns:
        for match in re.findall(pattern, html_str, re.IGNORECASE):
            try:
                price = float(match)
                if price > 0:
                    prices.append(price)
            except ValueError:
                continue
    
    # Get currency
    currency_patterns = [
        r'<meta[^>]*property=["\']og:price:currency["\'][^>]*content=["\'](\w+)["\']',
        r'<meta[^>]*content=["\'](\w+)["\'][^>]*property=["\']og:price:currency["\']',
    ]
    
    for pattern in currency_patterns:
        match = re.search(pattern, html_str, re.IGNORECASE)
        if match:
            currency = match.group(1).upper()
            break
    
    return prices, currency


def _extract_html_price_text(html_str: str) -> Tuple[List[float], Optional[str]]:
    """
    Extract prices from visible HTML text as a last resort.
    
    Patterns:
    - $99.99
    - £99.99
    - €99.99
    - ¥9999
    """
    prices = []
    currency = None
    
    # Currency patterns
    currency_map = {
        r'\$([0-9,]+(?:\.[0-9]{2})?)': 'USD',
        r'£([0-9,]+(?:\.[0-9]{2})?)': 'GBP',
        r'€([0-9,]+(?:\.[0-9]{2})?)': 'EUR',
        r'¥([0-9,]+)': 'JPY',
        r'₹([0-9,]+(?:\.[0-9]{2})?)': 'INR',
        r'C\$([0-9,]+(?:\.[0-9]{2})?)': 'CAD',
        r'A\$([0-9,]+(?:\.[0-9]{2})?)': 'AUD',
    }
    
    for pattern, curr in currency_map.items():
        for match in re.findall(pattern, html_str):
            try:
                # Remove commas
                clean = match.replace(',', '')
                price = float(clean)
                if price > 0:
                    prices.append(price)
                    if not currency:
                        currency = curr
            except ValueError:
                continue
    
    return prices, currency


def _detect_currency(html_str: str) -> Optional[str]:
    """Detect the primary currency from the page."""
    # Look for Shopify currency setting
    shopify_pattern = r'Shopify\.currency\s*=\s*\{[^}]*["\']active["\']:\s*["\'](\w+)["\']'
    match = re.search(shopify_pattern, html_str)
    if match:
        return match.group(1).upper()
    
    # Look for currency in meta tags
    meta_pattern = r'<meta[^>]*name=["\']currency["\'][^>]*content=["\'](\w+)["\']'
    match = re.search(meta_pattern, html_str, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Look for data-currency attribute
    data_pattern = r'data-currency=["\'](\w+)["\']'
    match = re.search(data_pattern, html_str, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    return None


# Convenience function for main.py integration
def extract_price_stats_from_html(html_str: str) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    """
    Extract price statistics from HTML.
    
    Returns:
        Tuple of (min_price, max_price, median_price, currency)
    """
    result = extract_prices_from_js(html_str)
    return (
        result.get('price_min'),
        result.get('price_max'),
        result.get('price_median'),
        result.get('currency', 'USD')
    )
