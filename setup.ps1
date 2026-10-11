<# 
.SYNOPSIS
    One-time setup script for E-commerce Intelligence Tool
.DESCRIPTION
    This script sets up the Python virtual environment, installs all dependencies,
    and optionally installs AI components (Ollama + Qwen2.5)
.NOTES
    Run this once after extracting the project
#>

param(
    [switch]$SkipAI,
    [switch]$InstallPlaywright
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  E-commerce Intelligence Tool Setup   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "[1/6] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -ge 3 -and $minor -ge 10) {
            Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Python 3.10+ required. Found: $pythonVersion" -ForegroundColor Red
            Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
            exit 1
        }
    }
} catch {
    Write-Host "  ✗ Python not found. Please install Python 3.10+" -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Create virtual environment
Write-Host ""
Write-Host "[2/6] Creating virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  Virtual environment already exists" -ForegroundColor Gray
} else {
    python -m venv venv
    Write-Host "  ✓ Created venv/" -ForegroundColor Green
}

# Activate virtual environment
Write-Host ""
Write-Host "[3/6] Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
Write-Host "  ✓ Activated" -ForegroundColor Green

# Upgrade pip
Write-Host ""
Write-Host "[4/6] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
Write-Host "  ✓ pip upgraded" -ForegroundColor Green

# Install requirements
Write-Host ""
Write-Host "[5/6] Installing Python dependencies..." -ForegroundColor Yellow
Write-Host "  This may take a few minutes..." -ForegroundColor Gray
pip install -r requirements.txt --quiet
Write-Host "  ✓ Core dependencies installed" -ForegroundColor Green

# Optional: Install browser automation for JS rendering
if ($InstallPlaywright) {
    Write-Host ""
    Write-Host "[5b] Installing Patchright for anti-bot bypass..." -ForegroundColor Yellow
    Write-Host "  Patchright is a patched Playwright that bypasses Cloudflare/DataDome" -ForegroundColor Gray
    
    # Install Patchright (preferred) - bypasses bot detection
    pip install patchright --quiet
    patchright install chrome
    Write-Host "  ✓ Patchright installed (anti-bot enabled)" -ForegroundColor Green
    
    # Also install cloudscraper as fallback
    pip install cloudscraper --quiet
    Write-Host "  ✓ Cloudscraper installed (Cloudflare fallback)" -ForegroundColor Green
}

# Create directories
Write-Host ""
Write-Host "[6/6] Creating directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "data" | Out-Null
New-Item -ItemType Directory -Force -Path "output" | Out-Null
Write-Host "  ✓ Created data/ and output/" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Core Setup Complete!                 " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# AI Setup (optional)
if (-not $SkipAI) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  AI Components Setup (Optional)       " -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Check if Ollama is installed
    $ollamaInstalled = $false
    try {
        $ollamaVersion = ollama --version 2>&1
        if ($ollamaVersion -match "ollama") {
            $ollamaInstalled = $true
            Write-Host "  ✓ Ollama is installed" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Ollama not found" -ForegroundColor Yellow
    }
    
    if (-not $ollamaInstalled) {
        Write-Host ""
        Write-Host "  To enable AI-powered analysis:" -ForegroundColor Yellow
        Write-Host "  1. Download Ollama from: https://ollama.com/download" -ForegroundColor White
        Write-Host "  2. Install and run Ollama" -ForegroundColor White
        Write-Host "  3. Run: ollama pull qwen2.5:7b" -ForegroundColor White
        Write-Host ""
        
        $installOllama = Read-Host "  Open Ollama download page? (y/n)"
        if ($installOllama -eq 'y') {
            Start-Process "https://ollama.com/download"
        }
    } else {
        # Check if Qwen model is available
        Write-Host ""
        Write-Host "  Checking for Qwen2.5 model..." -ForegroundColor Yellow
        $models = ollama list 2>&1
        if ($models -match "qwen2.5") {
            Write-Host "  ✓ Qwen2.5 model is available" -ForegroundColor Green
        } else {
            Write-Host "  Qwen2.5 not found. Pulling model..." -ForegroundColor Yellow
            Write-Host "  This downloads ~4.7GB and may take several minutes..." -ForegroundColor Gray
            
            $pullModel = Read-Host "  Download qwen2.5:7b now? (y/n)"
            if ($pullModel -eq 'y') {
                ollama pull qwen2.5:7b
                Write-Host "  ✓ Qwen2.5:7b model downloaded" -ForegroundColor Green
            } else {
                Write-Host "  Skipped. Run 'ollama pull qwen2.5:7b' later to enable AI features" -ForegroundColor Yellow
            }
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!                      " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit sites.txt with URLs to analyze" -ForegroundColor White
Write-Host "  2. Run: .\run.ps1" -ForegroundColor White
Write-Host "     Or:  .\run.ps1 -AI" -ForegroundColor White
Write-Host "     Or:  .\run.ps1 -RenderJS" -ForegroundColor White
Write-Host ""
