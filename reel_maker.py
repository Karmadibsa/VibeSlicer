import os
import subprocess
import msvcrt
from datetime import timedelta

# ==================================================================================
# CUDA AUTO-DETECTION (Inject System Path for DLLs)
# ==================================================================================
if os.name == 'nt':
    try:
        os.add_dll_directory(os.getcwd())
        os.add_dll_directory(os.path.dirname(os.path.abspath(__file__)))
    except AttributeError:
        pass

cuda_path_v13 = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin"
if os.path.exists(cuda_path_v13):
    try:
        os.add_dll_directory(cuda_path_v13)
        print(f"✅ CUDA v13 chargé depuis : {cuda_path_v13}")
    except: pass
else:
    default_cuda = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.exists(default_cuda):
        try:
            versions = os.listdir(default_cuda)
            for v in versions:
                if v.startswith("v12"):
                    found_path = os.path.join(default_cuda, v, "bin")
                    if os.path.exists(found_path):
                        os.add_dll_directory(found_path)
                        print(f"✅ CUDA v12 trouvé et chargé : {found_path}")
                        break
        except: pass

# ==================================================================================

from dotenv import load_dotenv
from colorama import init, Fore, Style
import moviepy.editor as mp
from pydub import AudioSegment, silence
from faster_whisper import WhisperModel

init(autoreset=True)
load_dotenv()

# DETECT IMAGEMAGICK
if os.name == 'nt':
    try:
        from shutil import which
        im_path = which("magick")
        if im_path:
            os.environ["IMAGEMAGICK_BINARY"] = im_path
        else:
            common_paths = [
                r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe",
                r"C:\Program Files\ImageMagick-7.1.3-Q16-HDRI\magick.exe",
                r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
            ]
            for p in common_paths:
                if os.path.exists(p):
                    os.environ["IMAGEMAGICK_BINARY"] = p
                    break
    except:
        pass

if os.name == 'nt':
    target_im = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
    if os.path.exists(target_im):
        os.environ["IMAGEMAGICK_BINARY"] = target_im
        try:
            import moviepy.config_defaults
            moviepy.config_defaults.IMAGEMAGICK_BINARY = target_im
        except ImportError:
            pass
    else:
        print("  ⚠ ImageMagick not found at expected path. Trying 'magick' in PATH...")
        os.environ["IMAGEMAGICK_BINARY"] = "magick"

