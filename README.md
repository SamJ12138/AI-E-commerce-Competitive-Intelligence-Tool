# E-commerce Competitive Intelligence Tool

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/AI-Qwen2.5-orange.svg" alt="AI Powered">
</p>

A professional-grade competitive intelligence tool that analyzes e-commerce websites and generates executive-level reports following McKinsey/BCG/Bain consulting frameworks. Built for cross-border sellers and market researchers.

![Architecture](https://github.com/user-attachments/assets/78c2c453-f8b2-4444-84d8-6c8e35decbc0)

## Features

**Automated Data Collection**
- Multi-platform detection (Shopify, WooCommerce, Magento, BigCommerce, Wix, Squarespace)
- Product catalog and pricing extraction
- Shipping and return policy analysis
- Marketing tactics identification (popups, email capture, loyalty programs)
- Trust signals and payment method detection

**Optional LLM step (`--ai`)**
- Key insights from a local model served by Ollama (default qwen2.5:7b) - no API costs
- Labelled AI in the reports only when the model actually produced the text

**Competitive pressure score (rule-based)**
- A fixed weighted rubric (1-10); the report prints every weight, factor score and input

**Professional Reports**
- Executive business report (consulting-style)
- Detailed technical report
- CSV export for Excel analysis
- Bilingual support (English/Chinese)

**Change Tracking**
- Historical scan storage
- Change detection between scans
- Trend analysis over time

## Quick Start

### Windows

```powershell
# Double-click CLICK_TO_RUN.bat or run:
.\START.ps1 -RenderJS -AI
```

### macOS / Linux

```bash
chmod +x START.sh
./START.sh --render-js --ai
```

That's it! The tool handles all setup automatically.

## Installation

### Prerequisites

- Python 3.10 or higher
- 4GB RAM minimum (8GB recommended for AI)

### Manual Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/ecommerce-intel.git
cd ecommerce-intel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: .\venv\Scripts\Activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py --sites sites.txt --render-js --ai
```

### Enable AI Analysis (Optional)

```bash
# Install Ollama
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh
# Windows: Download from https://ollama.com/download

# Start Ollama and pull model
ollama serve &
ollama pull qwen2.5:7b
```

## Usage

### Basic Commands

```bash
# Analyze sites listed in sites.txt
python main.py --sites sites.txt

# With JavaScript rendering (for dynamic sites)
python main.py --sites sites.txt --render-js

# With AI analysis
python main.py --sites sites.txt --ai

# English reports
python main.py --sites sites.txt --lang en

# Full analysis
python main.py --sites sites.txt --render-js --ai --lang en
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--sites`, `-s` | Path to sites.txt file (required) |
| `--render-js` | Enable JavaScript rendering |
| `--ai` | Enable AI-powered analysis |
| `--lang` | Report language: `en` or `zh` |
| `--outdir`, `-o` | Output directory (default: output) |
| `--monitor`, `-m` | Enable change detection mode |
| `--timeout`, `-t` | Request timeout in seconds |
| `--verbose`, `-v` | Enable verbose logging |

### Sites File Format

Create a `sites.txt` file with URLs to analyze:

```
# E-commerce sites to analyze
https://www.aloyoga.com
https://www.allbirds.com
https://www.glossier.com
https://www.warbyparker.com
```

## Output

### Generated Reports

| File | Description |
|------|-------------|
| `output/business_report.md` | Executive-level competitive analysis |
| `output/report.md` | Detailed technical report |
| `output/report.csv` | Data export for Excel |

### Business Report Structure

```
1. Executive Summary
   - Key findings
   - Platform landscape
   - Pricing insights
   - Changes detected

2. Market Overview
   - Industry landscape
   - Platform distribution
   - Pricing tiers

3. Competitor Profiles
   - Website & platform
   - Scan history
   - Key metrics
   - AI insights
   - Changes since last scan

4. Comparative Analysis
   - Feature comparison matrix

5. SWOT Analysis
   - Opportunities
   - Threats

6. Strategic Recommendations
   - Immediate actions (0-3 months)
   - Short-term initiatives (3-6 months)
   - Long-term strategy (6-12 months)

7. Appendix
   - Methodology
   - Data quality notes
```

### Sample Output

```markdown
## Executive Summary

**Platform Landscape:** 17 of 25 competitors (68%) use Shopify.

**Pricing:** Average price range is $45-$125. Market spans $5 to $350.

**Shipping:** 48% of competitors offer free shipping.

---

## Competitor Profiles

### aloyoga.com

**Website:** https://www.aloyoga.com | **Platform:** Shopify

**Scan History:** 3 scans (First: 2026-01-10, Latest: 2026-01-13)

**Key Metrics:**
- **Price Range:** $78 - $195 (Median: $136)
- **Shipping:** Free shipping on all orders
- **Returns:** 30 days (free)
- **Marketing:** Popup, Email Capture, Loyalty Program
```

## Legal Compliance

This tool respects website crawling policies through a **Policy Evidence Ladder**:

| Level | Source | Confidence |
|-------|--------|------------|
| ✅ Level 1 | Official policy pages | High |
| ✅ Level 2 | FAQ/Help center | High |
| ⚠️ Level 3 | Product/cart inference | Medium |
| ❌ Level 4 | Blocked by robots.txt | Manual verification needed |

- Respects `robots.txt` by default
- Tracks data source for each extracted value
- Flags items requiring manual verification
- No bypassing of crawl restrictions

## Architecture

```
ecommerce-intel/
├── main.py                 # Main entry point
├── modules/
│   ├── http_client.py      # HTTP client with anti-bot bypass
│   ├── platform_detector.py # E-commerce platform detection
│   ├── product_extractor.py # Product/price extraction
│   ├── policy_extractor.py  # Shipping/returns extraction
│   ├── policy_evidence.py   # Evidence ladder system
│   ├── ai_analyzer.py       # AI-powered analysis
│   ├── business_report.py   # Executive report generator
│   ├── report_writer.py     # Technical report generator
│   ├── snapshot_store.py    # SQLite storage for history
│   └── ...
├── data/
│   └── intel_cache.db      # Scan history database
├── output/
│   ├── business_report.md  # Executive report
│   ├── report.md           # Technical report
│   └── report.csv          # CSV export
└── sites.txt               # URLs to analyze
```

## Anti-Bot Technology

The tool includes advanced anti-bot bypass capabilities:

- **Patchright** - Patched Playwright that bypasses Cloudflare, DataDome
- **Cloudscraper** - Cloudflare challenge solver
- **Stealth Mode** - Real browser fingerprinting

Most e-commerce sites work out of the box. Sites with enterprise-level protection may require manual verification.

## Change Tracking

The tool maintains a SQLite database of all scans, enabling:

```
✓ Completed: aloyoga.com
  📊 Scan #3 for aloyoga.com

Changes Since Last Scan:
- Price range changed from $78-$195 to $75-$198
- Free shipping threshold changed from $100 to $75
```

To preserve scan history when upgrading, copy `data/intel_cache.db` to the new version.

## Configuration

### Environment Variables

```bash
# Optional: Custom Ollama endpoint
export OLLAMA_HOST=http://localhost:11434
```

### Config File (Optional)

Create `config.yaml`:

```yaml
render_js: true
timeout: 30
max_products: 50
max_pages: 20
db_path: data/intel_cache.db
```

## Troubleshooting

### Common Issues

**"Ollama not found"**
```bash
# Install Ollama
brew install ollama  # macOS
# or download from https://ollama.com/download
```

**"Playwright not installed"**
```bash
pip install patchright
patchright install chrome
```

**"SSL Certificate Error"**
- The tool automatically handles SSL errors
- Some sites may require manual verification

**"403 Forbidden"**
- Site has bot protection
- Tool will try fallback methods automatically
- Check `business_report.md` for manual verification notes

### Debug Mode

```bash
python main.py --sites sites.txt --verbose
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Patchright](https://github.com/AhmedSakrr/patchright-python) - Anti-bot browser automation
- [Ollama](https://ollama.com/) - Local AI inference
- [Qwen2.5](https://huggingface.co/Qwen) - AI model for analysis
- Consulting frameworks inspired by McKinsey, BCG, and Bain methodologies

## Disclaimer

This tool is designed for legitimate competitive research purposes. Users are responsible for:
- Complying with websites' Terms of Service
- Respecting robots.txt directives
- Using extracted data ethically and legally

The tool respects robots.txt by default and does not bypass access restrictions.

---

<p align="center">
  Made with ❤️ for cross-border sellers
</p>
