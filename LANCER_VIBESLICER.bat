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

:: Verifier PyTorch (GPU ou CPU, les deux sont supportes)
echo Verification de PyTorch...
python -c "import torch; v=torch.__version__; gpu='GPU' if '+cu' in v else 'CPU'; print(f'[OK] PyTorch {v} ({gpu})')" 2>nul || (
    echo [INFO] PyTorch non installe - installation version CPU...
    pip install torch --index-url https://download.pytorch.org/whl/cpu
)
echo.

:: Detecter le GPU NVIDIA disponible
echo Detection GPU NVIDIA...
python -c "import subprocess,re; r=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=5); print('[GPU] '+r.stdout.strip()) if r.returncode==0 else print('[INFO] Pas de GPU NVIDIA detecte - mode CPU actif')" 2>nul
echo.

:: Verifier que PyQt6 est bien installe
python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] PyQt6 n'a pas pu etre installe ou importe.
    echo Essayez manuellement : pip install PyQt6
    pause
    exit /b 1
)

:: Ajouter torch/lib au PATH AVANT de lancer Python
:: find_spec trouve le chemin SANS importer torch (evite l'oeuf-et-la-poule DLL)
echo Ajout de torch/lib au PATH...
for /f "delims=" %%P in ('python -c "import importlib.util,os; s=importlib.util.find_spec(\"torch\"); locs=list(s.submodule_search_locations) if s and s.submodule_search_locations else []; d=locs[0] if locs else (os.path.dirname(s.origin) if s and s.origin else \"\"); lib=os.path.join(d,\"lib\") if d else \"\"; print(lib if lib and os.path.isdir(lib) else \"\")" 2^>nul') do (
    if not "%%P"=="" set "TORCH_LIB=%%P"
)
if defined TORCH_LIB (
    set "PATH=%TORCH_LIB%;%PATH%"
    echo [OK] torch/lib ajoute au PATH : %TORCH_LIB%
) else (
    echo [WARN] torch/lib introuvable via find_spec
)
echo.

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
