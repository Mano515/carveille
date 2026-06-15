@echo off
chcp 65001 >nul
title Carveille - Mise a jour

cd /d "%~dp0"

echo.
echo  =========================================
echo    Carveille - Mise a jour
echo  =========================================
echo.

:: Arreter Carveille s'il est en cours (tuer le processus en ecoute sur le port 8765)
echo  Arret de Carveille en cours...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8765 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo  Carveille arrete.
echo.

:: Mise a jour depuis GitHub
echo  Telechargement de la mise a jour...
set GIT_TERMINAL_PROMPT=0
set GIT_ASKPASS=echo
git pull origin master
if errorlevel 1 (
    echo.
    echo  [ERREUR] Mise a jour impossible. Verifiez votre connexion internet.
    pause
    exit /b 1
)

echo.
echo  Mise a jour terminee ! Relancement de Carveille...
echo.
timeout /t 2 /nobreak >nul

start "" "%~dp0Lancer Carveille.bat"
exit
