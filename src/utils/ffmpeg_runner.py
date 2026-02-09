import shutil
import subprocess
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class FFmpegRunner:
    """
    Gestionnaire FFmpeg local.
    
    1. Vérifie si 'bin/ffmpeg.exe' existe dans le dossier de l'app.
    2. Sinon, cherche dans le PATH système.
    3. Exécute les commandes via subprocess.
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.local_bin = self.project_root / "bin"
        
        # Détection auto
        self.ffmpeg_path = self._find_executable("ffmpeg")
        self.ffprobe_path = self._find_executable("ffprobe")
        
        if not self.ffmpeg_path:
            logger.warning("⚠️ FFmpeg non trouvé ! Installez ffmpeg.exe dans le dossier 'bin/'")

    def _find_executable(self, name: str) -> str:
        """Trouve l'exécutable local ou système"""
        # Local (Windows)
        local_exe = self.local_bin / f"{name}.exe"
        if local_exe.exists():
            return str(local_exe)
            
        # Système
        system_exe = shutil.which(name)
        if system_exe:
            return system_exe
            
        return None

    def run(self, args: list, cwd=None) -> subprocess.CompletedProcess:
        """Exécute une commande FFmpeg"""
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg non trouvé")
            
        cmd = [self.ffmpeg_path] + args
        
        # Options pour cacher la console sous Windows
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
            
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        
        return subprocess.run(
            cmd,
            cwd=cwd,
            creationflags=creationflags,
            capture_output=True,
            text=True
        )

    def run_ffprobe(self, args: list) -> str:
        """Exécute une commande ffprobe"""
        if not self.ffprobe_path:
            raise RuntimeError("ffprobe non trouvé")
            
        cmd = [self.ffprobe_path] + args
        
        # Options pour cacher la console
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
            
        result = subprocess.run(
            cmd,
            creationflags=creationflags,
            capture_output=True,
            text=True
        )
        return result.stdout
