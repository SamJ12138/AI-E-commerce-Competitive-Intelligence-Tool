# E-commerce Intelligence Tool v15 - Release Notes

## 🎉 New Features

### 1. macOS/Linux Support (One-Click)
Mac users can now run the tool just as easily as Windows users!

**Files Added:**
- `START.sh` - Main shell script for macOS/Linux
- `CLICK_TO_RUN.command` - Double-click launcher for Finder

**Usage on macOS:**
```bash
# First time: Make executable
chmod +x START.sh CLICK_TO_RUN.command

# Option 1: Double-click CLICK_TO_RUN.command in Finder

# Option 2: Run from Terminal
./START.sh --render-js --ai
```

### 2. Bilingual Reports (English / Chinese)
Reports can now be generated in English or Chinese!

**Interactive Selection:**
When you run the tool, you'll be prompted:
```
SELECT REPORT LANGUAGE
[1] English (英文报告)
[2] Chinese 中文 (默认)
```

**Command Line:**
```bash
# Windows
.\START.ps1 -Lang en

# macOS/Linux  
./START.sh --lang en
```

### 3. Policy Evidence Ladder (Legal Compliance)
New feature that tracks WHERE each piece of policy data comes from, ensuring legal safety and data accuracy.

**Evidence Levels:**
| Level | Status | Source | Confidence |
|-------|--------|--------|------------|
| 1 | ✅ | Official policy page | 95% |
| 2 | ✅ | FAQ/Help Center | 85% |
| 3 | ⚠️ | Product/Cart page | 60% |
| 4 | ❌ | Blocked by robots.txt | Manual verify |

**Report Output:**
```markdown
### 📜 Policy Data Sources

| Policy | Status | Source | Verification |
|--------|--------|--------|--------------|
| Shipping | ✅ | Official policy page | Verified |
| Returns | ⚠️ | Product/cart page | Manual check needed |
```

**Key Benefits:**
- Always know where your data comes from
- Clear verification status for each data point
- Respects robots.txt by default (no bypassing)
- Blocked URLs listed for manual verification

### 4. Reduced Warning Verbosity
Fixed excessive warning messages in the output:
- SSL retry warnings now suppressed
- robots.txt fetch errors now at DEBUG level
- urllib3 connection warnings disabled

## 🔧 Bug Fixes

### Warnings Fixed:
- ❌ `WARNING: Retrying after connection broken by SSLEOFError` - Now silent
- ❌ `WARNING: Failed to fetch robots.txt` - Now at DEBUG level
- ❌ `WARNING: SSL error for X, retrying without verification` - Now at DEBUG level

## 📁 New Files in v15

```
ecommerce-intel-v15/
├── START.sh              # macOS/Linux launcher (NEW)
├── CLICK_TO_RUN.command  # macOS double-click (NEW)
├── modules/
│   ├── policy_evidence.py  # Evidence ladder system (NEW)
│   ├── report_writer.py    # Bilingual + evidence (UPDATED)
│   ├── robots_checker.py   # Tracks blocked URLs (UPDATED)
│   └── models.py           # Evidence tracking fields (UPDATED)
└── README.md               # Full documentation (UPDATED)
```

## 🌍 Platform Support

| Platform | One-Click | Script | Tested |
|----------|-----------|--------|--------|
| Windows 10/11 | ✅ CLICK_TO_RUN.bat | ✅ START.ps1 | ✅ |
| macOS 12+ | ✅ CLICK_TO_RUN.command | ✅ START.sh | ✅ |
| Linux (Ubuntu) | - | ✅ START.sh | ✅ |

## 📝 Command Reference

### Windows PowerShell
```powershell
.\START.ps1                    # Basic run
.\START.ps1 -RenderJS          # With browser automation
.\START.ps1 -AI                # With AI analysis
.\START.ps1 -Lang en           # English reports
.\START.ps1 -RenderJS -AI -Lang en  # Full options
```

### macOS/Linux Terminal
```bash
./START.sh                     # Basic run
./START.sh --render-js         # With browser automation
./START.sh --ai                # With AI analysis
./START.sh --lang en           # English reports
./START.sh --render-js --ai --lang en  # Full options
```

## 🔒 Legal Safety Note

The Policy Evidence Ladder ensures your tool usage is legally defensible:

1. **Respects robots.txt** - Never bypasses crawling restrictions
2. **Clear data provenance** - Every data point shows its source
3. **Manual verification flags** - Low-confidence data marked for human review
4. **No covert scraping** - Uses standard user agents and respects rate limits

When robots.txt blocks a policy page:
- ❌ Tool does NOT bypass the restriction
- ✅ Tool marks data as "blocked" in report
- ✅ Tool lists blocked URLs for manual checking
- ✅ Tool still extracts data from allowed pages (FAQ, product pages)

## 🔄 Upgrade from v14

1. Delete the old `venv` folder
2. Extract v15 to a new folder
3. Run `START.ps1` (Windows) or `START.sh` (macOS)

## 🙏 Feedback

If you encounter any issues, please report them with:
1. Operating system (Windows/macOS/Linux)
2. Python version (`python --version`)
3. Error message or screenshot
