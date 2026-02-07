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

    def render_final_video(self, video_path, srt_path, output_path, title_text="", title_color="#8A2BE2", music_path=None, style_cfg=None):
        """Advanced Render: Intro Freeze (1s), Music Mix (10%), Subtitles, Title"""
        
        # 1. Prepare paths
        srt_fixed = srt_path.replace("\\", "/").replace(":", "\\:")
        if music_path: music_path = music_path.replace("\\", "/")
        
        # Style Config
        font_name = "Poppins"
        font_size = 22
        
        # Default Violet for Outline if not specified
        primary_color = style_cfg.get("primary_color", "&HFFFFFF") if style_cfg else "&HFFFFFF"
        outline_color = style_cfg.get("outline_color", "&HE22B8A") if style_cfg else "&HE22B8A"
        
        style_str = (f"Fontname={font_name},Fontsize={font_size},"
                     f"PrimaryColour={primary_color},OutlineColour={outline_color},"
                     f"BorderStyle=1,Outline=3,Alignment=2,MarginV=120")

        # 2. INTRO GENERATION (If Title exists)
        main_input = video_path
        
        if title_text:
            intro_path = os.path.join(self.cfg.temp_dir, "intro_freeze.mp4")
            # a) Extract frame 0 image
            frame0_img = os.path.join(self.cfg.temp_dir, "frame0.jpg")
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path, "-vframes", "1", "-q:v", "2", frame0_img
            ], check=True)
            
            # b) Create 1s Blurred Video with Title
            # Title Font setup
            title_text = title_text.replace("'", "").replace(":", "\\:")
            font_path = os.path.join(self.cfg.assets_dir, "Poppins-Bold.ttf").replace("\\", "/").replace(":", "\\:")
            
            # Filter: Loop img -> Crop 9:16 -> Blur -> DrawText
            # Ensure output is YUV420P standard
            # Intro duration: 1s
            vf_intro = (
                f"loop=30:1,crop=ih*(9/16):ih,boxblur=20:5,"
                f"drawtext=fontfile='{font_path}':text='{title_text}':"
                f"fontcolor={title_color}:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2:"
                f"borderw=5:bordercolor=black"
            )
            
            # Generate Silent Audio for Intro (1s)
            subprocess.run([
                "ffmpeg", "-y", 
                "-loop", "1", "-i", frame0_img,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-vf", vf_intro,
                "-t", "1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                intro_path
            ], check=True)
            
            has_intro = True
        else:
            has_intro = False

        # 3. PROCESS BODY (Crop + Subtitles)
        body_path = os.path.join(self.cfg.temp_dir, "body_processed.mp4")
        vf_body = f"crop=ih*(9/16):ih,subtitles='{srt_fixed}':force_style='{style_str}'"
        
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf_body,
            "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            body_path
        ], check=True)
        
        # 4. CONCAT (Intro + Body)
        if has_intro:
            concat_list = os.path.join(self.cfg.temp_dir, "final_concat.txt")
            i_p = intro_path.replace("\\", "/")
            b_p = body_path.replace("\\", "/")
            
            with open(concat_list, "w") as f:
                f.write(f"file '{i_p}'\n")
                f.write(f"file '{b_p}'\n")
            
            video_no_music = os.path.join(self.cfg.temp_dir, "video_nomusic.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                "-c", "copy", video_no_music
            ], check=True)
        else:
            video_no_music = body_path # Just usage
        
        # 5. MIX MUSIC (If present)
        if music_path and os.path.exists(music_path):
            # Volume 0.10 (10%)
            cmd_mix = [
                "ffmpeg", "-y",
                "-i", video_no_music,
                "-i", music_path,
                "-filter_complex", "[1:a]volume=0.10[bgm];[0:a][bgm]amix=inputs=2:duration=first[mixed];[mixed]volume=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ]
            subprocess.run(cmd_mix, check=True)
            
        else:
            shutil.copy(video_no_music, output_path)

    def burn_subtitles(self, video_path, srt_path, output_path, style=None):
        """Burns subtitles into video using ffmpeg"""
        # Style formatting for ASS/SRT
        # Default style if none provided (Alignment=2 is Bottom-Center)
        style_str = "Fontname=Arial,Fontsize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=30,Alignment=2"
        
        if style:
            # Construct style string from dict
            # Example: style={"PrimaryColour": "&H00FFFF"}
            # We can merge with default or build fresh. 
            # Simple merge:
            defaults = {
                "Fontname": "Arial", "Fontsize": "24", 
                "PrimaryColour": "&HFFFFFF", "OutlineColour": "&H000000",
                "BorderStyle": "1", "Outline": "2", "Shadow": "0", "MarginV": "30",
                "Alignment": "2"
            }
            defaults.update(style)
            style_str = ",".join([f"{k}={v}" for k, v in defaults.items()])

        # Escape paths for ffmpeg filter
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            "ffmpeg", "-y", 
            "-i", video_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{style_str}'",
            "-c:a", "copy",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def add_background_music(self, video_path, music_path, output_path, volume=0.1):
        """Mixes background music with video audio"""
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
