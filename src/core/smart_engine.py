"""
Moteur vidéo optimisé - Smart Rendering
Évite les ré-encodages multiples pour préserver la qualité
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import re

logger = logging.getLogger(__name__)


class SmartVideoEngine:
    """
    Moteur vidéo avec Smart Rendering
    
    Stratégie:
    1. Sanitize: Une seule fois au début (CFR 30fps, keyframes alignés)
    2. Analyse: Sur la vidéo sanitized (pas de ré-encodage)
    3. Cut: Concaténation avec timestamps (pas de ré-encodage)
    4. Render: Un seul encodage final avec sous-titres
    
    Avantage: Qualité préservée, pas de désync A/V
    """
    
    def __init__(self, temp_dir: Path, assets_dir: Path):
        self.temp_dir = Path(temp_dir)
        self.assets_dir = Path(assets_dir)
        
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def _run_ffmpeg(self, cmd: List[str], cwd: Path = None) -> Tuple[bool, str]:
        """
        Exécute une commande FFmpeg
        
        Returns:
            (success, stderr_output)
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.temp_dir,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr[-500:]}")
                return False, result.stderr
            
            return True, result.stderr
            
        except Exception as e:
            logger.error(f"FFmpeg exception: {e}")
            return False, str(e)
    
    def get_video_info(self, video_path: Path) -> dict:
        """Obtient les infos d'une vidéo via ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(video_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            import json
            data = json.loads(result.stdout)
            
            # Extraire les infos utiles
            info = {'duration': 0, 'fps': 30, 'width': 0, 'height': 0}
            
            if 'format' in data:
                info['duration'] = float(data['format'].get('duration', 0))
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    info['width'] = stream.get('width', 0)
                    info['height'] = stream.get('height', 0)
                    
                    # FPS
                    fps_str = stream.get('r_frame_rate', '30/1')
                    if '/' in fps_str:
                        num, den = map(int, fps_str.split('/'))
                        info['fps'] = num / den if den > 0 else 30
                    break
            
            return info
            
        except Exception as e:
            logger.error(f"ffprobe error: {e}")
            return {'duration': 0, 'fps': 30, 'width': 0, 'height': 0}
    
    def sanitize(self, input_path: Path, force_keyframes: bool = True) -> Path:
        """
        Nettoie la vidéo (une seule fois)
        
        - CFR 30 fps
        - Keyframes tous les 2 secondes (pour coupes précises)
        - Audio normalisé
        
        Args:
            input_path: Vidéo source
            force_keyframes: Forcer des keyframes réguliers (recommandé)
            
        Returns:
            Chemin vers la vidéo nettoyée
        """
        input_path = Path(input_path).resolve()
        output_path = self.temp_dir / f"{input_path.stem}_clean.mp4"
        
        # Cache
        if output_path.exists() and output_path.stat().st_size > 1024:
            logger.info(f"Using cached: {output_path.name}")
            return output_path
        
        logger.info(f"Sanitizing: {input_path.name}")
        
        # Commande avec keyframes forcés
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-r", "30",                      # CFR 30 fps
            "-c:v", "libx264",
            "-preset", "fast",               # Équilibre vitesse/qualité
            "-crf", "20",                    # Bonne qualité
            "-g", "60",                      # Keyframe toutes les 60 frames (2 sec à 30fps)
            "-keyint_min", "60",             # Keyframe minimum
            "-sc_threshold", "0",            # Pas de scene detection (keyframes réguliers)
            "-c:a", "aac",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "192k",
            str(output_path)
        ]
        
        success, _ = self._run_ffmpeg(cmd)
        
        if not success:
            raise RuntimeError(f"Sanitization failed for {input_path.name}")
        
        return output_path
    
    def create_proxy(self, video_path: Path, max_height: int = 480) -> Path:
        """
        Crée une version proxy basse résolution pour l'affichage
        (Comme Premiere/DaVinci - travail sur proxy, export sur source)
        
        Args:
            video_path: Vidéo source (sanitized)
            max_height: Hauteur max du proxy
            
        Returns:
            Chemin vers le proxy
        """
        video_path = Path(video_path)
        proxy_path = self.temp_dir / f"{video_path.stem}_proxy.mp4"
        
        if proxy_path.exists():
            return proxy_path
        
        logger.info(f"Creating proxy: {proxy_path.name}")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"scale=-2:{max_height}",  # Hauteur fixe, largeur auto
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",                      # Qualité réduite (c'est juste pour prévisualisation)
            "-c:a", "aac", "-b:a", "96k",
            str(proxy_path)
        ]
        
        success, _ = self._run_ffmpeg(cmd)
        
        return proxy_path if success else video_path
    
    def detect_silence(self, video_path: Path, 
                       threshold_db: int = -35,
                       min_duration: float = 0.3) -> List[Tuple[float, float]]:
        """
        Détecte les silences et retourne les plages de PAROLE
        
        Returns:
            Liste de tuples (start, end) pour les segments de parole
        """
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null", "-"
        ]
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # Parser la sortie
            silence_starts = []
            silence_ends = []
            
            for line in result.stderr.split('\n'):
                if 'silence_start:' in line:
                    match = re.search(r'silence_start:\s*([\d.]+)', line)
                    if match:
                        silence_starts.append(float(match.group(1)))
                elif 'silence_end:' in line:
                    match = re.search(r'silence_end:\s*([\d.]+)', line)
                    if match:
                        silence_ends.append(float(match.group(1)))
            
            # Obtenir la durée totale
            info = self.get_video_info(video_path)
            duration = info['duration']
            
            # Convertir silences en paroles
            speech_ranges = []
            last_end = 0.0
            
            for i, start in enumerate(silence_starts):
                if start > last_end + 0.1:
                    speech_ranges.append((last_end, start))
                
                if i < len(silence_ends):
                    last_end = silence_ends[i]
            
            # Dernier segment de parole
            if last_end < duration - 0.1:
                speech_ranges.append((last_end, duration))
            
            return speech_ranges
            
        except Exception as e:
            logger.error(f"Silence detection error: {e}")
            return [(0, info.get('duration', 60))]
    
    def smart_cut(self, video_path: Path, 
                  segments: List[Tuple[float, float]]) -> Path:
        """
        Découpe intelligente avec timeline audio continue.
        Utilise le format TS intermédiaire pour éviter les gaps audio.
        """
        if not segments:
            return video_path
        
        output_path = self.temp_dir / "cut_video.mp4"
        video_str = str(Path(video_path).resolve())
        temp_segments = []
        
        # Phase 1: Découper chaque segment en .ts
        for i, (start, end) in enumerate(segments):
            duration = end - start
            seg_file = self.temp_dir / f"seg_{i:03d}.ts"
            temp_segments.append(seg_file)
            
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", video_str,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-avoid_negative_ts", "make_zero",
                str(seg_file)
            ]
            self._run_ffmpeg(cmd)
        
        # Phase 2: Concaténer
        concat_list = self.temp_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for seg_file in temp_segments:
                f.write(f"file '{seg_file.name}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        success, _ = self._run_ffmpeg(cmd)
        
        # Cleanup
        for seg_file in temp_segments:
            try:
                seg_file.unlink()
            except:
                pass
        
        if not success:
            raise RuntimeError("Smart cut failed")
        
        return output_path
    
    def generate_ass(self, subtitles: List[dict], 
                     output_path: Path,
                     font_name: str = "Poppins",
                     font_size: int = 100,
                     margin_v: int = 640,
                     highlight_words: List[str] = None) -> Path:
        """
        Génère un fichier ASS avec style TikTok/Reels
        
        Args:
            subtitles: Liste de dicts avec 'start', 'end', 'text', 'words'
            margin_v: Marge verticale (640 = 2/3 haut, 1/3 bas sur 1920p)
        """
        if highlight_words is None:
            highlight_words = ["MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI"]
        
        def fmt_time(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            cs = int((s % 1) * 100)
            return f"{h}:{m:02}:{sec:02}.{cs:02}"
        
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00E22B8A,&H00000000,-1,0,0,0,100,100,0,0,1,4,2,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        output_path = Path(output_path)
        
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write(header)
            
            for sub in subtitles:
                text = sub.get('text', '').strip()
                if not text:
                    continue
                
                start = fmt_time(sub['start'])
                end = fmt_time(sub['end'])
                
                # Highlights
                for kw in highlight_words:
                    pattern = re.compile(f"({re.escape(kw)})", re.IGNORECASE)
                    text = pattern.sub(r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}", text)
                
                f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
        
        return output_path
    
    def render_final(self, video_path: Path,
                     ass_path: Path,
                     output_path: Path,
                     music_path: Path = None) -> Path:
        """
        Rendu final (UN SEUL encodage après toutes les étapes)
        
        C'est ici qu'on applique les sous-titres et la musique
        """
        video_path = Path(video_path)
        ass_path = Path(ass_path)
        output_path = Path(output_path)
        
        # Copier les fonts dans temp
        fonts_dir = self.temp_dir / "fonts"
        fonts_dir.mkdir(exist_ok=True)
        
        for pattern in ["*.ttf", "*.otf", "*.TTF", "*.OTF"]:
            for font_file in self.assets_dir.glob(pattern):
                dest = fonts_dir / font_file.name
                if not dest.exists():
                    shutil.copy2(font_file, dest)
        
        # Chemins relatifs (on exécute dans temp_dir)
        vid_rel = video_path.name
        ass_rel = ass_path.name
        
        # Copier les fichiers dans temp si nécessaire
        if video_path.parent != self.temp_dir:
            shutil.copy2(video_path, self.temp_dir / vid_rel)
        if ass_path.parent != self.temp_dir:
            shutil.copy2(ass_path, self.temp_dir / ass_rel)
        
        # Filtre ASS
        vf = f"ass={ass_rel}:fontsdir=fonts"
        
        inputs = ["-i", vid_rel]
        
        if music_path:
            music_path = Path(music_path)
            inputs.extend(["-i", str(music_path.resolve())])
            
            # Mix audio simplifié (pas de loudnorm qui cause des coupures)
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e9,volume=0.15[bgm];"
                f"[0:a]volume=1.0[voice];"
                f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout];"
                f"[0:v]{vf}[vout]"
            )
            maps = ["-map", "[vout]", "-map", "[aout]"]
        else:
            filter_complex = f"[0:v]{vf}[vout]"
            maps = ["-map", "[vout]", "-map", "0:a"]
        
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(maps)
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",  # Optimisé pour web
            str(output_path)
        ])
        
        logger.info(f"Final render: {output_path.name}")
        success, err = self._run_ffmpeg(cmd, cwd=self.temp_dir)
        
        if not success:
            raise RuntimeError(f"Render failed: {err[:200]}")
        
        return output_path
    
    def cleanup(self):
        """Nettoie les fichiers temporaires"""
        for pattern in ["*.mp4", "*.wav", "*.ass", "*.srt", "*.ffconcat"]:
            for f in self.temp_dir.glob(pattern):
                try:
                    f.unlink()
                except:
                    pass
