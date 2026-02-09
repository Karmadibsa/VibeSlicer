import os
import subprocess
import json
import logging
import re
import math
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VibeEngine")

class VibeEngine:
    def __init__(self):
        self.base_dir = os.getcwd()
        self.temp_dir = os.path.abspath("temp")
        self.assets_dir = os.path.abspath("assets")
        self.input_dir = os.path.abspath("input")
        self.output_dir = os.path.abspath("output")
        
        for d in [self.temp_dir, self.assets_dir, self.input_dir, self.output_dir]:
            os.makedirs(d, exist_ok=True)

        self.whisper_model = None

    def _get_ffmpeg_path(self, path):
        """Retourne un chemin absolu formaté pour FFmpeg (forward slashes + échappement)"""
        p = Path(path).resolve()
        return str(p).replace("\\", "/")

    def _get_ffmpeg_filter_path(self, path):
        """Retourne un chemin échappé pour les filtres (avec \:)"""
        return self._get_ffmpeg_path(path).replace(":", "\\:")

    def _run_ffmpeg(self, cmd, cwd=None, capture_output=True):
        """Exécute FFmpeg avec gestion d'erreur et CWD"""
        if cwd is None:
            cwd = self.temp_dir # Travailler dans temp par défaut pour les chemins relatifs

        # Si cmd contient des chemins absolus, on essaie de les rendre relatifs si on est dans temp
        # (Optimisation pour Windows)
        
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        try:
            # On utilise shell=True sous Windows parfois pour éviter les problèmes de PATH, mais ici subprocess direct est mieux
            # Pour capturer stderr de silencedetect, on a besoin de PIPE
            process = subprocess.run(
                cmd, 
                cwd=cwd,
                stdout=subprocess.PIPE if capture_output else None, 
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
                encoding='utf-8',
                errors='replace' # Évite crash sur encodage bizarre
            )
            
            if process.returncode != 0:
                logger.error(f"FFmpeg Error:\n{process.stderr}")
                raise RuntimeError(f"FFmpeg failed: {process.stderr}")
            
            return process.stdout, process.stderr
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise

    # === STEP 1: SANITIZER (CFR 30fps / 44.1kHz / AAC) ===
    def sanitize(self, input_path):
        """
        Convertit la vidéo source en format pivot stable (CFR 30fps).
        Retourne le chemin ABSOLU du fichier nettoyé.
        """
        input_path = os.path.abspath(input_path)
        filename = Path(input_path).stem
        output_name = f"{filename}_clean.mp4"
        output_path = os.path.join(self.temp_dir, output_name)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            logger.info(f"Using cached clean video: {output_path}")
            return output_path

        logger.info(f"Sanitizing {input_path}...")
        
        # On exécute depuis temp_dir pour simplifier les chemins de sortie, 
        # mais input_path est absolu.
        cmd = [
            "ffmpeg", "-y", 
            "-i", input_path,
            "-r", "30",              # Force 30 fps
            "-c:v", "libx264",       # H.264
            "-preset", "ultrafast",  # Rapide
            "-crf", "23",            # Qualité standard
            "-c:a", "aac",           # AAC
            "-ar", "44100",          # 44.1kHz
            "-ac", "2",              # Stéréo
            output_name              # Sortie relative (dans temp_dir)
        ]
        
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path

    # === STEP 2: SILENCE DETECTION (NATIVE FFMPEG) ===
    def detect_silence(self, video_path, db_thresh=-30, min_silence_dur=0.5):
        """
        Utilise silencedetect de FFmpeg directement sur la vidéo.
        Retourne une liste de segments de PAROLE [(start, end), ...].
        """
        start_t = 0
        video_len = self._get_len(video_path)
        
        # On ne passe PAS par WAV intermédiaire. Direct sur le MP4.
        # Filtre: silencedetect
        # Sortie: stderr contient les logs
        video_name = os.path.basename(video_path)
        
        cmd = [
            "ffmpeg", "-i", video_name,
            "-af", f"silencedetect=noise={db_thresh}dB:d={min_silence_dur}",
            "-f", "null", "-"
        ]
        
        _, stderr = self._run_ffmpeg(cmd, cwd=self.temp_dir)
        
        # Parsing des logs
        # [silencedetect @ ...] silence_start: 12.345
        # [silencedetect @ ...] silence_end: 14.567 | silence_duration: 2.222
        
        silence_starts = []
        silence_ends = []
        
        for line in stderr.split('\n'):
            if "silence_start" in line:
                match = re.search(r"silence_start: ([\d\.]+)", line)
                if match: silence_starts.append(float(match.group(1)))
            elif "silence_end" in line:
                match = re.search(r"silence_end: ([\d\.]+)", line)
                if match: silence_ends.append(float(match.group(1)))
        
        # Reconstruire les segments de PAROLE (l'inverse du silence)
        speech_segments = []
        current_pos = 0.0
        
        # Si le premier silence commence après 0, il y a de la parole au début
        # silence_starts[i] correspond au début du silence, donc la FIN de la parole
        # silence_ends[i] correspond à la fin du silence, donc le DÉBUT de la parole
        
        for i in range(len(silence_starts)):
            sil_start = silence_starts[i]
            sil_end = silence_ends[i] if i < len(silence_ends) else video_len
            
            # Parole avant ce silence ?
            if sil_start > current_pos:
                speech_segments.append((current_pos, sil_start))
            
            current_pos = sil_end
            
        # Parole après le dernier silence ?
        if current_pos < video_len:
            speech_segments.append((current_pos, video_len))
            
        return speech_segments

    def _get_len(self, path):
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        try:
            val = subprocess.check_output(cmd).decode().strip()
            return float(val)
        except:
            return 0

    # === STEP 3: TRANSCRIPTION ===
    def transcribe(self, video_path, model_size="base"):
        if self.whisper_model is None:
            logger.info("Loading Whisper...")
            try:
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_size, device="cuda", compute_type="float16")
            except:
                logger.warning("GPU failed, fallback CPU")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        segments, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
        return list(segments)

    # === STEP 4: ASS GENERATION (STYLED SUBTITLES) ===
    def generate_ass(self, segments, ass_path, highlight_words=None):
        """
        Génère un fichier .ass (Advanced Substation Alpha).
        Plus robuste que SRT pour le style et la position.
        """
        if highlight_words is None:
            highlight_words = ["MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI"]
            
        def fmt_time(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            cs = int((s % 1) * 100)
            return f"{h}:{m:02}:{sec:02}.{cs:02}"

        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,60,&H00FFFFFF,&H000000FF,&H00E22B8A,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,350,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(ass_path, "w", encoding="utf-8-sig") as f:
            f.write(header)
            
            for seg in segments:
                words = seg.words
                if not words: continue
                
                # Group 2 words max roughly
                current_chunk = []
                chunks = []
                for w in words:
                    current_chunk.append(w)
                    if len(current_chunk) >= 2:
                        chunks.append(current_chunk)
                        current_chunk = []
                if current_chunk: chunks.append(current_chunk)
                
                for chunk in chunks:
                    start = fmt_time(chunk[0].start)
                    end = fmt_time(chunk[-1].end)
                    
                    text_parts = []
                    for w in chunk:
                        clean = w.word.strip().upper()
                        is_hl = any(k in clean for k in highlight_words)
                        val = w.word.strip()
                        if is_hl:
                            # ASS Color code is BGR: Yellow is 00FFFF (Cyan? No Blue-Green-Red) -> 00D7FF (Gold/Yellow)
                            # &H0000FFFF is Yellow (Blue=00, Green=FF, Red=FF)
                            val = f"{{\\c&H00FFFF&}}{val}{{\\c&HFFFFFF&}}" # Reset to white
                        text_parts.append(val)
                    
                    text = " ".join(text_parts)
                    f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    # === UTILS: FAST CUTTING ===
    def fast_cut_concat(self, video_path, segments, output_path):
        """
        Coupe et concatène rapidement la vidéo selon les segments (Keep=True)
        Utilise le protocole ffconcat pour éviter le ré-encodage si possible, 
        ou un ré-encodage rapide pour la fluidité.
        """
        concat_file = os.path.join(self.temp_dir, "cuts.ffconcat")
        
        # Chemins absolus ou relatifs ? Relatifs si CWD=temp_dir
        # On va écrire le ffconcat avec des chemins absolus échappés pour être sûr
        video_abs = self._get_ffmpeg_path(video_path)
        
        with open(concat_file, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for start, end in segments:
                f.write(f"file '{video_abs}'\n")
                f.write(f"inpoint {start:.3f}\n")
                f.write(f"outpoint {end:.3f}\n")
        
        # Rendu du cut
        # On ré-encode en ultrafast pour éviter les glitches de concaténation de timestamps
        # C'est nécessaire pour que la timeline MP4 soit propre pour Whisper derrière
        
        cmd = [
            "ffmpeg", "-y", 
            "-f", "concat", "-safe", "0", 
            "-i", concat_file,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-ar", "44100",
            output_path
        ]
        
        logger.info(f"Fast cutting to {output_path}...")
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path

    # === STEP 5: FINAL RENDER ===
    def render(self, video_path, ass_path, music_path, output_path):
        """
        Rendu final utilisant les fichiers relatifs dans temp_dir via os.chdir.
        C'est la méthode "Bulletproof" pour les chemins Windows.
        """
        # On va changer le CWD pour temp_dir pour FFmpeg
        # Il faut donc que video_path et ass_path soient relatifs à temp_dir s'ils y sont
        
        #video_name = os.path.basename(video_path)
        #ass_name = os.path.basename(ass_path)
        
        # Output absolu
        output_path = os.path.abspath(output_path)
        assets_dir = os.path.abspath("assets").replace("\\", "/") # Pour fontsdir
        
        # Filtres
        # ass=filename.ass:fontsdir=...
        # On échappe les backslashes pour filename si nécessaire, mais si on est dans CWD, juste le nom suffit
        
        # Commande
        cmd = ["ffmpeg", "-y"]
        
        # Inputs
        # Attention: video_path est un chemin absolu vers TEMP.
        # Si on change de CWD, on peut utiliser des chemins relatifs.
        
        # Strategie : On lance FFmpeg DANS temp_dir.
        # input video est dans temp_dir (le sanitized ou le cut).
        # ass est dans temp_dir.
        
        vid_rel = os.path.basename(video_path)
        ass_rel = os.path.basename(ass_path)
        
        inputs = ["-i", vid_rel]
        
        # Filtre ASS
        # fontsdir='C:/Path/To/Assets'
        # ass='subs.ass'
        
        # Attention: sous Windows, FFmpeg et les chemins absolus pour fontsdir c'est parfois la galère.
        # Mais avec des forward slashes ça passe.
        
        vf = f"ass='{ass_rel}':fontsdir='{assets_dir}'"
        
        if music_path:
            mus_abs = os.path.abspath(music_path).replace("\\", "/")
            inputs.extend(["-i", mus_abs])
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e9,volume=0.1[bgm];"
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
             
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(maps)
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            output_path
        ])
        
        logger.info(f"Rendering to {output_path}")
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path
