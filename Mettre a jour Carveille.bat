@echo off
chcp 65001 >nul
title Carveille - Mise a jour

cd /d "%~dp0"

echo.
echo  =========================================
echo    Carveille - Mise a jour
echo  =========================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Git n'est pas installe.
    echo  Consultez le fichier "Installer Git.txt".
    pause
    exit /b 1
)

echo  Telechargement de la mise a jour...
set GIT_TERMINAL_PROMPT=0
git pull origin master
if errorlevel 1 (
    echo.
    echo  [ERREUR] Mise a jour impossible.
    echo  Verifiez votre connexion internet.
) else (
    echo.
    echo  Carveille est a jour !
    echo  Vous pouvez maintenant lancer "Lancer Carveille.bat".
)

echo.
pause
