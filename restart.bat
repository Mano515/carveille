@echo off
:: Tue le processus Python de Carveille s'il tourne
taskkill /f /im python.exe /fi "WINDOWTITLE eq Carveille*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Carveille*" >nul 2>&1

:: Relance Carveille dans une nouvelle fenetre
start "Carveille" /d "%~dp0" ".venv\Scripts\python.exe" -u main.py ui

echo [OK] Carveille relance.
