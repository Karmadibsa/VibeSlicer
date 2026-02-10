import os
import subprocess
import logging
import re
import shutil
import math
import json
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [ENGINE] - %(message)s')
logger = logging.getLogger("VibeEnginePro")

class VibeEngine:
    def __init__(self):
        self.base_dir = os.getcwd()
        self.temp_dir = os.path.abspath("temp")
        self.assets_dir = os.path.abspath("assets")
        self.input_dir = os.path.abspath("input")
        self.output_dir = os.path.abspath("output")

        # On sépare les dossiers pour être propre
        for d in [self.temp_dir, self.assets_dir, self.input_dir, self.output_dir]:
            os.makedirs(d, exist_ok=True)

        self._fix_cuda_path()
        self.whisper_model = None

    def _fix_cuda_path(self):
        try:
            base_cuda = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
            if os.path.exists(base_cuda):
                for version in os.listdir(base_cuda):
                    bin_path = os.path.join(base_cuda, version, "bin")
                    if os.path.isdir(bin_path):
                        dll_path = os.path.join(bin_path, "cublas64_12.dll")
                        if os.path.exists(dll_path) and bin_path not in os.environ["PATH"]:
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
        except: pass

    def _run_ffmpeg(self, cmd, cwd=None):
        if cwd is None: cwd = self.temp_dir
        # Cache la fenêtre console sur Windows pour faire "Pro"
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        logger.info(f"CMD: {' '.join(cmd)}")
        try:
            process = subprocess.run(
                cmd, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace',
                startupinfo=startupinfo
            )
            if process.returncode != 0:
                logger.error(f"FFmpeg Error: {process.stderr}")
                raise RuntimeError(f"FFmpeg failed")
            return process.stdout, process.stderr
        except Exception as e:
            logger.error(f"Exec failed: {e}")
            raise

    # === C'EST ICI QUE TOUT CHANGE : LE PIVOT ===
    def create_pivot(self, input_path):
        """
        Transforme la vidéo OBS (VFR, instable) en Master Pivot (CFR 60fps, Stable).
        C'est l'étape 'Optimisation' des logiciels pros.
        """
        input_path = os.path.abspath(input_path)
        filename = Path(input_path).stem
        # Nom explicite pour ne pas confondre
        output_name = f"{filename}_PIVOT_60FPS.mp4"
        output_path = os.path.join(self.temp_dir, output_name)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            logger.info(f"Pivot existant trouvé : {output_path}")
            return output_path

        logger.info(f"Création du Master Pivot (Ceci peut prendre du temps)...")
        
        # fps=60 : On force 60 images/sec (FFmpeg duplique ou supprime pour s'aligner)
        # aresample : On force l'audio à s'aligner sur l'horloge vidéo
        cmd = [
            "ffmpeg", "-y", 
            "-i", input_path,
            "-filter_complex", "[0:v]fps=60,format=yuv420p[v];[0:a]aresample=44100:async=1[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-r", "60",
            output_name
        ]
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path

    def detect_silence(self, video_path, db_thresh=-35, min_silence_dur=0.4):
        """Analyse faite sur le PIVOT (donc temps fiables)"""
        video_name = os.path.basename(video_path)
        
        # Récup durée
        try:
            out, _ = self._run_ffmpeg(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_name])
            video_len = float(out.strip())
        except: video_len = 600.0

        # Détection
        cmd = ["ffmpeg", "-i", video_name, "-af", f"silencedetect=noise={db_thresh}dB:d={min_silence_dur}", "-f", "null", "-"]
        _, stderr = self._run_ffmpeg(cmd)
        
        silence_starts = []
        silence_ends = []
        for line in stderr.split('\n'):
            if "silence_start" in line:
                m = re.search(r"silence_start: ([\d\.]+)", line)
                if m: silence_starts.append(float(m.group(1)))
            elif "silence_end" in line:
                m = re.search(r"silence_end: ([\d\.]+)", line)
                if m: silence_ends.append(float(m.group(1)))
        
        segments = []
        curr = 0.0
        for i in range(len(silence_starts)):
            if silence_starts[i] > curr:
                segments.append((curr, silence_starts[i]))
            curr = silence_ends[i] if i < len(silence_ends) else video_len
        if curr < video_len:
            segments.append((curr, video_len))
            
        return segments

    def fast_cut_concat(self, video_path, segments, output_path):
        """
        Découpe 'Frame Perfect' basée sur le PIVOT.
        On convertit le Temps en Index d'Image.
        """
        if not segments: return video_path
        
        video_name = os.path.basename(video_path)
        FPS = 60
        SAMPLE_RATE = 44100
        SAMPLES_PER_FRAME = 735 # 44100/60
        PADDING = 0.15 # Marge de sécurité
        
        select_v = []
        select_a = []
        
        for start, end in segments:
            # Padding intelligent
            s = max(0, start - PADDING)
            e = end + PADDING
            
            # Conversion en Index (Le secret de la synchro)
            start_frame = int(round(s * FPS))
            end_frame = int(round(e * FPS))
            
            if end_frame <= start_frame: continue
            
            start_sample = start_frame * SAMPLES_PER_FRAME
            end_sample = end_frame * SAMPLES_PER_FRAME
            
            select_v.append(f"between(n,{start_frame},{end_frame})")
            select_a.append(f"between(n,{start_sample},{end_sample})")
            
        if not select_v: return video_path

        vf = f"select='{'+'.join(select_v)}',setpts=N/FRAME_RATE/TB"
        af = f"aselect='{'+'.join(select_a)}',asetpts=N/SR/TB"
        
        filter_file = os.path.join(self.temp_dir, "cut.txt")
        # On écrit le filtre complexe dans un fichier pour éviter la limite de caractères CMD
        with open(filter_file, "w") as f: f.write(f"{vf}[v];{af}[a]")
        
        cmd = [
            "ffmpeg", "-y", "-i", video_name,
            "-filter_complex_script", "cut.txt",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-r", "60",
            "-vsync", "cfr",
            os.path.basename(output_path)
        ]
        self._run_ffmpeg(cmd)
        return output_path

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
        
        try:
            segments, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
            return list(segments)
        except Exception as e:
            msg = str(e).lower()
            if "cublas" in msg or "dll" in msg or "library" in msg:
                logger.warning(f"⚠️ Erreur GPU Runtime ({e}). Bascule automatique vers CPU...")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
                segments, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
                return list(segments)
            else:
                raise e

    # === STEP 4: ASS GENERATION ===
    def generate_ass(self, segments, ass_path, highlight_words=None, subtitle_offset=0.0):
        if highlight_words is None:
            highlight_words = ["MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI"]
            
        def fmt_time(s):
            s = s + subtitle_offset
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            cs = int((s % 1) * 100)
            return f"{h}:{m:02}:{sec:02}.{cs:02}"
        
        def get_attr(seg, key, default=None):
            if isinstance(seg, dict): return seg.get(key, default)
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
                    words = get_attr(seg, 'words', None)
                    if words is None or len(words) == 0:
                        start = fmt_time(get_attr(seg, 'start', 0))
                        end = fmt_time(get_attr(seg, 'end', 0))
                        text = get_attr(seg, 'text', '').strip()
                        if text:
                            for kw in highlight_words:
                                if kw in text.upper():
                                    import re
                                    text = re.sub(f"({re.escape(kw)})", r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}", text, flags=re.IGNORECASE)
                            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
                        continue

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
                            val = w.word.strip()
                            if any(k in clean for k in highlight_words):
                                val = f"{{\\c&H00FFFF&}}{val}{{\\c&HFFFFFF&}}"
                            text_parts.append(val)
                        f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{' '.join(text_parts)}\n")
                except Exception as e:
                    logger.error(f"Error processing segment: {e}")
                    continue

    # === STEP 5: FINAL RENDER ===
    def render(self, video_path, ass_path, music_path, output_path):
        output_path = os.path.abspath(output_path)
        vid_rel = os.path.basename(video_path)
        ass_rel = os.path.basename(ass_path)
        
        # BULLETPROOF: Copier les fonts dans temp_dir
        fonts_in_temp = os.path.join(self.temp_dir, "fonts")
        os.makedirs(fonts_in_temp, exist_ok=True)
        import glob
        for font_file in glob.glob(os.path.join(self.assets_dir, "*.ttf")):
            shutil.copy2(font_file, os.path.join(fonts_in_temp, os.path.basename(font_file)))
        
        vf = f"ass={ass_rel}:fontsdir=fonts"
        inputs = ["-i", vid_rel]
        
        if music_path:
            mus_abs = os.path.abspath(music_path)
            inputs.extend(["-i", mus_abs])
            filter_complex = (
                f"[1:a]aloop=loop=-1:size=2e9,volume={0.15}[bgm];"
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
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest", output_path
        ])
        
        self._run_ffmpeg(cmd, cwd=self.temp_dir)
        return output_path
