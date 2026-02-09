import os
import threading
import logging
import re
from pathlib import Path
from src.core.project_state import ProjectState, EventType, Segment
from src.utils.ffmpeg_runner import FFmpegRunner

logger = logging.getLogger(__name__)

class VideoProcessor:
    """
    Gère les opérations lourdes (FFmpeg) en arrière-plan.
    - Génération de Proxy
    - Détection de silence
    - Export final
    """
    
    def __init__(self, state: ProjectState):
        self.state = state
        self.ffmpeg = FFmpegRunner(os.getcwd())
        
        # S'abonner au chargement de vidéo
        self.state.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded)
        self.state.subscribe(EventType.EXPORT_REQUESTED, self._on_export_requested)
        
    def _on_export_requested(self, output_path: Path):
        """Lance l'export en background"""
        t = threading.Thread(target=self.export_final, args=(output_path,))
        t.daemon = True
        t.start()
        
    def _on_video_loaded(self, video_path: Path):
        """Déclenche la pipeline d'analyse en background"""
        t = threading.Thread(target=self._process_pipeline, args=(video_path,))
        t.daemon = True
        t.start()
        
    def _process_pipeline(self, video_path: Path):
        """Pipeline complet : Proxy -> Analyse -> Update State"""
        try:
            # 1. Génération Proxy
            proxy_path = self._generate_proxy(video_path)
            self.state.set_proxy(proxy_path)
            
            # 2. Analyse des silences (sur le proxy pour aller vite)
            segments = self._detect_silence(proxy_path)
            self.state.update_segments(segments)
            
            logger.info("Pipeline terminée !")
            
        except Exception as e:
            logger.error(f"Erreur pipeline: {e}")

    def _generate_proxy(self, video_path: Path) -> Path:
        """Génère une version basse résolution (480p)"""
        output_dir = self.state.project_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        proxy_path = output_dir / f"{video_path.stem}_proxy.mp4"
        
        if proxy_path.exists():
            logger.info("Proxy existant trouvé.")
            return proxy_path
            
        logger.info("Génération du proxy 480p...")
        
        # Commande optimisée pour la vitesse
        self.ffmpeg.run([
            "-y",
            "-i", str(video_path),
            "-vf", "scale=-2:480",   # 480p hauteur
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Vitesse max
            "-crf", "28",            # Qualité "brouillon"
            "-c:a", "aac",
            "-b:a", "96k",
            str(proxy_path)
        ])
        
        return proxy_path

    def _detect_silence(self, video_path: Path, db_thresh=-35, min_dur=0.4) -> list[Segment]:
        """Détecte les silences et retourne les segments de PAROLE"""
        logger.info("Analyse des silences...")
        
        # 1. ffmpeg silencedetect
        cmd = [
            "-i", str(video_path),
            "-af", f"silencedetect=noise={db_thresh}dB:d={min_dur}",
            "-f", "null", "-"
        ]
        result = self.ffmpeg.run(cmd)
        
        # 2. Parsing de la sortie
        silence_starts = []
        silence_ends = []
        
        for line in result.stderr.split('\n'):
            if 'silence_start' in line:
                m = re.search(r'silence_start: ([\d\.]+)', line)
                if m: silence_starts.append(float(m.group(1)))
            elif 'silence_end' in line:
                m = re.search(r'silence_end: ([\d\.]+)', line)
                if m: silence_ends.append(float(m.group(1)))
                
        # 3. Inversion (Silence -> Parole)
        try:
            duration_str = self.ffmpeg.run_ffprobe([
                "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
            ])
            duration = float(duration_str.strip())
        except:
            duration = 600.0 # Fallback
            
        segments = []
        last_end = 0.0
        
        for i in range(len(silence_starts)):
            start_sil = silence_starts[i]
            # Ce qui est AVANT le silence est de la PAROLE
            if start_sil > last_end:
                segments.append(Segment(last_end, start_sil, "speech", True))
            
            # On ajoute le SILENCE (marqué comme à supprimer par défaut ?) (non keep=False ?)
            # Pour l'instant on garde tout comme segments, on filtrera visuellement
            if i < len(silence_ends):
                end_sil = silence_ends[i]
                segments.append(Segment(start_sil, end_sil, "silence", False)) # False = à couper
                last_end = end_sil
                
        # Dernier morceau
        if last_end < duration:
             segments.append(Segment(last_end, duration, "speech", True))
             
        return segments

    def export_final(self, output_path: Path):
        """Export final haute qualité utilisant la méthode Select Filter (Sync parfaite)"""
        logger.info(f"Début export vers {output_path}")
        
        source = self.state.source_video
        segments = [s for s in self.state.segments if s.keep]
        
        if not segments:
            logger.warning("Aucun segment à exporter !")
            return

        # Construction du filtre select
        select_parts = []
        for s in segments:
            select_parts.append(f"between(t,{s.start:.3f},{s.end:.3f})")
            
        select_expr = "+".join(select_parts)
        
        vf = f"select='{select_expr}',setpts=N/FRAME_RATE/TB"
        af = f"aselect='{select_expr}',asetpts=N/SR/TB"
        
        cmd = [
            "-y",
            "-i", str(source),
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path)
        ]
        
        self.ffmpeg.run(cmd)
        logger.info("Export terminé avec succès.")
