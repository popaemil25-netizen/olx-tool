@echo off
rem Rulare automata in bucla: cauta, apoi pauza 3 minute, apoi iar cauta. Jurnal in cauta-auto.log
chcp 65001 >nul
cd /d "%~dp0"
:bucla
echo ===== %date% %time% ===== >> cauta-auto.log
python -m olx_monitor.search %* >> cauta-auto.log 2>&1
echo ----- terminat %time%, pauza 3 minute ----- >> cauta-auto.log
ping -n 181 127.0.0.1 >nul
goto bucla
