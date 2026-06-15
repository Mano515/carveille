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
    echo  Consultez le fichier "Installer Python.txt" pour les instructions.
    echo.
    pause
    exit /b 1
)

:: Creer l'environnement virtuel si necessaire (premiere utilisation)
if not exist ".venv\Scripts\python.exe" (
    echo  Premiere utilisation - Creation de l'environnement Python...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer l'environnement Python.
        pause
        exit /b 1
    )
    echo  Environnement cree.
    echo.
)

:: Installer / mettre a jour les dependances
echo  Verification des modules Python...
.venv\Scripts\pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERREUR] Impossible d'installer les dependances.
    echo  Verifiez votre connexion internet et relancez.
    pause
    exit /b 1
)
echo  Modules OK.
echo.

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
