#!/bin/bash
# ============================================================
#   E-commerce Intelligence Tool - macOS Double-Click Launcher
#   
#   HOW TO USE:
#   1. Double-click this file in Finder
#   2. If prompted about security, go to:
#      System Preferences > Privacy & Security > Allow
#   
#   FIRST TIME SETUP:
#   Right-click this file > Open > Open (to bypass Gatekeeper)
# ============================================================

# Change to script directory
cd "$(dirname "$0")"

# Make START.sh executable if needed
chmod +x START.sh 2>/dev/null

# Run the main script with interactive mode
./START.sh --render-js --ai

# Keep terminal open
echo ""
read -p "Press Enter to close..."
