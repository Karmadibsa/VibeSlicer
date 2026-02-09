#!/usr/bin/env python3
"""
VibeSlicer Studio v8.0 - Architecture propre
Lecteur VLC + Smart Rendering + MVC Pattern
"""
import sys
import os
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from typing import List, Optional
import threading
import queue
import time
from dataclasses import dataclass, field

# Ajouter le dossier au path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.smart_engine import SmartVideoEngine
from src.ui.components.vlc_player import create_video_player, VLC_AVAILABLE

# Configuration
BG = "#0f0f0f"
CARD = "#1a1a1a"
ACCENT = "#E22B8A"
ACCENT_LIGHT = "#ff4da6"
SUCCESS = "#22c55e"
ERROR = "#ef4444"
TEXT = "#ffffff"
TEXT_MUTED = "#888888"

# Chemins
BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
MUSIC_DIR = BASE_DIR / "music"

# Créer les dossiers
for d in [TEMP_DIR, INPUT_DIR, OUTPUT_DIR, ASSETS_DIR, MUSIC_DIR]:
    d.mkdir(exist_ok=True)


# === Data Classes ===

@dataclass
class Segment:
    """Segment de vidéo"""
    start: float
    end: float
    segment_type: str  # 'speech' ou 'silence'
    keep: bool = True


@dataclass
class Subtitle:
    """Sous-titre"""
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)


class ProjectState:
    """État du projet (simplifié)"""
    def __init__(self):
        self.source_video: Optional[Path] = None
        self.clean_video: Optional[Path] = None
        self.cut_video: Optional[Path] = None
        self.proxy_video: Optional[Path] = None
        self.duration: float = 0
        self.fps: float = 30
    
    def set_source_video(self, path: Path):
        self.source_video = Path(path)


