@echo off
title VibeSlicer Studio v2.0
cls
echo.
echo  ============================================
echo   VibeSlicer Studio v2.0
echo   Automatisation Montage Video TikTok/Reels
echo  ============================================
echo.
echo  Lancement de l'application...
echo.

python app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERREUR] L'application n'a pas pu demarrer.
    echo  Verifiez que Python est installe et les dependances aussi.
    echo.
    echo  Pour installer les dependances : pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo  Application fermee.
pause
