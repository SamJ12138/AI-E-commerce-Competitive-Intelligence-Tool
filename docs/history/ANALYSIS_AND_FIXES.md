# E-commerce Intel Tool: Analysis & Fixes

## Issues Found in PowerShell Output

### Issue 1: Playwright Warning for Lululemon
```
WARNING  Failed to fetch https://shop.lululemon.com: Playwright error: Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR
```

**Root Cause:** HTTP/2 protocol mismatch - the site is blocking or having issues with the Playwright browser's HTTP/2 connection.

**Fix Location:** `modules/http_client.py`

**Solution:** Add HTTP/2 fallback and better error recovery:

```python
# In _fetch_with_playwright method, add retry with HTTP/1.1 fallback
def _fetch_with_playwright(self, url: str) -> Tuple[Optional[str], int, Dict[str, str], Optional[str]]:
    try:
        self._init_playwright()
        page = self._context.new_page()
        
        try:
            # First attempt with default settings
            response = page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # ... existing code
        except Exception as e:
            if "ERR_HTTP2_PROTOCOL_ERROR" in str(e):
                # Retry with HTTP/1.1 by using a different context
                logger.warning(f"HTTP/2 error for {url}, falling back to requests")
                page.close()
                return self._fetch_with_requests(url)
            raise
```

---

### Issue 2: robots.txt Blocking Policy Pages
```
INFO     URL blocked by robots.txt: https://www.aloyoga.com/policies/shipping-policy
INFO     URL blocked by robots.txt: https://www.aloyoga.com/policies/refund-policy
```

**Root Cause:** Shopify's default robots.txt blocks `/policies/*` paths, preventing extraction of shipping/return policy data.

**Impact on Data:** 
- `free_shipping_threshold`: Empty
- `return_days`: Empty  
- `free_returns`: Missing

**Solutions:**

#### Option A: Extract from Homepage/Footer JavaScript (Recommended)
The Alo Yoga source code shows policy data embedded in JavaScript:
```javascript
"returnsMessaging": {"us":{"pdp":"Free Shipping & Free Returns","cart":"Easy Returns"}},
"sddShippingOptions": {"shippingOptions":[{"service":"standard","title":"FREE Standard Shipping"...}]},
"sddReturnsInfo": "ALO will gladly accept merchandise for a refund within 30 days..."
```

**Fix:** Add JavaScript JSON extraction to `policy_extractor.py`:

```python
def extract_policies_from_js(self, html_str: str) -> Tuple[Optional[ShippingPolicy], Optional[ReturnPolicy]]:
    """Extract policy data from embedded JavaScript on homepage."""
    shipping = ShippingPolicy()
    returns = ReturnPolicy()
    
    # Pattern 1: Shopify settings JSON
    patterns = [
        r'"returnsMessaging"\s*:\s*(\{[^}]+\})',
        r'"sddShippingOptions"\s*:\s*(\{[^}]+\})',
        r'"sddReturnsInfo"\s*:\s*"([^"]+)"',
        r'"free_shipping_threshold"\s*:\s*(\d+)',
    ]
    
    # Extract return days from patterns like "within 30 days"
    return_days_match = re.search(r'within\s+(\d+)\s+days', html_str, re.I)
    if return_days_match:
        returns.return_days = int(return_days_match.group(1))
    
    # Check for free shipping/returns messaging
    if 'free shipping' in html_str.lower() and 'free returns' in html_str.lower():
        shipping.free_shipping_threshold = 0  # Free on all
        returns.free_returns = True
    
    return shipping, returns
```

#### Option B: Add `--ignore-robots` Flag Usage
For users who need policy page data, recommend using:
```powershell
.\run.ps1 -IgnoreRobots
```

---

### Issue 3: Missing Data in CSV

Analyzing the CSV output vs. source code:

| Field | Alo Yoga CSV | Actually Available in Source |
|-------|--------------|------------------------------|
| `price_min` | Empty | ❌ Homepage doesn't show products |
| `price_max` | Empty | ❌ Homepage doesn't show products |
| `free_shipping_threshold` | Empty | ✅ `"FREE Standard Shipping"` in JS |
| `return_days` | Empty | ✅ `"within 30 days"` in JS |
| `free_returns` | Empty | ✅ `"Free Returns"` in messaging |
| `review_platform` | Bazaarvoice | ✅ Correct |
| `announcement_bar` | Long string | ⚠️ Should be cleaner |

**Fix for Announcement Bar:** The current extraction captures too much. Clean it:

```python
def _extract_announcement_bar(self, soup: BeautifulSoup) -> str:
    # ... existing selectors ...
    
    # Clean the extracted text
    if text:
        # Remove excessive whitespace
        text = ' '.join(text.split())
        # Truncate to reasonable length
        if len(text) > 200:
            text = text[:200] + '...'
        return text
```

---

## Data Extraction Improvements

### New Patterns to Add for Future Sites

Based on the Alo Yoga source code analysis, add these patterns:

