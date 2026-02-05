import os
import time
import subprocess
import msvcrt
from datetime import timedelta

# Third-party imports
from dotenv import load_dotenv
from colorama import init, Fore, Style
import moviepy.editor as mp
from pydub import AudioSegment, silence
from faster_whisper import WhisperModel

# Initialize colorama
init(autoreset=True)
load_dotenv()

# ==================================================================================
# 1. CONFIGURATION
# ==================================================================================
CONFIG = {
    # Folders
    "INPUT_DIR": os.path.abspath("input"),
    "OUTPUT_DIR": os.path.abspath("output"),
    "ASSETS_DIR": os.path.abspath("assets"),
    "TEMP_DIR": os.path.abspath("temp"),
    
    # Silence Detection
    "SILENCE_THRESH": -35,      # dB
    "MIN_SILENCE_LEN": 500,     # milliseconds (0.5s)
    "PREVIEW_CTX": 1000,        # milliseconds (1s) context before/after
    
    # Transcription / AI
    "WHISPER_MODEL_SIZE": "small",
    "COMPUTE_TYPE": "float16",
    "DEVICE": "cuda",
    
    # Subtitles Design
    "FONT_NAME": "Poppins-Bold.ttf", # Expected in assets/
    "FONT_SIZE": 80,
    "FONT_COLOR": "white",
    "STROKE_COLOR": "#8A2BE2", # Purple
    "STROKE_WIDTH": 3,
    "POS": ("center", "center"),
}

# Ensure directories exist
for d in [CONFIG["INPUT_DIR"], CONFIG["OUTPUT_DIR"], CONFIG["ASSETS_DIR"], CONFIG["TEMP_DIR"]]:
    os.makedirs(d, exist_ok=True)

# ==================================================================================
# 2. HELPER FUNCTIONS
# ==================================================================================

def print_step(msg):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[STEP] {msg}{Style.RESET_ALL}")

def print_info(msg):
    print(f"{Fore.GREEN}  ℹ {msg}")

def print_warn(msg):
    print(f"{Fore.YELLOW}  ⚠ {msg}")

def format_time(ms):
    """Convert ms to MM:SS.mmm"""
    td = timedelta(milliseconds=ms)
    return str(td)[:-3]

def get_font_path():
    asset_font = os.path.join(CONFIG["ASSETS_DIR"], CONFIG["FONT_NAME"])
    if os.path.exists(asset_font):
        return asset_font
    # Fallback/Warning logic could go here, but MoviePy might handle system fonts by name.
    # However, user explicitly asked to load 'assets/Poppins-Bold.ttf'.
    print_warn(f"Font not found at {asset_font}, using 'Arial' as fallback.")
    return "Arial"

def wait_for_key_validation():
    """
    Waits for user input: 
    [Space] -> Cut ('cut')
    [N] -> Keep ('keep')
    [A] -> Cut All ('all')
    """
    print(f"{Fore.YELLOW}  >> [ESPACE] Couper | [N] Garder | [A] TOUT Couper (Auto){Style.RESET_ALL}", end="", flush=True)
    
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch().lower()
            if key == b' ':
                print(f"\n  {Fore.RED}X Coupé{Style.RESET_ALL}")
                return 'cut'
            elif key == b'n':
                print(f"\n  {Fore.GREEN}O Gardé{Style.RESET_ALL}")
                return 'keep'
            elif key == b'a':
                print(f"\n  {Fore.RED}>>> ACTIVATION AUTO-CUT <<< (Coupe tout le reste){Style.RESET_ALL}")
                return 'all'

# ==================================================================================
# 3. PHASE 1: FAST CUT
# ==================================================================================

