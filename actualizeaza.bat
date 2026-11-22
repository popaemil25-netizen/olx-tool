@echo off
rem Aduce ultimele modificari ale uneltei din depozitul GitHub (config.toml si baza de date NU se ating).
chcp 65001 >nul
cd /d "%~dp0"
git pull --ff-only
if errorlevel 1 (echo.& echo Actualizarea a esuat. Verifica mesajul de mai sus.& pause & exit /b 1)
python -m pip install -q -r requirements.txt
echo.
echo Gata, unealta este la zi.
pause
