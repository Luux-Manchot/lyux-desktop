# Launcher PowerShell pour LyuX
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "         BIENVENUE SUR LYUX - SYSTEME LINUX LYCEE (OPERATION MANCHOT)" -ForegroundColor Yellow
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[1/2] Ouverture du Portail Web LyuX Hub..." -ForegroundColor Green
Start-Process "http://localhost:8000"
Write-Host ""
Write-Host "[2/2] Lancement de l'Application Bureau PyQt6..." -ForegroundColor Green
python $PSScriptRoot/station/src/main.py