def fast_cut_workflow(video_path):
    print_step("Phase 1: Fast Cut (Detection & Validation)")
    
    # 1. Extract audio for analysis
    audio_path = os.path.join(CONFIG["TEMP_DIR"], "temp_audio.wav")
    video = mp.VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path, logger=None)
    
    audio = AudioSegment.from_wav(audio_path)
    print_info(f"Audio duration: {format_time(len(audio))}")
    
    # 2. Detect Silences
    print_info(f"Detecting silences (Thresh: {CONFIG['SILENCE_THRESH']}dB, Min: {CONFIG['MIN_SILENCE_LEN']}ms)...")
    silences = silence.detect_silence(
        audio, 
        min_silence_len=CONFIG["MIN_SILENCE_LEN"], 
        silence_thresh=CONFIG["SILENCE_THRESH"]
    )
    print_info(f"Found {len(silences)} potential cuts.")
    
    # 3. Validation Loop
    # We build a list of segments to KEEP.
    # Start with current_pos = 0. If we cut a silence, we keep 0->silence_start, then current_pos = silence_end.
    # If we keep a silence, we don't update current_pos, effectively merging it.
    
    final_clips = []
    current_pos_ms = 0
    auto_cut_remaining = False
    
    for i, (start_ms, end_ms) in enumerate(silences):
        # Logic: We are currently at current_pos_ms.
        # Check this silence from start_ms to end_ms.
        
        should_cut = False
        
        if auto_cut_remaining:
            should_cut = True
        else:
            # Determine context for preview
            ctx = CONFIG["PREVIEW_CTX"]
            prev_start = max(0, start_ms - ctx)
            prev_end = end_ms + ctx
            prev_duration = (prev_end - prev_start) / 1000.0
            
            print(f"\n{Fore.MAGENTA}--- Silence #{i+1}: {format_time(start_ms)} -> {format_time(end_ms)} ({end_ms-start_ms}ms) ---")
            
            # Launch FFplay preview
            cmd = [
                "ffplay", 
                "-ss", str(prev_start / 1000.0), 
                "-t", str(prev_duration), 
                "-autoexit", 
                "-window_title", f"CUT #{i+1} ?",
                "-x", "500", "-y", "300",
                "-hide_banner", "-loglevel", "error",
                video_path
            ]
            try:
                subprocess.run(cmd)
            except FileNotFoundError:
                print(f"\n{Fore.RED}[ERREUR] 'ffplay' non trouvé !{Style.RESET_ALL}")
            
            # Ask User
            action = wait_for_key_validation()
            if action == 'cut':
                should_cut = True
            elif action == 'all':
                should_cut = True
                auto_cut_remaining = True
            else:
                should_cut = False # Keep
        
        if should_cut:
            if auto_cut_remaining:
                print(f"{Fore.RED}.{Style.RESET_ALL}", end="", flush=True) # Minimal feedback in auto mode

            # We cut this silence.
            # Keep anything from current_pos_ms to start_ms
            if start_ms > current_pos_ms:
                # Add segment
                seg = video.subclip(current_pos_ms / 1000.0, start_ms / 1000.0)
                final_clips.append(seg)
            
            # Move current_pos to after the silence
            current_pos_ms = end_ms
        else:
            # Keep silence, effectively skipping logic
            pass
            
    # Add remainder of video
    video_len_ms = len(audio)
    if current_pos_ms < video_len_ms:
        seg = video.subclip(current_pos_ms / 1000.0, video_len_ms / 1000.0)
        final_clips.append(seg)
        
    print_step("Assembling clips...")
    final_cut = mp.concatenate_videoclips(final_clips)
    return final_cut

# ==================================================================================
# 4. PHASE 2 & 3: SUBTITLES & EXPORT
# ==================================================================================

