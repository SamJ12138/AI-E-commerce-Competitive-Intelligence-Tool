<#
.SYNOPSIS
    One-Click E-commerce Intelligence Tool - Complete Auto-Setup and Run
.DESCRIPTION
    This single script handles EVERYTHING automatically:
    - Checks/installs Python
    - Creates virtual environment
    - Installs all dependencies
    - Downloads and installs Ollama
    - Pulls the Qwen2.5 AI model
    - Runs the analysis
    
    Just double-click CLICK_TO_RUN.bat or run: powershell -ExecutionPolicy Bypass -File START.ps1
.NOTES
    No manual steps required!
#>

param(
    [switch]$SkipAI,
    [switch]$RenderJS,
    [switch]$Monitor,
    [switch]$Verbose,
    [string]$Sites = "sites.txt",
    [ValidateSet("en", "zh")]
    [string]$Lang = ""
)

# ============================================
# CONFIGURATION
# ============================================
$ErrorActionPreference = "Continue"
$ProgressPreference = "Continue"

$PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
$OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
$AI_MODEL = "qwen2.5:7b"

# ============================================
# HELPER FUNCTIONS
# ============================================
function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "                                                              " -ForegroundColor Cyan
    Write-Host "    E-commerce Competitive Intelligence Tool                  " -ForegroundColor Cyan
    Write-Host "    AI-Powered Analysis for Cross-Border Sellers              " -ForegroundColor Cyan
    Write-Host "                                                              " -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "  [$Step] $Message" -ForegroundColor Yellow
}

function Write-SubStep {
    param([string]$Message)
    Write-Host "       $Message" -ForegroundColor Gray
}

function Write-Success {
    param([string]$Message)
    Write-Host "       [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "       [!] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "       [X] $Message" -ForegroundColor Red
}

function Get-PythonVersion {
    try {
        $version = python --version 2>&1
        if ($version -match "Python (\d+)\.(\d+)\.(\d+)") {
            return @{
                Major = [int]$matches[1]
                Minor = [int]$matches[2]
                Patch = [int]$matches[3]
                VersionString = $version
            }
        }
    } catch {
        # Python not found
    }
    return $null
}

function Test-PythonInstalled {
    $pyVer = Get-PythonVersion
    if ($pyVer -and $pyVer.Major -ge 3 -and $pyVer.Minor -ge 10) {
        return $true
    }
    return $false
}

function Test-OllamaInstalled {
    try {
        $result = ollama --version 2>&1
        if ($result -match "ollama") {
            return $true
        }
    } catch {
        # Ollama not found
    }
    return $false
}

function Test-OllamaRunning {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            return $true
        }
    } catch {
        # Ollama not running
    }
    return $false
}

function Test-ModelAvailable {
    param([string]$ModelName)
    try {
        $models = ollama list 2>&1
        if ($models -match $ModelName) {
            return $true
        }
    } catch {
        # Error checking models
    }
    return $false
}

function Install-Python {
    Write-SubStep "Downloading Python installer..."
    $installerPath = "$env:TEMP\python_installer.exe"
    
    try {
        Invoke-WebRequest -Uri $PYTHON_INSTALLER_URL -OutFile $installerPath -UseBasicParsing
        Write-SubStep "Installing Python (this may take a minute)..."
        
        Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait
        
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
        
        Start-Sleep -Seconds 2
        if (Test-PythonInstalled) {
            Write-Success "Python installed successfully"
            return $true
        }
    } catch {
        Write-Err "Failed to install Python: $_"
    }
    return $false
}

function Install-Ollama {
    Write-SubStep "Downloading Ollama installer..."
    $installerPath = "$env:TEMP\OllamaSetup.exe"
    
    try {
        Invoke-WebRequest -Uri $OLLAMA_INSTALLER_URL -OutFile $installerPath -UseBasicParsing
        Write-SubStep "Installing Ollama..."
        
        Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait
        
        Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
        
        Start-Sleep -Seconds 3
        
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        Write-Success "Ollama installed"
        return $true
    } catch {
        Write-Err "Failed to install Ollama: $_"
        return $false
    }
}

function Start-OllamaService {
    Write-SubStep "Starting Ollama service..."
    
    try {
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        
        $maxWait = 30
        $waited = 0
        while ((-not (Test-OllamaRunning)) -and ($waited -lt $maxWait)) {
            Start-Sleep -Seconds 1
            $waited++
        }
        
        if (Test-OllamaRunning) {
            Write-Success "Ollama service started"
            return $true
        }
    } catch {
        Write-Warn "Could not start Ollama service"
    }
    return $false
}

function Pull-AIModel {
    param([string]$ModelName)
    
    Write-SubStep "Downloading AI model: $ModelName"
    Write-SubStep "Model size: ~4.7 GB - this may take several minutes..."
    
    try {
        $process = Start-Process -FilePath "ollama" -ArgumentList "pull", $ModelName -Wait -PassThru -NoNewWindow
        
        if ($process.ExitCode -eq 0) {
            Write-Success "AI model downloaded successfully"
            return $true
        }
    } catch {
        Write-Err "Failed to download model: $_"
    }
    return $false
}

