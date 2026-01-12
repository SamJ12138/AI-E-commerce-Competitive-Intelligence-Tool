# E-commerce Intelligence Tool v16 - Release Notes

## 🎉 What's New in v16

### 1. Professional Business Report
New executive-level competitive intelligence report following McKinsey/BCG/Bain consulting frameworks.

**Report Structure:**
1. **Executive Summary** - Key findings at a glance
2. **Market Overview** - Platform distribution, pricing landscape
3. **Competitor Profiles** - Deep-dive on each competitor
4. **Comparative Analysis** - Feature comparison matrix
5. **SWOT Analysis** - Strategic opportunities and threats
6. **Strategic Recommendations** - Actionable next steps
7. **Appendix** - Methodology and data quality notes

**Output:** `output/business_report.md`

### 2. Scan History Tracking
Now tracks and displays scan history for each website:

```
✓ Completed: aloyoga.com
  📊 Scan #3 for aloyoga.com
```

**Features:**
- Counts total scans per domain
- Stores first scan date and latest scan date
- Tracks historical price ranges, shipping policies, return windows
- Enables change detection across multiple scans

### 3. Change Detection Improvements
When changes are detected between scans:

```markdown
### Changes Since Last Scan:
- Price range changed from $78-$195 to $75-$198
- Free shipping threshold changed from $100 to $75
- Return period extended from 30 to 45 days
```

### 4. Warning Fixes
Reduced console noise by fixing verbose warnings:

**Before:**
```
WARNING  Playwright network error for https://...
WARNING  Cloudscraper failed: HTTPSConnectionPool...
WARNING  Invalid URL '/sitemap.xml'...
```

**After:**
*(Silent or at DEBUG level - errors handled gracefully)*

## 📊 Business Report Sample

```markdown
# Competitive Intelligence Report

**Report Date:** January 13, 2026
**Competitors Analyzed:** 25

---

## Executive Summary

### Key Findings

**Platform Landscape:** 17 of 25 competitors (68%) use Shopify.

**Pricing:** Average price range across competitors is $45-$125. 
Market spans $5 to $350.

**Shipping:** 12 of 25 competitors (48%) offer free shipping.

**Returns:** Average return window is 30 days.

---

## Competitor Profiles

### aloyoga.com

**Website:** [https://www.aloyoga.com](https://www.aloyoga.com) | **Platform:** Shopify

**Scan History:** 3 scans (First: 2026-01-10, Latest: 2026-01-13)

**Key Metrics:**
- **Price Range:** $78 - $195 (Median: $136)
- **Shipping:** Free shipping on all orders
- **Returns:** 30 days (free)
- **Marketing:** Popup, Email Capture, Loyalty Program

**Key Insights:**
- Premium athleisure brand targeting health-conscious consumers
- Strong email capture with 15% first-order discount
- Free shipping drives conversion

---

## Comparative Analysis

### Feature Comparison Matrix

| Competitor | Price Range | Free Ship | Returns | Loyalty | Subscriptions |
|------------|-------------|-----------|---------|---------|---------------|
| aloyoga.com | $78-$195 | ✅ All | 30d ✅ | ✅ | ❌ |
| allbirds.com | $98-$155 | $50+ | 30d | ❌ | ❌ |
| glossier.com | $12-$60 | ✅ All | 30d ✅ | ✅ | ✅ |

---

## Strategic Recommendations

### Immediate Actions (0-3 months)
1. **Benchmark Pricing:** Review your pricing against competitive median
2. **Shipping Policy Review:** Evaluate free shipping threshold
3. **Return Policy Optimization:** Align with industry standard

### Short-term Initiatives (3-6 months)
1. **Customer Retention:** Implement loyalty program if gaps exist
2. **Email Marketing:** Strengthen email capture and nurturing
3. **Product Bundling:** Consider bundles/subscriptions

### Long-term Strategy (6-12 months)
1. **Differentiation:** Identify unique value propositions
2. **Market Expansion:** Consider underserved segments
3. **Technology Investment:** Evaluate platform capabilities
```

## 🔧 Technical Fixes

### Warnings Fixed:
| Issue | Before | After |
|-------|--------|-------|
| Playwright network errors | WARNING level | DEBUG level |
| Cloudscraper SSL failures | WARNING with full traceback | DEBUG with type only |
| Invalid sitemap URLs | Error shown | Silently skipped |
| robots.txt SSL errors | WARNING | DEBUG |

### Invalid URL Fix:
```
Before: WARNING Cloudscraper failed: Invalid URL '/sitemap.xml'
After: (Silently skipped - invalid URLs detected before fetch)
```

## 📁 New Files

```
modules/business_report.py    # Professional report generator
```

## 📝 Updated Files

```
main.py                       # Scan history display, business report gen
modules/snapshot_store.py     # New history tracking methods
modules/http_client.py        # Reduced warning verbosity
modules/page_discovery.py     # URL validation for sitemaps
START.ps1                     # Shows business report path
```

## 🚀 Usage

```powershell
# Windows - Full analysis with business report
.\START.ps1 -RenderJS -AI -Lang en

# macOS/Linux
./START.sh --render-js --ai --lang en
```

**Output Files:**
- `output/report.md` - Detailed technical report
- `output/report.csv` - Data export for Excel
- `output/business_report.md` - Executive business report (NEW)

## 💡 Best Practices

1. **Run Multiple Scans:** The tool tracks history, so run weekly/monthly for change detection
2. **Use Business Report:** Share `business_report.md` with stakeholders
3. **Enable AI:** AI analysis provides better insights (`-AI` flag)
4. **Check Scan Count:** Look for "Scan #N" messages to verify tracking

## 🔄 Upgrade from v15

1. Delete old `venv` folder
2. Extract v16 to new folder  
3. Copy `data/intel_cache.db` from v15 to preserve scan history
4. Run `START.ps1` or `START.sh`

Your historical scan data will be preserved!
