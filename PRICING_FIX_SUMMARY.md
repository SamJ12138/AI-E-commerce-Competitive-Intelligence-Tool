# Pricing Extraction Fix Summary (v12)

## Problem Identified

The report.csv showed missing pricing data for multiple sites:

| Site | Issue |
|------|-------|
| **Alo Yoga** | `price_min`, `price_max`, `price_median` all EMPTY |
| **Lululemon** | All fields empty (HTTP/2 error prevented fetch) |
| **Hyundai** | Empty (expected - not e-commerce) |

## Root Cause Analysis

### Alo Yoga
The standard product extraction was finding **no products** on the homepage because:
1. Alo Yoga uses a React-based SPA that renders products dynamically
2. Product data is embedded in JavaScript objects (`searchSettings.suggestedProducts`)
3. The existing extractor was looking for HTML product cards that don't exist on the homepage

**Price Data Location Found (lines 6004-6039):**
```javascript
searchSettings.suggestedProducts.push({
    title: "Accolade Crew Neck Pullover - Black",
    price: 138.0,
    priceFormatted: "$138.00",
    ...
});
```

### Lululemon
Playwright fails with `net::ERR_HTTP2_PROTOCOL_ERROR` when fetching. The HTTP/2 fallback to requests was already added in v11.

## Solution Implemented

### 1. New Module: `price_extractor.py`

Created comprehensive price extraction from JavaScript with multiple fallback methods:

1. **Shopify searchSettings.suggestedProducts** - Primary method for Shopify sites
2. **Window-based product arrays** - `window.products`, `var products = [...]`
3. **JSON-LD structured data** - `@type: Product` with offers
4. **Data attributes** - `data-price`, `data-product-price`
5. **Inline JavaScript** - Price assignments in script tags
6. **Meta tags** - `og:price:amount`
7. **HTML text patterns** - Last resort `$XX.XX` parsing

### 2. Integration in `main.py`

Added fallback after standard product extraction:

```python
# FALLBACK: If no prices found from product extraction, try JavaScript extraction
if not intel.price_min and html_str:
    logger.info("No prices from product extraction, trying JavaScript fallback...")
    js_price_min, js_price_max, js_price_median, js_currency = extract_price_stats_from_html(html_str)
    if js_price_min is not None:
        intel.price_min = js_price_min
        intel.price_max = js_price_max
        intel.price_median = js_price_median
        intel.currency = js_currency
```

### 3. Tested with Alo Yoga Source Code

```
=== PRICE EXTRACTION TEST (Alo Yoga) ===
Prices found: [138.0, 134.0, 195.0, 78.0]
Min: $78.0
Max: $195.0
Median: $136.0
Currency: USD
```

## Expected Results After Fix

| Site | Field | Before | After |
|------|-------|--------|-------|
| Alo Yoga | price_min | empty | 78.0 |
| Alo Yoga | price_max | empty | 195.0 |
| Alo Yoga | price_median | empty | 136.0 |
| Lululemon | all | empty | Should extract if HTTP fallback works |
| Hyundai | all | empty | empty (correct - not e-commerce) |

## Files Added/Modified

1. **NEW: `modules/price_extractor.py`** - JavaScript price extraction module
2. **MODIFIED: `modules/__init__.py`** - Added exports for new functions
3. **MODIFIED: `main.py`** - Added fallback price extraction
4. **NEW: `PRICING_PATTERNS.md`** - Documentation of discovered patterns

## Universal Patterns for Future Sites

When pricing extraction fails on new sites:

1. Save the homepage source code
2. Search for patterns:
   - `suggestedProducts` (Shopify)
   - `"price":` in script tags
   - `application/ld+json` with Product type
   - `data-price` attributes
3. Add new patterns to `price_extractor.py`
4. Test with saved source code
5. Document in `PRICING_PATTERNS.md`

## Testing Command

```powershell
# Run with JavaScript rendering enabled
.\run.ps1 -RenderJS -AI

# Check results in output/report.csv for price_min, price_max, price_median
```
