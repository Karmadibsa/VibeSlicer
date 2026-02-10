import os
import threading
import logging
import re
import json
import time
from pathlib import Path
from src.core.state import ProjectState, EventType, Segment
from src.utils.ffmpeg_runner import FFmpegRunner

logger = logging.getLogger(__name__)

class VideoProcessor:
    """
    Gère les opérations lourdes (FFmpeg).
    Version : ULTRA-STRICT SYNC & DEBUG LOGGING
    Concept : On convertit TOUT en un format "Pivot" (Mezzanine) parfait avant de toucher à quoi que ce soit.
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
        """Dès qu'une vidéo est chargée, on lance la pipeline de Sanitisation."""
        t = threading.Thread(target=self._process_pipeline, args=(video_path,))
        t.daemon = True
        t.start()
        
    def _process_pipeline(self, raw_video_path: Path):
        try:
            logger.info(f"=== DÉBUT TRAITEMENT : {raw_video_path.name} ===")
            self._probe_deep_info(raw_video_path, "ORIGINAL_FILE")

            # 1. CRITIQUE : Génération du 'Pivot' (Mezzanine)
            pivot_path = self._create_perfect_pivot(raw_video_path)
            
            # 2. Bascule : tout le logiciel utilise le Pivot, pas l'original
            if pivot_path != raw_video_path:
                logger.warning(f"Bascule forcée sur le fichier Pivot : {pivot_path.name}")
                self.state.source_video = pivot_path 
                self.state.set_proxy(pivot_path) 

            # 3. Analyse des silences (sur le Pivot)
            segments = self._detect_silence(pivot_path)
            self.state.update_segments(segments)
            
            logger.info("=== PIPELINE TERMINÉE AVEC SUCCÈS ===")
            
        except Exception as e:
            logger.error(f"ERREUR CRITIQUE PIPELINE: {e}", exc_info=True)

    def _probe_deep_info(self, path: Path, label: str):
        """Dump complet des infos techniques pour le debug"""
        try:
            cmd = [
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path)
            ]
            json_str = self.ffmpeg.run_ffprobe(cmd)
            data = json.loads(json_str)
            
            streams_info = []
            for s in data.get('streams', []):
                s_type = s.get('codec_type')
                if s_type == 'video':
                    streams_info.append(f"VIDEO: r_frame_rate={s.get('r_frame_rate')}, avg={s.get('avg_frame_rate')}, start_time={s.get('start_time')}, time_base={s.get('time_base')}")
                elif s_type == 'audio':
                    streams_info.append(f"AUDIO: sample_rate={s.get('sample_rate')}, start_time={s.get('start_time')}, time_base={s.get('time_base')}")
            
            logger.info(f"DEBUG [{label}]:\n" + "\n".join(streams_info))
            
        except Exception as e:
            logger.warning(f"Impossible de sonder le fichier {path}: {e}")

    def _create_perfect_pivot(self, input_path: Path) -> Path:
        """
        Crée un fichier intermédiaire PARFAIT :
        - Vidéo : FPS constant (CFR) via filtre fps=60
        - Audio : Resample 44100Hz avec async=1 (corrige le drift OBS)
        - Timecodes : Réécrits à zéro
        """
        output_dir = self.state.project_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        pivot_path = output_dir / f"{input_path.stem}_PIVOT_CFR.mp4"
        
        if pivot_path.exists():
            logger.info("Pivot existant trouvé.")
            return pivot_path
            
        logger.info("Création du Fichier Pivot (Normalisation A/V)...")
        
        # filter_complex :
        # fps=60 : Recalcule les frames pour avoir exactement 60/sec
        # aresample=44100:async=1 : Corrige le drift audio OBS
        cmd = [
            "-y",
            "-i", str(input_path),
            "-filter_complex", "[0:v]fps=60,format=yuv420p[v];[0:a]aresample=44100:async=1[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "superfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "60",
            str(pivot_path)
        ]
        
        self.ffmpeg.run(cmd)
        self._probe_deep_info(pivot_path, "PIVOT_CREATED")
        return pivot_path

    def _detect_silence(self, video_path: Path, db_thresh=-35, min_dur=0.4) -> list[Segment]:
        logger.info(f"Analyse des silences sur {video_path.name}...")
        
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
        
        try:
            dur_str = self.ffmpeg.run_ffprobe([
                "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
            ])
            duration = float(dur_str.strip())
        except:
            duration = 1000.0
            
        segments = []
        last_end = 0.0
        
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
             
        logger.info(f"{len(segments)} segments détectés.")
        return segments

    def export_final(self, output_path: Path):
        """
        Export final depuis le fichier PIVOT.
        Coupe stricte par INDEX d'échantillons.
        """
        source = self.state.source_video
        logger.info(f"DÉBUT EXPORT depuis : {source.name}")
        self._probe_deep_info(source, "EXPORT_SOURCE_CHECK")
        
        segments = [s for s in self.state.segments if s.keep]
        
        if not segments:
            logger.warning("Aucun segment à exporter !")
            return

        FPS = 60
        SAMPLE_RATE = 44100
        SAMPLES_PER_FRAME = 735  # 44100 / 60
        PADDING = 0.15 

        select_parts_v = []
        select_parts_a = []
        total_frames_kept = 0

        for i, s in enumerate(segments):
            start_t = max(0, s.start - PADDING)
            end_t = s.end + PADDING
            
            start_frame = int(round(start_t * FPS))
            end_frame = int(round(end_t * FPS))
            
            if end_frame <= start_frame:
                continue
                
            total_frames_kept += end_frame - start_frame
            
            start_sample = start_frame * SAMPLES_PER_FRAME
            end_sample = end_frame * SAMPLES_PER_FRAME
            
            if i < 3:
                logger.debug(f"Seg {i}: T[{start_t:.3f}-{end_t:.3f}] -> F[{start_frame}-{end_frame}] -> S[{start_sample}-{end_sample}]")

            select_parts_v.append(f"between(n,{start_frame},{end_frame})")
            select_parts_a.append(f"between(n,{start_sample},{end_sample})")
            
        select_expr_v = "+".join(select_parts_v)
        select_expr_a = "+".join(select_parts_a)
        
        vf = f"select='{select_expr_v}',setpts=N/FRAME_RATE/TB"
        af = f"aselect='{select_expr_a}',asetpts=N/SR/TB"
        
        cmd = [
            "-y",
            "-i", str(source),
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE),
            "-r", str(FPS),
            str(output_path)
        ]
        
        logger.info(f"Lancement FFmpeg Export ({total_frames_kept} frames)...")
        self.ffmpeg.run(cmd)
        logger.info("Export terminé.")

    def _has_audio_stream(self, video_path: Path) -> bool:
        """Vérifie si la vidéo contient une piste audio"""
        try:
            result = self.ffmpeg.run_ffprobe([
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(video_path)
            ])
            return len(result.strip()) > 0
        except:
            return True
