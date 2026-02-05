import os
import subprocess
import shutil
import time
from datetime import timedelta
import colorama
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from faster_whisper import WhisperModel

# --- CONFIG DEFAULT ---
class TrimConfig:
    def __init__(self):
        self.silence_thresh = -40
        self.min_silence_len = 500
        self.keep_padding = 250
        self.input_dir = os.path.abspath("input")
        self.output_dir = os.path.abspath("output")
        self.temp_dir = os.path.abspath("temp")
        self.assets_dir = os.path.abspath("assets")

# --- UTILS ---
def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except:
        return False

def format_timestamp_ffmpeg(seconds):
    return f"{seconds:.3f}"

def format_timestamp_srt(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

# --- CORE LOGIC CLASS ---
class VibeProcessor:
    def __init__(self, config=None):
        self.cfg = config if config else TrimConfig()
        os.makedirs(self.cfg.temp_dir, exist_ok=True)
        os.makedirs(self.cfg.output_dir, exist_ok=True)

    def extract_audio(self, video_path):
        """Extract wav for analysis"""
        temp_audio = os.path.join(self.cfg.temp_dir, "analysis.wav")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            temp_audio
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return temp_audio

    def analyze_segments(self, audio_path, start_range=None, end_range=None):
        """Return raw segments [(start, end)] based on silence, filtering by range if provided"""
        audio = AudioSegment.from_wav(audio_path)
        input_len_ms = len(audio)
        
        # Determine strict analysis window
        clip_start_ms = int(start_range * 1000) if start_range is not None else 0
        clip_end_ms = int(end_range * 1000) if end_range is not None else input_len_ms
        
        # Safety: clip audio to analyze only the relevant part? 
        # Actually better to detect on whole and filter results, OR slice audio. 
        # Slicing is faster for analysis.
        
        audio_slice = audio[clip_start_ms:clip_end_ms]
        
        nonsilent_ranges = detect_nonsilent(
            audio_slice,
            min_silence_len=self.cfg.min_silence_len,
            silence_thresh=self.cfg.silence_thresh,
            seek_step=50
        )
        
        segments = []
        for start_ms, end_ms in nonsilent_ranges:
            # Shift back to absolute time
            abs_start = clip_start_ms + start_ms
            abs_end = clip_start_ms + end_ms
            
            # Padding
            start = max(0, abs_start - self.cfg.keep_padding)
            end = min(input_len_ms, abs_end + self.cfg.keep_padding)
            
            segments.append((start / 1000.0, end / 1000.0))
            
        # Merge overlaps
        if not segments: return []
        
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

    def create_cut_file(self, video_path, segments, concat_path):
        """Generates ffconcat file"""
        file_ref = video_path.replace("\\", "/").replace("'", "'\\''")
        with open(concat_path, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for start, end in segments:
                f.write(f"file '{file_ref}'\n")
                f.write(f"inpoint {format_timestamp_ffmpeg(start)}\n")
                f.write(f"outpoint {format_timestamp_ffmpeg(end)}\n")

    def render_cut(self, concat_path, output_path):
        """Render the cut video (intermediate)"""
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-ac", "2", "-ar", "44100",
            "-af", "aresample=async=1000",
            "-avoid_negative_ts", "make_zero",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def transcribe(self, video_path, model_size="base"):
        """Returns whisper segments list directly with robust error handling"""
        try:
            device = "cuda" if subprocess.run("nvidia-smi", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 else "cpu"
            model = WhisperModel(model_size, device=device, compute_type="float16" if device=="cuda" else "int8")
        except Exception:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            
        try:
            segments_gen, _ = model.transcribe(video_path, word_timestamps=True)
            return list(segments_gen)
        except RuntimeError as e:
            if "cublas" in str(e).lower() or "library" in str(e).lower():
                print("CUDA Error detected in core, switching to CPU...")
                model = WhisperModel(model_size, device="cpu", compute_type="int8")
                segments_gen, _ = model.transcribe(video_path, word_timestamps=True)
                return list(segments_gen)
            else:
                raise e

    def generate_srt(self, segments, srt_path, max_words=4, uppercase=False):
        """Generates dynamic srt"""
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
                        if not current_group: continue
                        start = current_group[0].start
                        end = current_group[-1].end
                        text = "".join([w.word for w in current_group]).strip()
                        if uppercase: text = text.upper()
                        
                        f.write(f"{idx}\n")
                        f.write(f"{format_timestamp_srt(start)} --> {format_timestamp_srt(end)}\n")
                        f.write(f"{text}\n\n")
                        idx += 1
                        current_group = []

    def burn_subtitle_and_title(self, video_path, srt_path, output_path, title_text="", title_duration=3, style_cfg=None):
        """Final render with subtitles and optional title"""
        srt_fixed = srt_path.replace("\\", "/").replace(":", "\\:")
        
        # Default Style
        font_name = "Poppins"
        font_size = 22
        primary_color = "&HFFFFFF"
        outline_color = "&HE22B8A"
        
        if style_cfg:
            # Override if provided
            pass 

        style_str = (f"Fontname={font_name},Fontsize={font_size},"
                     f"PrimaryColour={primary_color},OutlineColour={outline_color},"
                     f"BorderStyle=1,Outline=3,Alignment=2,MarginV=120")

        # Filters
        filters = [
            "crop=ih*(9/16):ih", # Crop Portrait
            f"subtitles='{srt_fixed}':force_style='{style_str}'"
        ]
        
        # Add Title if present (drawtext)
        if title_text:
            # Escape text for FFmpeg: escape single quotes and colons
            title_text = title_text.replace("'", "").replace(":", "\\:")
            
            # Absolute font path with FFmpeg escaping
            font_path = os.path.join(self.cfg.assets_dir, "Poppins-Bold.ttf").replace("\\", "/").replace(":", "\\:")
            
            drawtext = (f"drawtext=fontfile='{font_path}':text='{title_text}':"
                        f"fontcolor=white:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/3:"
                        f"borderw=2:bordercolor=black:enable='between(t,0,{title_duration})'")
            # Insert before subtitles so subs are on top? Or after? Usually title is overlay.
            # Let's put title AFTER crop, combined with subtitles
            filters.insert(1, drawtext)

        vf_chain = ",".join(filters)
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "slow", "-crf", "21",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
