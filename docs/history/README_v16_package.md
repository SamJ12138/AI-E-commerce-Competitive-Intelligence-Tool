# E-commerce Competitive Intelligence Tool

A production-quality Python tool for analyzing independent e-commerce sites (Shopify, DTC sites) and generating actionable competitive intelligence for Chinese merchants selling cross-border (China → US).

## ✨ Features

### Core Features
- **Multi-platform detection**: Automatically identifies Shopify, WooCommerce, Magento, BigCommerce, Wix, Squarespace, and custom platforms
- **Comprehensive extraction**: Products, prices, promotions, policies, trust signals, and more
- **Bilingual reports**: Generate reports in English or Chinese (选择英文或中文报告)
- **Change detection**: Monitor mode tracks changes between scans
- **robots.txt compliance**: Respects website crawling policies by default

### 🤖 AI-Powered Analysis
- **Qwen2.5 LLM**: Generate intelligent insights using local AI (via Ollama)
- **Pricing Prediction**: ML-based optimal pricing recommendations
- **Threat Scoring**: Automated competitor threat assessment (1-10 scale)
- **Competitive Positioning**: Deep analysis of brand positioning and strategy

### 🛡️ Anti-Bot Bypass (NEW in v15)
- **Patchright Integration**: Bypasses Cloudflare, DataDome, and other bot detection
- **Cloudscraper Fallback**: Alternative Cloudflare bypass without browser
- **Stealth Mode**: Real Chrome browser fingerprinting

## 🚀 Quick Start

### Windows (One-Click)

```powershell
# Option 1: Double-click CLICK_TO_RUN.bat

# Option 2: Run from PowerShell
.\START.ps1 -RenderJS -AI

# With English reports
.\START.ps1 -RenderJS -AI -Lang en
```

### macOS / Linux (One-Click)

```bash
# Make executable (first time only)
chmod +x START.sh CLICK_TO_RUN.command

# Option 1: Double-click CLICK_TO_RUN.command in Finder

# Option 2: Run from Terminal
./START.sh --render-js --ai

# With English reports
./START.sh --render-js --ai --lang en
```

### Language Selection

When you run the tool, you'll be prompted to choose:
```
SELECT REPORT LANGUAGE
[1] English (英文报告)
[2] Chinese 中文 (默认)

Select language (1 or 2) [default: 2]:
```

Or specify directly:
```bash
# Windows
.\START.ps1 -Lang en

# macOS/Linux
./START.sh --lang en
```

Reports are generated in the `output/` folder.

## 🤖 Enabling AI Analysis

AI analysis uses **Qwen2.5** running locally via **Ollama** (free, private, no API costs).

### Install Ollama

**Windows:**
1. Download from: https://ollama.com/download
2. Install and run Ollama

**macOS:**
```bash
brew install ollama
ollama serve &
```

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
```

### Pull the AI Model

```bash
ollama pull qwen2.5:7b
```

### Verify AI is Working

```bash
# Check Ollama is running
ollama list

# Should show qwen2.5:7b in the list
```

### Run with AI

```bash
# Windows
.\START.ps1 -AI

# macOS/Linux
./START.sh --ai
```

## 📜 Policy Evidence Ladder (Legal Compliance)

This tool respects `robots.txt` by default and implements a **Policy Evidence Ladder** to ensure legal compliance and data accuracy.

### How It Works

Each extracted policy is tracked with its source and confidence level:

| Level | Status | Source | Confidence |
|-------|--------|--------|------------|
| 1 | ✅ | Official policy page (`/policies/shipping`) | 95% |
| 2 | ✅ | FAQ/Help Center (`/faq`, `/help`) | 85% |
| 3 | ⚠️ | Product/Cart page inference | 60% |
| 4 | ❌ | Blocked by robots.txt | Manual verify |

### Report Output

```markdown
### 📜 Policy Data Sources

| Policy | Status | Source | Verification |
|--------|--------|--------|--------------|
| Shipping | ✅ | Official policy page | Verified |
| Returns | ⚠️ | Product/cart page | Manual check needed |

*⚠️ Some policy data requires manual verification.*
```

### When Robots.txt Blocks Access

Instead of bypassing restrictions, the tool will:
1. Mark the data as "blocked" in the report
2. Flag it for manual verification
3. List the blocked URLs for reference

This ensures you always know where your data comes from and its reliability level.

## 📊 Output Format

### Markdown Report (`output/report.md`)

For each site:
- 🔍 **关键洞察** (Key Insights) - 6-12 AI-generated bullet points
- 💡 **可复制的动作建议** (Recommendations) - 3 actionable items
- ⚠️ **竞争威胁评估** (Threat Score) - 1-10 with explanation
- 💰 **定价策略建议** (Pricing Advice) - Optimal price recommendations
- 📋 **数据证据** (Evidence) - Links and extracted values
- 📜 **政策数据来源** (Policy Sources) - Evidence ladder with verification status
- 📈 **变化追踪** (Changes) - If monitor mode enabled

### Comparison Table

| 网站 | 平台 | 品牌定位 | 价格区间 | 促销手段 | 威胁评分 |
|------|------|----------|----------|----------|----------|
| example.com | Shopify | 配饰品牌 | $15-$50 | 弹窗、会员 | 7/10 |

## 🔧 Advanced Usage

### Command Line Options

```powershell
python main.py --help

