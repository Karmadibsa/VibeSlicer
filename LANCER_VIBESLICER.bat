@echo off
title VibeSlicer Pro - Reel Maker
color 0B

:: Se placer dans le dossier du .bat (CRITIQUE)
cd /d "%~dp0"

echo =======================================================
echo          LANCEMENT DE VIBE SLICER PRO
echo =======================================================
echo Dossier : %~dp0
echo.

:: Verification de Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas detecte dans le PATH !
    echo Assurez-vous d'avoir installe Python et coche "Add to PATH".
    pause
    exit /b 1
)

echo Python detecte :
python --version
echo.

:: Installation des dependances
echo Installation / Mise a jour des bibliotheques...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERREUR] pip install a echoue. Verifiez votre connexion internet.
    pause
    exit /b 1
)
echo.

:: Forcer PyTorch CPU-only (evite les erreurs c10.dll / CUDA)
echo Verification de PyTorch CPU-only...
python -c "import torch; ok = '+cpu' in torch.__version__; exit(0 if ok else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Version GPU de PyTorch detectee - remplacement par la version CPU...
    pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu
    if %errorlevel% neq 0 (
        echo [WARN] Impossible d'installer PyTorch CPU. La transcription pourrait echouer.
    ) else (
        echo [OK] PyTorch CPU-only installe avec succes.
    )
) else (
    echo [OK] PyTorch CPU-only deja installe.
)
echo.

:: Verifier que PyQt6 est bien installe
python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] PyQt6 n'a pas pu etre installe ou importe.
    echo Essayez manuellement : pip install PyQt6
    pause
    exit /b 1
)

:: Lancer l'interface graphique
echo Lancement de l'interface...
echo.
python gui.py

:: Si on arrive ici avec une erreur, afficher le code
if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] gui.py s'est termine avec une erreur (code %errorlevel%).
    echo Relancez ce .bat depuis un terminal pour voir le detail de l'erreur.
)

echo.
echo =======================================================
echo          VIBESLICER FERME
echo =======================================================
pause
