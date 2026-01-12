# Anti-Bot Bypass Guide (v14)

## 🚀 Quick Setup

```powershell
# Run with anti-bot bypass enabled
.\START.ps1 -RenderJS -AI
```

This will automatically install:
1. **Patchright** - Patched Playwright that bypasses Cloudflare/DataDome
2. **Cloudscraper** - Fallback for Cloudflare without browser

---

## 🏆 Best GitHub Solutions for Bot Detection Bypass

### 1. Patchright (RECOMMENDED - Now Integrated)
**GitHub:** https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python

**What it does:**
- Patches CDP (Chrome DevTools Protocol) leaks
- Executes JavaScript in isolated contexts (undetectable)
- Passes Cloudflare, DataDome, and all major bot tests
- Same API as Playwright (drop-in replacement)

**Manual install:**
```bash
pip install patchright
patchright install chrome
```

### 2. Cloudscraper (Fallback - Now Integrated)
**GitHub:** https://github.com/VeNoMouS/cloudscraper

**What it does:**
- Bypasses Cloudflare without needing a browser
- Supports Cloudflare v1, v2, v3 challenges
- Supports Cloudflare Turnstile
- Lightweight

**Manual install:**
```bash
pip install cloudscraper
```

### 3. Other Options (Not Integrated)

| Tool | GitHub | Use Case |
|------|--------|----------|
| **Nodriver** | github.com/ultrafunkamsterdam/nodriver | Alternative to undetected-chromedriver |
| **SeleniumBase UC** | github.com/seleniumbase/SeleniumBase | Selenium with undetected mode |
| **Camoufox** | github.com/AresS31/camoufox | Firefox-based anti-detect |

---

## 🔧 How the Anti-Bot System Works

### Fallback Hierarchy:
```
1. Patchright (browser) → Best for all sites
      ↓ (if fails)
2. Cloudscraper (no browser) → Good for Cloudflare
      ↓ (if fails)
3. Protected Site Handler → Returns placeholder
```

### Detection Methods Bypassed:

| Detection | How Patchright Bypasses |
|-----------|------------------------|
| CDP Detection | Avoids Runtime.enable command |
| WebDriver flag | navigator.webdriver = undefined |
| Headless detection | Uses real Chrome, not Chromium |
| Fingerprinting | Realistic browser fingerprint |
| Console API | Disabled to avoid detection |

---

## 📊 Expected Results

### Before (Standard Playwright):
```
WARNING  Playwright network error for https://shop.lululemon.com
WARNING  Failed to fetch: Access forbidden (403)
```

### After (Patchright):
```
INFO     Browser engine: patchright
INFO     Browser initialized: Chrome via patchright
✓ Completed: lululemon.com
```

---

## ⚠️ Sites That May Still Block

Some sites have enterprise-level protection that even Patchright can't bypass:
- Sites using Cloudflare Enterprise with Turnstile CAPTCHA
- Sites requiring human verification
- Sites with per-customer ML models

For these sites, consider:
1. **Manual analysis** - Visit the site yourself
2. **Proxy services** - Bright Data, ScrapingBee, etc.
3. **CAPTCHA solving services** - 2Captcha, Anti-Captcha

---

## 🔄 Upgrading from Previous Versions

If you had v13 or earlier:

```powershell
# 1. Delete old venv
Remove-Item -Recurse -Force venv

# 2. Run fresh setup
.\START.ps1 -RenderJS -AI
```

This ensures Patchright is installed instead of standard Playwright.

---

## 📝 Troubleshooting

### "Patchright not found"
```powershell
pip install patchright
patchright install chrome
```

### "Chrome not available"
Patchright will automatically fall back to Chromium.

### Still getting blocked?
1. Try without `-RenderJS` flag first
2. Check if site requires CAPTCHA
3. Some sites simply cannot be automated

---

## 🔗 Resources

- [Patchright GitHub](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python)
- [Cloudscraper GitHub](https://github.com/VeNoMouS/cloudscraper)
- [How Cloudflare Detects Bots](https://blog.cloudflare.com/bot-management/)
- [ScrapFly Bypass Guide](https://scrapfly.io/blog/how-to-bypass-cloudflare/)