#### 1. Free Shipping from Announcement Banner
```python
# In promo_extractor.py
ANNOUNCEMENT_FREE_SHIPPING_PATTERNS = [
    r'FREE\s+SHIPPING\s*[&+]\s*FREE\s+RETURNS',
    r'FREE\s+SHIPPING\s+OVER\s+\$(\d+)',
    r'FREE\s+STANDARD\s+SHIPPING',
]
```

#### 2. Return Days from JS Settings
```python
# In policy_extractor.py  
JS_RETURN_PATTERNS = [
    r'"returnDays"\s*:\s*(\d+)',
    r'refund\s+within\s+(\d+)\s+days',
    r'"sddReturnsInfo"\s*:.*?(\d+)\s+days',
]
```

#### 3. Loyalty Detection from Scripts
```python
# Already present but needs these additions:
LOYALTY_SCRIPT_PATTERNS = [
    'loyalty-top-panel',  # Alo Yoga pattern
    'smile.io',
    'yotpo-loyalty',
    'swell-rewards',
]
```

---

## robots.txt Behavior Explanation

**Why Some Sites Show Blocked, Others Don't:**

| Site | robots.txt Status | Policies Blocked? |
|------|-------------------|-------------------|
| Alo Yoga | `/policies/*` blocked | ✅ Yes |
| Gymshark | `/policies/*` blocked | ✅ Yes |
| Lululemon | Different structure | N/A (site error) |
| Nike.com.cn | Magento (different paths) | ❌ No |
| Hyundai | Non-ecommerce | ❌ No |

**Shopify sites** typically block `/policies/*` in robots.txt because those pages aren't meant to be indexed by search engines.

---

## Recommended Code Changes

### 1. `modules/http_client.py` - Add HTTP/2 Fallback

```python
def _fetch_with_playwright(self, url: str) -> Tuple[...]:
    try:
        # ... existing code ...
        response = page.goto(url, timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        error_msg = str(e)
        if "HTTP2_PROTOCOL_ERROR" in error_msg or "ERR_HTTP2" in error_msg:
            logger.warning(f"HTTP/2 error for {url}, falling back to requests library")
            page.close()
            return self._fetch_with_requests(url)
        raise
```

### 2. `modules/policy_extractor.py` - Add JS Extraction

```python
def extract_policies_from_homepage_js(self, html_str: str) -> dict:
    """Extract shipping/return policies from embedded JS on homepage."""
    result = {
        'free_shipping_threshold': None,
        'return_days': None,
        'free_returns': False,
        'shipping_options': [],
    }
    
    # Shopify settings patterns
    html_lower = html_str.lower()
    
    # Free shipping + free returns combo
    if 'free shipping' in html_lower and 'free returns' in html_lower:
        result['free_returns'] = True
        result['free_shipping_threshold'] = 0
    
    # Return days extraction
    return_match = re.search(
        r'(?:refund|return).*?within\s+(\d+)\s+days',
        html_str, re.I
    )
    if return_match:
        result['return_days'] = int(return_match.group(1))
    
    # Shipping options from JSON
    shipping_match = re.search(
        r'"sddShippingOptions"\s*:\s*(\{[^}]+\})',
        html_str
    )
    if shipping_match:
        try:
            # Parse shipping options
            pass  # Add JSON parsing
        except:
            pass
    
    return result
```

### 3. `main.py` - Use JS Extraction When Policy Pages Blocked

```python
# After analyze_site(), add fallback extraction:
if not intel.shipping_policy.free_shipping_threshold:
    # Try to extract from homepage JS
    js_policies = PolicyExtractor().extract_policies_from_homepage_js(homepage_html)
    if js_policies['free_shipping_threshold'] is not None:
        intel.shipping_policy.free_shipping_threshold = js_policies['free_shipping_threshold']
    if js_policies['return_days']:
        intel.return_policy.return_days = js_policies['return_days']
    if js_policies['free_returns']:
        intel.return_policy.free_returns = True
```

---

## Updated Data Extraction Summary

### What to Look For in Future Sites

| Data Point | Primary Source | Fallback Source |
|------------|----------------|-----------------|
| Free Shipping | `/policies/shipping-policy` | Homepage JS, Announcement bar |
| Return Days | `/policies/refund-policy` | Homepage JS (`sddReturnsInfo`) |
| Free Returns | Policy page | Homepage messaging JSON |
| Loyalty | Script tags, footer links | `loyalty-top-panel`, smile.io |
| Prices | Product pages, collections | JSON-LD schema |

### Key JavaScript Patterns (Shopify)

```javascript
// Look for these in page source:
window.theme_settings = { ... }
window.server_cart_data = { ... }  
"returnsMessaging": { ... }
"sddShippingOptions": { ... }
"sddReturnsInfo": "..."
```

---

## Testing Recommendations

After applying fixes:

```powershell
# Test with robots.txt respected (default)
.\run.ps1 -AI -RenderJS

# Test with robots.txt ignored (for policy pages)
.\run.ps1 -AI -RenderJS -IgnoreRobots

# Compare results
```

Expected improvements:
- `free_shipping_threshold` should populate from homepage JS
- `return_days` should show 30 for Alo Yoga
- `free_returns` should be True for Alo Yoga
- Lululemon should fall back to requests when Playwright fails
