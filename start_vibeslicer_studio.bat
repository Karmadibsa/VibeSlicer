@echo off
setlocal

echo ============================================
echo  VibeSlicer Studio - Montage Video Auto
echo ============================================
echo.

python main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] L'application a plante.
    pause
) else (
    echo.
    echo [OK] Fin normale.
    pause
)
