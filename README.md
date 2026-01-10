# 🔍 E-commerce Competitive Intelligence Tool

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](https://github.com)

A production-ready Python tool for analyzing e-commerce websites (Shopify, WooCommerce, BigCommerce, etc.) and generating actionable competitive intelligence reports—with AI-powered insights in Chinese (中文) for cross-border merchants.

---

## 🌟 Features

### Core Capabilities
- **Multi-Platform Detection** — Automatically identifies Shopify, WooCommerce, Magento, BigCommerce, Wix, Squarespace, and custom platforms
- **Comprehensive Data Extraction** — Products, prices, promotions, shipping/return policies, trust signals, and analytics tracking
- **Chinese Insights (关键洞察)** — Generates actionable bullet points and recommendations in Chinese
- **Change Detection** — Monitor mode tracks price changes, new products, and policy updates between scans
- **Ethical Crawling** — Respects `robots.txt` and implements rate limiting by default

### 🤖 AI-Powered Analysis
- **Local LLM Integration** — Uses Qwen2.5 via Ollama (free, private, no API costs)
- **Pricing Prediction** — ML-based optimal pricing recommendations using XGBoost
- **Threat Scoring** — Automated competitor threat assessment (1-10 scale)
- **Brand Positioning Analysis** — Deep analysis of competitive positioning and strategy

---

## 📋 Table of Contents
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage](#-usage)
- [Configuration](#-configuration)
- [Output Format](#-output-format)
- [Architecture](#-architecture)
- [AI Setup](#-ai-setup-optional)
- [Extending the Tool](#-extending-the-tool)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

---

## 💻 Installation

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)
- (Optional) [Ollama](https://ollama.com/) for AI-powered analysis

### Windows (Recommended)

```powershell
# Clone the repository
git clone https://github.com/yourusername/ecommerce-intel.git
cd ecommerce-intel

# Run the setup script (creates virtual environment & installs dependencies)
.\setup.ps1

# Optional: Install Playwright for JavaScript-heavy sites
.\setup.ps1 -InstallPlaywright
```

### Linux / macOS

```bash
# Clone the repository
git clone https://github.com/yourusername/ecommerce-intel.git
cd ecommerce-intel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Optional: Install Playwright for JS rendering
pip install playwright
playwright install chromium
```

---

## 🚀 Quick Start

### 1. Add Target Sites
Edit `sites.txt` with the e-commerce URLs you want to analyze:

```
https://allbirds.com
https://gymshark.com
https://fashionnova.com
```

### 2. Run the Tool

**Windows:**
```powershell
.\run.ps1
```

**Linux/macOS:**
```bash
python main.py --sites sites.txt
```

### 3. View Reports
Reports are generated in the `output/` folder:
- `report.md` — Full Markdown report with insights
- `report.csv` — Data export for spreadsheets

---

## 📖 Usage

### Command Line Options

```bash
python main.py --help

Options:
  -s, --sites TEXT       Path to sites.txt file (required)
  -o, --outdir TEXT      Output directory [default: output]
  --render-js            Use Playwright for JavaScript rendering
  --ignore-robots        Ignore robots.txt restrictions
  -t, --timeout INTEGER  Request timeout in seconds [default: 30]
  --max-products INTEGER Maximum products to extract per site [default: 50]
  --max-pages INTEGER    Maximum pages to crawl per site [default: 20]
  -m, --monitor          Enable change detection mode
  --ai                   Enable AI-powered analysis (requires Ollama)
  --ai-model TEXT        Ollama model to use [default: qwen2.5:7b]
  -v, --verbose          Enable verbose logging
```

### Example Commands

```bash
# Basic analysis
python main.py --sites sites.txt

# With AI-powered insights
python main.py --sites sites.txt --ai

# JavaScript-heavy sites (Shopify 2.0, React SPAs)
python main.py --sites sites.txt --render-js

# Monitor mode (track changes over time)
python main.py --sites sites.txt --monitor

# Full analysis with all features
python main.py --sites sites.txt --ai --render-js --monitor --verbose
```

### Windows PowerShell Shortcuts

```powershell
# Basic run
.\run.ps1

# With AI analysis
.\run.ps1 -AI

# With JavaScript rendering
.\run.ps1 -RenderJS

# All features
.\run.ps1 -AI -RenderJS -Monitor -Verbose
```

---

## ⚙️ Configuration

Create a `config.yaml` file based on `config.example.yaml`:

```yaml
# Request settings
timeout: 30
rate_limit_delay: 1.5  # Seconds between requests

# Crawling limits
max_products: 50
max_pages: 20

# Feature flags
render_js: false
ignore_robots: false

# Output
output_dir: output
db_path: data/intel_cache.db
```

---

## 📊 Output Format

### Markdown Report (`output/report.md`)

For each analyzed site, the report includes:

| Section | Description |
|---------|-------------|
| 🔍 **关键洞察** (Key Insights) | 6-12 AI-generated bullet points in Chinese |
| 💡 **可复制的动作建议** (Recommendations) | 3 actionable items for your store |
| ⚠️ **竞争威胁评估** (Threat Score) | 1-10 rating with explanation |
| 💰 **定价策略建议** (Pricing Advice) | Optimal price recommendations |
| 📋 **数据证据** (Evidence) | Extracted links and values |
| 📈 **变化追踪** (Changes) | Price/product changes (monitor mode) |

### Comparison Table

| 网站 | 平台 | 品牌定位 | 价格区间 | 促销手段 | 威胁评分 |
|------|------|----------|----------|----------|----------|
| allbirds.com | Shopify | 环保鞋履品牌 | $98-$160 | 会员折扣、节日促销 | 8/10 |

### Data Extracted Per Site

| Category | Data Points |
|----------|-------------|
| **Platform** | Shopify, WooCommerce, Magento, BigCommerce, etc. |
| **Brand** | Name, positioning, meta description |
| **Products** | Titles, URLs, prices, images, categories |
| **Pricing** | Min/max/median prices, currency, discount patterns |
| **Promotions** | Announcement bars, popups, email capture, discount codes |
| **Programs** | Loyalty, referral, subscriptions, bundles |
| **Shipping** | Free threshold, regions, delivery times |
| **Returns** | Return window, conditions, free returns |
| **Trust Signals** | Review platforms, ratings, payment badges, certifications |
| **Analytics** | Google Analytics, Meta Pixel, TikTok Pixel, Klaviyo |

---

## 🏗️ Architecture

```
ecommerce-intel/
├── main.py                    # CLI entry point & orchestration
├── modules/
│   ├── __init__.py            # Module exports
│   ├── models.py              # Data models (dataclasses)
│   ├── http_client.py         # HTTP client with rate limiting & retries
│   ├── robots_checker.py      # robots.txt compliance
│   ├── url_utils.py           # URL normalization & validation
│   ├── platform_detector.py   # E-commerce platform detection
│   ├── page_discovery.py      # Sitemap parsing & link crawling
│   ├── product_extractor.py   # Product data extraction
│   ├── promo_extractor.py     # Promotion & discount detection
│   ├── policy_extractor.py    # Shipping/returns policy parsing
│   ├── trust_extractor.py     # Trust signals & reviews
│   ├── category_extractor.py  # Product category detection
│   ├── snapshot_store.py      # SQLite caching & change detection
│   ├── insight_generator.py   # Chinese insight generation
│   ├── ai_analyzer.py         # AI/ML analysis (Ollama + XGBoost)
│   └── report_writer.py       # Markdown & CSV report generation
├── tests/
│   └── test_modules.py        # Unit tests
├── data/                      # SQLite cache & ML models
├── output/                    # Generated reports
├── sites.txt                  # Target URLs
├── config.example.yaml        # Configuration template
├── requirements.txt           # Python dependencies
├── setup.ps1                  # Windows setup script
├── run.ps1                    # Windows run script
└── README.md
```

---

## 🤖 AI Setup (Optional)

AI analysis uses **Qwen2.5** running locally via **Ollama**—free, private, and no API costs.

### Step 1: Install Ollama

Download and install from: https://ollama.com/download

### Step 2: Pull the Model

```bash
# Default model (7B parameters, ~4GB VRAM)
ollama pull qwen2.5:7b

# Larger model for better quality (14B parameters, ~8GB VRAM)
ollama pull qwen2.5:14b
```

### Step 3: Verify Installation

```bash
# List available models
ollama list

# Test the model
ollama run qwen2.5:7b "Hello, can you respond in Chinese?"
```

### Step 4: Run with AI

```bash
python main.py --sites sites.txt --ai

# Or with a specific model
python main.py --sites sites.txt --ai --ai-model qwen2.5:14b
```

---

## 🔧 Extending the Tool

### Adding a New Extractor

1. Create a new module in `modules/`:

```python
# modules/my_extractor.py
from bs4 import BeautifulSoup
from typing import Dict, Any

def extract_my_data(soup: BeautifulSoup, html_str: str) -> Dict[str, Any]:
    """Extract custom data from page."""
    result = {}
    
    # Your extraction logic here
    element = soup.select_one('.my-selector')
    if element:
        result['my_field'] = element.get_text(strip=True)
    
    return result
```

2. Export in `modules/__init__.py`:

```python
from .my_extractor import extract_my_data
```

3. Call from `main.py` in the `analyze_site()` function.

### Adding Platform Detection

Edit `modules/platform_detector.py`:

```python
Platform.NEW_PLATFORM: {
    'html': [r'pattern1', r'pattern2'],
    'scripts': [r'script_pattern\.js'],
    'headers': [('x-powered-by', 'NewPlatform')],
    'meta': [('generator', r'NewPlatform.*', False)],
}
```

---

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **SSL Errors** | Tool automatically retries without SSL verification |
| **403 Forbidden** | Site blocking bots—try `--render-js` or check `robots.txt` |
| **Timeout** | Increase with `--timeout 60` |
| **No products found** | Site uses heavy JavaScript—use `--render-js` |
| **Ollama not found** | Ensure Ollama is running: `ollama serve` |

### Debug Mode

```bash
python main.py --sites sites.txt --verbose
```

### PowerShell Execution Policy (Windows)

If scripts are blocked:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black isort

# Run tests
pytest tests/ -v

# Format code
black .
isort .
```

---

## 📄 License

This project is licensed under the MIT License—see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- [Ollama](https://ollama.com/) for local LLM inference
- [Qwen2.5](https://github.com/QwenLM/Qwen2.5) for Chinese language AI
- [Rich](https://rich.readthedocs.io/) for beautiful terminal output

---

## 📬 Contact

- **Issues**: [GitHub Issues](https://github.com/yourusername/ecommerce-intel/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/ecommerce-intel/discussions)

---

<p align="center">
  Made with ❤️ for cross-border e-commerce merchants
</p>
