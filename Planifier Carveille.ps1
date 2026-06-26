# ─────────────────────────────────────────────────────────────────
# Planifier Carveille.ps1
# Enregistre une tâche planifiée Windows qui lance Carveille
# automatiquement chaque matin à l'heure choisie, en admin.
#
# Usage : clic droit → "Exécuter avec PowerShell"
# ─────────────────────────────────────────────────────────────────

$NomTache   = "Carveille - Autorun"
$Dossier    = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatPath    = Join-Path $Dossier "Autorun Carveille.bat"
$Heure      = "09:00"   # ← modifiez l'heure ici si besoin

# Vérifier que le .bat existe
if (-not (Test-Path $BatPath)) {
    Write-Host "[ERREUR] Fichier introuvable : $BatPath" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée pour quitter"
    exit 1
}

Write-Host ""
Write-Host "Configuration de la tâche planifiée :" -ForegroundColor Cyan
Write-Host "  Nom    : $NomTache"
Write-Host "  Heure  : $Heure (tous les jours)"
Write-Host "  Script : $BatPath"
Write-Host "  Compte : SYSTEM (admin, tourne même sans session ouverte)"
Write-Host ""

# Supprimer l'ancienne tâche si elle existe déjà
Unregister-ScheduledTask -TaskName $NomTache -Confirm:$false -ErrorAction SilentlyContinue

# Créer le déclencheur quotidien
$declencheur = New-ScheduledTaskTrigger -Daily -At $Heure

# L'action : cmd.exe lance le .bat (nécessaire pour que %~dp0 fonctionne correctement)
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $Dossier

# Exécution en SYSTEM = admin garanti, pas besoin que l'utilisateur soit connecté
$parametres = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $NomTache `
    -Trigger $declencheur `
    -Action $action `
    -Settings $parametres `
    -RunLevel Highest `
    -User "SYSTEM" `
    -Force | Out-Null

Write-Host "[OK] Tâche '$NomTache' créée avec succès !" -ForegroundColor Green
Write-Host "     Carveille tournera automatiquement tous les jours à $Heure."
Write-Host ""
Write-Host "Logs disponibles dans : $Dossier\db\autorun.log"
Write-Host ""

# Option : lancer immédiatement pour tester
$reponse = Read-Host "Voulez-vous lancer un run de test maintenant ? (o/n)"
if ($reponse -eq "o" -or $reponse -eq "O") {
    Write-Host "Lancement du run de test..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $NomTache
    Write-Host "Run lancé. Consultez $Dossier\db\autorun.log pour suivre la progression."
}

Read-Host "Appuyez sur Entrée pour fermer"
