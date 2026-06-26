@echo off
:: ─────────────────────────────────────────────────────────────────
:: Autorun Carveille.bat
:: Lance Carveille en mode automatique : scrape toutes les recherches
:: et s'arrête tout seul quand c'est terminé.
:: Conçu pour être appelé par le Planificateur de tâches Windows.
:: NE PAS double-cliquer pour une utilisation normale → utiliser
:: "Lancer Carveille.bat" à la place.
:: ─────────────────────────────────────────────────────────────────

chcp 65001 >nul
title Carveille - Run automatique

cd /d "%~dp0"

:: Logs horodatés dans db\autorun.log
set LOGFILE=%~dp0db\autorun.log
echo. >> "%LOGFILE%"
echo =============================== >> "%LOGFILE%"
echo [%DATE% %TIME%] Autorun démarré >> "%LOGFILE%"
echo =============================== >> "%LOGFILE%"

:: Vérifier que l'environnement virtuel existe
if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement Python manquant. Lancez "Lancer Carveille.bat" une fois d'abord.
    echo [%DATE% %TIME%] ERREUR: .venv absent >> "%LOGFILE%"
    exit /b 1
)

:: PYTHONUTF8=1 : force UTF-8 sur stdout/stderr (évite les erreurs 'charmap' sur Windows)
:: -u            : stdout non-bufférisé → logs en temps réel dans le fichier
set PYTHONUTF8=1
.venv\Scripts\python -u main.py --autorun >> "%LOGFILE%" 2>&1

echo [%DATE% %TIME%] Autorun terminé >> "%LOGFILE%"
