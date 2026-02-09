"""
Processeur vidéo principal
Gère le nettoyage, découpage, et rendu final
"""
import os
import shutil
import glob
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

from ..utils.logger import logger
from ..utils.ffmpeg_runner import FFmpegRunner
from ..utils.config import app_config


@dataclass
class Segment:
    """Représente un segment de vidéo"""
    start: float
    end: float
    segment_type: str  # 'speech' ou 'silence'
    keep: bool = True
    
    @property
    def duration(self) -> float:
        return self.end - self.start


class VideoProcessor:
    """Traitement vidéo principal"""
    
    def __init__(self, config=None):
        self.config = config or app_config
        self.ffmpeg = FFmpegRunner(self.config.temp_dir)
        
        # Créer les dossiers
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
    
    def sanitize(self, input_path: Path) -> Path:
        """
        Nettoie une vidéo (CFR 30fps, audio 44.1kHz)
        
        Returns:
            Chemin vers la vidéo nettoyée
        """
        input_path = Path(input_path).resolve()
        output_name = f"{input_path.stem}_clean.mp4"
        output_path = self.config.temp_dir / output_name
        
        # Cache: ne pas re-traiter si déjà fait
        if output_path.exists() and output_path.stat().st_size > 1024:
            logger.info(f"Using cached: {output_path.name}")
            return output_path
        
        logger.info(f"Sanitizing: {input_path.name}...")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-r", str(self.config.target_fps),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            str(output_path)
        ]
        
        result = self.ffmpeg.run(cmd)
        if not result.success:
            raise RuntimeError(f"Sanitization failed: {result.stderr[:200]}")
        
        logger.info(f"Sanitized: {output_path.name}")
        return output_path
    
    def analyze_silence(self, video_path: Path, 
                        threshold_db: int = None) -> List[Segment]:
        """
        Analyse les silences et retourne les segments
        
        Returns:
            Liste de Segments (parole et silence)
        """
        threshold = threshold_db or self.config.silence_threshold_db
        
        logger.info(f"Analyzing silence ({threshold}dB)...")
        
        speech_ranges = self.ffmpeg.detect_silence(
            video_path,
            threshold_db=threshold,
            min_duration=self.config.min_silence_duration
        )
        
        # Convertir en segments structurés
        segments = []
        duration = self.ffmpeg.get_duration(video_path)
        last_end = 0.0
        
        for start, end in speech_ranges:
            # Silence avant ce segment de parole
            if start > last_end:
                segments.append(Segment(
                    start=last_end,
                    end=start,
                    segment_type='silence',
                    keep=False
                ))
            
            # Segment de parole
            segments.append(Segment(
                start=start,
                end=end,
                segment_type='speech',
                keep=True
            ))
            
            last_end = end
        
        # Silence final
        if last_end < duration:
            segments.append(Segment(
                start=last_end,
                end=duration,
                segment_type='silence',
                keep=False
            ))
        
        logger.info(f"Found {len(segments)} segments")
        return segments
    
    def cut_segments(self, video_path: Path, 
                     segments: List[Segment]) -> Path:
        """
        Découpe et concatène les segments sélectionnés
        
        Returns:
            Chemin vers la vidéo découpée
        """
        output_path = self.config.temp_dir / "cut_video.mp4"
        concat_file = self.config.temp_dir / "cuts.ffconcat"
        
        # Filtrer les segments à garder
        keep_segments = [(s.start, s.end) for s in segments if s.keep]
        
        if not keep_segments:
            raise ValueError("No segments selected!")
        
        logger.info(f"Cutting {len(keep_segments)} segments...")
        
        # Créer le fichier de concaténation
        video_abs = str(video_path.resolve()).replace("\\", "/")
        
        with open(concat_file, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for start, end in keep_segments:
                f.write(f"file '{video_abs}'\n")
                f.write(f"inpoint {start:.3f}\n")
                f.write(f"outpoint {end:.3f}\n")
        
        # Découper
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-ar", "44100",
            str(output_path)
        ]
        
        result = self.ffmpeg.run(cmd)
        if not result.success:
            raise RuntimeError(f"Cutting failed: {result.stderr[:200]}")
        
        logger.info(f"Cut video: {output_path.name}")
        return output_path
    
    def _copy_fonts_to_temp(self):
        """Copie les polices dans temp/fonts pour éviter les problèmes de chemin"""
        fonts_dir = self.config.temp_dir / "fonts"
        fonts_dir.mkdir(exist_ok=True)
        
        for pattern in ["*.ttf", "*.otf", "*.TTF", "*.OTF"]:
            for font_file in self.config.assets_dir.glob(pattern):
                dest = fonts_dir / font_file.name
                if not dest.exists():
                    shutil.copy2(font_file, dest)
                    logger.debug(f"Copied font: {font_file.name}")
        
        return fonts_dir
    
    def render(self, video_path: Path, 
               ass_path: Path,
               music_path: Path = None,
               output_path: Path = None) -> Path:
        """
        Rendu final avec sous-titres et musique
        
        Args:
            video_path: Vidéo source (dans temp)
            ass_path: Fichier ASS (dans temp)
            music_path: Musique de fond (optionnel)
            output_path: Chemin de sortie
            
        Returns:
            Chemin vers la vidéo finale
        """
        if output_path is None:
            output_path = self.config.output_dir / f"{video_path.stem}_final.mp4"
        
        output_path = Path(output_path).resolve()
        
        # Copier les fonts dans temp pour éviter les chemins avec espaces
        self._copy_fonts_to_temp()
        
        # Noms relatifs (on exécute dans temp_dir)
        vid_rel = video_path.name
        ass_rel = ass_path.name
        
        # Filtre ASS avec chemin relatif
        vf = f"ass={ass_rel}:fontsdir=fonts"
        
        logger.info(f"Rendering to {output_path.name}...")
        
        inputs = ["-i", vid_rel]
        
        if music_path:
            music_abs = str(Path(music_path).resolve())
            inputs.extend(["-i", music_abs])
            
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e9,volume={self.config.background_music_volume}[bgm];"
                f"[0:a][bgm]amix=inputs=2:duration=first[mixed];"
                f"[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[aout];"
                f"[0:v]{vf}[vout]"
            )
            maps = ["-map", "[vout]", "-map", "[aout]"]
        else:
            filter_complex = (
                f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout];"
                f"[0:v]{vf}[vout]"
            )
            maps = ["-map", "[vout]", "-map", "[aout]"]
        
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(maps)
        cmd.extend([
            "-c:v", "libx264",
            "-preset", self.config.video_preset,
            "-crf", str(self.config.video_crf),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(output_path)
        ])
        
        result = self.ffmpeg.run(cmd, cwd=self.config.temp_dir)
        
        if not result.success:
            raise RuntimeError(f"Render failed: {result.stderr[:300]}")
        
        logger.info(f"Rendered: {output_path}")
        return output_path
    
    def get_duration(self, video_path: Path) -> float:
        """Retourne la durée d'une vidéo"""
        return self.ffmpeg.get_duration(video_path)
    
    def cleanup_temp(self):
        """Nettoie les fichiers temporaires"""
        for pattern in ["*.mp4", "*.wav", "*.ass", "*.srt", "*.ffconcat"]:
            for f in self.config.temp_dir.glob(pattern):
                try:
                    f.unlink()
                except:
                    pass
        logger.info("Temp files cleaned")
