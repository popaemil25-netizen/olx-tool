@echo off
rem Scoate pornirea automata a uneltei la pornirea Windows.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item ([Environment]::GetFolderPath('Startup')+'\OLX-cautare-auto.lnk') -ErrorAction SilentlyContinue"
echo Pornirea automata a fost scoasa. Daca bucla ruleaza acum, inchide fereastra ei.
pause