def transcribe_and_burn(video_clip, original_filename):
    print_step("Phase 2: Whisper Transcription")
    
    # Export temp audio of the CUT video
    temp_audio = os.path.join(CONFIG["TEMP_DIR"], "cut_audio.wav")
    # Fix for 'CompositeAudioClip has no fps': specify fps (e.g., 44100)
    video_clip.audio.write_audiofile(temp_audio, fps=44100, logger=None)
    
    # Load Whisper
    print_info(f"Loading Whisper ({CONFIG['WHISPER_MODEL_SIZE']}) on {CONFIG['DEVICE']}...")
    # try:
    #     model = WhisperModel(CONFIG["WHISPER_MODEL_SIZE"], device=CONFIG["DEVICE"], compute_type=CONFIG["COMPUTE_TYPE"])
    # except (Exception, OSError, RuntimeError) as e:
    #     print_warn(f"GPU Load Failed (CUDA missing?): {e}")
    #     print_warn("Falling back to CPU (slower but works)...")
    #     model = WhisperModel(CONFIG["WHISPER_MODEL_SIZE"], device="cpu", compute_type="int8")

    # FORCE CPU TEMPORARILY - CUDA INSTALL TOO COMPLEX FOR NOW
    print_warn("Forcing CPU mode (simplest setup)...")
    model = WhisperModel(CONFIG["WHISPER_MODEL_SIZE"], device="cpu", compute_type="int8")

        
    segments, info = model.transcribe(temp_audio, word_timestamps=True)
    
    # Accumulate words
    words_data = []
    for s in segments:
        for w in s.words:
            words_data.append({
                "start": w.start,
                "end": w.end,
                "word": w.word.strip()
            })
            
    # Save to temp_subs.txt
    txt_path = "temp_subs.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("# START | END | WORD\n")
        for wd in words_data:
            f.write(f"{wd['start']:.2f} | {wd['end']:.2f} | {wd['word']}\n")
            
    print(f"\n{Fore.CYAN}--- PAUSE ---{Style.RESET_ALL}")
    print(f"Fichier de sous-titres généré : {Fore.YELLOW}{txt_path}{Style.RESET_ALL}")
    input(f"{Fore.WHITE}Editez le fichier si besoin, sauvegardez, puis appuyez sur [ENTRÉE] pour continuer...{Style.RESET_ALL}")
    
    # Reload subs
    final_words = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    final_words.append({
                        "start": float(parts[0].strip()),
                        "end": float(parts[1].strip()),
                        "word": parts[2].strip()
                    })
                except: pass
                
    # Create Clips (Phase 3)
    print_step("Phase 3: Burning Subtitles (Clean Style)")
    font_path = get_font_path()
    
    text_clips = []
    for item in final_words:
        # Create TextClip
        # center, center
        txt = (mp.TextClip(
            item["word"],
            font=font_path,
            fontsize=CONFIG["FONT_SIZE"],
            color=CONFIG["FONT_COLOR"],
            stroke_color=CONFIG["STROKE_COLOR"],
            stroke_width=CONFIG["STROKE_WIDTH"],
            method='label'
        )
        .set_position(CONFIG["POS"])
        .set_start(item["start"])
        .set_duration(item["end"] - item["start"]))
        
        text_clips.append(txt)
        
    # Composite
    final_video = mp.CompositeVideoClip([video_clip] + text_clips)
    
    # Export
    name_root = os.path.splitext(original_filename)[0]
    output_filename = f"Reel_Ready_{name_root}.mp4"
    output_path = os.path.join(CONFIG["OUTPUT_DIR"], output_filename)
    
    print_step(f"Exporting to {output_path} (NVENC)...")

    try:
        final_video.write_videofile(
            output_path,
            fps=30,
            codec="h264_nvenc",
            audio_codec="aac",
            preset="fast",
            threads=4
        )
    except Exception as e:
        print_warn(f"NVENC failed ({e}). Using CPU (libx264).")
        final_video.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac"
        )
        
    print(f"\n{Fore.GREEN}SUCCESS! Video ready: {output_path}{Style.RESET_ALL}")

# ==================================================================================
# MAIN ENTRY
# ==================================================================================

def main():
    print(f"{Fore.MAGENTA}=== REEL MAKER: ESSENTIAL CUT & SUB ==={Style.RESET_ALL}")
    
    # Find videos
    files = [f for f in os.listdir(CONFIG["INPUT_DIR"]) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
    if not files:
        print_warn(f"No video found in {CONFIG['INPUT_DIR']}")
        return
    
    print_info(f"Found {len(files)} video(s) to process.")

    for i, filename in enumerate(files):
        print(f"\n{Fore.CYAN}--- Processing File {i+1}/{len(files)}: {filename} ---{Style.RESET_ALL}")
        target_vid = os.path.join(CONFIG["INPUT_DIR"], filename)
        
        # 1. Fast Cut
        # We need to wrap the whole process per file
        try:
            cut_clip = fast_cut_workflow(target_vid)
            
            # SAVE INTERMEDIATE CUT (Raw video before subtitles)
            name_root = os.path.splitext(filename)[0]
            raw_cut_name = f"Raw_Cut_{name_root}.mp4"
            raw_cut_path = os.path.join(CONFIG["OUTPUT_DIR"], raw_cut_name)
            
            print_step(f"Saving Intermediate Cut Video to {raw_cut_path}...")
            # Use same encoding settings as final export for consistency
            cut_clip.write_videofile(
                raw_cut_path,
                fps=30,
                codec="h264_nvenc", # Or libx264 if nvenc fails, but let's stick to default trial
                audio_codec="aac",
                threads=4,
                preset="fast",
                logger=None # Less spam
            )
            print(f"{Fore.GREEN}>> Video monté (sans sous-titres) sauvegardé !{Style.RESET_ALL}")
            
            # 2. Transcription & Burn
            # Pass the filename to helper to generate better output name
            transcribe_and_burn(cut_clip, filename)
            
        except Exception as e:
            print(f"{Fore.RED}Error processing {filename}: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
