@echo off
title VibeSlicer - Reel Maker
color 0B

echo =======================================================
echo          LANCEMENT DE VIBE SLICER
echo =======================================================
echo.

:: Vérification de Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas detecte !
    echo Assurez-vous d'avoir installe Python et coche "Add to PATH".
    pause
    exit
)

:: Lancer le script
python reel_maker.py

echo.
echo =======================================================
echo          TRAITEMENT TERMINE
echo =======================================================
pause