# ==================================================================================
# 1. CONFIGURATION
# ==================================================================================
CONFIG = {
    "INPUT_DIR": os.path.abspath("input"),
    "OUTPUT_DIR": os.path.abspath("output"),
    "ASSETS_DIR": os.path.abspath("assets"),
    "TEMP_DIR": os.path.abspath("temp"),
    "SILENCE_THRESH": -35,
    "MIN_SILENCE_LEN": 500,
    "PREVIEW_CTX": 1000,
    "WHISPER_MODEL_SIZE": "small",
    "COMPUTE_TYPE": "float16",
    "DEVICE": "cuda",
    "FONT_NAME": "Poppins-Bold.ttf",
    "FONT_SIZE": 80,
    "FONT_COLOR": "white",
    "STROKE_COLOR": "#8A2BE2",
    "STROKE_WIDTH": 3,
    "POS": ("center", "center"),
}

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
    total_s = ms / 1000.0
    minutes = int(total_s // 60)
    seconds = total_s % 60
    return f"{minutes:02d}:{seconds:06.3f}"

def get_font_path():
    asset_font = os.path.join(CONFIG["ASSETS_DIR"], CONFIG["FONT_NAME"])
    if os.path.exists(asset_font):
        return asset_font
    print_warn(f"Font not found at {asset_font}, using 'Arial' as fallback.")
    return "Arial"

# ==================================================================================
# 3. PHASE 1 — SPLIT INTO TWO GUI-CALLABLE FUNCTIONS
# ==================================================================================

def extract_and_detect_silences(video_path, silence_thresh=None, min_silence_len=None,
                                 progress_callback=None):
    """
    Phase 1a: Extract audio and detect silences.
    Returns (video, silences) where silences is a list of (start_ms, end_ms).
    progress_callback(float 0-1, str message) is called if provided.
    """
    thresh = silence_thresh if silence_thresh is not None else CONFIG["SILENCE_THRESH"]
    min_len = min_silence_len if min_silence_len is not None else CONFIG["MIN_SILENCE_LEN"]

    def _progress(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    _progress(0.0, "Chargement de la vidéo...")
    video = mp.VideoFileClip(video_path)

    audio_path = os.path.join(CONFIG["TEMP_DIR"], "temp_audio.wav")
    _progress(0.1, "Extraction de l'audio...")
    video.audio.write_audiofile(audio_path, logger=None)

    _progress(0.4, "Chargement de l'audio...")
    audio = AudioSegment.from_wav(audio_path)

    _progress(0.5, f"Détection des silences (seuil: {thresh}dB, min: {min_len}ms)...")
    silences = silence.detect_silence(
        audio,
        min_silence_len=min_len,
        silence_thresh=thresh
    )
    _progress(1.0, f"{len(silences)} silence(s) détecté(s).")
    return video, silences


def assemble_clips(video, silences, decisions, progress_callback=None):
    """
    Phase 1b: Assemble clips based on cut decisions.
    decisions: list of bool, same length as silences. True = cut, False = keep.
    Returns concatenated VideoFileClip or None if nothing to assemble.
    progress_callback(float 0-1, str message) is called if provided.
    """
    def _progress(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    final_clips = []
    current_pos_ms = 0

    for i, ((start_ms, end_ms), should_cut) in enumerate(zip(silences, decisions)):
        _progress(i / max(len(silences), 1), f"Traitement silence {i+1}/{len(silences)}...")
        if should_cut:
            if start_ms > current_pos_ms:
                seg = video.subclip(current_pos_ms / 1000.0, start_ms / 1000.0)
                final_clips.append(seg)
            current_pos_ms = end_ms

    # Add remainder
    video_len_ms = video.duration * 1000.0
    if current_pos_ms < video_len_ms:
        seg = video.subclip(current_pos_ms / 1000.0, video_len_ms / 1000.0)
        final_clips.append(seg)

    if not final_clips:
        video.close()
        return None

    _progress(0.9, "Assemblage des clips...")
    final_cut = mp.concatenate_videoclips(final_clips)
    video.close()
    _progress(1.0, "Assemblage terminé.")
    return final_cut


def save_raw_cut(cut_clip, raw_cut_path, progress_callback=None):
    """Save the assembled clip to disk and reload it. Returns reloaded VideoFileClip."""
    def _progress(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    _progress(0.0, f"Sauvegarde du montage brut...")
    try:
        cut_clip.write_videofile(
            raw_cut_path, fps=30, codec="h264_nvenc",
            audio_codec="aac", threads=4, preset="fast", logger=None
        )
    except Exception:
        cut_clip.write_videofile(
            raw_cut_path, fps=30, codec="libx264",
            audio_codec="aac", logger=None
        )
    cut_clip.close()
    _progress(0.9, "Rechargement depuis le disque...")
    reloaded = mp.VideoFileClip(raw_cut_path)
    _progress(1.0, "Montage brut prêt.")
    return reloaded


# ==================================================================================
# 4. PHASE 2 — TRANSCRIPTION (GUI-CALLABLE)
# ==================================================================================

def transcribe(cut_clip, progress_callback=None):
    """
    Phase 2: Run Whisper transcription on cut_clip audio.
    Returns list of {"start", "end", "word"} dicts and writes temp_subs.txt.
    progress_callback(float 0-1, str message) is called if provided.
    """
    def _progress(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    temp_audio = os.path.join(CONFIG["TEMP_DIR"], "cut_audio.wav")
    _progress(0.0, "Extraction audio pour transcription...")
    cut_clip.audio.write_audiofile(temp_audio, fps=44100, logger=None)

    def run_transcription_safe(device_type, compute_type):
        _progress(0.3, f"Transcription sur {device_type}...")
        model = WhisperModel(CONFIG["WHISPER_MODEL_SIZE"], device=device_type, compute_type=compute_type)
        segs, _ = model.transcribe(temp_audio, word_timestamps=True)
        return list(segs)

    try:
        segments_list = run_transcription_safe(CONFIG["DEVICE"], CONFIG["COMPUTE_TYPE"])
    except:
        import traceback
        traceback.print_exc()
        _progress(0.5, "GPU échoué — bascule sur CPU...")
        try:
            segments_list = run_transcription_safe("cpu", "int8")
        except Exception as cpu_e:
            raise cpu_e

    words_data = []
    for s in segments_list:
        for w in s.words:
            words_data.append({
                "start": w.start,
                "end": w.end,
                "word": w.word.strip()
            })

    txt_path = os.path.join(CONFIG["TEMP_DIR"], "temp_subs.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("# START | END | WORD\n")
        for wd in words_data:
            f.write(f"{wd['start']:.2f} | {wd['end']:.2f} | {wd['word']}\n")

    _progress(1.0, f"{len(words_data)} mots transcrits.")
    return words_data, txt_path


def load_subs_from_file(txt_path):
    """Parse temp_subs.txt and return list of {"start", "end", "word"}."""
    final_words = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    final_words.append({
                        "start": float(parts[0].strip()),
                        "end": float(parts[1].strip()),
                        "word": parts[2].strip()
                    })
                except:
                    pass
    return final_words


# ==================================================================================
# 5. PHASE 3 — BURN SUBTITLES (GUI-CALLABLE)
# ==================================================================================

def burn_subtitles(video_clip, words_data, output_path, progress_callback=None):
    """
    Phase 3: Burn subtitles onto video_clip and export to output_path.
    progress_callback(float 0-1, str message) is called if provided.
    """
    def _progress(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    _progress(0.0, "Création des clips de sous-titres...")
    font_path = get_font_path()
    fps = video_clip.fps or 30
    frame_duration = 1.0 / fps

    text_clips = []
    for item in words_data:
        start_frame = round(item["start"] * fps) / fps
        end_frame = round(item["end"] * fps) / fps
        duration = max(frame_duration, end_frame - start_frame)

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
        .set_start(start_frame)
        .set_duration(duration))
        text_clips.append(txt)

    _progress(0.3, "Composition vidéo + sous-titres...")
    final_video = mp.CompositeVideoClip([video_clip] + text_clips)

    _progress(0.4, f"Export vers {output_path}...")
    try:
        final_video.write_videofile(
            output_path, fps=30, codec="h264_nvenc",
            audio_codec="aac", preset="fast", threads=4
        )
    except Exception as e:
        _progress(0.5, f"NVENC échoué ({e}), bascule CPU...")
        final_video.write_videofile(
            output_path, fps=30, codec="libx264", audio_codec="aac"
        )

    _progress(1.0, f"Export terminé : {output_path}")
    return output_path


# ==================================================================================
# 6. CLI LEGACY — kept for backward compatibility (python reel_maker.py still works)
# ==================================================================================

def wait_for_key_validation():
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


def fast_cut_workflow(video_path):
    """Legacy CLI wrapper around extract_and_detect_silences + assemble_clips."""
    print_step("Phase 1: Fast Cut (Detection & Validation)")

    video, silences = extract_and_detect_silences(video_path)
    print_info(f"Found {len(silences)} potential cuts.")

    decisions = []
    auto_cut_remaining = False

    for i, (start_ms, end_ms) in enumerate(silences):
        if auto_cut_remaining:
            decisions.append(True)
            print(f"{Fore.RED}.{Style.RESET_ALL}", end="", flush=True)
            continue

        ctx = CONFIG["PREVIEW_CTX"]
        prev_start = max(0, start_ms - ctx)
        prev_end = end_ms + ctx
        prev_duration = (prev_end - prev_start) / 1000.0

        print(f"\n{Fore.MAGENTA}--- Silence #{i+1}: {format_time(start_ms)} -> {format_time(end_ms)} ({end_ms-start_ms}ms) ---")

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

        action = wait_for_key_validation()
        if action == 'cut':
            decisions.append(True)
        elif action == 'all':
            decisions.append(True)
            auto_cut_remaining = True
        else:
            decisions.append(False)

    return assemble_clips(video, silences, decisions)


def transcribe_and_burn(video_clip, original_filename):
    """Legacy CLI wrapper around transcribe + burn_subtitles."""
    print_step("Phase 2: Whisper Transcription")

    words_data, txt_path = transcribe(video_clip)

    print(f"\n{Fore.CYAN}--- PAUSE ---{Style.RESET_ALL}")
    print(f"Fichier de sous-titres généré : {Fore.YELLOW}{txt_path}{Style.RESET_ALL}")
    input(f"{Fore.WHITE}Editez le fichier si besoin, sauvegardez, puis appuyez sur [ENTRÉE] pour continuer...{Style.RESET_ALL}")

    final_words = load_subs_from_file(txt_path)

    print_step("Phase 3: Burning Subtitles (Clean Style)")
    name_root = os.path.splitext(original_filename)[0]
    output_filename = f"Reel_Ready_{name_root}.mp4"
    output_path = os.path.join(CONFIG["OUTPUT_DIR"], output_filename)

    burn_subtitles(video_clip, final_words, output_path)
    print(f"\n{Fore.GREEN}SUCCESS! Video ready: {output_path}{Style.RESET_ALL}")


def main():
    print(f"{Fore.MAGENTA}=== REEL MAKER: ESSENTIAL CUT & SUB ==={Style.RESET_ALL}")

    files = [f for f in os.listdir(CONFIG["INPUT_DIR"]) if f.lower().endswith(('.mp4', '.mov', '.mkv'))]
    if not files:
        print_warn(f"No video found in {CONFIG['INPUT_DIR']}")
        return

    print_info(f"Found {len(files)} video(s) to process.")

    for i, filename in enumerate(files):
        print(f"\n{Fore.CYAN}--- Processing File {i+1}/{len(files)}: {filename} ---{Style.RESET_ALL}")
        target_vid = os.path.join(CONFIG["INPUT_DIR"], filename)

        try:
            cut_clip = fast_cut_workflow(target_vid)

            if cut_clip is None:
                print_warn(f"Skipping {filename} — no content after cuts.")
                continue

            name_root = os.path.splitext(filename)[0]
            raw_cut_path = os.path.join(CONFIG["OUTPUT_DIR"], f"Raw_Cut_{name_root}.mp4")

            print_step(f"Saving Intermediate Cut Video to {raw_cut_path}...")
            cut_clip = save_raw_cut(cut_clip, raw_cut_path)
            print(f"{Fore.GREEN}>> Video monté (sans sous-titres) sauvegardé !{Style.RESET_ALL}")

            transcribe_and_burn(cut_clip, filename)

        except Exception as e:
            print(f"{Fore.RED}Error processing {filename}: {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
