import os
import sys
import subprocess
import shutil
import math
import time
from datetime import timedelta
import colorama
from colorama import Fore, Style, Back
from pydub import AudioSegment
from faster_whisper import WhisperModel

# Init Colorama
colorama.init(autoreset=True)

# Cores Config
class Config:
    INPUT_DIR = os.path.abspath("input")
    OUTPUT_DIR = os.path.abspath("output")
    TEMP_DIR = os.path.abspath("temp")
    ASSETS_DIR = os.path.abspath("assets")
    FONT_PATH = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")
    
    # Silence Detection
    SILENCE_THRESH = -40  # dB (Lower = keep more quiet sounds)
    MIN_SILENCE_LEN = 500 # ms
    KEEP_PADDING = 250    # ms (Smoother audio cuts)

    # Subtitle Dynamics
    MAX_WORDS_PER_LINE = 4  # TikTok/Reel style: 3-5 words max
    MAX_CHARS_PER_LINE = 20 # Safety limit

    # Style
    # MarginV lowered a bit for "Reel" center-bottom look
    SUB_STYLE = (
        "Fontname=Poppins,"
        "Fontsize=22,"
        "PrimaryColour=&HFFFFFF,"
        "OutlineColour=&HE22B8A,"
        "BorderStyle=1,"
        "Outline=3,"
        "Alignment=2,"
        "MarginV=120"
    )

def check_ffmpeg():
    """Vérifie si FFmpeg est installé et accessible."""
    print(Display.info("Vérification de FFmpeg..."))
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(Display.success("FFmpeg détecté."))
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(Display.error("CRITIQUE : FFmpeg n'est pas détecté dans le PATH."))
        sys.exit(1)

