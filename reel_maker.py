"""
reel_maker.py — Moteur de traitement vidéo (FFmpeg pur, zéro moviepy)
Toutes les opérations vidéo passent par des sous-processus ffmpeg/ffprobe.
Aucun DLL hack, aucun chemin codé en dur.
"""
import os
import subprocess
from datetime import timedelta

from dotenv import load_dotenv
from colorama import init, Fore, Style
from pydub import AudioSegment
from pydub import silence as pydub_silence

init(autoreset=True)
load_dotenv()

# ── Windows: pas de fenêtre console lors des appels ffmpeg ───────────────────
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# ==================================================================================
# 1. CONFIGURATION
# ==================================================================================
CONFIG = {
    "INPUT_DIR":  os.path.abspath("input"),
    "OUTPUT_DIR": os.path.abspath("output"),
    "ASSETS_DIR": os.path.abspath("assets"),
    "TEMP_DIR":   os.path.abspath("temp"),
    # Détection des silences
    "SILENCE_THRESH":    -54,   # dB (valeur basse = uniquement vrais silences)
    "MIN_SILENCE_LEN":   500,   # ms
    # Whisper
    "WHISPER_MODEL_SIZE": "small",
    "COMPUTE_TYPE": "float16",
    "DEVICE":       "cuda",
    # Sous-titres (style ASS compatible FFmpeg)
    "SUB_STYLE": (
        "Fontname=Poppins,"
        "Fontsize=22,"
        "PrimaryColour=&HFFFFFF,"
        "OutlineColour=&HE22B8A,"
        "BorderStyle=1,"
        "Outline=3,"
        "Alignment=2,"
        "MarginV=40"
    ),
    "MAX_WORDS_PER_SUB": 8,
}

for d in [CONFIG["INPUT_DIR"], CONFIG["OUTPUT_DIR"], CONFIG["ASSETS_DIR"], CONFIG["TEMP_DIR"]]:
    os.makedirs(d, exist_ok=True)


# ==================================================================================
# 2. HELPERS
# ==================================================================================

def print_step(msg):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}[STEP] {msg}{Style.RESET_ALL}")

def print_info(msg):
    print(f"{Fore.GREEN}  ℹ {msg}")

def print_warn(msg):
    print(f"{Fore.YELLOW}  ⚠ {msg}")


class VideoDuration:
    """Wrapper minimal pour fournir l'attribut .duration sans moviepy."""
    def __init__(self, duration_seconds: float):
        self.duration = duration_seconds


def get_video_duration(video_path: str) -> float:
    """Retourne la durée en secondes via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             video_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATIONFLAGS,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def format_timestamp_srt(seconds: float) -> str:
    """Convertit des secondes en format SRT : HH:MM:SS,mmm"""
    seconds = max(0.0, seconds)
    total_ms = round(seconds * 1000)
    ms   = total_ms % 1000
    s    = (total_ms // 1000) % 60
    m    = (total_ms // 60000) % 60
    h    = total_ms // 3600000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _run_ffmpeg(cmd: list, msg: str = "FFmpeg en cours...") -> subprocess.CompletedProcess:
    """Lance une commande FFmpeg sans ouvrir de console Windows."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATIONFLAGS,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")
            raise RuntimeError(f"FFmpeg erreur (code {result.returncode}):\n{err[-1500:]}")
        return result
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg introuvable. Installez FFmpeg et ajoutez-le au PATH système."
        )


def _write_srt_grouped(words_data: list, srt_path: str, max_words: int = None):
    """
    Écrit un fichier SRT en regroupant les mots par blocs (style TikTok/Reel).
    Ex. : 4 mots max par sous-titre.
    """
    max_w = max_words or CONFIG.get("MAX_WORDS_PER_SUB", 4)
    with open(srt_path, "w", encoding="utf-8") as f:
        idx = 1
        i = 0
        while i < len(words_data):
            group = words_data[i: i + max_w]
            if not group:
                break
            start_t = group[0]["start"]
            end_t   = group[-1]["end"]
            text    = " ".join(w["word"] for w in group).strip()
            if text:
                f.write(f"{idx}\n")
                f.write(f"{format_timestamp_srt(start_t)} --> {format_timestamp_srt(end_t)}\n")
                f.write(f"{text}\n\n")
                idx += 1
            i += max_w


