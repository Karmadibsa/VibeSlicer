"""
VibeSlicer Studio v7.0 - Final Polish
Auto-workflow, Sound playback, History tracking
"""

import os
import sys
import json
import threading
import queue
import subprocess
import time
import re
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from pathlib import Path

try:
    import cv2
    CV2_AVAILABLE = True
except:
    CV2_AVAILABLE = False

# Theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colors - Modern Dark Theme
BG = "#0f0f0f"
CARD = "#1a1a1a"
SIDEBAR = "#141414"
ACCENT = "#8b5cf6"      # Violet moderne
ACCENT_HOVER = "#7c3aed"
TEXT = "#fafafa"
TEXT_MUTED = "#a1a1aa"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
ERROR = "#ef4444"
SPEECH_COLOR = "#22c55e"
SPEECH_COLOR_DIM = "#14532d"  # Vert sombre
SILENCE_COLOR = "#f59e0b"
SILENCE_COLOR_DIM = "#78350f" # Orange sombre
PROCESSED_COLOR = "#3f3f46"

# Paths
INPUT_DIR = os.path.abspath("input")
OUTPUT_DIR = os.path.abspath("output")
TEMP_DIR = os.path.abspath("temp")
ASSETS_DIR = os.path.abspath("assets")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
HISTORY_FILE = os.path.join(TEMP_DIR, "processed_videos.json")

for d in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)


def load_history():
    """Charge l'historique des vidéos traitées"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return []


def save_history(videos):
    """Sauvegarde l'historique"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(videos, f)