class VibeSlicerApp(ctk.CTk):
    """Application principale avec architecture MVC"""
    
    def __init__(self):
        super().__init__()
        
        self.title("VibeSlicer Studio v8.0")
        self.geometry("1500x900")
        self.minsize(1200, 700)
        self.configure(fg_color=BG)
        
        ctk.set_appearance_mode("dark")
        
        # State (MVC - Model)
        self.state = ProjectState()
        
        # Engine
        self.engine = SmartVideoEngine(TEMP_DIR, ASSETS_DIR)
        
        # Video players
        self.player1 = None  # Step 1
        self.player2 = None  # Step 2 (subtitles)
        
        # Segments et Subtitles locaux (pour UI)
        self.segments: List[Segment] = []
        self.subtitles: List[Subtitle] = []
        
        # Queue pour thread-safe updates
        self.ui_queue = queue.Queue()
        
        # Scanner les vidéos
        self.available_videos = self._scan_videos()
        
        # Build UI
        self._build_ui()
        
        # Démarrer le polling de la queue UI
        self._poll_ui_queue()
        
        self.log(f"🎬 VibeSlicer Studio v8.0")
        self.log(f"📂 {len(self.available_videos)} vidéo(s) trouvée(s)")
        
        if not VLC_AVAILABLE:
            self.log("⚠️ VLC non détecté - Installez VLC 64-bit")
    
    def _scan_videos(self) -> List[Path]:
        """Scanne le dossier input"""
        videos = []
        for ext in ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.MP4", "*.MOV"]:
            videos.extend(INPUT_DIR.glob(ext))
        return sorted(videos, key=lambda p: p.stat().st_mtime, reverse=True)
    
    
    def _poll_ui_queue(self):
        """Poll la queue pour les mises à jour UI thread-safe"""
        try:
            while True:
                func, args = self.ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        
        self.after(50, self._poll_ui_queue)
    
    def _queue_ui(self, func, *args):
        """Ajoute une mise à jour UI à la queue (thread-safe)"""
        self.ui_queue.put((func, args))
    
    def _build_ui(self):
        """Construit l'interface"""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # Sidebar
        self._build_sidebar()
        
        # Main content
        self.main_frame = ctk.CTkFrame(self, fg_color=BG)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Steps
        self.step_frames = []
        self._build_step0()
        self._build_step1()
        self._build_step2()
        self._build_step3()
        
        self._show_step(0)
    
    def _build_sidebar(self):
        """Construit la sidebar"""
        sidebar = ctk.CTkFrame(self, width=240, fg_color=CARD, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Logo
        ctk.CTkLabel(
            sidebar, text="🎬 VibeSlicer",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=20)
        
        # Steps
        self.step_btns = []
        steps = ["1. Sélection", "2. Analyse", "3. Sous-titres", "4. Export"]
        
        for i, name in enumerate(steps):
            btn = ctk.CTkButton(
                sidebar, text=name, height=40,
                fg_color="transparent", text_color=TEXT_MUTED,
                hover_color=CARD, anchor="w",
                command=lambda idx=i: self._show_step(idx)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.step_btns.append(btn)
        
        # Spacer
        ctk.CTkFrame(sidebar, fg_color="transparent").pack(fill="both", expand=True)
        
        # Console
        log_frame = ctk.CTkFrame(sidebar, fg_color=BG, corner_radius=8)
        log_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            log_frame, text="📋 Console",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=10, pady=(5, 0))
        
        self.log_text = ctk.CTkTextbox(
            log_frame, height=150,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=BG, text_color=TEXT_MUTED
        )
        self.log_text.pack(fill="x", padx=5, pady=5)
    
    def _build_step0(self):
        """Step 0: Sélection vidéo"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        ctk.CTkLabel(
            frame, text="📁 Sélectionnez une vidéo",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=20)
        
        scroll = ctk.CTkScrollableFrame(frame, fg_color=CARD, corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        if not self.available_videos:
            ctk.CTkLabel(
                scroll, text="Aucune vidéo dans 'input/'",
                text_color=TEXT_MUTED
            ).pack(pady=50)
        else:
            for video in self.available_videos:
                self._create_video_card(scroll, video)
    
    def _create_video_card(self, parent, video_path: Path):
        """Crée une carte vidéo"""
        card = ctk.CTkFrame(parent, fg_color="#222222", corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)
        
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=15, pady=10)
        
        ctk.CTkLabel(
            info, text=video_path.name,
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).pack(anchor="w")
        
        size_mb = video_path.stat().st_size / (1024 * 1024)
        ctk.CTkLabel(
            info, text=f"{size_mb:.1f} MB",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED
        ).pack(anchor="w")
        
        ctk.CTkButton(
            card, text="Sélectionner →", width=120, height=35,
            fg_color=ACCENT, hover_color=ACCENT_LIGHT,
            command=lambda p=video_path: self._select_video(p)
        ).pack(side="right", padx=15, pady=10)
    
    def _build_step1(self):
        """Step 1: Analyse et Timeline"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent", height=50)
        header.pack(fill="x", padx=20, pady=10)
        
        self.step1_title = ctk.CTkLabel(
            header, text="🎥 Analyse des silences",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.step1_title.pack(side="left")
        
        self.analyze_btn = ctk.CTkButton(
            header, text="🔍 Analyser", width=120,
            fg_color=ACCENT, command=self._analyze_video
        )
        self.analyze_btn.pack(side="right")
        
        # Video frame
        video_container = ctk.CTkFrame(frame, fg_color="#0a0a0a", corner_radius=10)
        video_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.video_frame1 = tk.Frame(video_container, bg='black')
        self.video_frame1.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Controls
        controls = ctk.CTkFrame(video_container, fg_color="transparent", height=40)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        
        self.play_btn1 = ctk.CTkButton(
            controls, text="▶️", width=40,
            command=self._toggle_play1
        )
        self.play_btn1.pack(side="left", padx=5)
        
        self.time_label1 = ctk.CTkLabel(controls, text="0:00 / 0:00")
        self.time_label1.pack(side="left", padx=10)
        
        # Timeline Canvas
        timeline_frame = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=10, height=80)
        timeline_frame.pack(fill="x", padx=20, pady=(0, 10))
        timeline_frame.pack_propagate(False)
        
        self.timeline_canvas = tk.Canvas(
            timeline_frame, height=70, bg=CARD, highlightthickness=0
        )
        self.timeline_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)
        
        # Next button
        self.next_btn1 = ctk.CTkButton(
            frame, text="✂️ Découper & Transcrire →",
            height=40, fg_color=SUCCESS,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._cut_and_transcribe
        )
        self.next_btn1.pack(pady=15)
    
    def _build_step2(self):
        """Step 2: Sous-titres"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Header
        ctk.CTkLabel(
            frame, text="📝 Éditez les sous-titres",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=10)
        
        # Content
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=10)
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        
        # Video
        video_frame = ctk.CTkFrame(content, fg_color="#0a0a0a", corner_radius=10)
        video_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        self.video_frame2 = tk.Frame(video_frame, bg='black')
        self.video_frame2.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Video controls
        controls2 = ctk.CTkFrame(video_frame, fg_color="transparent", height=40)
        controls2.pack(fill="x", padx=10, pady=(0, 10))
        
        self.play_btn2 = ctk.CTkButton(
            controls2, text="▶️", width=40, command=self._toggle_play2
        )
        self.play_btn2.pack(side="left", padx=5)
        
        self.time_label2 = ctk.CTkLabel(controls2, text="0:00 / 0:00")
        self.time_label2.pack(side="left", padx=10)
        
        # Subtitle editor
        sub_frame = ctk.CTkFrame(content, fg_color=CARD, corner_radius=10)
        sub_frame.grid(row=0, column=1, sticky="nsew")
        
        ctk.CTkLabel(
            sub_frame, text="📝 Sous-titres",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=10, pady=10)
        
        self.sub_scroll = ctk.CTkScrollableFrame(sub_frame, fg_color=BG)
        self.sub_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Export button
        ctk.CTkButton(
            frame, text="🎬 Exporter →",
            height=40, fg_color=SUCCESS,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._show_step(3)
        ).pack(pady=15)
    
    def _build_step3(self):
        """Step 3: Export"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        center = ctk.CTkFrame(frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            center, text="🎬 Export Final",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=20)
        
        # Options
        options = ctk.CTkFrame(center, fg_color=CARD, corner_radius=10)
        options.pack(pady=20, ipadx=30, ipady=20)
        
        ctk.CTkLabel(
            options, text="🎵 Musique de fond",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 5))
        
        music_files = ["Aucune"] + [f.name for f in MUSIC_DIR.glob("*.mp3")]
        self.music_var = ctk.StringVar(value="Aucune")
        self.music_combo = ctk.CTkOptionMenu(
            options, variable=self.music_var,
            values=music_files, width=300
        )
        self.music_combo.pack(padx=20, pady=(0, 15))
        
        # Export button
        self.export_btn = ctk.CTkButton(
            center, text="🚀 Lancer l'export",
            height=50, width=250,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=ACCENT, command=self._start_export
        )
        self.export_btn.pack(pady=20)
        
        # Progress
        self.progress_bar = ctk.CTkProgressBar(center, width=300)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(
            center, text="", text_color=TEXT_MUTED
        )
        self.progress_label.pack()
    
    def _show_step(self, step: int):
        """Affiche une étape"""
        for i, f in enumerate(self.step_frames):
            if i == step:
                f.pack(fill="both", expand=True)
            else:
                f.pack_forget()
        
        for i, btn in enumerate(self.step_btns):
            if i == step:
                btn.configure(fg_color=ACCENT, text_color=TEXT)
            elif i < step:
                btn.configure(fg_color="transparent", text_color=SUCCESS)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_MUTED)
    
    def log(self, msg: str):
        """Ajoute un message au log"""
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        print(msg)
    
    # === VIDEO SELECTION ===
    
    def _select_video(self, video_path: Path):
        """Sélectionne et prépare une vidéo"""
        self.state.set_source_video(video_path)
        self.log(f"✅ Sélection: {video_path.name}")
        
        self.analyze_btn.configure(state="disabled", text="⏳ Préparation...")
        
        def prepare():
            try:
                # Sanitize (une seule fois)
                clean = self.engine.sanitize(video_path)
                self.state.clean_video = clean
                
                # Créer proxy pour preview rapide
                proxy = self.engine.create_proxy(clean)
                self.state.proxy_video = proxy
                
                # Infos
                info = self.engine.get_video_info(clean)
                self.state.duration = info['duration']
                self.state.fps = info['fps']
                
                self._queue_ui(self._load_player1, proxy)
                self._queue_ui(self.log, f"✨ Prêt ({info['duration']:.1f}s)")
                self._queue_ui(self._show_step, 1)
                
            except Exception as e:
                self._queue_ui(self.log, f"❌ Erreur: {e}")
            finally:
                self._queue_ui(
                    lambda: self.analyze_btn.configure(state="normal", text="🔍 Analyser")
                )
        
        threading.Thread(target=prepare, daemon=True).start()
    
    def _load_player1(self, video_path: Path):
        """Charge le lecteur de l'étape 1"""
        if self.player1:
            self.player1.release()
        
        self.player1 = create_video_player(
            self.video_frame1,
            on_time_update=self._on_time1
        )
        self.player1.load(str(video_path))
    
    def _on_time1(self, time_sec: float):
        """Callback temps étape 1"""
        m, s = divmod(int(time_sec), 60)
        dur = self.state.duration
        dm, ds = divmod(int(dur), 60)
        self.time_label1.configure(text=f"{m}:{s:02d} / {dm}:{ds:02d}")
        
        self._draw_playhead(time_sec)
    
    def _toggle_play1(self):
        """Toggle lecture étape 1"""
        if self.player1:
            self.player1.toggle()
            playing = self.player1.is_playing()
            self.play_btn1.configure(text="⏸️" if playing else "▶️")
    
    # === ANALYSIS ===
    
    def _analyze_video(self):
        """Analyse les silences"""
        if not self.state.clean_video:
            return
        
        self.analyze_btn.configure(state="disabled", text="⏳ Analyse...")
        
        def analyze():
            try:
                self._queue_ui(self.log, "🔍 Analyse des silences...")
                
                speech_ranges = self.engine.detect_silence(self.state.clean_video)
                
                # Convertir en Segments
                self.segments = []
                duration = self.state.duration
                last_end = 0.0
                
                for start, end in speech_ranges:
                    if start > last_end + 0.1:
                        self.segments.append(Segment(last_end, start, 'silence', False))
                    self.segments.append(Segment(start, end, 'speech', True))
                    last_end = end
                
                if last_end < duration - 0.1:
                    self.segments.append(Segment(last_end, duration, 'silence', False))
                
                self._queue_ui(self._draw_timeline)
                self._queue_ui(self.log, f"✅ {len(self.segments)} segments détectés")
                
            except Exception as e:
                self._queue_ui(self.log, f"❌ Erreur: {e}")
            finally:
                self._queue_ui(
                    lambda: self.analyze_btn.configure(state="normal", text="🔍 Analyser")
                )
        
        threading.Thread(target=analyze, daemon=True).start()
    
    def _draw_timeline(self):
        """Dessine la timeline"""
        self.timeline_canvas.delete("all")
        
        w = self.timeline_canvas.winfo_width()
        h = self.timeline_canvas.winfo_height()
        dur = self.state.duration
        
        if w < 10 or dur <= 0:
            return
        
        for seg in self.segments:
            x1 = (seg.start / dur) * w
            x2 = (seg.end / dur) * w
            
            if seg.segment_type == 'speech':
                color = SUCCESS if seg.keep else "#0f3320"
            else:
                color = "#3d1c0a" if seg.keep else "#f97316"
            
            self.timeline_canvas.create_rectangle(
                x1, 5, x2, h - 15, fill=color, outline=""
            )
    
    def _draw_playhead(self, time_sec: float):
        """Dessine le playhead"""
        self.timeline_canvas.delete("playhead")
        
        w = self.timeline_canvas.winfo_width()
        h = self.timeline_canvas.winfo_height()
        dur = self.state.duration
        
        if dur <= 0:
            return
        
        x = (time_sec / dur) * w
        
        self.timeline_canvas.create_line(
            x, 0, x, h - 12, fill=ACCENT, width=2, tags="playhead"
        )
    
    def _on_timeline_click(self, event):
        """Click sur la timeline"""
        w = self.timeline_canvas.winfo_width()
        dur = self.state.duration
        
        if w > 0 and dur > 0:
            time_sec = (event.x / w) * dur
            
            if self.player1:
                self.player1.seek(time_sec)
    
    # === CUT & TRANSCRIBE ===
    
    def _cut_and_transcribe(self):
        """Découpe et transcrit"""
        if not self.segments:
            self.log("⚠️ Analysez d'abord la vidéo")
            return
        
        self.next_btn1.configure(state="disabled", text="⏳ En cours...")
        
        def process():
            try:
                # Get segments to keep
                keep_segs = [(s.start, s.end) for s in self.segments if s.keep]
                
                if not keep_segs:
                    self._queue_ui(self.log, "⚠️ Aucun segment sélectionné")
                    return
                
                # Smart cut
                self._queue_ui(self.log, "✂️ Découpe en cours...")
                cut_video = self.engine.smart_cut(self.state.clean_video, keep_segs)
                self.state.cut_video = cut_video
                
                # Transcription
                self._queue_ui(self.log, "🧠 Transcription Whisper...")
                
                try:
                    from faster_whisper import WhisperModel
                    
                    model = WhisperModel("base", device="cpu", compute_type="int8")
                    segments, _ = model.transcribe(str(cut_video), word_timestamps=True, language="fr")
                    
                    self.subtitles = []
                    for seg in segments:
                        self.subtitles.append(Subtitle(
                            start=seg.start,
                            end=seg.end,
                            text=seg.text.strip(),
                            words=list(seg.words) if seg.words else []
                        ))
                    
                    self._queue_ui(self.log, f"✅ {len(self.subtitles)} lignes transcrites")
                    
                except Exception as e:
                    self._queue_ui(self.log, f"⚠️ Whisper error: {e}")
                    self.subtitles = []
                
                # Générer ASS
                ass_path = TEMP_DIR / "subs.ass"
                self.engine.generate_ass(
                    [{'start': s.start, 'end': s.end, 'text': s.text} for s in self.subtitles],
                    ass_path
                )
                
                # Setup step 2
                self._queue_ui(self._setup_step2)
                self._queue_ui(lambda: self._show_step(2))
                
            except Exception as e:
                self._queue_ui(self.log, f"❌ Erreur: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self._queue_ui(
                    lambda: self.next_btn1.configure(state="normal", text="✂️ Découper & Transcrire →")
                )
        
        threading.Thread(target=process, daemon=True).start()
    
    def _setup_step2(self):
        """Configure l'étape 2"""
        # Charger le lecteur
        if self.player2:
            self.player2.release()
        
        self.player2 = create_video_player(
            self.video_frame2,
            on_time_update=self._on_time2
        )
        
        if self.state.cut_video:
            self.player2.load(str(self.state.cut_video))
        
        # Afficher les sous-titres
        for widget in self.sub_scroll.winfo_children():
            widget.destroy()
        
        for i, sub in enumerate(self.subtitles):
            self._create_subtitle_row(i, sub)
    
    def _create_subtitle_row(self, index: int, sub: Subtitle):
        """Crée une ligne de sous-titre éditable"""
        row = ctk.CTkFrame(self.sub_scroll, fg_color="#1a1a1a", corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)
        
        # Bouton timestamp
        ctk.CTkButton(
            row, text=f"{sub.start:.1f}s", width=55, height=30,
            fg_color="#2a2a2a", hover_color=ACCENT,
            command=lambda t=sub.start: self._seek_sub(t)
        ).pack(side="left", padx=5, pady=5)
        
        # Entry
        entry = ctk.CTkEntry(row, font=ctk.CTkFont(size=11), fg_color=BG)
        entry.insert(0, sub.text)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=5)
        
        # Bind save
        entry.bind("<FocusOut>", lambda e, i=index: self._save_subtitle(i, entry.get()))
    
    def _seek_sub(self, time_sec: float):
        """Seek depuis un sous-titre"""
        if self.player2:
            self.player2.seek(time_sec)
    
    def _save_subtitle(self, index: int, text: str):
        """Sauvegarde un sous-titre"""
        if 0 <= index < len(self.subtitles):
            self.subtitles[index].text = text.strip()
    
    def _on_time2(self, time_sec: float):
        """Callback temps étape 2"""
        dur = self.player2.get_duration() if self.player2 else 0
        m, s = divmod(int(time_sec), 60)
        dm, ds = divmod(int(dur), 60)
        self.time_label2.configure(text=f"{m}:{s:02d} / {dm}:{ds:02d}")
    
    def _toggle_play2(self):
        """Toggle lecture étape 2"""
        if self.player2:
            self.player2.toggle()
            playing = self.player2.is_playing()
            self.play_btn2.configure(text="⏸️" if playing else "▶️")
    
    # === EXPORT ===
    
    def _start_export(self):
        """Lance l'export final"""
        self.export_btn.configure(state="disabled", text="⏳ Export...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Préparation...")
        
        def export():
            try:
                # Regénérer ASS avec les modifs
                ass_path = TEMP_DIR / "subs.ass"
                self.engine.generate_ass(
                    [{'start': s.start, 'end': s.end, 'text': s.text} for s in self.subtitles],
                    ass_path
                )
                
                self._queue_ui(lambda: self.progress_bar.set(0.3))
                self._queue_ui(lambda: self.progress_label.configure(text="Rendu en cours..."))
                
                # Musique
                music = None
                music_choice = self.music_var.get()
                if music_choice != "Aucune":
                    music = MUSIC_DIR / music_choice
                
                # Output path
                output_name = f"{self.state.source_video.stem}_VibeSlicer.mp4"
                output_path = OUTPUT_DIR / output_name
                
                # Render
                self.engine.render_final(
                    self.state.cut_video,
                    ass_path,
                    output_path,
                    music
                )
                
                self._queue_ui(lambda: self.progress_bar.set(1.0))
                self._queue_ui(lambda: self.progress_label.configure(text=f"✅ {output_name}"))
                self._queue_ui(self.log, f"🎉 Export terminé: {output_path}")
                
            except Exception as e:
                self._queue_ui(lambda: self.progress_label.configure(text=f"❌ Erreur"))
                self._queue_ui(self.log, f"❌ Erreur export: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self._queue_ui(
                    lambda: self.export_btn.configure(state="normal", text="🚀 Lancer l'export")
                )
        
        threading.Thread(target=export, daemon=True).start()
    
    def _on_time_updated(self, time_sec: float):
        """Événement: temps mis à jour"""
        pass
    
    def _on_segment_toggled(self, index: int):
        """Événement: segment togglé"""
        self._draw_timeline()
    
    def on_closing(self):
        """Nettoyage à la fermeture"""
        if self.player1:
            self.player1.release()
        if self.player2:
            self.player2.release()
        self.destroy()


def main():
    print("=" * 50)
    print("  VibeSlicer Studio v8.0")
    print("  Architecture propre - VLC + Smart Rendering")
    print("=" * 50)
    print()
    
    app = VibeSlicerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
