#!/bin/bash
# ============================================================
#   E-commerce Competitive Intelligence Tool
#   One-Click Setup & Run Script for macOS/Linux
# ============================================================
#
# USAGE:
#   ./START.sh                    # Run with defaults
#   ./START.sh --render-js        # Enable JavaScript rendering
#   ./START.sh --ai               # Enable AI analysis
#   ./START.sh --render-js --ai   # Enable both
#   ./START.sh --skip-ai          # Skip AI setup
#   ./START.sh --lang en          # English reports
#   ./START.sh --lang zh          # Chinese reports (default)
#   ./START.sh --help             # Show help
#
# ============================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
RENDER_JS=false
USE_AI=false
SKIP_AI=false
SITES_FILE="sites.txt"
LANGUAGE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --render-js|-r)
            RENDER_JS=true
            shift
            ;;
        --ai|-a)
            USE_AI=true
            shift
            ;;
        --skip-ai|-s)
            SKIP_AI=true
            shift
            ;;
        --sites|-f)
            SITES_FILE="$2"
            shift 2
            ;;
        --lang|-l)
            LANGUAGE="$2"
            shift 2
            ;;
        --help|-h)
            echo ""
            echo "E-commerce Competitive Intelligence Tool"
            echo ""
            echo "Usage: ./START.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --render-js, -r    Enable JavaScript rendering (requires Chrome)"
            echo "  --ai, -a           Enable AI-powered analysis (requires Ollama)"
            echo "  --skip-ai, -s      Skip AI setup even if available"
            echo "  --sites, -f FILE   Specify sites file (default: sites.txt)"
            echo "  --lang, -l LANG    Report language: 'en' for English, 'zh' for Chinese"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./START.sh --render-js --ai           # Full analysis"
            echo "  ./START.sh --lang en                  # English reports"
            echo "  ./START.sh -r -a -l en                # Full analysis, English"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Print banner
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}    E-commerce Competitive Intelligence Tool${NC}"
echo -e "${CYAN}    AI-Powered Analysis for Cross-Border Sellers${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Working directory: $SCRIPT_DIR"
echo ""

# ============================================
# STEP 1: Check Python Installation
# ============================================
echo -e "${YELLOW}[1/7] Checking Python installation...${NC}"

if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}     [ERROR] Python not found!${NC}"
    echo "     Please install Python 3.10+ from https://www.python.org/downloads/"
    echo "     Or use Homebrew: brew install python3"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo -e "${GREEN}     [OK] $PYTHON_VERSION found${NC}"

# Check Python version is 3.10+
PYTHON_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    echo -e "${RED}     [ERROR] Python 3.10+ required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi

# ============================================
# STEP 2: Setup Virtual Environment
# ============================================
echo -e "${YELLOW}[2/7] Setting up Python environment...${NC}"

if [ -d "venv" ]; then
    echo "     Virtual environment already exists"
else
    echo "     Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
echo "     Activating environment..."
source venv/bin/activate
echo -e "${GREEN}     [OK] Environment activated${NC}"

# ============================================
# STEP 3: Install Dependencies
# ============================================
echo -e "${YELLOW}[3/7] Installing Python dependencies...${NC}"
echo "     Upgrading pip..."
pip install --upgrade pip --quiet

echo "     Installing packages (this may take 1-2 minutes)..."
pip install -r requirements.txt --quiet 2>/dev/null || pip install -r requirements.txt

echo -e "${GREEN}     [OK] Dependencies installed${NC}"

# ============================================
# STEP 4: Create Directories
# ============================================
echo -e "${YELLOW}[4/7] Creating directories...${NC}"
mkdir -p data output
echo -e "${GREEN}     [OK] Directories ready${NC}"

# ============================================
# STEP 5: Setup AI (Optional)
# ============================================
echo -e "${YELLOW}[5/7] Setting up AI analysis...${NC}"

if [ "$SKIP_AI" = true ]; then
    echo "     Skipping AI setup (--skip-ai flag)"
    USE_AI=false
else
    # Check if Ollama is installed
    if command -v ollama &> /dev/null; then
        echo -e "${GREEN}     [OK] Ollama is installed${NC}"
        
        # Check if Ollama is running
        if curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}     [OK] Ollama service is running${NC}"
            
            # Check if model exists
            if ollama list | grep -q "qwen2.5:7b"; then
                echo -e "${GREEN}     [OK] AI model qwen2.5:7b is ready${NC}"
            else
                echo "     Downloading AI model (this may take a few minutes)..."
                ollama pull qwen2.5:7b
                echo -e "${GREEN}     [OK] AI model downloaded${NC}"
            fi
        else
            echo -e "${YELLOW}     [WARN] Ollama not running. Starting...${NC}"
            ollama serve &> /dev/null &
            sleep 3
            
            if curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
                echo -e "${GREEN}     [OK] Ollama service started${NC}"
            else
                echo -e "${YELLOW}     [WARN] Could not start Ollama. AI analysis disabled.${NC}"
                USE_AI=false
            fi
        fi
    else
        echo -e "${YELLOW}     [WARN] Ollama not installed. AI analysis disabled.${NC}"
        echo "     To enable AI: brew install ollama && ollama pull qwen2.5:7b"
        USE_AI=false
    fi
