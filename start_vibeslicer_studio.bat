@echo off
setlocal

echo ============================================
echo  VibeSlicer Studio v8.0 (Refactored)
echo  Montage Video TikTok/Reels
echo ============================================
echo.

echo 1. Verification des dependances...
if not exist "bin\ffmpeg.exe" (
    echo [INFO] FFmpeg local non trouve dans bin/. Utilisation du systeme...
) else (
    echo [OK] FFmpeg local detecte.
)

REM Vérifier si python-vlc est installé
python -c "import vlc" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Module 'python-vlc' manquant. Tentative d'installation...
    pip install python-vlc
)

echo.
echo 2. Lancement de l'application (main.py)...
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
