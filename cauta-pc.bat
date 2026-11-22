@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m olx_monitor.search --piata pc- %*
pause
