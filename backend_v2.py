import os
import subprocess
import json
import math
from pathlib import Path
from pydub import AudioSegment, silence

# Configuration par défaut
class VideoConfig:
    def __init__(self):
        self.silence_thresh = -40  # dB
        self.min_silence_len = 500 # ms
        self.keep_silence_len = 200 # ms
        self.temp_dir = os.path.abspath("temp")
        self.assets_dir = os.path.abspath("assets")
        
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)

class VibeProcessor:
    def __init__(self, config=None):
        self.cfg = config if config else VideoConfig()
        self.whisper_model = None

    # === STEP 0: SANITIZATION (CRITIQUE POUR LA SYNC) ===
    def sanitize_video(self, input_path):
        """
        Convertit la vidéo en format PIVOT stable :
        - Constant Frame Rate (CFR) 30fps
        - Audio 44.1kHz AAC
        - Codec H.264
        Cela corrige 99% des problèmes de drift audio/vidéo des enregistrements OBS.
        """
        import time
        start_t = time.time()
        
        filename = Path(input_path).stem
        sanitized_path = os.path.join(self.cfg.temp_dir, f"{filename}_CLEAN.mp4")
        
        # Si le fichier existe déjà et est récent, on ne refait pas (cache simple)
        if os.path.exists(sanitized_path) and os.path.getsize(sanitized_path) > 1000:
            print(f"✨ Vidéo déjà nettoyée : {sanitized_path}")
            return sanitized_path

        print(f"🧹 Nettoyage vidéo (CFR 30fps + Audio 44.1kHz)...")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-r", "30",              # Force 30 FPS Constant
            "-c:v", "libx264",       # Codec vidéo standard
            "-preset", "ultrafast",  # Rapide pour le pré-traitement
            "-crf", "23",            # Qualité correcte
            "-c:a", "aac",           # Codec audio standard
            "-ar", "44100",          # Fréquence d'échantillonnage standard
            "-ac", "2",              # Stéréo
            sanitized_path
        ]
        
        # On masque la sortie sauf erreur
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if process.returncode != 0:
            print(f"❌ Erreur sanitization:\n{process.stderr.decode()}")
            raise RuntimeError("Impossible de nettoyer la vidéo.")
            
        print(f"✅ Vidéo nettoyée en {time.time() - start_t:.1f}s")
        return sanitized_path

    # === STEP 1: Audio Extraction ===
    def extract_audio(self, video_path):
        """Extrait l'audio en WAV pour analyse Pydub"""
        audio_path = os.path.join(self.cfg.temp_dir, "extracted_audio.wav")
        # On force aussi le 44100Hz ici pour être sûr que Pydub est content
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            audio_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return audio_path

    # === STEP 2: Silence Detection ===
    def analyze_silence(self, audio_path):
        """Détecte les plages de parole avec Pydub"""
        print(f"🔍 Analyse audio ({self.cfg.silence_thresh}dB)...")
        audio = AudioSegment.from_wav(audio_path)
        
        # split_on_silence retourne des chunks audio, mais on veut les timestamps.
        # on utilise detect_nonsilent qui est plus adapté pour avoir [start, end]
        from pydub.silence import detect_nonsilent
        
        nonsilent_ranges = detect_nonsilent(
            audio,
            min_silence_len=self.cfg.min_silence_len,
            silence_thresh=self.cfg.silence_thresh,
            seek_step=10
        )
        
        # Convertir ms -> secondes
        segments = []
        for start_ms, end_ms in nonsilent_ranges:
            # Ajouter un peu de marge (keep_silence_len)
            start = max(0, start_ms - self.cfg.keep_silence_len) / 1000.0
            end = min(len(audio), end_ms + self.cfg.keep_silence_len) / 1000.0
            segments.append((start, end))
            
        # Fusionner les segments qui se chevauchent après ajout des marges
        if not segments:
            return []
            
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

    # === STEP 3: Transcription (Lazy Load) ===
    def _load_whisper(self, model_size="base"):
        if self.whisper_model is not None:
            return self.whisper_model
        
        print("🧠 Chargement Whisper...")
        try:
            # Essayer GPU
            from faster_whisper import WhisperModel
            self.whisper_model = WhisperModel(model_size, device="cuda", compute_type="float16")
        except Exception as e:
            print(f"⚠️ GPU non disponible ou erreur, fallback CPU: {e}")
            from faster_whisper import WhisperModel
            self.whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            
        return self.whisper_model

    def transcribe(self, video_path, model_size="base"):
        model = self._load_whisper(model_size)
        segments_gen, _ = model.transcribe(video_path, word_timestamps=True, language="fr")
        return list(segments_gen)

    # === STEP 4: SRT Generation with Formatting ===
    def generate_srt_with_highlights(self, segments, srt_path, max_words=2, uppercase=True):
        """
        Génère un SRT propre.
        Note: Les balises de couleur FFmpeg sont <font color='#RRGGBB'>Text</font>
        """
        with open(srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for seg in segments:
                words = seg.words
                if not words:
                    continue
                
                # Group words
                chunks = []
                current_chunk = []
                
                for w in words:
                    current_chunk.append(w)
                    if len(current_chunk) >= max_words:
                        chunks.append(current_chunk)
                        current_chunk = []
                if current_chunk:
                    chunks.append(current_chunk)
                
                for chunk in chunks:
                    start = chunk[0].start
                    end = chunk[-1].end
                    
                    # Highlight logic: Color the whole chunk for now (Karaoke simple)
                    # Or highlight specific words. Let's do simple white text + Yellow Outline predefined in Style
                    # But if we want specific colors in text:
                    text_content = " ".join([w.word.strip() for w in chunk])
                    
                    if uppercase:
                        text_content = text_content.upper()
                    
                    # Format timestamp
                    start_str = self._fmt_time(start)
                    end_str = self._fmt_time(end)
                    
                    f.write(f"{idx}\n{start_str} --> {end_str}\n{text_content}\n\n")
                    idx += 1

    def _fmt_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    # === STEP 5: Final Render (Robust) ===
    def render_final(self, video_path, srt_path, output_path, music_path=None):
        """
        Rendu final robuste :
        - Pas de crop
        - Fontsdir paramétré
        - Loudnorm pour l'audio
        - Chemins absolus échappés
        """
        import shlex
        
        # 1. Préparer les chemins absolus style UNIX pour FFmpeg (même sous Windows)
        # FFmpeg filter paths are tricky. Le mieux est d'utiliser des slashs.
        video_path = str(Path(video_path).absolute()).replace("\\", "/")
        srt_path = str(Path(srt_path).absolute()).replace("\\", "/")
        assets_dir = str(Path(self.cfg.assets_dir).absolute()).replace("\\", "/")
        output_path = str(Path(output_path).absolute())
        
        # Échapper les deux-points pour le filter graph (C:/... devient C\:/...)
        srt_escaped = srt_path.replace(":", "\\:")
        assets_escaped = assets_dir.replace(":", "\\:")
        
        # 2. Définir le Style ASS pour les sous-titres
        # Alignment=2 (Bas), MarginV=80 (Un peu remonté), FontPoppings
        # Fontsdir indique à FFmpeg où chercher Poppins-Bold.ttf
        style = (
            "Fontname=Poppins-Bold,Fontsize=12,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&HE22B8A,"
            "BorderStyle=1,Outline=1,Shadow=1,Alignment=2,MarginV=300"
        )
        
        # Commande Subtitles avec fontsdir
        vf_subs = f"subtitles='{srt_escaped}':fontsdir='{assets_escaped}':force_style='{style}'"
        
        # 3. Filtres Audio (Mix Musique + Loudnorm)
        # Entrées: 0:v (video), 0:a (audio video), [1:a] (musique optionnelle)
        filter_complex = ""
        map_cmd = []
        
        if music_path:
            music_path = str(Path(music_path).absolute()).replace("\\", "/")
            inputs = ["-i", video_path, "-i", music_path]
            # Mixage: Musique à 10% (-20dB), Bouclée, puis mixée avec la voix
            # Puis Loudnorm sur le tout
            filter_complex = (
                f"[1:a]volume=0.1,aloop=loop=-1:size=2e9[bgm];"
                f"[0:a][bgm]amix=inputs=2:duration=first[mixed];"
                f"[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[aout];"
                f"[0:v]{vf_subs}[vout]"
            )
            map_cmd = ["-map", "[vout]", "-map", "[aout]"]
        else:
            inputs = ["-i", video_path]
            # Juste Loudnorm sur la voix originale
            filter_complex = (
                f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout];"
                f"[0:v]{vf_subs}[vout]"
            )
            map_cmd = ["-map", "[vout]", "-map", "[aout]"]

        print(f"🎬 Rendu Final Safe...\n  Video: {video_path}\n  SRT: {srt_path}")
        
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            *map_cmd,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            output_path
        ]
        
        subprocess.run(cmd, check=True)
