# PowerShell Usage Guide for E-commerce Intelligence Tool

This guide provides detailed instructions for running the tool on Windows using PowerShell.

---

## Table of Contents

1. [First-Time Setup](#first-time-setup)
2. [Running the Tool](#running-the-tool)
3. [Enabling AI Analysis](#enabling-ai-analysis)
4. [Common Commands](#common-commands)
5. [Troubleshooting](#troubleshooting)

---

## First-Time Setup

### Step 1: Extract the ZIP File

Right-click `ecommerce-intel-v3.zip` → **Extract All** → Choose location

Or use PowerShell:
```powershell
Expand-Archive -Path ecommerce-intel-v3.zip -DestinationPath C:\Projects\
```

### Step 2: Open PowerShell in the Project Folder

```powershell
cd C:\Projects\ecommerce-intel
```

Or: Open File Explorer → Navigate to folder → Type `powershell` in address bar → Press Enter

### Step 3: Run Setup Script

```powershell
.\setup.ps1
```

**If you get "execution policy" error:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then run `.\setup.ps1` again.

### What Setup Does:
- ✅ Checks Python version (3.10+ required)
- ✅ Creates virtual environment (`venv/`)
- ✅ Installs all Python dependencies
- ✅ Creates `data/` and `output/` folders
- ✅ Optionally sets up Ollama for AI analysis

---

## Running the Tool

### Basic Usage

```powershell
.\run.ps1
```

This will:
1. Activate the virtual environment
2. Read sites from `sites.txt`
3. Analyze each site
4. Generate reports in `output/`

### With Options

```powershell
# Enable AI-powered analysis (requires Ollama)
.\run.ps1 -AI

# Enable JavaScript rendering (for dynamic sites)
.\run.ps1 -RenderJS

# Enable change detection (compare with previous scan)
.\run.ps1 -Monitor

# Show detailed logging
.\run.ps1 -Verbose

# Use different sites file
.\run.ps1 -Sites "my_competitors.txt"

# Change output directory
.\run.ps1 -OutputDir "reports_jan"

# Combine multiple options
.\run.ps1 -AI -RenderJS -Verbose
```

### Manual Run (Without Scripts)

If you prefer running manually:

```powershell
# 1. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 2. Run the tool
python main.py --sites sites.txt

# 3. With options
python main.py --sites sites.txt --ai --render-js --verbose

# 4. Deactivate when done
deactivate
```

---

## Enabling AI Analysis

AI analysis uses **Qwen2.5** (free, runs locally, no API costs).

### Step 1: Install Ollama

1. Go to: https://ollama.com/download
2. Download Windows installer
3. Run installer
4. Ollama starts automatically (check system tray)

### Step 2: Download Qwen2.5 Model

Open PowerShell and run:
```powershell
ollama pull qwen2.5:7b
```

This downloads ~4.7GB. Wait for completion.

### Step 3: Verify Installation

```powershell
ollama list
```

Should show:
```
NAME            ID              SIZE    MODIFIED
qwen2.5:7b      xxxxxxxxx       4.7 GB  Just now
```

### Step 4: Run with AI

```powershell
.\run.ps1 -AI
```

### Using Different AI Models

```powershell
# Larger model (better quality, needs 16GB+ VRAM)
python main.py --sites sites.txt --ai --ai-model qwen2.5:14b

# First pull the model
ollama pull qwen2.5:14b
```

---

## Common Commands

### Adding Sites to Analyze

Edit `sites.txt` with Notepad:
```powershell
notepad sites.txt
```

Add URLs (one per line):
```
https://rastaclat.com
https://allbirds.com
https://gymshark.com
# Lines starting with # are comments
```

### Viewing Reports

```powershell
# Open Markdown report
notepad .\output\report.md

# Open CSV in Excel
start .\output\report.csv

# Open output folder
explorer .\output
```

### Cleaning Up Old Reports

```powershell
Remove-Item .\output\*.md
Remove-Item .\output\*.csv
```

### Updating Dependencies

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade
deactivate
```

### Installing Playwright (for JavaScript-heavy sites)

```powershell
.\venv\Scripts\Activate.ps1
pip install playwright
playwright install chromium
deactivate
```

---

## Troubleshooting

### "execution policy" Error

```
.\setup.ps1 : File cannot be loaded because running scripts is disabled
```

**Fix:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### "python is not recognized"

**Fix:** Install Python from https://www.python.org/downloads/

During installation, **CHECK** ☑️ "Add Python to PATH"

### "Permission denied" on report.csv

**Cause:** File is open in Excel

**Fix:** Close Excel, then run again

Or use different output folder:
```powershell
.\run.ps1 -OutputDir "output2"
```

### "Ollama not running"

**Fix:**
1. Check if Ollama is in system tray (bottom right)
2. If not, start Ollama from Start menu
3. Or run: `ollama serve`

### "Model not found" 

**Fix:**
```powershell
ollama pull qwen2.5:7b
```

### Empty Results / No Products Found

**Cause:** Site uses heavy JavaScript

**Fix:** Enable JavaScript rendering:
```powershell
# First install Playwright
.\venv\Scripts\Activate.ps1
pip install playwright
playwright install chromium
deactivate

# Then run with JS rendering
.\run.ps1 -RenderJS
```

### Timeout Errors

**Fix:** Increase timeout:
```powershell
python main.py --sites sites.txt --timeout 60
```

### SSL Errors

The tool automatically handles SSL errors. If persistent:
```powershell
python main.py --sites sites.txt --ignore-robots
```

---

## Quick Reference

| Task | Command |
|------|---------|
| First-time setup | `.\setup.ps1` |
| Run analysis | `.\run.ps1` |
| Run with AI | `.\run.ps1 -AI` |
| Run with JS rendering | `.\run.ps1 -RenderJS` |
| Run all features | `.\run.ps1 -AI -RenderJS -Verbose` |
| Edit sites | `notepad sites.txt` |
| View report | `notepad .\output\report.md` |
| Open in Excel | `start .\output\report.csv` |
| Pull AI model | `ollama pull qwen2.5:7b` |
| Check AI models | `ollama list` |

---

## File Locations

```
ecommerce-intel/
├── setup.ps1          # Run once to set up
├── run.ps1            # Run to analyze sites
├── sites.txt          # Add your URLs here
├── output/
│   ├── report.md      # Main report (Chinese insights)
│   └── report.csv     # Data export for Excel
├── data/
│   └── intel_cache.db # Stored snapshots for change detection
└── venv/              # Python virtual environment
```

---

## Getting Help

```powershell
# Show all command options
python main.py --help

# Show run.ps1 options
Get-Help .\run.ps1 -Detailed
```
