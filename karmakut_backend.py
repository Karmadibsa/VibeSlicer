"""
VibeSlicer Studio - Backend Core
Version: 2.1 (Lazy Loading)
"""

import os
import subprocess
import shutil
import re
from datetime import timedelta


# --- CONFIGURATION ---
class VideoConfig:
    """Configuration pour le traitement vidéo"""
    def __init__(self):
        self.silence_thresh = -40  # dB
        self.min_silence_len = 500  # ms
        self.keep_padding = 250  # ms
        self.input_dir = os.path.abspath("input")
        self.output_dir = os.path.abspath("output")
        self.temp_dir = os.path.abspath("temp")
        self.assets_dir = os.path.abspath("assets")
        self.highlight_keywords = ["MDR", "FOU", "ATTENTION", "GAGNÉ", "INCROYABLE", "WOW", "OUFF"]


# --- UTILITIES ---
def check_ffmpeg():
    """Vérifie si FFmpeg est disponible"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except:
        return False


def format_timestamp_srt(seconds):
    """Formatte un timestamp pour SRT (HH:MM:SS,mmm)"""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _setup_cuda_dlls():
    """Configure les DLLs CUDA (appelé uniquement quand nécessaire)"""
    import pathlib
    import site
    
    print("🔍 Vérification CUDA...")
    try:
        possible_paths = site.getsitepackages() + [site.getusersitepackages()]
        for p in possible_paths:
            nvidia_path = pathlib.Path(p) / "nvidia"
            if nvidia_path.exists():
                print(f"  ✓ Trouvé: {nvidia_path}")
                for lib_dir in nvidia_path.iterdir():
                    if lib_dir.is_dir():
                        bin_dir = lib_dir / "bin"
                        if bin_dir.exists():
                            os.add_dll_directory(str(bin_dir))
                            os.environ["PATH"] = str(bin_dir) + ";" + os.environ["PATH"]
                            print(f"    ✓ DLL: {bin_dir.name}")
                return True
    except Exception as e:
        print(f"  ⚠️  Erreur CUDA: {e}")
    return False


# --- CORE PROCESSOR ---
class VibeProcessor:
    """Processeur principal pour VibeSlicer Studio"""
    
    def __init__(self, config=None):
        self.cfg = config if config else VideoConfig()
        self.whisper_model = None  # Lazy loading
        os.makedirs(self.cfg.temp_dir, exist_ok=True)
        os.makedirs(self.cfg.output_dir, exist_ok=True)
    
    def _load_whisper(self, model_size="base"):
        """Charge Whisper à la demande (lazy loading)"""
        if self.whisper_model is not None:
            return self.whisper_model
        
        # Setup CUDA DLLs first
        _setup_cuda_dlls()
        
        # Import whisper
        from faster_whisper import WhisperModel
        
        print(f"🎤 Chargement Whisper ({model_size})...")
        try:
            print("  🚀 GPU (CUDA)...")
            self.whisper_model = WhisperModel(model_size, device="cuda", compute_type="float16")
            print("  ✅ GPU OK !")
        except Exception as e:
            print(f"  ⚠️  GPU échoué: {e}")
            print("  🐌 CPU fallback...")
            self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print("  ✅ CPU OK")
        
        return self.whisper_model
    
    # === STEP 1: Audio Extraction ===
    def extract_audio(self, video_path):
        """Extrait l'audio de la vidéo"""
        temp_audio = os.path.join(self.cfg.temp_dir, "analysis.wav")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            temp_audio
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return temp_audio
    
    # === STEP 2: Silence Detection ===
    def analyze_silence(self, audio_path):
        """Détecte les segments non-silencieux"""
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
        
        audio = AudioSegment.from_wav(audio_path)
        input_len_ms = len(audio)
        
        nonsilent_ranges = detect_nonsilent(
            audio,
            min_silence_len=self.cfg.min_silence_len,
            silence_thresh=self.cfg.silence_thresh,
            seek_step=50
        )
        
        segments = []
        for start_ms, end_ms in nonsilent_ranges:
            start = max(0, start_ms - self.cfg.keep_padding)
            end = min(input_len_ms, end_ms + self.cfg.keep_padding)
            segments.append((start / 1000.0, end / 1000.0))
        
        if not segments:
            return []
        
        # Merge overlapping
        merged = []
        curr_start, curr_end = segments[0]
        for next_start, next_end in segments[1:]:
            if next_start < curr_end:
                curr_end = max(curr_end, next_end)
            else:
                merged.append((curr_start, curr_end))
                curr_start, curr_end = next_start, next_end
        merged.append((curr_start, curr_end))
        
        return merged
    
    # === STEP 3: Transcription ===
    def transcribe(self, video_path, model_size="base"):
        """Transcrit l'audio avec Whisper"""
        model = self._load_whisper(model_size)
        
        try:
            segments_gen, _ = model.transcribe(video_path, word_timestamps=True, language="fr")
            return list(segments_gen)
        except RuntimeError as e:
            if "cublas" in str(e).lower() or "library" in str(e).lower():
                print("  ⚠️  Erreur CUDA, retry CPU...")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
                segments_gen, _ = self.whisper_model.transcribe(video_path, word_timestamps=True, language="fr")
                return list(segments_gen)
            raise
    
    # === STEP 4: SRT Generation ===
    def generate_srt_with_highlights(self, segments, srt_path, max_words=2, uppercase=True):
        """Génère un SRT avec mots-clés en jaune"""
        with open(srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for seg in segments:
                words = seg.words
                current_group = []
                
                for i, word in enumerate(words):
                    current_group.append(word)
                    is_full = len(current_group) >= max_words
                    is_last = (i == len(words) - 1)
                    
                    if is_full or is_last:
                        if not current_group:
                            continue
                        
                        start = current_group[0].start
                        end = current_group[-1].end
                        text = "".join([w.word for w in current_group]).strip()
                        
                        if uppercase:
                            text = text.upper()
                        
                        for keyword in self.cfg.highlight_keywords:
                            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                            text = pattern.sub(lambda m: f'<font color="#FFFF00">{m.group()}</font>', text)
                        
                        f.write(f"{idx}\n")
                        f.write(f"{format_timestamp_srt(start)} --> {format_timestamp_srt(end)}\n")
                        f.write(f"{text}\n\n")
                        idx += 1
                        current_group = []
    
    # === STEP 5: Final Render ===
    def render_final(self, video_path, srt_path, output_path, music_path=None):
        """Rendu final (no crop, loudnorm, music mix)"""
        print("🎬 Rendu Final...")
        
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        
        style_str = (
            "Fontname=Poppins-Bold,Fontsize=14,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&HE22B8A,"
            "BorderStyle=1,Outline=1,Shadow=1,Alignment=2,MarginV=40"
        )
        
        temp_video = os.path.join(self.cfg.temp_dir, "temp_subtitled.mp4")
        vf = f"subtitles='{srt_escaped}':force_style='{style_str}'"
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
        
        cmd_base = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf, "-af", af,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            temp_video
        ]
        
        print("  🎨 Subtitles + audio...")
        subprocess.run(cmd_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        if music_path and os.path.exists(music_path):
            print(f"  🎶 Music mix (10%)...")
            cmd_music = [
                "ffmpeg", "-y",
                "-i", temp_video, "-i", music_path,
                "-filter_complex", 
                "[1:a]volume=0.1,aloop=loop=-1:size=2e9[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
            subprocess.run(cmd_music, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        else:
            shutil.copy(temp_video, output_path)
        
        print(f"  ✅ Done: {output_path}")
        return output_path
    
    def get_video_duration(self, video_path):
        """Récupère la durée de la vidéo en secondes"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())


# === TEST ===
if __name__ == "__main__":
    print("=" * 50)
    print("VibeSlicer Backend Test")
    print("=" * 50)
    print(f"FFmpeg: {check_ffmpeg()}")
    print("✅ Backend OK (lazy loading - no Whisper loaded yet)")

