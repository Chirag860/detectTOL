@echo off
rem Double-click to install detectTOL for this Windows user (see install.ps1 for what it does).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
