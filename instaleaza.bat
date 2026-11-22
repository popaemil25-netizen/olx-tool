@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if not exist config.toml copy config.example.toml config.toml
echo.
echo Gata. Ruleaza cauta.bat
pause
