@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Easy Reels Generator Windows Build

echo.
echo Easy Reels Generator by ProAI
echo Portable Windows build
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\build-portable.ps1"
if errorlevel 1 (
    echo.
    echo Build failed. Keep this window open and take a screenshot of the error.
    pause
    exit /b 1
)

echo.
echo Done. The final ZIP is in the artifacts\windows folder.
pause