def format_timestamp_srt(seconds):
    """Convertit des secondes en format SRT (HH:MM:SS,mmm)."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def format_timestamp_ffmpeg(seconds):
    """Format precise pour ffmpeg concat file."""
    return f"{seconds:.3f}"

class Display:
    @staticmethod
    def title(text):
        return f"{Fore.CYAN}{Style.BRIGHT}\n=== {text} ==={Style.RESET_ALL}"
    
    @staticmethod
    def step(text):
        return f"{Fore.YELLOW}>> {text}{Style.RESET_ALL}"
    
    @staticmethod
    def success(text):
        return f"{Fore.GREEN}[OK] {text}{Style.RESET_ALL}"
    
    @staticmethod
    def error(text):
        return f"{Fore.RED}[ERREUR] {text}{Style.RESET_ALL}"
    
    @staticmethod
    def info(text):
        return f"{Fore.BLUE}[INFO] {text}{Style.RESET_ALL}"

def get_input_video():
    if not os.path.exists(Config.INPUT_DIR):
        os.makedirs(Config.INPUT_DIR)
    files = [f for f in os.listdir(Config.INPUT_DIR) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
    if not files:
        print(Display.error(f"Aucune vidéo trouvée dans {Config.INPUT_DIR}"))
        sys.exit(1)
    return os.path.join(Config.INPUT_DIR, files[0])

def analyze_audio_pydub(video_path):
    print(Display.step(" Extraction de l'audio pour analyse..."))
    temp_audio = os.path.join(Config.TEMP_DIR, "analysis_audio.wav")
    
    # Extract audio purely
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path, 
        "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        temp_audio
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    print(Display.step(" Analyse du volume (Pydub)..."))
    audio = AudioSegment.from_wav(temp_audio)
    
    from pydub.silence import detect_nonsilent
    input_len_ms = len(audio)
    
    nonsilent_ranges = detect_nonsilent(
        audio,
        min_silence_len=Config.MIN_SILENCE_LEN,
        silence_thresh=Config.SILENCE_THRESH,
        seek_step=50
    )
    
    if not nonsilent_ranges:
        print(Display.error("Aucune voix détectée !"))
        return []

    # Merge logic with padding
    segments_sec = []
    for start_ms, end_ms in nonsilent_ranges:
        start = max(0, start_ms - Config.KEEP_PADDING)
        end = min(input_len_ms, end_ms + Config.KEEP_PADDING)
        segments_sec.append((start / 1000.0, end / 1000.0))
    
    merged = []
    if segments_sec:
        current_start, current_end = segments_sec[0]
        for next_start, next_end in segments_sec[1:]:
            if next_start < current_end:
                current_end = max(current_end, next_end)
            else:
                merged.append((current_start, current_end))
                current_start, current_end = next_start, next_end
        merged.append((current_start, current_end))
    
    print(Display.success(f"Détecté {len(merged)} segments parlés."))
    return merged

def create_concat_file(segments, input_video, concat_filepath):
    """
    Crée un fichier .ffconcat qui liste les segments à garder.
    C'est BEAUCOUP plus robuste que le filtre 'select' pour la synchro.
    """
    # FFmpeg concat format requires escaped paths
    # Windows paths need forward slashes and extra escaping
    file_ref = input_video.replace("\\", "/").replace("'", "'\\''")
    
    with open(concat_filepath, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        f.write(f"# Generated by KarmaKut\n")
        
        for start, end in segments:
            f.write(f"file '{file_ref}'\n")
            f.write(f"inpoint {format_timestamp_ffmpeg(start)}\n")
            f.write(f"outpoint {format_timestamp_ffmpeg(end)}\n")

def step1_cut_silence(input_path, output_cut_path):
    print(Display.title("Étape 1 : Silence Remover (FFmpeg Concat Mode)"))
    
    segments = analyze_audio_pydub(input_path)
    if not segments:
        print(Display.info("Aucun silence à couper, copie simple..."))
        shutil.copy(input_path, output_cut_path)
        return

    # Method: Concat Demuxer
    concat_file = os.path.join(Config.TEMP_DIR, "cuts.ffconcat")
    create_concat_file(segments, input_path, concat_file)
    
    print(Display.info("Génération de la vidéo coupée via Concat Demuxer..."))
    
    # Note: On ré-encode ici pour fixer le timing une bonne fois pour toutes avant Whisper
    # Cela évite les bugs de timestamp bizarres dans Whisper
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-segment_time_metadata", "1",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        "-ac", "2",           # Force stereo
        "-ar", "44100",       # Force standard sample rate
        "-af", "aresample=async=1000", # Fix sync drift/gaps
        "-max_interleave_delta", "0",  # Fix buffering
        "-avoid_negative_ts", "make_zero",
        output_cut_path
    ]
    
    # print(" ".join(cmd))
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(Display.success("Cut terminé proprement."))
    except subprocess.CalledProcessError as e:
        print(Display.error("Erreur FFmpeg Concat:"))
        print(e.stderr.decode(errors='ignore'))
        sys.exit(1)

def generate_dynamic_srt(segments, srt_path):
    """
    Génère un SRT dynamique (style Reel/TikTok) en groupant par petits blocs de mots.
    """
    with open(srt_path, "w", encoding="utf-8") as f:
        idx = 1
        for segment in segments:
            # segment.words exists because we used word_timestamps=True
            words = segment.words
            
            # On groupe les mots
            current_group = []
            
            # Simple greedy grouping
            for i, word in enumerate(words):
                current_group.append(word)
                
                # Check breaks
                current_text = "".join([w.word for w in current_group]).strip()
                is_full = len(current_group) >= Config.MAX_WORDS_PER_LINE
                is_long = len(current_text) > Config.MAX_CHARS_PER_LINE
                is_last = (i == len(words) - 1)
                
                if is_full or is_long or is_last:
                    # Flush group
                    if not current_group: continue
                    
                    start_t = current_group[0].start
                    end_t = current_group[-1].end
                    text = "".join([w.word for w in current_group]).strip()
                    
                    f.write(f"{idx}\n")
                    f.write(f"{format_timestamp_srt(start_t)} --> {format_timestamp_srt(end_t)}\n")
                    f.write(f"{text}\n\n")
                    
                    idx += 1
                    current_group = []

def step2_transcribe(video_path, srt_path):
    print(Display.title("Étape 2 : Transcription Dynamique (Whisper)"))
    
    device = "cuda" if subprocess.run("nvidia-smi", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 else "cpu"
    print(Display.info(f"Mode: {device.upper()}"))
    
    try:
        model = WhisperModel("base", device=device, compute_type="float16" if device=="cuda" else "int8")
    except Exception:
        model = WhisperModel("base", device="cpu", compute_type="int8")

    print(Display.step("Transcribing with Word Timestamps..."))
    
    try:
        # word_timestamps=True is KEY for dynamic subtitles
        segments_gen, info = model.transcribe(video_path, beam_size=5, word_timestamps=True)
        # We need to convert generator to list to catch errors during iteration safely or iterate carefully
        # But faster-whisper executes lazily.
        
        # To handle CUDA errors during transcription (not just init), we wrap the generation
        segments = []
        try:
            for s in segments_gen:
                segments.append(s)
                print(f"\rRecu: {s.start:.1f}s -> {s.end:.1f}s...", end="")
        except RuntimeError as e:
             if "cublas" in str(e).lower() or "library" in str(e).lower():
                print(Display.error("\nCrash CUDA pendant la transcription."))
                print(Display.info("Restart complet sur CPU..."))
                model = WhisperModel("base", device="cpu", compute_type="int8")
                segments_gen, info = model.transcribe(video_path, beam_size=5, word_timestamps=True)
                segments = list(segments_gen)
             else:
                 raise e

    except RuntimeError as e:
        # Fallback for init errors caught late
        print(Display.info("Fallback CPU global."))
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments_gen, _ = model.transcribe(video_path, beam_size=5, word_timestamps=True)
        segments = list(segments_gen)

    print(Display.success(f"\nTranscription terminée. ({len(segments)} blocks)"))
    
    print(Display.step("Génération des sous-titres dynamiques..."))
    generate_dynamic_srt(segments, srt_path)
    
    print(Display.title("INTERVENTION RECOMMANDÉE"))
    print(f"{Fore.MAGENTA}Fichier: {srt_path}")
    input(f"{Back.WHITE}{Fore.BLACK} [ENTRÉE] pour continuer (modifiez le SRT si besoin)... {Style.RESET_ALL}")

def step3_burn_and_render(input_path, srt_path, final_output):
    print(Display.title("Étape 3 : Rendu Final 9:16"))
    
    srt_fixed = srt_path.replace("\\", "/").replace(":", "\\:")
    
    # 1. Crop 9:16 centered
    # 2. Burn subtitles
    
    # Note: On force un format de pixel standard (yuv420p) pour compatibilité maximale
    # On ajoute setpts=PTS pour être sûr
    
    vf_chain = (
        f"crop=ih*(9/16):ih,"
        f"subtitles='{srt_fixed}':force_style='{Config.SUB_STYLE}'"
    )
    
    codec = "libx264"
    # Check NVENC
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, text=True)
        if "h264_nvenc" in res.stdout:
            codec = "h264_nvenc"
            print(Display.success("NVENC Activé 🚀"))
    except: pass
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf_chain,
        "-c:v", codec,
        # Settings for quality/compatibility
        "-pix_fmt", "yuv420p", 
    ]
    
    if codec == "libx264":
        cmd.extend(["-preset", "slow", "-crf", "21"])
    else:
        cmd.extend(["-preset", "p4", "-rc", "vbr", "-cq", "22", "-b:v", "5M"])
        
    cmd.extend(["-c:a", "aac", "-b:a", "192k", final_output])
    
    print(Display.step("Rendu en cours..."))
    t0 = time.time()
    
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as p:
        for line in p.stdout:
            pass # Keep it clean or print dots
            # if "frame=" in line: print(f"\r{line.strip()}", end="")
            
    if p.returncode == 0:
        print(Display.success(f"TERMINÉ: {final_output} ({time.time()-t0:.1f}s)"))
    else:
        print(Display.error("Erreur Rendu."))

def main():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{Back.MAGENTA}{Fore.WHITE}  KARMAKUT V2.1 (STABLE)  {Style.RESET_ALL}")
    
    check_ffmpeg()
    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
    
    input_video = get_input_video()
    print(Display.info(f"Source: {os.path.basename(input_video)}"))
    
    cut_video = os.path.join(Config.TEMP_DIR, "video_cut.mp4")
    srt_file = os.path.join(Config.TEMP_DIR, "subtitles.srt")
    final_video = os.path.join(Config.OUTPUT_DIR, f"KarmaKut_{int(time.time())}.mp4")
    
    # 1. CUT (New Concat Engine)
    step1_cut_silence(input_video, cut_video)
    
    # 2. Transcribe (Dynamic SRT)
    step2_transcribe(cut_video, srt_file)
    
    # 3. Render
    step3_burn_and_render(cut_video, srt_file, final_video)
    
    print(Display.title("FINI."))

if __name__ == "__main__":
    main()