fi

# ============================================
# STEP 6: Install Browser Automation (Optional)
# ============================================
echo -e "${YELLOW}[6/7] Installing browser automation...${NC}"

if [ "$RENDER_JS" = true ]; then
    echo "     Installing Patchright for anti-bot bypass..."
    pip install patchright --quiet 2>/dev/null || pip install patchright
    
    # Install Chrome browser
    patchright install chrome 2>/dev/null || echo "     Note: Chrome install may require manual setup"
    
    # Also install cloudscraper as fallback
    pip install cloudscraper --quiet 2>/dev/null || pip install cloudscraper
    
    echo -e "${GREEN}     [OK] Browser automation installed${NC}"
else
    echo "     Skipping browser automation (use --render-js to enable)"
fi

# ============================================
# STEP 7: Check Sites File
# ============================================
echo -e "${YELLOW}[7/7] Checking sites configuration...${NC}"

if [ -f "$SITES_FILE" ]; then
    SITE_COUNT=$(grep -v "^#" "$SITES_FILE" | grep -v "^$" | wc -l | tr -d ' ')
    echo -e "${GREEN}     [OK] Found $SITE_COUNT sites in $SITES_FILE${NC}"
else
    echo -e "${YELLOW}     [WARN] Sites file not found: $SITES_FILE${NC}"
    echo "     Creating sample sites.txt..."
    cat > sites.txt << 'EOF'
# E-commerce Sites to Analyze
# Add URLs below (one per line)
# Lines starting with # are comments

https://www.aloyoga.com
https://www.gymshark.com
https://allbirds.com
EOF
    echo -e "${GREEN}     [OK] Created sample sites.txt${NC}"
fi

# ============================================
# Ask for Language Preference
# ============================================
if [ -z "$LANGUAGE" ]; then
    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}           SELECT REPORT LANGUAGE${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""
    echo "  [1] English (英文报告)"
    echo "  [2] Chinese 中文 (默认)"
    echo ""
    read -p "Select language (1 or 2) [default: 2]: " LANG_CHOICE
    
    case $LANG_CHOICE in
        1|en|EN|english|English)
            LANGUAGE="en"
            echo -e "${GREEN}     Selected: English${NC}"
            ;;
        *)
            LANGUAGE="zh"
            echo -e "${GREEN}     Selected: 中文 (Chinese)${NC}"
            ;;
    esac
fi

# ============================================
# Start Analysis
# ============================================
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}          SETUP COMPLETE - STARTING ANALYSIS${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Build command
CMD="$PYTHON_CMD main.py --sites \"$SITES_FILE\" --lang $LANGUAGE"

if [ "$USE_AI" = true ]; then
    CMD="$CMD --ai"
    echo -e "  ${GREEN}[AI]${NC} AI Analysis: ENABLED (Qwen2.5)"
else
    echo -e "  ${YELLOW}[AI]${NC} AI Analysis: DISABLED"
fi

if [ "$RENDER_JS" = true ]; then
    CMD="$CMD --render-js"
    echo -e "  ${GREEN}[JS]${NC} JavaScript Rendering: ENABLED"
else
    echo -e "  ${YELLOW}[JS]${NC} JavaScript Rendering: DISABLED"
fi

echo ""
echo "Running: $CMD"
echo ""
echo "------------------------------------------------------------"
echo ""

# Run the analysis
eval $CMD

# ============================================
# Complete
# ============================================
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${GREEN}                 ANALYSIS COMPLETE!${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "Reports generated:"
echo "   Markdown: $SCRIPT_DIR/output/report.md"
echo "   CSV:      $SCRIPT_DIR/output/report.csv"
echo ""

# Ask to open report
read -p "Open report now? (y/n): " OPEN_REPORT
if [[ $OPEN_REPORT =~ ^[Yy]$ ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open output/report.md
    else
        xdg-open output/report.md 2>/dev/null || echo "Please open output/report.md manually"
    fi
fi

echo ""
echo "------------------------------------------------------------"
echo "To run again: ./START.sh"
echo "Full options: ./START.sh --render-js --ai --lang en"
echo "------------------------------------------------------------"
echo ""
