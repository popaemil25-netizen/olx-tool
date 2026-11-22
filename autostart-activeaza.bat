@echo off
rem Pune cautarea automata la pornirea Windows (scurtatura in folderul Startup, fara drepturi de administrator).
rem Ruleaza-l O SINGURA DATA, din folderul uneltei. Pentru a opri pornirea automata: autostart-opreste.bat
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=(Get-Location).Path; $s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\OLX-cautare-auto.lnk');" ^
  "$s.TargetPath='cmd.exe'; $s.Arguments='/c timeout /t 30 /nobreak >nul & call cauta-auto.bat'; $s.WorkingDirectory=$d; $s.WindowStyle=7; $s.Save()"
if errorlevel 1 (echo Eroare la crearea scurtaturii. & pause & exit /b 1)
echo Gata: cautarea automata va porni singura la fiecare pornire a Windows (dupa ~30 secunde, ca sa existe internet).
echo Folder unealta: %cd%
echo Pornirea merge doar dupa ce te loghezi in Windows. Jurnal: cauta-auto.log
pause