# ==================================================================================
# 3. PHASE 1a — EXTRACTION AUDIO & DÉTECTION DES SILENCES
# ==================================================================================

def extract_and_detect_silences(video_path: str,
                                 silence_thresh: int = None,
                                 min_silence_len: int = None,
                                 progress_callback=None):
    """
    Phase 1a : Extraction audio via FFmpeg + détection des silences via pydub.

    Retourne
    --------
    video_info : VideoDuration
        Objet avec attribut .duration (secondes) pour compatibilité GUI.
    silences : list of (start_ms, end_ms)
        Plages de silences détectées.
    working_path : str
        Chemin vers la vidéo normalisée CFR.
    """
    thresh  = silence_thresh  if silence_thresh  is not None else CONFIG["SILENCE_THRESH"]
    min_len = min_silence_len if min_silence_len is not None else CONFIG["MIN_SILENCE_LEN"]

    def _p(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    # ── 1. Normalisation CFR (30 fps fixe) ───────────────────────────────────
    _p(0.0, "Normalisation CFR (30 fps)...")
    cfr_path = os.path.join(CONFIG["TEMP_DIR"], "temp_cfr.mp4")
    try:
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", video_path,
            "-c:v", "libx264", "-crf", "18", "-preset", "ultrafast",
            "-r", "30", "-c:a", "aac", "-b:a", "192k",
            cfr_path,
        ])
        working_path = cfr_path if os.path.exists(cfr_path) else video_path
    except Exception:
        working_path = video_path   # Fallback si ffmpeg absent

    # ── 2. Durée via ffprobe ──────────────────────────────────────────────────
    _p(0.1, "Lecture des métadonnées vidéo...")
    duration_s = get_video_duration(working_path)
    video_info = VideoDuration(duration_s)

    # ── 3. Extraction audio via FFmpeg ────────────────────────────────────────
    _p(0.2, "Extraction de l'audio...")
    audio_path = os.path.join(CONFIG["TEMP_DIR"], "temp_audio.wav")
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", working_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        audio_path,
    ])

    # ── 4. Détection des silences via pydub ───────────────────────────────────
    _p(0.5, "Chargement de l'audio...")
    audio = AudioSegment.from_wav(audio_path)

    _p(0.6, f"Détection des silences (seuil: {thresh} dB, min: {min_len} ms)...")
    silences = pydub_silence.detect_silence(
        audio,
        min_silence_len=min_len,
        silence_thresh=thresh,
    )

    _p(1.0, f"{len(silences)} silence(s) détecté(s).")
    return video_info, silences, working_path


# ==================================================================================
# 4. PHASE 1b — ASSEMBLAGE DES CLIPS (FFmpeg Concat Demuxer)
# ==================================================================================

def _build_keep_segments(silences, decisions, total_duration_ms: float):
    """
    Convertit une liste (silences à couper, décisions) en liste de segments à GARDER.
    Retourne list of (start_s, end_s).
    """
    cuts = sorted(
        [(s, e) for (s, e), d in zip(silences, decisions) if d],
        key=lambda x: x[0],
    )
    keep = []
    pos = 0.0
    for cut_start, cut_end in cuts:
        if cut_start > pos:
            keep.append((pos / 1000.0, cut_start / 1000.0))
        pos = max(pos, cut_end)
    if pos < total_duration_ms:
        keep.append((pos / 1000.0, total_duration_ms / 1000.0))
    return keep


def _create_concat_file(segments_keep, input_video: str, concat_path: str):
    """Écrit un fichier ffconcat listant les segments à conserver."""
    file_ref = input_video.replace("\\", "/")
    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for start, end in segments_keep:
            f.write(f"file '{file_ref}'\n")
            f.write(f"inpoint {start:.3f}\n")
            f.write(f"outpoint {end:.3f}\n")


