# E-Commerce Pricing Extraction Patterns

## Overview

This document catalogs the pricing data patterns discovered across different e-commerce platforms. 
Use these patterns when extracting prices fails with standard product extraction methods.

## Discovered Patterns by Platform

### 1. Shopify Sites (Alo Yoga, Gymshark, etc.)

**Primary Pattern: searchSettings.suggestedProducts**

Location in HTML: Inside `<script id="SearchSettingsPassedFromShopify">` or inline script

```javascript
searchSettings.suggestedProducts.push({
    title: "Product Name",
    image_url: "//cdn.shopify.com/...",
    price: 138.0,                    // <-- CURRENT PRICE (float)
    priceFormatted: "$138.00",       // <-- FORMATTED PRICE
    url: "/products/product-handle",
    list_price: 0,                   // <-- COMPARE-AT PRICE (0 if not on sale)
    product_id: 7325031202996
});
```

**Regex Pattern:**
```python
r'suggestedProducts\.push\s*\(\s*\{[^}]*?["\']?price["\']?\s*:\s*([0-9]+(?:\.[0-9]+)?)[^}]*?\}\s*\)'
```

**Currency Detection:**
```javascript
Shopify.currency = {"active":"USD","rate":"1.0"};
```

**Regex:**
```python
r'Shopify\.currency\s*=\s*\{[^}]*["\']active["\']:\s*["\'](\w+)["\']'
```

### 2. JSON-LD Structured Data (All Platforms)

Location: `<script type="application/ld+json">`

```json
{
    "@type": "Product",
    "name": "Product Name",
    "offers": {
        "@type": "Offer",
        "price": "99.99",
        "priceCurrency": "USD"
    }
}
```

**Or with price range:**
```json
{
    "@type": "Product",
    "offers": {
        "@type": "AggregateOffer",
        "lowPrice": "49.99",
        "highPrice": "199.99",
        "priceCurrency": "USD"
    }
}
```

### 3. Meta Tags

```html
<meta property="og:price:amount" content="99.99">
<meta property="og:price:currency" content="USD">
<meta property="product:price:amount" content="99.99">
```

### 4. Data Attributes

```html
<div data-price="99.99" data-currency="USD">
<span data-product-price="99.99">
<div data-price-amount="99.99">
```

### 5. Inline JavaScript Variables

```javascript
var products = [{price: 99.99, ...}];
window.products = [...];
window.productData = {price: 99.99};
```

## Platform-Specific Examples

### Alo Yoga (Shopify)
- **File Location:** Lines 6004-6039 in homepage source
- **Pattern:** `searchSettings.suggestedProducts`
- **Sample Prices Found:** $78, $134, $138, $195

### Lululemon
- **Issue:** HTTP/2 protocol error prevents standard fetching
- **Solution:** Fallback to requests library (HTTP/1.1)
- **Note:** May need to check `/products.json` endpoint

### Hyundai (Non E-Commerce)
- **Issue:** Not a product-selling e-commerce site
- **Expected:** No product prices to extract
- **Note:** Different business model (automotive configurator/dealer locator)

## Extraction Priority Order

1. **Standard Product Cards** - BeautifulSoup DOM parsing
2. **Shopify searchSettings.suggestedProducts** - Most reliable for Shopify
3. **JSON-LD Structured Data** - Standardized format
4. **Meta Tags** - Open Graph price tags
5. **Data Attributes** - HTML5 data-* attributes
6. **Inline JavaScript** - Window/var assignments
7. **HTML Text Patterns** - Last resort, parse $XX.XX patterns

## Currency Detection Priority

1. `Shopify.currency = {...}` 
2. `<meta name="currency" content="...">`
3. `data-currency="..."` attributes
4. Currency symbol in price text ($ £ € ¥)

## Implementation Notes

### When Standard Extraction Fails
Add fallback in `main.py`:

```python
if not intel.price_min and html_str:
    js_price_min, js_price_max, js_price_median, js_currency = extract_price_stats_from_html(html_str)
    if js_price_min is not None:
        intel.price_min = js_price_min
        intel.price_max = js_price_max
        intel.price_median = js_price_median
        intel.currency = js_currency
```

### HTTP/2 Error Handling
Sites like Lululemon may fail with Playwright due to HTTP/2 protocol issues:

```python
if 'HTTP2_PROTOCOL_ERROR' in error_msg or 'ERR_HTTP2' in error_msg:
    logger.warning(f"HTTP/2 error, falling back to requests")
    return self._fetch_with_requests(url)
```

## Expected Results After Fixes

| Site | Before Fix | After Fix |
|------|------------|-----------|
| Alo Yoga | price_min: empty | price_min: 78.0 |
| Alo Yoga | price_max: empty | price_max: 195.0 |
| Alo Yoga | price_median: empty | price_median: 136.0 |
| Lululemon | Failed to fetch | Should fetch via requests fallback |
| Hyundai | empty | empty (expected - not e-commerce) |

## Adding New Patterns

When a new site's pricing isn't extracted:

1. Save the page source code
2. Search for "price" in the source
3. Identify the pattern (JSON, JS variable, data attribute)
4. Add the pattern to `modules/price_extractor.py`
5. Test with the saved source code
6. Document the pattern here

## Files Modified

- `modules/price_extractor.py` - New module for JS-based price extraction
- `modules/http_client.py` - HTTP/2 fallback handling
- `modules/__init__.py` - Export new functions
- `main.py` - Integrate fallback extraction