# ============================================
# MAIN SCRIPT
# ============================================

Write-Banner

# Determine project directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = $ScriptDir

# Change to project directory
Set-Location $ProjectDir
Write-Host "  Working directory: $ProjectDir" -ForegroundColor Gray
Write-Host ""

# ============================================
# STEP 1: Check/Install Python
# ============================================
Write-Step "1/7" "Checking Python installation..."

if (Test-PythonInstalled) {
    $pyVer = Get-PythonVersion
    Write-Success "Python $($pyVer.VersionString) found"
} else {
    Write-Warn "Python 3.10+ not found"
    Write-SubStep "Installing Python automatically..."
    
    $installed = Install-Python
    if (-not $installed) {
        Write-Err "Could not install Python automatically"
        Write-Host ""
        Write-Host "  Please install Python manually from: https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "  Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "  Press Enter after installing Python to continue"
        
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        if (-not (Test-PythonInstalled)) {
            Write-Err "Python still not detected. Please restart this script."
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
}

# ============================================
# STEP 2: Create Virtual Environment
# ============================================
Write-Step "2/7" "Setting up Python environment..."

if (-not (Test-Path "venv")) {
    Write-SubStep "Creating virtual environment..."
    python -m venv venv
    Write-Success "Virtual environment created"
} else {
    Write-Success "Virtual environment exists"
}

# Activate venv
Write-SubStep "Activating environment..."
& .\venv\Scripts\Activate.ps1
Write-Success "Environment activated"

# ============================================
# STEP 3: Install Python Dependencies
# ============================================
Write-Step "3/7" "Installing Python dependencies..."

Write-SubStep "Upgrading pip..."
python -m pip install --upgrade pip --quiet 2>$null

Write-SubStep "Installing packages (this may take 1-2 minutes)..."
pip install -r requirements.txt --quiet 2>$null
Write-Success "Dependencies installed"

# ============================================
# STEP 4: Create Directories
# ============================================
Write-Step "4/7" "Creating directories..."

if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Force -Path "data" | Out-Null
}
if (-not (Test-Path "output")) {
    New-Item -ItemType Directory -Force -Path "output" | Out-Null
}
Write-Success "Directories ready"

# ============================================
# STEP 5: Setup AI (Ollama + Qwen)
# ============================================
if (-not $SkipAI) {
    Write-Step "5/7" "Setting up AI analysis..."
    
    # Check/Install Ollama
    if (-not (Test-OllamaInstalled)) {
        Write-SubStep "Ollama not found, installing..."
        $ollamaInstalled = Install-Ollama
        if (-not $ollamaInstalled) {
            Write-Warn "Could not install Ollama automatically"
            Write-SubStep "AI features will be disabled."
            $SkipAI = $true
        }
    } else {
        Write-Success "Ollama is installed"
    }
    
    if (-not $SkipAI) {
        # Start Ollama service if not running
        if (-not (Test-OllamaRunning)) {
            $started = Start-OllamaService
            if (-not $started) {
                Write-Warn "Ollama service not running, AI disabled"
                $SkipAI = $true
            }
        } else {
            Write-Success "Ollama service is running"
        }
    }
    
    if (-not $SkipAI) {
        # Check if model is available
        if (-not (Test-ModelAvailable $AI_MODEL)) {
            Write-SubStep "AI model not found, downloading..."
            $modelPulled = Pull-AIModel $AI_MODEL
            if (-not $modelPulled) {
                Write-Warn "Could not download AI model"
                Write-SubStep "Run later: ollama pull $AI_MODEL"
                $SkipAI = $true
            }
        } else {
            Write-Success "AI model $AI_MODEL is ready"
        }
    }
} else {
    Write-Step "5/7" "Skipping AI setup (--SkipAI flag)"
}

# ============================================
# STEP 6: Install Patchright for Anti-Bot Bypass
# ============================================
if ($RenderJS) {
    Write-Step "6/7" "Installing Patchright for JavaScript rendering..."
    Write-SubStep "Patchright bypasses Cloudflare, DataDome, and other bot detection"
    
    # Install Patchright (patched Playwright that bypasses bot detection)
    pip install patchright --quiet 2>$null
    patchright install chrome 2>$null
    Write-Success "Patchright installed"
    
    # Install cloudscraper as fallback
    pip install cloudscraper --quiet 2>$null
    Write-SubStep "Cloudscraper fallback installed"
} else {
    Write-Step "6/7" "Skipping Patchright (use -RenderJS to enable)"
}

# ============================================
# STEP 7: Check Sites File
# ============================================
Write-Step "7/7" "Checking sites configuration..."

$SitesPath = Join-Path $ProjectDir $Sites
if (-not (Test-Path $SitesPath)) {
    Write-Warn "Sites file not found: $Sites"
    Write-SubStep "Creating sample sites.txt..."
    
    $sampleContent = @"
# E-commerce Sites to Analyze
# Add URLs below (one per line)
# Lines starting with # are comments

https://rastaclat.com
https://allbirds.com

# Add your competitor sites here:

"@
    $sampleContent | Out-File -FilePath $SitesPath -Encoding UTF8
    
    Write-Success "Created sample sites.txt"
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Yellow
    Write-Host "  IMPORTANT: Edit sites.txt to add your competitor URLs!" -ForegroundColor Yellow
    Write-Host "  ============================================================" -ForegroundColor Yellow
    Write-Host ""
    
    $editNow = Read-Host "  Open sites.txt to edit now? (y/n)"
    if ($editNow -eq 'y') {
        Start-Process notepad $SitesPath -Wait
    }
} else {
    $siteCount = (Get-Content $SitesPath | Where-Object { $_ -and (-not $_.StartsWith('#')) }).Count
    Write-Success "Found $siteCount sites in $Sites"
}

# ============================================
# SETUP COMPLETE - RUN ANALYSIS
# ============================================
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "            SETUP COMPLETE - STARTING ANALYSIS                " -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

# ============================================
# Language Selection
# ============================================
if (-not $Lang) {
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "             SELECT REPORT LANGUAGE                           " -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  [1] English (英文报告)" -ForegroundColor White
    Write-Host "  [2] Chinese 中文 (默认)" -ForegroundColor White
    Write-Host ""
    $langChoice = Read-Host "  Select language (1 or 2) [default: 2]"
    
    switch ($langChoice) {
        "1" { $Lang = "en"; Write-Host "  Selected: English" -ForegroundColor Green }
        "en" { $Lang = "en"; Write-Host "  Selected: English" -ForegroundColor Green }
        "EN" { $Lang = "en"; Write-Host "  Selected: English" -ForegroundColor Green }
        default { $Lang = "zh"; Write-Host "  Selected: 中文 (Chinese)" -ForegroundColor Green }
    }
    Write-Host ""
}

# Build command
$cmd = "python main.py --sites `"$Sites`" --lang $Lang"

$aiEnabled = $false
if ((-not $SkipAI) -and (Test-OllamaRunning)) {
    $cmd += " --ai"
    $aiEnabled = $true
    Write-Host "  [AI] AI Analysis: ENABLED (Qwen2.5)" -ForegroundColor Cyan
} else {
    Write-Host "  [AI] AI Analysis: DISABLED" -ForegroundColor Gray
}

if ($RenderJS) {
    $cmd += " --render-js"
    Write-Host "  [JS] JavaScript Rendering: ENABLED" -ForegroundColor Cyan
}

if ($Monitor) {
    $cmd += " --monitor"
    Write-Host "  [MON] Change Detection: ENABLED" -ForegroundColor Cyan
}

if ($Verbose) {
    $cmd += " --verbose"
}

$langDisplay = if ($Lang -eq "en") { "English" } else { "Chinese (中文)" }
Write-Host "  [LANG] Report Language: $langDisplay" -ForegroundColor Cyan

Write-Host ""
Write-Host "  Running: $cmd" -ForegroundColor Gray
Write-Host ""
Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray

# Run the analysis
Invoke-Expression $cmd

Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# ============================================
# SHOW RESULTS
# ============================================
$mdReport = Join-Path $ProjectDir "output\report.md"
$csvReport = Join-Path $ProjectDir "output\report.csv"

if (Test-Path $mdReport) {
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "                   ANALYSIS COMPLETE!                         " -ForegroundColor Green
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Reports generated:" -ForegroundColor White
    Write-Host "     Markdown:        $mdReport" -ForegroundColor Gray
    Write-Host "     CSV:             $csvReport" -ForegroundColor Gray
    
    $businessReport = Join-Path $WorkDir "output\business_report.md"
    if (Test-Path $businessReport) {
        Write-Host "     Business Report: $businessReport" -ForegroundColor Cyan
    }
    Write-Host ""
    
    $openReport = Read-Host "  Open report now? (y/n)"
    if ($openReport -eq 'y') {
        if (Test-Path $businessReport) {
            Start-Process $businessReport
        } else {
            Start-Process $mdReport
        }
    }
    
    $openCsv = Read-Host "  Open CSV in Excel? (y/n)"
    if ($openCsv -eq 'y') {
        Start-Process $csvReport
    }
} else {
    Write-Host "  [!] No report generated. Check errors above." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  To run again: .\START.ps1" -ForegroundColor Gray
Write-Host "  To skip AI: .\START.ps1 -SkipAI" -ForegroundColor Gray
Write-Host "  With English reports: .\START.ps1 -Lang en" -ForegroundColor Gray
Write-Host "  ------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Read-Host "  Press Enter to exit"
