import os
import subprocess
import json
import logging
import re
import math
import shutil
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

        self._fix_cuda_path()
        self.whisper_model = None

    def _fix_cuda_path(self):
        """Tente d'ajouter les libs NVIDIA au PATH pour éviter l'erreur cublas64_12.dll"""
        # 1. Try pip packages (nvidia-*)
        try:
            import nvidia.cublas.lib
            import nvidia.cudnn.lib
            
            paths_to_add = [
                os.path.dirname(nvidia.cublas.lib.__file__),
                os.path.dirname(nvidia.cudnn.lib.__file__)
            ]
            
            for p in paths_to_add:
                if os.path.exists(p) and p not in os.environ["PATH"]:
                    os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]
                    logger.info(f"🔧 Added CUDA lib (pip) to PATH: {p}")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to fix pip CUDA path: {e}")

        # 2. Try System Path (C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin)
        # On cherche les DLLs cublas64_12.dll
        try:
            base_cuda = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
            if os.path.exists(base_cuda):
                for version in os.listdir(base_cuda):
                    bin_path = os.path.join(base_cuda, version, "bin")
                    if os.path.isdir(bin_path):
                        dll_path = os.path.join(bin_path, "cublas64_12.dll")
                        if os.path.exists(dll_path) and bin_path not in os.environ["PATH"]:
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                            logger.info(f"🔧 Added System CUDA bin to PATH: {bin_path}")
                            break # Found one, good enough
        except Exception as e:
            logger.warning(f"Failed to check System CUDA path: {e}")

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
        
        # Execution 'Bulletproof' : On tente, et si le GPU plante (DLL manquante), on fallback CPU
        try:
            segments, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
            return list(segments)
        except Exception as e:
            msg = str(e).lower()
            if "cublas" in msg or "dll" in msg or "library" in msg:
                logger.warning(f"⚠️ Erreur GPU Runtime ({e}). Bascule automatique vers CPU...")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
                
                # Retry CPU
                segments, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
                return list(segments)
            else:
                raise e

    # === STEP 4: ASS GENERATION (STYLED SUBTITLES) ===
    def generate_ass(self, segments, ass_path, highlight_words=None, subtitle_offset=0.0):
        """
        Génère un fichier .ass (Advanced Substation Alpha).
        Plus robuste que SRT pour le style et la position.
        Supporte les objets Whisper Segment ET les dictionnaires (pour édition).
        
        Args:
            subtitle_offset: Décalage en secondes pour décaler tous les sous-titres (ex: 2.0 pour intro)
        """
        if highlight_words is None:
            highlight_words = ["MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI"]
            
        def fmt_time(s):
            s = s + subtitle_offset  # Appliquer le décalage
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            cs = int((s % 1) * 100)
            return f"{h}:{m:02}:{sec:02}.{cs:02}"
        
        def get_attr(seg, key, default=None):
            """Get attribute from dict or object"""
            if isinstance(seg, dict):
                return seg.get(key, default)
            return getattr(seg, key, default)

        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,120,&H00FFFFFF,&H000000FF,&H00E22B8A,&H00000000,-1,0,0,0,100,100,0,0,1,6,2,2,10,10,640,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(ass_path, "w", encoding="utf-8-sig") as f:
            f.write(header)
            
            for seg in segments:
                try:
                    # Get words - works for both dict and object
                    words = get_attr(seg, 'words', None)
                    
                    # Check if we have words for word-level timing
                    if words is None or len(words) == 0:
                        # Fallback: use full text as one chunk (for edited subtitles)
                        start = fmt_time(get_attr(seg, 'start', 0))
                        end = fmt_time(get_attr(seg, 'end', 0))
                        text = get_attr(seg, 'text', '').strip()
                        if text:
                            # Apply highlights to full text
                            for kw in highlight_words:
                                if kw in text.upper():
                                    # Simple highlight - find and wrap keywords
                                    import re
                                    text = re.sub(
                                        f"({re.escape(kw)})",
                                        r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}",
                                        text,
                                        flags=re.IGNORECASE
                                    )
                            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
                        continue

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
                                val = f"{{\\c&H00FFFF&}}{val}{{\\c&HFFFFFF&}}" # Yellow highlight
                            text_parts.append(val)
                        
                        text = " ".join(text_parts)
                        f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
                except Exception as e:
                    logger.error(f"Error processing segment: {e}")
                    continue
    # === UTILS: FAST CUTTING ===
    def fast_cut_concat(self, video_path, segments, output_path):
        """
        Coupe la vidéo en utilisant le filtre 'select'.
        
        C'est la méthode "Gold Standard" pour la synchro A/V :
        Au lieu de couper des fichiers et les recoller (risque de décalage),
        on filtre les frames voulues en une seule passe.
        """
        if not segments:
            return video_path
            
        video_abs = self._get_ffmpeg_path(video_path)
        
        # Construire les expressions de sélection
        # select='between(t,s1,e1)+between(t,s2,e2)+...'
        
        # Attention à la limite de caractères Windows (8191)
        # Avec ~30-40 chars par segment, on tient environ 200 segments.
        # Si trop de segments, on fallback sur la méthode chunks.
        
        select_parts = []
        for start, end in segments:
            select_parts.append(f"between(t,{start:.3f},{end:.3f})")
            
        select_expr = "+".join(select_parts)
        
        # Filtres Vidéo et Audio
        # setpts=N/FRAME_RATE/TB : Recalcule les timestamps vidéo pour qu'ils soient continus
        # asetpts=N/SR/TB : Recalcule les timestamps audio
        
        vf = f"select='{select_expr}',setpts=N/FRAME_RATE/TB"
        af = f"aselect='{select_expr}',asetpts=N/SR/TB"
        
        logger.info(f"Advanced Sync Cutting ({len(segments)} segments)...")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_abs,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-vsync", "cfr",
            output_path
        ]
        
        # Si la commande est trop longue pour Windows, on utilise un script filter complex
        if len(str(cmd)) > 8000:
            logger.warning("Command too long, falling back to script file...")
            filter_script = os.path.join(self.temp_dir, "filter_script.txt")
            with open(filter_script, "w", encoding="utf-8") as f:
                f.write(f"select='{select_expr}',setpts=N/FRAME_RATE/TB[v];\n")
                f.write(f"aselect='{select_expr}',asetpts=N/SR/TB[a]")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", video_abs,
                "-filter_complex_script", filter_script,
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-vsync", "cfr",
                output_path
            ]
            
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path

    # === STEP 5: FINAL RENDER ===
    def render(self, video_path, ass_path, music_path, output_path):
        """
        Rendu final utilisant les fichiers relatifs dans temp_dir.
        SOLUTION BULLETPROOF: On copie les fonts dans temp_dir pour éviter
        tous les problèmes d'échappement de chemins Windows avec FFmpeg.
        """
        output_path = os.path.abspath(output_path)
        
        # === BULLETPROOF: Copier les fonts dans temp_dir ===
        # Cela évite tous les problèmes de chemins avec espaces/caractères spéciaux
        fonts_in_temp = os.path.join(self.temp_dir, "fonts")
        os.makedirs(fonts_in_temp, exist_ok=True)
        
        # Copier toutes les polices depuis assets vers temp/fonts
        for ext in ["*.ttf", "*.otf", "*.TTF", "*.OTF"]:
            import glob
            for font_file in glob.glob(os.path.join(self.assets_dir, ext)):
                dest = os.path.join(fonts_in_temp, os.path.basename(font_file))
                if not os.path.exists(dest):
                    shutil.copy2(font_file, dest)
                    logger.info(f"Copied font: {os.path.basename(font_file)}")
        
        vid_rel = os.path.basename(video_path)
        ass_rel = os.path.basename(ass_path)
        
        # Filtre ASS avec chemin RELATIF vers fonts (pas de caractères spéciaux!)
        # fontsdir=fonts fonctionne car on exécute FFmpeg dans temp_dir
        vf = f"ass={ass_rel}:fontsdir=fonts"
        
        inputs = ["-i", vid_rel]
        
        if music_path:
            # Pour la musique, on utilise le chemin absolu
            mus_abs = os.path.abspath(music_path)
            inputs.extend(["-i", mus_abs])
            # Filtre simplifié - pas de loudnorm qui peut causer des coupures
            # aloop pour boucler la musique, volume réduit, amix pour mixer
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e9,volume={0.15}[bgm];"
                f"[0:a]volume=1.0[voice];"
                f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout];"
                f"[0:v]{vf}[vout]"
            )
            maps = ["-map", "[vout]", "-map", "[aout]"]
        else:
            # Sans musique, juste la vidéo avec son original
            filter_complex = f"[0:v]{vf}[vout]"
            maps = ["-map", "[vout]", "-map", "0:a"]
        
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(maps)
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest",  # Arrêter quand le stream le plus court finit
            output_path
        ])
        
        logger.info(f"Rendering to {output_path}")
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path
