@echo off
:: ============================================
:: E-commerce Intelligence Tool - One Click Launcher
:: Just double-click this file to run everything!
:: ============================================

title E-commerce Competitive Intelligence Tool

echo.
echo   ========================================
echo   E-commerce Competitive Intelligence
echo   One-Click Launcher (with JavaScript Rendering)
echo   ========================================
echo.

:: Run PowerShell with bypass execution policy and RenderJS enabled
powershell -ExecutionPolicy Bypass -File "%~dp0START.ps1" -RenderJS %*

:: Keep window open if there was an error
if errorlevel 1 (
    echo.
    echo   Something went wrong. Check the errors above.
    pause
)
