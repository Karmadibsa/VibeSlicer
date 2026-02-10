
import re
import os

ASSETS_DIR = r"assets"
TEMP_DIR = r"temp"

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Regex pour capturer la méthode _create_title_intro jusqu'à la prochaine méthode _reset
pattern = r"def _create_title_intro\(self, title_text\):.*?def _reset\(self\):"

# Remplacement avec la nouvelle méthode
replacement = r"""def _create_title_intro(self, title_text):
        intro_path = os.path.join(TEMP_DIR, "intro.mp4")
        output_with_intro = os.path.join(TEMP_DIR, "with_intro.mp4")
        
        # 1. Extraction d'une image pour le fond depuis le PIVOT (clean)
        frame_path = os.path.join(TEMP_DIR, "first_frame.jpg")
        # On utilise clean_video_path (le Pivot) pour avoir une image FULL qualité sans artefacts de compression du cut
        subprocess.run(["ffmpeg", "-y", "-i", self.clean_video_path, "-vframes", "1", frame_path], 
                      capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        clean_title = title_text.replace("'", "").replace(":", "\\:")
        poppins = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf").replace("\\", "/").replace(":", "\\:")
        font_opt = f":fontfile='{poppins}'" if os.path.exists(os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")) else ""
        
        # 2. Génération de l'intro avec les paramètres EXACTS du Pivot (60fps, 44100Hz)
        # C'est crucial pour que la concaténation ne décale pas le son
        cmd_gen = [
            "ffmpeg", "-y", 
            "-loop", "1", "-i", frame_path,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", # Silence audio
            "-vf", f"boxblur=20:20,drawtext=text='{clean_title}':fontsize=100:fontcolor={self.title_color}:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=4:shadowy=4{font_opt},format=yuv420p",
            "-t", "2",
            "-r", "60", # Force frame rate
            "-c:v", "libx264", "-preset", "ultrafast", 
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            intro_path
        ]
        subprocess.run(cmd_gen, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # 3. Concaténation (Méthode TS plus robuste pour la synchro)
        # On convertit les deux en .ts (transport stream) intermédiaire
        intro_ts = os.path.join(TEMP_DIR, "intro.ts")
        cut_ts = os.path.join(TEMP_DIR, "cut.ts")
        
        subprocess.run(["ffmpeg", "-y", "-i", intro_path, "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", intro_ts], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        subprocess.run(["ffmpeg", "-y", "-i", self.cut_video_path, "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", cut_ts], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # On concatène les TS
        concat_cmd = [
            "ffmpeg", "-y", 
            "-i", f"concat:{intro_ts}|{cut_ts}",
            "-c", "copy", # Pas de réencodage = Pas de perte de synchro !
            "-bsf:a", "aac_adtstoasc",
            output_with_intro
        ]
        subprocess.run(concat_cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        return output_with_intro

    def _reset(self):"""

# Remplacement avec DOTALL pour matcher les sauts de ligne
new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Patch applied successfully.")
