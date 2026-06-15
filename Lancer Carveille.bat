@echo off
chcp 65001 >nul
title Carveille - Veille Automobile

cd /d "%~dp0"

echo.
echo  =========================================
echo    Carveille - Veille Automobile
echo  =========================================
echo.
echo  Dossier courant : %CD%
echo.
pause

echo  [1/5] Verification de Python...
python --version
if errorlevel 1 (
    echo  [ERREUR] Python introuvable dans le PATH.
    pause
    exit /b 1
)
echo  Python OK.
pause

echo  [2/5] Verification de Git...
git --version
if errorlevel 1 (
    echo  [INFO] Git non installe, mise a jour ignoree.
) else (
    echo  Git OK. Tentative de mise a jour...
    git -c credential.helper= pull --no-rebase origin master
    echo  Fin git pull (code : %ERRORLEVEL%)
)
pause

echo  [3/5] Verification de l'environnement Python (.venv)...
if not exist ".venv\Scripts\python.exe" (
    echo  Creation du .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer le .venv.
        pause
        exit /b 1
    )
    echo  .venv cree.
) else (
    echo  .venv deja present.
)
pause

echo  [4/5] Installation des dependances...
.venv\Scripts\pip install -r requirements.txt --disable-pip-version-check
echo  Fin pip install (code : %ERRORLEVEL%)
pause

echo  [5/5] Lancement de Carveille...
echo.
.venv\Scripts\python main.py ui

echo.
echo  Carveille arrete.
pause
