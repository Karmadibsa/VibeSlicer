import os
import threading
import logging
import re
from pathlib import Path
from src.core.state import ProjectState, EventType, Segment
from src.utils.ffmpeg_runner import FFmpegRunner

logger = logging.getLogger(__name__)

class VideoProcessor:
    """
    Gère les opérations lourdes (FFmpeg) en arrière-plan.
    Version corrigée pour SYNCHRONISATION PARFAITE (Audio/Vidéo)
    """
    
    def __init__(self, state: ProjectState):
        self.state = state
        self.ffmpeg = FFmpegRunner(os.getcwd())
        
        self.state.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded)
        self.state.subscribe(EventType.EXPORT_REQUESTED, self._on_export_requested)

    def _on_export_requested(self, output_path: Path):
        t = threading.Thread(target=self.export_final, args=(output_path,))
        t.daemon = True
        t.start()
        
    def _on_video_loaded(self, video_path: Path):
        t = threading.Thread(target=self._process_pipeline, args=(video_path,))
        t.daemon = True
        t.start()
        
    def _process_pipeline(self, video_path: Path):
        try:
            # 1. Génération Proxy (ET Nettoyage VFR -> CFR)
            proxy_path = self._generate_proxy(video_path)
            self.state.set_proxy(proxy_path)
            
            # 2. Analyse
            segments = self._detect_silence(proxy_path)
            self.state.update_segments(segments)
            
            logger.info("Pipeline terminée !")
            
        except Exception as e:
            logger.error(f"Erreur pipeline: {e}")

    def _generate_proxy(self, video_path: Path) -> Path:
        """
        Génère une version basse résolution MAIS avec un framerate constant (CFR).
        Cela garantit que les timestamps détectés correspondront à la vidéo finale.
        """
        output_dir = self.state.project_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        proxy_path = output_dir / f"{video_path.stem}_proxy.mp4"
        
        if proxy_path.exists():
            logger.info("Proxy existant trouvé.")
            return proxy_path
            
        logger.info("Génération du proxy 60fps constant...")
        
        # AJOUT CRITIQUE : -r 60 et audio standardisé pour forcer la synchro
        self.ffmpeg.run([
            "-y",
            "-i", str(video_path),
            "-vf", "scale=-2:480",
            "-r", "60",              # Force 60 FPS Constant
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-ar", "44100",          # Standardise l'audio
            "-ac", "2",
            str(proxy_path)
        ])
        
        return proxy_path

    def _detect_silence(self, video_path: Path, db_thresh=-35, min_dur=0.4) -> list[Segment]:
        logger.info("Analyse des silences...")
        
        cmd = [
            "-i", str(video_path),
            "-af", f"silencedetect=noise={db_thresh}dB:d={min_dur}",
            "-f", "null", "-"
        ]
        result = self.ffmpeg.run(cmd)
        
        silence_starts = []
        silence_ends = []
        
        for line in result.stderr.split('\n'):
            if 'silence_start' in line:
                m = re.search(r'silence_start: ([\d\.]+)', line)
                if m: silence_starts.append(float(m.group(1)))
            elif 'silence_end' in line:
                m = re.search(r'silence_end: ([\d\.]+)', line)
                if m: silence_ends.append(float(m.group(1)))
        
        # Récupération durée totale
        try:
            dur_str = self.ffmpeg.run_ffprobe([
                "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
            ])
            duration = float(dur_str.strip())
        except:
            duration = 600.0
            
        segments = []
        last_end = 0.0
        
        # Logique d'inversion (Silence -> Parole)
        for i in range(len(silence_starts)):
            start_sil = silence_starts[i]
            if start_sil > last_end:
                segments.append(Segment(last_end, start_sil, "speech", True))
            
            if i < len(silence_ends):
                end_sil = silence_ends[i]
                segments.append(Segment(start_sil, end_sil, "silence", False))
                last_end = end_sil
                
        if last_end < duration:
             segments.append(Segment(last_end, duration, "speech", True))
             
        return segments

    def export_final(self, output_path: Path):
        """
        Export final avec ALIGNEMENT TEMPOREL (Snap-to-Frame).
        C'est ici que la magie de la synchro opère.
        """
        logger.info(f"Début export vers {output_path}")
        
        source = self.state.source_video
        segments = [s for s in self.state.segments if s.keep]
        
        if not segments:
            logger.warning("Aucun segment à exporter !")
            return

        # --- CORRECTION SYNC : SNAP TO GRID ---
        # On aligne chaque coupe sur la grille exacte de 60 FPS (0.01666s)
        # Cela empêche FFmpeg d'hésiter entre deux frames.
        FPS = 60.0
        FRAME_DUR = 1.0 / FPS
        
        def snap(t):
            return round(t / FRAME_DUR) * FRAME_DUR

        select_parts = []
        for s in segments:
            # --- PADDING : Marge de sécurité anti-coupe-sèche ---
            # Évite de manger le début des mots ("onjour" -> "Bonjour")
            PADDING = 0.15  # 150ms de marge
            start_padded = max(0, s.start - PADDING)
            end_padded = s.end + PADDING
            
            # On snap sur la grille APRES avoir ajouté le padding
            start_clean = snap(start_padded)
            end_clean = snap(end_padded)
            
            # Sécurité anti-glitch (éviter les segments nuls)
            if end_clean - start_clean < FRAME_DUR:
                continue
                
            # 4 décimales pour être ultra précis
            select_parts.append(f"between(t,{start_clean:.4f},{end_clean:.4f})")
            
        select_expr = "+".join(select_parts)
        
        # setpts=N/FRAME_RATE/TB reconstruit les timestamps proprement
        # car les coupes sont alignées sur les frames
        vf = f"select='{select_expr}',setpts=N/FRAME_RATE/TB"
        af = f"aselect='{select_expr}',asetpts=N/SR/TB"
        
        cmd = [
            "-y",
            "-i", str(source),
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", 
            "-preset", "fast",   # Meilleure qualité que ultrafast
            "-crf", "22",
            "-r", "60",          # Force la sortie à 60fps strict
            "-c:a", "aac", 
            "-b:a", "192k",
            "-ar", "44100",      # Force l'audio à 44.1kHz standard
            str(output_path)
        ]
        
        self.ffmpeg.run(cmd)
        logger.info("Export terminé avec succès.")
