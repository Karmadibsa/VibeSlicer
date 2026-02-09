"""
Wrapper FFmpeg robuste pour Windows
Gère les chemins avec espaces et caractères spéciaux
"""
import subprocess
import os
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .logger import logger


@dataclass
class FFmpegResult:
    """Résultat d'une commande FFmpeg"""
    success: bool
    stdout: str
    stderr: str
    returncode: int


class FFmpegRunner:
    """Exécuteur FFmpeg robuste pour Windows"""
    
    def __init__(self, working_dir: Path = None):
        self.working_dir = working_dir or Path.cwd()
    
    def run(self, cmd: List[str], cwd: Path = None, 
            capture_output: bool = True) -> FFmpegResult:
        """
        Exécute une commande FFmpeg
        
        Args:
            cmd: Liste des arguments de la commande
            cwd: Répertoire de travail (défaut: self.working_dir)
            capture_output: Capturer stdout/stderr
            
        Returns:
            FFmpegResult avec les résultats
        """
        cwd = cwd or self.working_dir
        
        logger.debug(f"FFmpeg: {' '.join(cmd)}")
        
        try:
            process = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            result = FFmpegResult(
                success=process.returncode == 0,
                stdout=process.stdout or "",
                stderr=process.stderr or "",
                returncode=process.returncode
            )
            
            if not result.success:
                logger.error(f"FFmpeg failed: {result.stderr[:500]}")
            
            return result
            
        except Exception as e:
            logger.error(f"FFmpeg execution error: {e}")
            return FFmpegResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-1
            )
    
    def get_duration(self, video_path: Path) -> float:
        """Obtient la durée d'une vidéo en secondes"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        result = self.run(cmd)
        if result.success:
            try:
                return float(result.stdout.strip())
            except ValueError:
                pass
        return 0.0
    
    def extract_audio(self, video_path: Path, audio_path: Path) -> bool:
        """Extrait l'audio d'une vidéo"""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(audio_path)
        ]
        return self.run(cmd).success
    
    def detect_silence(self, video_path: Path, 
                       threshold_db: int = -40,
                       min_duration: float = 0.5) -> List[Tuple[float, float]]:
        """
        Détecte les silences dans une vidéo
        
        Returns:
            Liste de tuples (start, end) des segments de PAROLE
        """
        import re
        
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null", "-"
        ]
        
        result = self.run(cmd)
        if not result.success:
            return []
        
        # Parse silence detection output
        silence_starts = []
        silence_ends = []
        
        for line in result.stderr.split('\n'):
            if "silence_start" in line:
                match = re.search(r"silence_start: ([\d.]+)", line)
                if match:
                    silence_starts.append(float(match.group(1)))
            elif "silence_end" in line:
                match = re.search(r"silence_end: ([\d.]+)", line)
                if match:
                    silence_ends.append(float(match.group(1)))
        
        # Get video duration
        video_duration = self.get_duration(video_path)
        
        # Convert silence regions to speech regions
        speech_segments = []
        current_pos = 0.0
        
        for i in range(len(silence_starts)):
            sil_start = silence_starts[i]
            sil_end = silence_ends[i] if i < len(silence_ends) else video_duration
            
            if sil_start > current_pos:
                speech_segments.append((current_pos, sil_start))
            
            current_pos = sil_end
        
        if current_pos < video_duration:
            speech_segments.append((current_pos, video_duration))
        
        return speech_segments
