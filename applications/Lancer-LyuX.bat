@echo off
chcp 65001 > nul
cls
echo ===============================================================================
echo            🐧 BIENVENUE SUR LYUX — SYSTÈME LINUX LYCÉE (OPÉRATION MANCHOT)
echo ===============================================================================
echo.
echo [1/2] Ouverture du Portail Web LyuX Hub (Enrôlement Express & 2 Classes)...
start http://localhost:8000
echo.
echo [2/2] Démarrage de la Station de Travail Graphique PyQt6...
python station\src\main.py
pause