def assemble_clips(working_path: str, silences, decisions, output_path: str,
                   progress_callback=None) -> str:
    """
    Phase 1b : Assemble la vidéo en supprimant les silences.
    Utilise le Concat Demuxer FFmpeg — rapide, zéro RAM, synchronisation parfaite.

    Paramètres
    ----------
    working_path : str
        Vidéo source normalisée (chemin).
    silences : list of (start_ms, end_ms)
        Plages à couper dont la décision correspondante est True.
    decisions : list of bool
        True = couper ce silence.
    output_path : str
        Où sauvegarder la vidéo assemblée.

    Retourne
    --------
    str : output_path
    """
    def _p(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    _p(0.0, "Calcul des segments à garder...")
    duration_ms = get_video_duration(working_path) * 1000.0
    keep_segments = _build_keep_segments(silences, decisions, duration_ms)

    if not keep_segments:
        raise RuntimeError("Aucun segment à garder après les coupes.")

    _p(0.1, f"Assemblage de {len(keep_segments)} segment(s) via FFmpeg...")
    concat_file = os.path.join(CONFIG["TEMP_DIR"], "cuts.ffconcat")
    _create_concat_file(keep_segments, working_path, concat_file)

    _p(0.3, "Encodage FFmpeg en cours (Concat Demuxer)...")
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-segment_time_metadata", "1",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        "-ac", "2",
        "-ar", "44100",
        "-af", "aresample=async=1000",
        "-max_interleave_delta", "0",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ], msg="Encodage FFmpeg (concat)...")

    _p(1.0, f"Assemblage terminé : {output_path}")
    return output_path


def save_raw_cut(working_path: str, silences, decisions, output_path: str,
                 progress_callback=None) -> str:
    """Alias de assemble_clips (compatibilité avec les anciens appels CLI)."""
    return assemble_clips(working_path, silences, decisions, output_path, progress_callback)


# ==================================================================================
# 5. PHASE 2 — TRANSCRIPTION WHISPER (GUI-CALLABLE)
# ==================================================================================

def transcribe(video_path: str, progress_callback=None):
    """
    Phase 2 : Transcription Whisper sur un fichier vidéo.
    Écrit temp_subs.txt (éditable dans le GUI) et temp_subs.srt (pour FFmpeg).

    Paramètres
    ----------
    video_path : str
        Chemin vers la vidéo coupée (Raw_Cut).

    Retourne
    --------
    words_data : list of {'start', 'end', 'word'}
    txt_path   : str — chemin vers temp_subs.txt
    """
    def _p(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    # Extraction audio pour Whisper (mono 16 kHz — optimal)
    temp_audio = os.path.join(CONFIG["TEMP_DIR"], "cut_audio.wav")
    _p(0.0, "Extraction audio pour transcription...")
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        temp_audio,
    ])

    def _run_whisper(device_type, compute_type, label=""):
        from faster_whisper import WhisperModel  # import lazy — DLLs chargés ici seulement
        _p(0.3, f"Chargement modèle Whisper ({label})...")
        model = WhisperModel(
            CONFIG["WHISPER_MODEL_SIZE"],
            device=device_type,
            compute_type=compute_type,
        )
        _p(0.5, f"Transcription ({label})...")
        segs, _ = model.transcribe(temp_audio, word_timestamps=True)
        return list(segs)

    def _is_dll_error(e):
        s = str(e)
        return "WinError 1114" in s or "c10.dll" in s

    def _gpu_error_msg(e):
        s = str(e).lower()
        if "cudnn" in s or "libcudnn" in s:
            return "cuDNN introuvable"
        if "cublas" in s or "libcublas" in s:
            return "cuBLAS introuvable"
        if "cuda" in s and any(k in s for k in ("not found", "failed", "unavailable")):
            return "CUDA non disponible"
        if "out of memory" in s or "oom" in s:
            return "VRAM insuffisante"
        return str(e)[:120]

    # ── Tentative GPU, fallback CPU ───────────────────────────────────────────
    gpu_used = False
    gpu_err  = None

    if CONFIG["DEVICE"] == "cuda":
        try:
            segments_list = _run_whisper(CONFIG["DEVICE"], CONFIG["COMPUTE_TYPE"], "GPU CUDA")
            gpu_used = True
            _p(0.55, "Transcription GPU en cours...")
        except Exception as e:
            gpu_err = _gpu_error_msg(e)
            _p(0.4, f"GPU échoué ({gpu_err}) — bascule CPU...")

    if not gpu_used:
        try:
            segments_list = _run_whisper("cpu", "int8", "CPU")
            _p(0.55, "Transcription CPU en cours...")
        except Exception as cpu_e:
            if _is_dll_error(cpu_e):
                raise RuntimeError(
                    "ctranslate2 ne peut pas charger ses DLLs.\n"
                    f"Erreur GPU : {gpu_err or 'N/A'}\n"
                    f"Erreur CPU : {cpu_e}\n\n"
                    "Réinstallez PyTorch CPU-only :\n"
                    "  pip install torch --index-url https://download.pytorch.org/whl/cpu"
                ) from None
            raise RuntimeError(
                f"Transcription CPU échouée : {cpu_e}\n"
                f"(Erreur GPU initiale : {gpu_err or 'N/A'})"
            ) from cpu_e

    # Construire la liste de mots
    words_data = []
    for seg in segments_list:
        if seg.words:
            for w in seg.words:
                words_data.append({
                    "start": w.start,
                    "end":   w.end,
                    "word":  w.word.strip(),
                })

    # ── Écriture temp_subs.txt (pour le GUI) ─────────────────────────────────
    txt_path = os.path.join(CONFIG["TEMP_DIR"], "temp_subs.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("# START | END | WORD\n")
        for wd in words_data:
            f.write(f"{wd['start']:.2f} | {wd['end']:.2f} | {wd['word']}\n")

    # ── Écriture temp_subs.srt (pour la gravure FFmpeg) ───────────────────────
    srt_path = os.path.join(CONFIG["TEMP_DIR"], "temp_subs.srt")
    _write_srt_grouped(words_data, srt_path)

    _p(1.0, f"{len(words_data)} mots transcrits.")
    return words_data, txt_path


def load_subs_from_file(txt_path: str) -> list:
    """Parse temp_subs.txt et retourne list of {'start', 'end', 'word'}."""
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
                        "end":   float(parts[1].strip()),
                        "word":  parts[2].strip(),
                    })
                except Exception:
                    pass
    return final_words