class VideoPlayer:
    """Lecteur vidéo OpenCV avec sync audio précis"""
    
    def __init__(self, canvas, on_frame_callback=None):
        self.canvas = canvas
        self.on_frame = on_frame_callback
        self.cap = None
        self.playing = False
        self.current_time = 0
        self.duration = 0
        self.fps = 30
        self.photo = None
        self.video_path = None
        self._play_job = None
        self._play_start_time = 0  # Temps réel au démarrage de la lecture
        self._play_start_pos = 0   # Position vidéo au démarrage
        self._sound_process = None
    
    def load(self, video_path):
        self.stop_sound()
        if self.cap:
            self.cap.release()
        
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            return False
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self.duration = frame_count / self.fps if self.fps > 0 else 0
        self.current_time = 0
        
        self._show_frame()
        return True
    
    def _show_frame(self):
        if not self.cap or not self.cap.isOpened():
            return False
        
        ret, frame = self.cap.read()
        if not ret:
            self.pause()
            return False
        
        h, w = frame.shape[:2]
        cw = self.canvas.winfo_width() or 640
        ch = self.canvas.winfo_height() or 360
        
        scale = min(cw / w, ch / h)
        nw, nh = int(w * scale), int(h * scale)
        
        frame = cv2.resize(frame, (nw, nh))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        img = Image.fromarray(frame)
        self.photo = ImageTk.PhotoImage(img)
        
        self.canvas.delete("all")
        x = (cw - nw) // 2
        y = (ch - nh) // 2
        self.canvas.create_image(x, y, anchor="nw", image=self.photo)
        
        self.current_time = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        
        if self.on_frame:
            self.on_frame(self.current_time)
        
        return True
    
    def play(self):
        if not self.cap:
            return
        self.playing = True
        self._play_start_time = time.time()
        self._play_start_pos = self.current_time
        self._start_sound()
        self._play_loop()
    
    def _play_loop(self):
        if not self.playing:
            return
        
        # Calculer le temps cible basé sur le temps réel écoulé
        elapsed_real = time.time() - self._play_start_time
        target_time = self._play_start_pos + elapsed_real
        
        # Seek à la bonne position si on est en retard
        if target_time < self.duration:
            target_frame = int(target_time * self.fps)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self._show_frame()
        else:
            self.pause()
            return
        
        # Prochain frame basé sur le FPS
        delay = max(1, int(1000 / self.fps) - 5)
        self._play_job = self.canvas.after(delay, self._play_loop)
    
    def _start_sound(self):
        """Lance ffplay pour le son"""
        self.stop_sound()
        try:
            self._sound_process = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-ss", str(self.current_time), self.video_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except:
            pass
    
    def stop_sound(self):
        if self._sound_process:
            try:
                self._sound_process.terminate()
            except:
                pass
            self._sound_process = None
    
    def pause(self):
        self.playing = False
        if self._play_job:
            self.canvas.after_cancel(self._play_job)
        self.stop_sound()
    
    def seek(self, time_sec):
        if not self.cap:
            return
        was_playing = self.playing
        self.pause()
        frame_num = int(time_sec * self.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        self.current_time = time_sec
        self._show_frame()
        if was_playing:
            self.play()
    
    def toggle(self):
        if self.playing:
            self.pause()
        else:
            self.play()
    
    def release(self):
        self.pause()
        if self.cap:
            self.cap.release()


class VibeslicerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("VibeSlicer Studio v7.0")
        self.geometry("1500x900")
        self.minsize(1300, 800)
        self.configure(fg_color=BG)
        
        # State
        self.current_step = 0
        self.video_path = None # Raw path
        self.clean_video_path = None # Sanitized path (CFR 30fps)
        self.video_duration = 0
        self.segments = []
        self.cut_video_path = None
        self.subtitles = []
        self.processor = None
        self.log_queue = queue.Queue()
        self.shift_start = None
        self.player = None
        self.sub_player = None
        self.processed_videos = load_history()
        
        self.steps = []
        self.step_titles = ["Sélection", "Découpe", "Sous-titres", "Export"]
        
        self._build_ui()
        self._show_step(0)
        self._process_logs()
        
        self.bind("<space>", lambda e: self._toggle_current_player())
        self.bind("<Left>", lambda e: self._seek_relative(-3))
        self.bind("<Right>", lambda e: self._seek_relative(3))
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _on_close(self):
        if self.player:
            self.player.release()
        if self.sub_player:
            self.sub_player.release()
        self.destroy()
    
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        header = ctk.CTkFrame(self, fg_color=SIDEBAR, height=55, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(header, text="🎬 VibeSlicer", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=ACCENT).grid(row=0, column=0, padx=20, pady=12, sticky="w")
        
        # Steps indicator
        steps_frame = ctk.CTkFrame(header, fg_color="transparent")
        steps_frame.grid(row=0, column=1)
        
        self.step_indicators = []
        for i, title in enumerate(self.step_titles):
            lbl = ctk.CTkLabel(steps_frame, text=f"{i+1}. {title}", font=ctk.CTkFont(size=11),
                               text_color=TEXT_MUTED)
            lbl.pack(side="left", padx=15)
            self.step_indicators.append(lbl)
        
        self.console_mini = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=9), text_color=SUCCESS)
        self.console_mini.grid(row=0, column=2, padx=20)
        
        # Content
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        
        self._create_step1()
        self._create_step2()
        self._create_step3()
        self._create_step4()
        
        # Footer
        footer = ctk.CTkFrame(self, fg_color=SIDEBAR, height=50, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(1, weight=1)
        
        self.prev_btn = ctk.CTkButton(footer, text="← Retour", command=self._prev_step,
                                       fg_color=CARD, hover_color="#2a2a2a", width=120, height=32,
                                       corner_radius=6)
        self.prev_btn.grid(row=0, column=0, padx=20, pady=9)
        
        ctk.CTkLabel(footer, text="Espace=Play | ←→=Seek | Alt+Clic=Couper | Shift+Clics=Plage",
                     font=ctk.CTkFont(size=8), text_color=TEXT_MUTED).grid(row=0, column=1)
        
        self.next_btn = ctk.CTkButton(footer, text="Suivant →", command=self._next_step,
                                       fg_color=ACCENT, hover_color=ACCENT_HOVER, width=120, height=32,
                                       corner_radius=6, font=ctk.CTkFont(weight="bold"))
        self.next_btn.grid(row=0, column=2, padx=20, pady=9)
    
    # === STEP 1 ===
    def _create_step1(self):
        frame = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self.steps.append(frame)
        frame.grid_columnconfigure((0, 1), weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="📁 Choisissez une vidéo", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # List
        left = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        
        header_row = ctk.CTkFrame(left, fg_color="transparent")
        header_row.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        
        ctk.CTkLabel(header_row, text=f"📂 input/", font=ctk.CTkFont(size=9), text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkButton(header_row, text="↻", width=28, height=24, fg_color=ACCENT, corner_radius=4,
                      command=self._scan_videos).pack(side="right")
        
        self.video_list = ctk.CTkScrollableFrame(left, fg_color=BG, corner_radius=6)
        self.video_list.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        
        # Preview
        right = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(right, text="📹 Aperçu", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")
        
        self.preview_canvas = tk.Canvas(right, bg="#0a0a0a", highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        
        self.video_info = ctk.CTkLabel(right, text="Cliquez sur une vidéo", text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
        self.video_info.grid(row=2, column=0, padx=12, pady=(6, 12))
        
        self._scan_videos()
    
    def _scan_videos(self):
        for w in self.video_list.winfo_children():
            w.destroy()
        
        exts = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
        videos = [f for f in os.listdir(INPUT_DIR) if any(f.lower().endswith(e) for e in exts)] if os.path.exists(INPUT_DIR) else []
        
        if not videos:
            ctk.CTkLabel(self.video_list, text="Aucune vidéo dans input/", text_color=TEXT_MUTED).pack(pady=30)
        else:
            for v in videos:
                is_processed = v in self.processed_videos
                fg = PROCESSED_COLOR if is_processed else CARD
                text = f"{'✓ ' if is_processed else '🎥 '}{v}"
                
                btn = ctk.CTkButton(self.video_list, text=text, command=lambda x=v: self._select_video(x),
                                     fg_color=fg, hover_color=ACCENT_HOVER, anchor="w", height=36,
                                     corner_radius=6, font=ctk.CTkFont(size=11))
                btn.pack(fill="x", pady=2)
        
        self.log(f"📂 {len(videos)} vidéo(s)")
    
    def _select_video(self, name):
        self.video_path = os.path.join(INPUT_DIR, name)
        self.log(f"✅ Sélection : {name}")
        
        # Launch Sanitization Thread
        self.video_info.configure(text="⏳ Nettoyage vidéo (Sync Audio/Vidéo)...")
        threading.Thread(target=self._sanitize_thread, daemon=True).start()

    def _sanitize_thread(self):
        try:
            if not self.processor:
                from karmakut_backend import VibeProcessor, VideoConfig
                self.processor = VibeProcessor()
            
            # SANITIZE STEP
            self.clean_video_path = self.processor.sanitize_video(self.video_path)
            self.log(f"✨ Vidéo prête : {os.path.basename(self.clean_video_path)}")
            
            # Update Info with Clean Video
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.clean_video_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.video_duration = float(result.stdout.strip())
            
            self.after(0, lambda: self.video_info.configure(text=f"✅ Prêt • {self.video_duration:.0f}s"))
            
            # Show preview of CLEAN video
            if CV2_AVAILABLE:
                cap = cv2.VideoCapture(self.clean_video_path)
                ret, frame = cap.read()
                if ret:
                    self.after(0, lambda: self._show_frame_on_canvas(frame, self.preview_canvas))
                cap.release()

        except Exception as e:
            self.log(f"❌ Erreur nettoyage: {e}")
            self.after(0, lambda: self.video_info.configure(text="❌ Erreur nettoyage", text_color=ERROR))
    
    def _show_frame_on_canvas(self, frame, canvas):
        h, w = frame.shape[:2]
        cw = canvas.winfo_width() or 400
        ch = canvas.winfo_height() or 300
        
        scale = min(cw / w, ch / h)
        nw, nh = int(w * scale), int(h * scale)
        
        frame = cv2.resize(frame, (nw, nh))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        img = Image.fromarray(frame)
        photo = ImageTk.PhotoImage(img)
        
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, image=photo)
        canvas._photo = photo
    
    # === STEP 2 ===
    def _create_step2(self):
        frame = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self.steps.append(frame)
        frame.grid_columnconfigure(0, weight=2)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="✂️ Éditeur Timeline", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # Left: Video
        left = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        
        self.player_canvas = tk.Canvas(left, bg="#0a0a0a", highlightthickness=0)
        self.player_canvas.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        # Controls
        ctrl = ctk.CTkFrame(left, fg_color=BG, corner_radius=6)
        ctrl.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1)
        
        self.play_btn = ctk.CTkButton(ctrl, text="▶", width=40, height=28, command=self._toggle_play, fg_color=ACCENT, corner_radius=6)
        self.play_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.time_label = ctk.CTkLabel(ctrl, text="0:00 / 0:00", font=ctk.CTkFont(size=10), text_color=TEXT)
        self.time_label.grid(row=0, column=1, padx=8)
        
        self.seek_slider = ctk.CTkSlider(ctrl, from_=0, to=100, command=self._on_seek_slider, button_color=ACCENT, progress_color=ACCENT, height=12)
        self.seek_slider.grid(row=0, column=2, padx=8, pady=5, sticky="ew")
        
        # Timeline
        timeline_frame = ctk.CTkFrame(left, fg_color=BG, corner_radius=6)
        timeline_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        timeline_frame.grid_columnconfigure(0, weight=1)
        
        legend = ctk.CTkFrame(timeline_frame, fg_color="transparent")
        legend.grid(row=0, column=0, pady=4, sticky="w")
        
        ctk.CTkLabel(legend, text="🟢 Parole", font=ctk.CTkFont(size=8), text_color=SPEECH_COLOR).pack(side="left", padx=6)
        ctk.CTkLabel(legend, text="🟠 Silence", font=ctk.CTkFont(size=8), text_color=SILENCE_COLOR).pack(side="left", padx=6)
        ctk.CTkLabel(legend, text="⬛ Suppr", font=ctk.CTkFont(size=8), text_color=TEXT_MUTED).pack(side="left", padx=6)
        
        self.timeline_canvas = tk.Canvas(timeline_frame, bg="#1a1a1a", height=40, highlightthickness=0)
        self.timeline_canvas.grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)
        
        # Right
        right = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        # Settings
        settings = ctk.CTkFrame(right, fg_color=BG, corner_radius=6)
        settings.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        settings.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(settings, text="🔇 Seuil", font=ctk.CTkFont(size=9), text_color=TEXT).grid(row=0, column=0, padx=8, pady=6)
        
        self.thresh_val = ctk.CTkLabel(settings, text="-40", font=ctk.CTkFont(size=9), text_color=ACCENT)
        self.thresh_val.grid(row=0, column=2, padx=6)
        
        self.thresh_slider = ctk.CTkSlider(settings, from_=-60, to=-10, width=100, height=12,
                                            command=self._on_thresh_change, button_color=ACCENT)
        self.thresh_slider.set(-40)
        self.thresh_slider.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        
        # Segments
        ctk.CTkLabel(right, text="📋 Segments", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT).grid(row=1, column=0, padx=10, pady=(6, 4), sticky="w")
        
        self.seg_list = ctk.CTkScrollableFrame(right, fg_color=BG, corner_radius=6)
        self.seg_list.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="nsew")
        
        # Buttons for selection
        sel_frame = ctk.CTkFrame(right, fg_color="transparent")
        sel_frame.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="ew")
        sel_frame.grid_columnconfigure((0, 1), weight=1)
        
        ctk.CTkButton(sel_frame, text="✅ Parole", command=lambda: self._set_all('speech', True), 
                      fg_color=SPEECH_COLOR_DIM, hover_color=SPEECH_COLOR, height=24, font=ctk.CTkFont(size=10)).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(sel_frame, text="❌ Parole", command=lambda: self._set_all('speech', False), 
                      fg_color=CARD, hover_color="#333", height=24, font=ctk.CTkFont(size=10)).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        
        ctk.CTkButton(sel_frame, text="✅ Silence", command=lambda: self._set_all('silence', True), 
                      fg_color=SILENCE_COLOR_DIM, hover_color=SILENCE_COLOR, height=24, font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(sel_frame, text="❌ Silence", command=lambda: self._set_all('silence', False), 
                      fg_color=CARD, hover_color="#333", height=24, font=ctk.CTkFont(size=10)).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        
        # Cut button
        self.cut_btn = ctk.CTkButton(right, text="✂️ Découper →", command=self._apply_cut_and_transcribe,
                                      fg_color=ACCENT, font=ctk.CTkFont(weight="bold"), height=36, corner_radius=6)
        self.cut_btn.grid(row=4, column=0, padx=10, pady=(4, 10), sticky="ew")
    
    def _toggle_play(self):
        if self.player:
            self.player.toggle()
            self.play_btn.configure(text="⏸" if self.player.playing else "▶")
    
    def _toggle_current_player(self):
        if self.current_step == 1 and self.player:
            self._toggle_play()
        elif self.current_step == 2 and self.sub_player:
            self._toggle_sub_play()
    
    def _seek_relative(self, delta):
        player = self.player if self.current_step == 1 else self.sub_player
        if player:
            new_time = max(0, min(player.duration, player.current_time + delta))
            player.seek(new_time)
    
    def _on_seek_slider(self, value):
        if self.player and self.video_duration:
            time_sec = (value / 100) * self.video_duration
            self.player.seek(time_sec)
    
    def _on_player_frame(self, current_time):
        if self.video_duration > 0:
            cur = f"{int(current_time // 60)}:{int(current_time % 60):02d}"
            dur = f"{int(self.video_duration // 60)}:{int(self.video_duration % 60):02d}"
            self.time_label.configure(text=f"{cur} / {dur}")
            self.seek_slider.set((current_time / self.video_duration) * 100)
            self._draw_playhead(current_time)
    
    def _draw_playhead(self, time_sec):
        self.timeline_canvas.delete("playhead")
        if self.video_duration <= 0:
            return
        width = self.timeline_canvas.winfo_width()
        x = int((time_sec / self.video_duration) * width)
        self.timeline_canvas.create_line(x, 0, x, 40, fill="#fff", width=2, tags="playhead")
    
    def _on_timeline_click(self, event):
        if not self.segments or self.video_duration <= 0:
            return
        
        width = self.timeline_canvas.winfo_width()
        click_time = (event.x / width) * self.video_duration
        
        if event.state & 0x20000:  # Alt
            self._split_segment_at(click_time)
            return
        
        if event.state & 0x1:  # Shift
            if self.shift_start is None:
                self.shift_start = click_time
                self.log(f"🔵 Début: {click_time:.1f}s")
            else:
                self._toggle_range(self.shift_start, click_time)
                self.shift_start = None
            return
        
        for i, (start, end, seg_type, keep) in enumerate(self.segments):
            if start <= click_time <= end:
                self.segments[i] = (start, end, seg_type, not keep)
                self._draw_timeline()
                self._update_seg_list_minimal()
                break
        
        if self.player:
            self.player.seek(click_time)
    
    def _split_segment_at(self, time_sec):
        for i, (start, end, seg_type, keep) in enumerate(self.segments):
            if start < time_sec < end:
                self.segments[i] = (start, time_sec, seg_type, keep)
                self.segments.insert(i + 1, (time_sec, end, seg_type, keep))
                self._draw_timeline()
                self._update_seg_list_full()
                self.log(f"✂️ Coupé: {time_sec:.1f}s")
                return
    
    def _toggle_range(self, start_time, end_time):
        if start_time > end_time:
            start_time, end_time = end_time, start_time
        
        for i, (start, end, seg_type, keep) in enumerate(self.segments):
            if end > start_time and start < end_time:
                self.segments[i] = (start, end, seg_type, not keep)
        
        self._draw_timeline()
        self._update_seg_list_minimal()
    
    def _on_thresh_change(self, value):
        self.thresh_val.configure(text=str(int(value)))
        # Debounce: wait 500ms before triggering analysis
        if hasattr(self, '_analyze_timer') and self._analyze_timer:
            self.after_cancel(self._analyze_timer)
        self._analyze_timer = self.after(600, self._analyze)
        
    
    def _analyze(self, callback=None):
        """Analyse la vidéo"""
        if getattr(self, '_is_analyzing', False):
            return
        
        self.log("🔍 Analyse auto...")
        self._is_analyzing = True
        threading.Thread(target=self._analyze_thread, args=(callback,), daemon=True).start()
    
    def _analyze_thread(self, callback=None):
        try:
            if not self.processor:
                from karmakut_backend import VibeProcessor, VideoConfig
                cfg = VideoConfig()
                cfg.silence_thresh = int(self.thresh_slider.get())
                self.processor = VibeProcessor(cfg)
            else:
                self.processor.cfg.silence_thresh = int(self.thresh_slider.get())
            
            if not self.clean_video_path:
                self.log("⚠️ Vidéo non nettoyée, attente...")
                return

            audio_path = self.processor.extract_audio(self.clean_video_path)
            raw_segments = self.processor.analyze_silence(audio_path)
            
            self.segments = []
            last_end = 0
            
            for start, end in raw_segments:
                if start > last_end:
                    self.segments.append((last_end, start, 'silence', False))
                self.segments.append((start, end, 'speech', True))
                last_end = end
            
            if last_end < self.video_duration:
                self.segments.append((last_end, self.video_duration, 'silence', False))
            
            self.log(f"✅ {len(self.segments)} segments")
            
            if not self.player and CV2_AVAILABLE:
                self.player = VideoPlayer(self.player_canvas, self._on_player_frame)
                self.player.load(self.clean_video_path)
            
            self.after(0, self._draw_timeline)
            self.after(0, self._update_seg_list_full)
            
            if callback:
                self.after(0, callback)
            
        except Exception as e:
            self.log(f"❌ {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._is_analyzing = False

    def _draw_timeline(self):
        self.timeline_canvas.delete("all")
        if not self.segments:
            return
        
        width = self.timeline_canvas.winfo_width() or 600
        height = 40
        
        for i, (start, end, seg_type, keep) in enumerate(self.segments):
            x1 = int((start / self.video_duration) * width)
            x2 = int((end / self.video_duration) * width)
            
            if not keep:
                color = SPEECH_COLOR_DIM if seg_type == 'speech' else SILENCE_COLOR_DIM
            elif seg_type == 'speech':
                color = SPEECH_COLOR
            else:
                color = SILENCE_COLOR
            
            self.timeline_canvas.create_rectangle(x1, 3, x2, height - 3, fill=color, outline="#202020")
    
    def _update_seg_list_full(self):
        """Mise à jour complète de la liste"""
        for w in self.seg_list.winfo_children():
            w.destroy()
        
        self._checkboxes = []
        
        for i, (start, end, seg_type, keep) in enumerate(self.segments):
            duration = end - start
            icon = "🗣" if seg_type == 'speech' else "🔇"
            type_color = SPEECH_COLOR if seg_type == 'speech' else SILENCE_COLOR
            bg = CARD if keep else "#1a1a1a"
            
            row = ctk.CTkFrame(self.seg_list, fg_color=bg, corner_radius=6, height=32)
            row.pack(fill="x", pady=2)
            # row.pack_propagate(False) # Removed to avoid layout issues
            
            var = ctk.BooleanVar(value=keep)
            cb = ctk.CTkCheckBox(row, text="", variable=var, width=22, checkbox_height=18, checkbox_width=18,
                                  command=lambda idx=i, v=var: self._toggle_seg_fast(idx, v), fg_color=SUCCESS if keep else CARD)
            cb.pack(side="left", padx=6, pady=6)
            
            type_name = "Parole" if seg_type == 'speech' else "Silence"
            ctk.CTkLabel(row, text=f"{icon} {type_name} {start:.1f}→{end:.1f}s ({duration:.1f}s)", font=ctk.CTkFont(size=11),
                         text_color=type_color if keep else TEXT_MUTED).pack(side="left", padx=6)
            
            self._checkboxes.append((var, i))
    
    def _update_seg_list_minimal(self):
        """Mise à jour minimale sans recréer les widgets"""
        for var, idx in self._checkboxes:
            if idx < len(self.segments):
                var.set(self.segments[idx][3])
    
    def _toggle_seg_fast(self, idx, var):
        start, end, seg_type, _ = self.segments[idx]
        new_state = var.get()
        self.segments[idx] = (start, end, seg_type, new_state)
        # self.log(f"Toggle {idx}: {new_state}")
        self._draw_timeline()
        
        # Mettre à jour la couleur de fond du row pour feedback visuel
        # On doit retrouver le widget row parent de la checkbox pour changer sa couleur
        # Astuce : self._checkboxes[idx] contient (var, i) mais pas le widget...
        # Simplification : On force un redraw complet si nécessaire, ou on laisse tel quel car la checkbox change de couleur
        self.update_idletasks()
    
    def _keep_all(self):
        self.segments = [(s, e, t, True) for s, e, t, _ in self.segments]
        self._draw_timeline()
        self._update_seg_list_minimal()
    
    def _set_all(self, target_type, state):
        for i, (s, e, t, k) in enumerate(self.segments):
            if t == target_type:
                self.segments[i] = (s, e, t, state)
        self._draw_timeline()
        self._update_seg_list_minimal()
    
    def _apply_cut_and_transcribe(self):
        selected = [(s, e) for s, e, _, k in self.segments if k]
        if not selected:
            self.log("⚠️ Sélectionnez des segments")
            return
        
        self.log("✂️ Découpe & Transcrire...")
        self.cut_btn.configure(state="disabled", text="⏳...")
        threading.Thread(target=self._cut_and_transcribe_thread, args=(selected,), daemon=True).start()
    
    def _cut_and_transcribe_thread(self, segments):
        try:
            # CUT
            concat_path = os.path.join(TEMP_DIR, "concat.txt")
            cuts = []
            
            for i, (start, end) in enumerate(segments):
                cut_file = os.path.join(TEMP_DIR, f"cut_{i}.mp4")
                # Use CLEAN video for cutting
                # No need for complex filters as input is already sanitized
                cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", self.clean_video_path,
                       "-t", str(end - start), "-c:v", "libx264", "-preset", "ultrafast",
                       "-c:a", "aac", cut_file]
                subprocess.run(cmd, capture_output=True)
                cuts.append(cut_file)
            
            with open(concat_path, "w") as f:
                for c in cuts:
                    f.write(f"file '{c}'\n")
            
            self.cut_video_path = os.path.join(TEMP_DIR, "cut_video.mp4")
            # FIX SYNC: Add -vsync 1 -async 1 to ensure constant frame rate and audio sync
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
                   "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ar", "44100", 
                   "-vsync", "1", "-async", "1", self.cut_video_path]
            subprocess.run(cmd, capture_output=True)
            
            # TRANSCRIBE
            self.log("🎤 Transcription...")
            
            if not self.processor:
                from karmakut_backend import VibeProcessor, VideoConfig
                self.processor = VibeProcessor(VideoConfig())
            
            segs = self.processor.transcribe(self.cut_video_path)
            
            srt_path = os.path.join(TEMP_DIR, "subtitles.srt")
            self.processor.generate_srt_with_highlights(segs, srt_path, max_words=2, uppercase=True)
            
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()
            
            self.subtitles = self._parse_srt(srt_content)
            self.log(f"✅ {len(self.subtitles)} sous-titres")
            
            # Auto-next step + FORCE UPDATE UI
            self.after(0, lambda: self._show_step(2))
            self.after(100, lambda: self._update_sub_list()) 
            
        except Exception as e:
            self.log(f"❌ {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.after(0, lambda: self.cut_btn.configure(state="normal", text="✂️ Découper →"))
    
    def _parse_srt(self, content):
        subtitles = []
        blocks = content.strip().split("\n\n")
        
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                tc = lines[1]
                match = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", tc)
                if match:
                    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
                    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
                    end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
                    text = " ".join(lines[2:])
                    clean_text = re.sub(r"<[^>]+>", "", text)
                    subtitles.append([start, end, clean_text])
        
        return subtitles
    
    # === STEP 3 ===
    def _create_step3(self):
        frame = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self.steps.append(frame)
        frame.grid_columnconfigure(0, weight=2)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(frame, text="📝 Sous-titres", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # Left: Video (same layout as step 2)
        left = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        left.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        
        self.sub_video_canvas = tk.Canvas(left, bg="#0a0a0a", highlightthickness=0)
        self.sub_video_canvas.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        # Controls
        ctrl = ctk.CTkFrame(left, fg_color=BG, corner_radius=6)
        ctrl.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")
        ctrl.grid_columnconfigure(2, weight=1)
        
        self.sub_play_btn = ctk.CTkButton(ctrl, text="▶", width=40, height=28, command=self._toggle_sub_play, fg_color=ACCENT, corner_radius=6)
        self.sub_play_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.sub_time_label = ctk.CTkLabel(ctrl, text="0:00", font=ctk.CTkFont(size=10), text_color=TEXT)
        self.sub_time_label.grid(row=0, column=1, padx=8)
        
        self.sub_seek_slider = ctk.CTkSlider(ctrl, from_=0, to=100, command=self._on_sub_seek, button_color=ACCENT, height=12)
        self.sub_seek_slider.grid(row=0, column=2, padx=8, pady=5, sticky="ew")
        
        # Current sub
        self.current_sub_label = ctk.CTkLabel(left, text="", font=ctk.CTkFont(size=11, weight="bold"),
                                               text_color=SUCCESS, wraplength=500)
        self.current_sub_label.grid(row=2, column=0, padx=10, pady=(4, 10))
        
        # Right: Subtitles
        right = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        right.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(right, text="📝 Éditer les sous-titres", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, padx=10, pady=(10, 6), sticky="w")
        
        self.sub_list = ctk.CTkScrollableFrame(right, fg_color=BG, corner_radius=6)
        self.sub_list.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
    
    def _toggle_sub_play(self):
        if self.sub_player:
            self.sub_player.toggle()
            self.sub_play_btn.configure(text="⏸" if self.sub_player.playing else "▶")
    
    def _on_sub_seek(self, value):
        if self.sub_player and self.sub_player.duration > 0:
            time_sec = (value / 100) * self.sub_player.duration
            self.sub_player.seek(time_sec)
    
    def _on_sub_frame(self, current_time):
        self.sub_time_label.configure(text=f"{int(current_time // 60)}:{int(current_time % 60):02d}")
        
        if self.sub_player and self.sub_player.duration > 0:
            self.sub_seek_slider.set((current_time / self.sub_player.duration) * 100)
        
        for start, end, text in self.subtitles:
            if start <= current_time <= end:
                self.current_sub_label.configure(text=text)
                return
        
        self.current_sub_label.configure(text="")
    
    def _update_sub_list(self):
        for w in self.sub_list.winfo_children():
            w.destroy()
        
        for i, (start, end, text) in enumerate(self.subtitles):
            row = ctk.CTkFrame(self.sub_list, fg_color=CARD, corner_radius=4)
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(1, weight=1)
            
            time_str = f"{int(start // 60)}:{int(start % 60):02d}"
            ctk.CTkButton(row, text=time_str, width=40, height=22, fg_color=ACCENT, corner_radius=4,
                          command=lambda s=start: self._seek_sub(s), font=ctk.CTkFont(size=8)).grid(row=0, column=0, padx=4, pady=4)
            
            entry = ctk.CTkEntry(row, font=ctk.CTkFont(size=9), fg_color=BG, height=24, corner_radius=4)
            entry.insert(0, text)
            entry.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
            entry.bind("<FocusOut>", lambda e, idx=i, ent=entry: self._save_sub_text(idx, ent))
            entry.bind("<Return>", lambda e, idx=i, ent=entry: self._save_sub_text(idx, ent))
    
    def _save_sub_text(self, idx, entry):
        if idx < len(self.subtitles):
            self.subtitles[idx][2] = entry.get()
    
    def _seek_sub(self, time_sec):
        if self.sub_player:
            self.sub_player.seek(time_sec)
    
    # === STEP 4 ===
    def _create_step4(self):
        frame = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self.steps.append(frame)
        frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(frame, text="🎬 Export", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")
        
        # Options
        opts = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10)
        opts.grid(row=1, column=0, padx=20, sticky="ew", pady=(0, 15))
        opts.grid_columnconfigure(1, weight=1)
        
        # Title
        ctk.CTkLabel(opts, text="📌 Titre intro (2s):", font=ctk.CTkFont(size=10), text_color=TEXT).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.title_entry = ctk.CTkEntry(opts, placeholder_text="Titre...", fg_color=BG, height=28, corner_radius=6)
        self.title_entry.grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        
        self.color_btn = ctk.CTkButton(opts, text="🎨", width=30, height=28, fg_color="white", corner_radius=6,
                                        command=self._pick_color)
        self.color_btn.grid(row=0, column=2, padx=4, pady=8)
        self.title_color = "#ffffff"
        
        # Music
        ctk.CTkLabel(opts, text="🎵 Musique:", font=ctk.CTkFont(size=10), text_color=TEXT).grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.music_var = ctk.StringVar(value="Aucune")
        self.music_menu = ctk.CTkOptionMenu(opts, variable=self.music_var, values=["Aucune"], fg_color=BG, height=28, corner_radius=6)
        self.music_menu.grid(row=1, column=1, padx=12, pady=8, sticky="ew")
        self._scan_music()
        
        # Checkboxes
        self.use_subs = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="📝 Sous-titres", variable=self.use_subs, fg_color=ACCENT).grid(row=2, column=0, columnspan=2, padx=12, pady=4, sticky="w")
        
        self.normalize = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="🔊 Normaliser audio", variable=self.normalize, fg_color=ACCENT).grid(row=3, column=0, columnspan=2, padx=12, pady=(4, 12), sticky="w")
        
        # Export
        self.export_btn = ctk.CTkButton(frame, text="🎬 EXPORTER", command=self._export,
                                         fg_color=SUCCESS, hover_color="#16a34a", height=45, corner_radius=8,
                                         font=ctk.CTkFont(size=14, weight="bold"))
        self.export_btn.grid(row=2, column=0, padx=20, pady=15, sticky="ew")
        
        self.output_label = ctk.CTkLabel(frame, text=f"📂 {OUTPUT_DIR}", text_color=TEXT_MUTED, font=ctk.CTkFont(size=9))
        self.output_label.grid(row=3, column=0, padx=20)
        
        # New video button
        self.new_video_btn = ctk.CTkButton(frame, text="🔄 Nouvelle Vidéo", command=self._reset,
                                            fg_color=CARD, hover_color="#2a2a2a", height=35, corner_radius=6)
        self.new_video_btn.grid(row=4, column=0, padx=20, pady=(20, 20))
    
    def _scan_music(self):
        files = ["Aucune"]
        if os.path.exists(MUSIC_DIR):
            files += [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith((".mp3", ".wav", ".flac"))]
        self.music_menu.configure(values=files)
    
    def _export(self):
        if not self.cut_video_path:
            self.log("⚠️ Pas de vidéo")
            return
        
        self.log("🎬 Export...")
        self.export_btn.configure(state="disabled", text="⏳...")
        threading.Thread(target=self._export_thread, daemon=True).start()
    
    def _export_thread(self):
        try:
            if not self.processor:
                from karmakut_backend import VibeProcessor, VideoConfig
                self.processor = VibeProcessor(VideoConfig())
            
            name = Path(self.video_path).stem
            output = os.path.join(OUTPUT_DIR, f"{name}_FINAL.mp4")
            
            # Save SRT
            srt_path = os.path.join(TEMP_DIR, "edited.srt")
            self._save_srt(srt_path)
            
            music = None
            if self.music_var.get() != "Aucune":
                music = os.path.join(MUSIC_DIR, self.music_var.get())
            
            # Title intro?
            title_text = self.title_entry.get().strip()
            input_video = self.cut_video_path
            
            if title_text:
                self.log("📌 Création intro (+2s)...")
                input_video = self._create_title_intro(title_text)
                # Shift subtitle timestamps by 2 seconds
                self._shift_subtitles(2.0)
                # Re-save SRT with new timestamps
                self._save_srt(srt_path)
            
            # Render
            if self.use_subs.get() and self.subtitles:
                self.processor.render_final(input_video, srt_path, output, music)
            else:
                if music:
                    cmd = ["ffmpeg", "-y", "-i", input_video, "-i", music,
                           "-filter_complex", "[1:a]volume=0.1,aloop=loop=-1:size=2e9[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
                           "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", output]
                    subprocess.run(cmd, capture_output=True)
                else:
                    import shutil
                    shutil.copy(input_video, output)
            
            # Save to history
            video_name = Path(self.video_path).name
            if video_name not in self.processed_videos:
                self.processed_videos.append(video_name)
                save_history(self.processed_videos)
            
            self.log(f"🎉 {output}")
            self.after(0, lambda: self.output_label.configure(text=f"✅ {output}", text_color=SUCCESS))
            
        except Exception as e:
            self.log(f"❌ {e}")
        finally:
            self.after(0, lambda: self.export_btn.configure(state="normal", text="🎬 EXPORTER"))
    
    def _save_srt(self, path):
        with open(path, "w", encoding="utf-8") as f:
            for i, (start, end, text) in enumerate(self.subtitles, 1):
                start_str = f"{int(start // 3600):02}:{int((start % 3600) // 60):02}:{int(start % 60):02},{int((start % 1) * 1000):03}"
                end_str = f"{int(end // 3600):02}:{int((end % 3600) // 60):02}:{int(end % 60):02},{int((end % 1) * 1000):03}"
                f.write(f"{i}\n{start_str} --> {end_str}\n{text}\n\n")
    
    def _pick_color(self):
        from tkinter import colorchooser
        color = colorchooser.askcolor(initialcolor=self.title_color)[1]
        if color:
            self.title_color = color
            self.color_btn.configure(fg_color=color)
            
    def _shift_subtitles(self, offset):
        """Décale les sous-titres"""
        for i in range(len(self.subtitles)):
            self.subtitles[i][0] += offset
            self.subtitles[i][1] += offset
        self.log(f"⏩ Sous-titres décalés de {offset}s")

    def _create_title_intro(self, title_text):
        intro_path = os.path.join(TEMP_DIR, "intro.mp4")
        output_with_intro = os.path.join(TEMP_DIR, "with_intro.mp4")
        
        # 1. Extract first frame as image
        frame_path = os.path.join(TEMP_DIR, "first_frame.jpg")
        subprocess.run(["ffmpeg", "-y", "-i", self.cut_video_path, "-vframes", "1", frame_path], capture_output=True)
        
        # 2. Loop image for 2s with blur and text
        # Escape text for drawtext
        clean_title = title_text.replace("'", "").replace(":", "\\:")
        
        # Use Poppins font if available
        poppins = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf").replace("\\", "/").replace(":", "\\:")
        font_opt = f":fontfile='{poppins}'" if os.path.exists(os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")) else ""
        
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", frame_path,
            "-f", "lavfi", "-i", "anullsrc",  # Silent audio
            "-vf", f"boxblur=20:20,drawtext=text='{clean_title}':fontsize=80:fontcolor={self.title_color}:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=4:shadowy=4{font_opt}",
            "-t", "2", "-c:v", "libx264", "-c:a", "aac", "-ar", "44100", "-shortest",
            intro_path
        ]
        subprocess.run(cmd, capture_output=True)
        
        concat_file = os.path.join(TEMP_DIR, "intro_concat.txt")
        with open(concat_file, "w") as f:
            f.write(f"file '{intro_path}'\nfile '{self.cut_video_path}'\n")
        
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
               "-c:v", "libx264", "-c:a", "aac", "-ar", "44100", output_with_intro]
        subprocess.run(cmd, capture_output=True)
        
        return output_with_intro
    
    def _reset(self):
        """Reset pour nouvelle vidéo"""
        if self.player:
            self.player.release()
            self.player = None
        if self.sub_player:
            self.sub_player.release()
            self.sub_player = None
        
        self.video_path = None
        self.segments = []
        self.subtitles = []
        self.cut_video_path = None
        
        self._scan_videos()
        self._show_step(0)
    
    # === Navigation ===
    def _show_step(self, idx):
        for s in self.steps:
            s.grid_forget()
        
        self.steps[idx].grid(row=0, column=0, sticky="nsew")
        self.current_step = idx
        
        # Update indicators
        for i, lbl in enumerate(self.step_indicators):
            if i == idx:
                lbl.configure(text_color=ACCENT, font=ctk.CTkFont(size=11, weight="bold"))
            else:
                lbl.configure(text_color=TEXT_MUTED, font=ctk.CTkFont(size=11))
        
        self.prev_btn.configure(state="normal" if idx > 0 else "disabled")
        self.next_btn.configure(text="Terminer" if idx == 3 else "Suivant →")
        
        # Load sub player on step 3
        if idx == 2 and self.cut_video_path and CV2_AVAILABLE:
            self.sub_player = VideoPlayer(self.sub_video_canvas, self._on_sub_frame)
            self.sub_player.load(self.cut_video_path)
            self._update_sub_list()
    
    def _next_step(self):
        if self.current_step == 0:
            if not self.clean_video_path:
                self.log("⏳ Attendez la fin du nettoyage...")
                return
            # Auto-analyze when going to step 2
            self._show_step(1)
            self._analyze()
            return
        
        if self.current_step == 1:
            if not self.cut_video_path:
                self.log("⚠️ Cliquez sur Découper")
                return
        
        if self.current_step < 3:
            self._show_step(self.current_step + 1)
    
    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)
    
    # === Logging ===
    def log(self, msg):
        self.log_queue.put(msg)
    
    def _process_logs(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.console_mini.configure(text=msg[-50:] if len(msg) > 50 else msg)
                print(msg)
        except:
            pass
        self.after(100, self._process_logs)


if __name__ == "__main__":
    print("🎬 VibeSlicer Studio v7.0")
    app = VibeslicerApp()
    app.mainloop()
