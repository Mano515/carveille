@echo off
chcp 65001 >nul
title Carveille - Mise a jour

:: Empecher plusieurs instances simultanees
tasklist /fi "WINDOWTITLE eq Carveille - Mise a jour" 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 (
    echo Une mise a jour est deja en cours.
    timeout /t 3 /nobreak >nul
    exit
)

cd /d "%~dp0"

echo.
echo  =========================================
echo    Carveille - Mise a jour
echo  =========================================
echo.

:: Arreter Carveille s'il est en cours
echo  Arret de Carveille en cours...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8765 "') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo  Carveille arrete.
echo.

:: Mise a jour depuis GitHub
echo  Telechargement de la mise a jour...
set GIT_TERMINAL_PROMPT=0
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