# ==================================================================================
# 6. PHASE 3 — GRAVURE DES SOUS-TITRES (FFmpeg subtitles filter)
# ==================================================================================

def burn_subtitles(video_path: str, words_data: list, output_path: str,
                   progress_callback=None,
                   music_path: str = None, music_volume: float = 0.15) -> str:
    """
    Phase 3 : Grave les sous-titres sur la vidéo via FFmpeg.
    Utilise le filtre 'subtitles' natif FFmpeg — zéro MoviePy, zéro Pillow.

    Paramètres
    ----------
    video_path : str
        Vidéo source (Raw_Cut).
    words_data : list of {'start', 'end', 'word'}
        Mots à afficher (depuis load_subs_from_file).
    output_path : str
        Chemin du fichier de sortie final.
    music_path : str, optional
        Chemin vers un fichier audio pour la musique de fond.
    music_volume : float
        Volume de la musique de fond (0.0–1.0). Défaut 0.15.
    """
    def _p(p, msg):
        if progress_callback:
            progress_callback(p, msg)
        else:
            print_info(msg)

    _p(0.0, "Génération du fichier SRT pour gravure...")
    srt_path = os.path.join(CONFIG["TEMP_DIR"], "burn_subs.srt")
    _write_srt_grouped(words_data, srt_path)

    # Échappement du chemin pour le filtre FFmpeg (Windows)
    srt_esc = srt_path.replace("\\", "/").replace(":", "\\:")
    sub_style = CONFIG.get("SUB_STYLE", "Fontsize=22,PrimaryColour=&HFFFFFF,Outline=3")
    vf_chain = f"subtitles='{srt_esc}':force_style='{sub_style}'"

    # Détection NVENC
    _p(0.1, "Détection du codec disponible...")
    codec = "libx264"
    try:
        res = subprocess.run(
            ["ffmpeg", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATIONFLAGS,
        )
        if b"h264_nvenc" in res.stdout:
            codec = "h264_nvenc"
            _p(0.15, "NVENC GPU détecté.")
    except Exception:
        pass

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
    ]

    # Musique de fond : ajout comme 2ème input + filtre amix
    af_chain = None
    if music_path and os.path.isfile(music_path):
        _p(0.15, f"Ajout musique de fond ({int(music_volume * 100)}%)...")
        cmd.extend(["-stream_loop", "-1", "-i", music_path])
        # amix : [0:a] = audio original (volume 1.0), [1:a] = musique (volume réduit)
        af_chain = (
            f"[1:a]volume={music_volume:.2f}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

    cmd.extend(["-vf", vf_chain])

    if af_chain:
        cmd.extend(["-filter_complex", af_chain, "-map", "0:v", "-map", "[aout]"])

    cmd.extend(["-c:v", codec, "-pix_fmt", "yuv420p"])

    if codec == "libx264":
        cmd.extend(["-preset", "slow", "-crf", "21"])
    else:
        cmd.extend(["-preset", "p4", "-rc", "vbr", "-cq", "22", "-b:v", "5M"])
    cmd.extend(["-c:a", "aac", "-b:a", "192k", output_path])

    _p(0.2, f"Rendu final ({'NVENC GPU' if codec == 'h264_nvenc' else 'CPU libx264'})...")
    _run_ffmpeg(cmd, msg="Rendu FFmpeg (gravure sous-titres)...")

    _p(1.0, f"Export terminé : {output_path}")
    return output_path


# ==================================================================================
# 7. CLI LEGACY — usage : python reel_maker.py (toujours fonctionnel)
# ==================================================================================

def fast_cut_workflow(video_path: str):
    """CLI : détection interactive des silences et assemblage."""
    import msvcrt
    print_step("Phase 1 : Détection des silences")
    video_info, silences, working_path = extract_and_detect_silences(video_path)
    print_info(f"{len(silences)} silence(s) détecté(s).")

    decisions = []
    auto_cut = False

    for i, (start_ms, end_ms) in enumerate(silences):
        if auto_cut:
            decisions.append(True)
            print(f"{Fore.RED}.{Style.RESET_ALL}", end="", flush=True)
            continue

        print(f"\n{Fore.MAGENTA}--- Silence #{i+1} : {start_ms}ms → {end_ms}ms ---")
        print(f"{Fore.YELLOW}  >> [ESPACE] Couper | [N] Garder | [A] Tout couper{Style.RESET_ALL}",
              end="", flush=True)

        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch().lower()
                if key == b" ":
                    decisions.append(True)
                    print(f"\n  {Fore.RED}✂ Coupé{Style.RESET_ALL}")
                    break
                elif key == b"n":
                    decisions.append(False)
                    print(f"\n  {Fore.GREEN}○ Gardé{Style.RESET_ALL}")
                    break
                elif key == b"a":
                    decisions.append(True)
                    auto_cut = True
                    print(f"\n  {Fore.RED}>>> AUTO-CUT activé{Style.RESET_ALL}")
                    break

    name_root = os.path.splitext(os.path.basename(video_path))[0]
    raw_cut_path = os.path.join(CONFIG["OUTPUT_DIR"], f"Raw_Cut_{name_root}.mp4")
    print_step(f"Assemblage → {raw_cut_path}")
    assemble_clips(working_path, silences, decisions, raw_cut_path)
    return raw_cut_path


def main():
    print(f"{Fore.MAGENTA}=== REEL MAKER : CUT & SUB ==={Style.RESET_ALL}")
    files = [f for f in os.listdir(CONFIG["INPUT_DIR"])
             if f.lower().endswith((".mp4", ".mov", ".mkv"))]
    if not files:
        print_warn(f"Aucune vidéo dans {CONFIG['INPUT_DIR']}")
        return

    for filename in files:
        print(f"\n{Fore.CYAN}--- {filename} ---{Style.RESET_ALL}")
        target_vid = os.path.join(CONFIG["INPUT_DIR"], filename)
        name_root  = os.path.splitext(filename)[0]

        try:
            raw_cut_path = fast_cut_workflow(target_vid)

            print_step("Phase 2 : Transcription Whisper")
            words_data, txt_path = transcribe(raw_cut_path)
            print(f"\n{Fore.CYAN}Sous-titres : {txt_path}")
            input(f"{Fore.WHITE}Éditez si besoin, puis [ENTRÉE] pour continuer...{Style.RESET_ALL}")

            final_words = load_subs_from_file(txt_path)
            out_path = os.path.join(CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")
            print_step(f"Phase 3 : Gravure → {out_path}")
            burn_subtitles(raw_cut_path, final_words, out_path)
            print(f"{Fore.GREEN}✅ Terminé : {out_path}{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}Erreur : {e}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