Options:
  -s, --sites TEXT       Path to sites.txt file (required)
  -o, --outdir TEXT      Output directory [default: output]
  --render-js            Use Playwright for JS rendering
  --ignore-robots        Ignore robots.txt restrictions
  -t, --timeout INTEGER  Request timeout [default: 30]
  --max-products INTEGER Max products per site [default: 50]
  --max-pages INTEGER    Max pages per site [default: 20]
  -m, --monitor          Enable change detection
  --ai                   Enable AI analysis
  --ai-model TEXT        Ollama model [default: qwen2.5:7b]
  -v, --verbose          Verbose logging
```

### Using Different AI Models

```powershell
# Use larger Qwen model (requires more VRAM)
python main.py --sites sites.txt --ai --ai-model qwen2.5:14b

# Use DeepSeek (if available)
python main.py --sites sites.txt --ai --ai-model deepseek-v2
```

## Data Extracted

### Per Site

| Category | Data Points |
|----------|-------------|
| **Platform** | Shopify, WooCommerce, Magento, etc. |
| **Brand** | Name, positioning, meta description |
| **Products** | Titles, URLs, prices, categories |
| **Pricing** | Min/max/median, currency, discounts |
| **Promotions** | Announcement bars, popups, email capture |
| **Programs** | Loyalty, referral, subscriptions, bundles |
| **Shipping** | Free threshold, regions, delivery times |
| **Returns** | Days, free returns, conditions |
| **Trust** | Reviews (platform + count), badges, payments |
| **Analytics** | GA, Meta Pixel, TikTok, Klaviyo |

## Architecture

```
ecommerce-intel/
├── main.py                 # CLI entry point
├── modules/
│   ├── __init__.py
│   ├── models.py           # Data models (dataclasses)
│   ├── http_client.py      # HTTP with rate limiting
│   ├── robots_checker.py   # robots.txt compliance
│   ├── url_utils.py        # URL normalization
│   ├── platform_detector.py # Platform detection
│   ├── page_discovery.py   # Sitemap/link crawling
│   ├── product_extractor.py # Product extraction
│   ├── promo_extractor.py  # Promotion detection
│   ├── policy_extractor.py # Policy extraction
│   ├── trust_extractor.py  # Trust signals
│   ├── snapshot_store.py   # SQLite caching
│   ├── insight_generator.py # Chinese insights
│   └── report_writer.py    # Report generation
├── data/                   # SQLite cache
├── output/                 # Generated reports
├── requirements.txt
├── config.example.yaml
├── sites.txt
└── README.md
```

## Extending the Tool

### Adding New Extractors

1. Create a new module in `modules/`:

```python
# modules/my_extractor.py
from bs4 import BeautifulSoup

def extract_my_data(soup: BeautifulSoup, html_str: str) -> dict:
    # Your extraction logic
    return {'key': 'value'}
```

2. Import in `modules/__init__.py`
3. Call from `main.py` in the `analyze_site()` function

### Adding New Platforms

Edit `modules/platform_detector.py` and add patterns:

```python
Platform.NEW_PLATFORM: {
    'html': [r'pattern1', r'pattern2'],
    'scripts': [r'script_pattern'],
    'headers': [('x-header-name', '')],
    'meta': [('generator', r'platform_name', False)],
}
```

### Custom Insights

Edit `modules/insight_generator.py` to customize:
- Chinese bullet point generation
- Recommendation logic
- Price tier classification

## Limitations

1. **Dynamic content**: Some sites require JavaScript rendering (`--render-js`)
2. **Anti-bot protection**: Sites with aggressive protection may block requests
3. **Login walls**: Cannot access content behind authentication
4. **CAPTCHAs**: Not bypassed (returns "无法获取")
5. **Rate limits**: Respects 1.5s delay between requests

## Ethical Usage

- **Respect robots.txt** by default
- **Rate limiting** prevents server overload
- **No login bypass** - only public content
- **No CAPTCHA solving** - marks blocked content
- Use for competitive intelligence only

## Troubleshooting

### Common Issues

**SSL Errors**:
```
SSL error for https://example.com
```
The tool automatically retries without SSL verification.

**403 Forbidden**:
```
Access forbidden (403)
```
Site is blocking automated requests. Try `--render-js` or check robots.txt.

**Timeout**:
```
Timeout after 30s
```
Increase timeout: `--timeout 60`

**No products found**:
Site may use heavy JavaScript. Try `--render-js`.

### Debug Mode

```bash
python main.py --sites sites.txt --verbose
```

## License

MIT License - See LICENSE file.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Changelog

### v1.0.0
- Initial release
- Multi-platform detection
- Chinese insight generation
- Change detection (monitor mode)
- Markdown and CSV reports
