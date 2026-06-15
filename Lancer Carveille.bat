@echo off
chcp 65001 >nul
title Carveille - Veille Automobile

cd /d "%~dp0"

echo.
echo  =========================================
echo    Carveille - Veille Automobile
echo  =========================================
echo.

:: Verifier que Python est installe
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python n'est pas installe sur cet ordinateur.
    echo.
    echo  Installez Python depuis : https://www.python.org/downloads/
    echo  Cochez bien "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)

:: Creer l'environnement virtuel si necessaire (premiere utilisation)
if not exist ".venv\Scripts\python.exe" (
    echo  Premiere utilisation - Installation en cours...
    echo  (Cela peut prendre 1 a 2 minutes, merci de patienter)
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer l'environnement Python.
        pause
        exit /b 1
    )
    .venv\Scripts\pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  [ERREUR] Impossible d'installer les dependances.
        pause
        exit /b 1
    )
    echo  Installation terminee !
    echo.
)

echo  Carveille demarre...
echo  Votre navigateur va s'ouvrir automatiquement dans quelques secondes.
echo.
echo  -------------------------------------------
echo  IMPORTANT : Laissez cette fenetre ouverte
echo  pendant toute votre utilisation de Carveille.
echo  Pour fermer Carveille, fermez cette fenetre.
echo  -------------------------------------------
echo.

.venv\Scripts\python main.py ui

echo.
echo  Carveille est arrete. Vous pouvez fermer cette fenetre.
pause
