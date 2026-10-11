<#
.SYNOPSIS
    Run the E-commerce Intelligence Tool
.DESCRIPTION
    Activates the virtual environment and runs the analysis tool
.PARAMETER Sites
    Path to sites file (default: sites.txt)
.PARAMETER AI
    Enable AI-powered analysis with Ollama/Qwen2.5
.PARAMETER RenderJS
    Use Playwright for JavaScript rendering (slower but more accurate)
.PARAMETER Monitor
    Enable change detection mode (compare with previous scan)
.PARAMETER Verbose
    Show detailed logging
.PARAMETER OutputDir
    Output directory for reports (default: output)
.EXAMPLE
    .\run.ps1
.EXAMPLE
    .\run.ps1 -AI
.EXAMPLE
    .\run.ps1 -AI -RenderJS -Verbose
#>

param(
    [string]$Sites = "sites.txt",
    [switch]$AI,
    [switch]$RenderJS,
    [switch]$Monitor,
    [switch]$Verbose,
    [string]$OutputDir = "output"
)

$ErrorActionPreference = "Stop"

# Colors
function Write-Step { param($msg) Write-Host "► $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "✗ $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║  E-commerce Competitive Intelligence     ║" -ForegroundColor Blue
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Check if venv exists
if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Err "Virtual environment not found!"
    Write-Host "Run setup.ps1 first: .\setup.ps1" -ForegroundColor Yellow
    exit 1
}

# Check sites file
if (-not (Test-Path $Sites)) {
    Write-Err "Sites file not found: $Sites"
    Write-Host "Create a file with URLs (one per line)" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
Write-Step "Activating virtual environment..."
& .\venv\Scripts\Activate.ps1

# Clean previous output if exists and locked
if (Test-Path "$OutputDir\report.csv") {
    try {
        # Try to open file to check if it's locked
        $file = [System.IO.File]::Open("$OutputDir\report.csv", 'Open', 'Read', 'None')
        $file.Close()
    } catch {
        Write-Warn "Previous report.csv is locked (probably open in Excel)"
        Write-Host "  Removing old files..." -ForegroundColor Gray
        Remove-Item "$OutputDir\report.csv" -Force -ErrorAction SilentlyContinue
        Remove-Item "$OutputDir\report.md" -Force -ErrorAction SilentlyContinue
    }
}

# Build command
$cmd = "python main.py --sites `"$Sites`" --outdir `"$OutputDir`""

if ($AI) {
    $cmd += " --ai"
    Write-Step "AI analysis enabled (Qwen2.5)"
    
    # Check if Ollama is running
    try {
        $ollamaCheck = ollama list 2>&1
        if ($ollamaCheck -match "qwen2.5") {
            Write-Success "Ollama is running with Qwen2.5"
        } else {
            Write-Warn "Qwen2.5 model not found"
            Write-Host "  Run: ollama pull qwen2.5:7b" -ForegroundColor Yellow
        }
    } catch {
        Write-Warn "Ollama not running"
        Write-Host "  Start Ollama first, or run without -AI flag" -ForegroundColor Yellow
    }
}

if ($RenderJS) {
    $cmd += " --render-js"
    Write-Step "JavaScript rendering enabled (Playwright)"
}

if ($Monitor) {
    $cmd += " --monitor"
    Write-Step "Monitor mode enabled (change detection)"
}

if ($Verbose) {
    $cmd += " --verbose"
}

# Count sites
$siteCount = (Get-Content $Sites | Where-Object { $_ -and -not $_.StartsWith('#') }).Count
Write-Step "Analyzing $siteCount sites from $Sites"
Write-Host ""

# Run the tool
Write-Host "Running: $cmd" -ForegroundColor Gray
Write-Host ""

Invoke-Expression $cmd

# Check results
Write-Host ""
if (Test-Path "$OutputDir\report.md") {
    Write-Success "Reports generated!"
    Write-Host ""
    Write-Host "  📄 Markdown: $OutputDir\report.md" -ForegroundColor White
    Write-Host "  📊 CSV:      $OutputDir\report.csv" -ForegroundColor White
    Write-Host ""
    
    # Ask to open report
    $openReport = Read-Host "Open report in browser? (y/n)"
    if ($openReport -eq 'y') {
        # Convert MD to temp HTML and open
        $mdContent = Get-Content "$OutputDir\report.md" -Raw
        Start-Process "$OutputDir\report.md"
    }
} else {
    Write-Err "Report generation failed. Check errors above."
}

Write-Host ""
