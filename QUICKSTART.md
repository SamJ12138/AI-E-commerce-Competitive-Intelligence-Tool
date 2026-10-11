# 🚀 Quick Start - One Click Setup

## How to Run (Super Easy!)

### Option 1: Double-Click (Easiest)
1. Extract this ZIP file
2. Double-click **`CLICK_TO_RUN.bat`**
3. Done! The tool will automatically:
   - Install Python (if needed)
   - Set up the environment
   - Install Ollama AI (if not present)
   - Download the Qwen2.5 AI model
   - Run the analysis

### Option 2: PowerShell
1. Extract this ZIP file
2. Right-click in the folder → "Open in Terminal" or "Open PowerShell window here"
3. Run:
   ```powershell
   .\START.ps1
   ```

---

## What Gets Installed Automatically

| Component | Purpose | Size |
|-----------|---------|------|
| Python 3.12 | Core runtime | ~100 MB |
| Python packages | Analysis tools | ~200 MB |
| Ollama | AI runtime | ~200 MB |
| Qwen2.5:7b | AI model | ~4.7 GB |

**Total: ~5.2 GB** (one-time download)

---

## Adding Your Competitor Sites

Edit `sites.txt` and add URLs:
```
https://competitor1.com
https://competitor2.com
https://competitor3.com
```

The tool will prompt you to edit this file on first run.

---

## Options

Run with different options:

```powershell
# Skip AI (faster, no AI insights)
.\START.ps1 -SkipAI

# Enable JavaScript rendering (for dynamic sites)
.\START.ps1 -RenderJS

# Enable change detection
.\START.ps1 -Monitor

# All options
.\START.ps1 -RenderJS -Monitor
```

---

## Output

Reports are saved to the `output/` folder:
- **report.md** - Full analysis with Chinese insights
- **report.csv** - Data for Excel

---

## Requirements

- Windows 10/11
- Internet connection (for first-time setup)
- 8 GB RAM minimum (16 GB recommended for AI)
- 6 GB free disk space

---

## Troubleshooting

### "Windows protected your PC" message
Click "More info" → "Run anyway"

### Script won't run
Right-click `CLICK_TO_RUN.bat` → "Run as administrator"

### AI features not working
The tool works fine without AI - it will use rule-based analysis instead.

---

## Files Overview

```
📁 ecommerce-intel/
├── 🖱️ CLICK_TO_RUN.bat    ← Double-click this!
├── 📜 START.ps1           ← PowerShell script
├── 📝 sites.txt           ← Add your URLs here
├── 📁 output/             ← Reports saved here
└── 📁 modules/            ← Tool code
```
