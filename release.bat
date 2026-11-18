@echo off
chcp 65001 >nul
title Online Subtitle Generator - Automated Release Publisher

echo ============================================================
echo   Online Subtitle Generator - Release Publisher
echo ============================================================
echo.

python scripts\publish_release.py %*

echo.
echo Press any key to exit...
pause >nul
