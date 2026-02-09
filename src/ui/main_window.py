"""
Fenêtre principale de VibeSlicer Studio
"""
import os
import sys
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from typing import Optional, List
import threading

from . import styles
from .components.video_player import VideoPlayer, CV2_AVAILABLE
from .components.timeline import Timeline
from .components.subtitle_editor import SubtitleEditor

from ..core.video_processor import VideoProcessor, Segment
from ..core.transcriber import Transcriber
from ..core.subtitle_manager import SubtitleManager, Subtitle
from ..utils.config import app_config, ui_config
from ..utils.logger import logger


class MainWindow(ctk.CTk):
    """Fenêtre principale de VibeSlicer Studio"""
    
    def __init__(self):
        super().__init__()
        
        # Configuration fenêtre
        self.title(ui_config.window_title)
        self.geometry(ui_config.window_geometry)
        self.minsize(*ui_config.window_min_size)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        # Services
        self.processor = VideoProcessor(app_config)
        self.transcriber = Transcriber(
            model_size=app_config.whisper_model,
            language=app_config.whisper_language
        )
        self.subtitle_manager = SubtitleManager(app_config.highlight_words)
        
        # État
        self.current_video: Optional[Path] = None
        self.clean_video: Optional[Path] = None
        self.cut_video: Optional[Path] = None
        self.segments: List[Segment] = []
        self.current_step: int = 0
        
        # Chargement des vidéos disponibles
        self.available_videos = self._scan_videos()
        
        # Construction UI
        self._setup_ui()
        
        logger.info(f"🎬 {ui_config.window_title}")
        logger.info(f"📂 {len(self.available_videos)} vidéo(s) trouvée(s)")
    
    def _scan_videos(self) -> List[Path]:
        """Scanne le dossier input pour les vidéos"""
        videos = []
        for ext in ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.MP4", "*.MOV"]:
            videos.extend(app_config.input_dir.glob(ext))
        return sorted(videos, key=lambda p: p.stat().st_mtime, reverse=True)
    
    def _setup_ui(self):
        """Configure l'interface principale"""
        # Layout principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # === SIDEBAR ===
        self._create_sidebar()
        
        # === MAIN CONTENT ===
        self.main_frame = ctk.CTkFrame(self, fg_color=styles.BG)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Steps frames
        self.step_frames = []
        
        self._create_step0()  # Sélection vidéo
        self._create_step1()  # Analyse & Timeline
        self._create_step2()  # Sous-titres
        self._create_step3()  # Export
        
        # Afficher étape 0
        self._show_step(0)
    
    def _create_sidebar(self):
        """Crée la barre latérale"""
        sidebar = ctk.CTkFrame(self, width=250, fg_color=styles.CARD, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Logo / Titre
        title = ctk.CTkLabel(
            sidebar,
            text="🎬 VibeSlicer",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=20)
        
        # Indicateurs d'étape
        self.step_indicators = []
        step_names = [
            "1. Sélection",
            "2. Analyse",
            "3. Sous-titres",
            "4. Export"
        ]
        
        for i, name in enumerate(step_names):
            indicator = ctk.CTkButton(
                sidebar,
                text=name,
                font=ctk.CTkFont(size=12),
                height=40,
                fg_color="transparent",
                text_color=styles.TEXT_MUTED,
                hover_color=styles.CARD,
                anchor="w",
                command=lambda idx=i: self._try_show_step(idx)
            )
            indicator.pack(fill="x", padx=10, pady=2)
            self.step_indicators.append(indicator)
        
        # Spacer
        ctk.CTkFrame(sidebar, fg_color="transparent").pack(fill="both", expand=True)
        
        # Console de log
        log_frame = ctk.CTkFrame(sidebar, fg_color=styles.BG, corner_radius=8)
        log_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            log_frame,
            text="📋 Console",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=10, pady=(5, 0))
        
        self.log_text = ctk.CTkTextbox(
            log_frame,
            height=150,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=styles.BG,
            text_color=styles.TEXT_MUTED
        )
        self.log_text.pack(fill="x", padx=5, pady=5)
    
    def _create_step0(self):
        """Étape 0: Sélection de la vidéo"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Titre
        ctk.CTkLabel(
            frame,
            text="📁 Sélectionnez une vidéo",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=20)
        
        # Liste des vidéos
        video_scroll = ctk.CTkScrollableFrame(
            frame,
            fg_color=styles.CARD,
            corner_radius=10
        )
        video_scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        if not self.available_videos:
            ctk.CTkLabel(
                video_scroll,
                text="Aucune vidéo dans le dossier 'input/'",
                text_color=styles.TEXT_MUTED
            ).pack(pady=50)
        else:
            for video in self.available_videos:
                self._create_video_card(video_scroll, video)
    
    def _create_video_card(self, parent, video_path: Path):
        """Crée une carte pour une vidéo"""
        card = ctk.CTkFrame(parent, fg_color="#222222", corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)
        
        # Infos
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=15, pady=10)
        
        ctk.CTkLabel(
            info_frame,
            text=video_path.name,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        ).pack(anchor="w")
        
        size_mb = video_path.stat().st_size / (1024 * 1024)
        ctk.CTkLabel(
            info_frame,
            text=f"{size_mb:.1f} MB",
            font=ctk.CTkFont(size=10),
            text_color=styles.TEXT_MUTED,
            anchor="w"
        ).pack(anchor="w")
        
        # Bouton sélection
        ctk.CTkButton(
            card,
            text="Sélectionner →",
            width=120,
            height=35,
            fg_color=styles.ACCENT,
            hover_color=styles.ACCENT_LIGHT,
            command=lambda p=video_path: self._select_video(p)
        ).pack(side="right", padx=15, pady=10)
    
    def _create_step1(self):
        """Étape 1: Analyse et Timeline"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent", height=60)
        header.pack(fill="x", padx=20, pady=10)
        
        self.step1_title = ctk.CTkLabel(
            header,
            text="🎥 Sélectionnez les segments à garder",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.step1_title.pack(side="left")
        
        self.analyze_btn = ctk.CTkButton(
            header,
            text="🔍 Analyser",
            width=120,
            fg_color=styles.ACCENT,
            command=self._analyze_video
        )
        self.analyze_btn.pack(side="right")
        
        # Zone vidéo
        video_frame = ctk.CTkFrame(frame, fg_color="#0a0a0a", corner_radius=10)
        video_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.step1_canvas = tk.Canvas(
            video_frame,
            bg="#0a0a0a",
            highlightthickness=0
        )
        self.step1_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Contrôles
        controls = ctk.CTkFrame(video_frame, fg_color="transparent", height=40)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        
        self.play_btn1 = ctk.CTkButton(
            controls,
            text="▶️",
            width=40,
            command=self._toggle_play1
        )
        self.play_btn1.pack(side="left", padx=5)
        
        self.time_label1 = ctk.CTkLabel(controls, text="0:00 / 0:00")
        self.time_label1.pack(side="left", padx=10)
        
        # Timeline
        timeline_frame = ctk.CTkFrame(frame, fg_color=styles.CARD, corner_radius=10, height=80)
        timeline_frame.pack(fill="x", padx=20, pady=(0, 10))
        timeline_frame.pack_propagate(False)
        
        self.timeline = Timeline(
            timeline_frame,
            on_seek=self._on_timeline_seek,
            height=70
        )
        self.timeline.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Bouton suivant
        self.next_btn1 = ctk.CTkButton(
            frame,
            text="✂️ Découper & Transcrire →",
            height=40,
            fg_color=styles.SUCCESS,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._cut_and_transcribe
        )
        self.next_btn1.pack(pady=15)
        
        # Video player
        if CV2_AVAILABLE:
            self.player1 = VideoPlayer(self.step1_canvas, self._on_frame1)
        else:
            self.player1 = None
    
    def _create_step2(self):
        """Étape 2: Édition des sous-titres"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent", height=60)
        header.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            header,
            text="📝 Éditez les sous-titres",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")
        
        # Contenu principal (vidéo + éditeur)
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=10)
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        
        # Zone vidéo
        video_frame = ctk.CTkFrame(content, fg_color="#0a0a0a", corner_radius=10)
        video_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        self.step2_canvas = tk.Canvas(
            video_frame,
            bg="#0a0a0a",
            highlightthickness=0
        )
        self.step2_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Contrôles vidéo
        controls2 = ctk.CTkFrame(video_frame, fg_color="transparent", height=40)
        controls2.pack(fill="x", padx=10, pady=(0, 10))
        
        self.play_btn2 = ctk.CTkButton(
            controls2,
            text="▶️",
            width=40,
            command=self._toggle_play2
        )
        self.play_btn2.pack(side="left", padx=5)
        
        self.time_label2 = ctk.CTkLabel(controls2, text="0:00 / 0:00")
        self.time_label2.pack(side="left", padx=10)
        
        # Éditeur de sous-titres
        self.sub_editor = SubtitleEditor(
            content,
            on_seek=self._on_sub_seek
        )
        self.sub_editor.grid(row=0, column=1, sticky="nsew")
        
        # Bouton export
        self.export_btn = ctk.CTkButton(
            frame,
            text="🎬 Exporter →",
            height=40,
            fg_color=styles.SUCCESS,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._go_to_export
        )
        self.export_btn.pack(pady=15)
        
        # Player
        if CV2_AVAILABLE:
            self.player2 = VideoPlayer(self.step2_canvas, self._on_frame2)
        else:
            self.player2 = None
    
    def _create_step3(self):
        """Étape 3: Export"""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.step_frames.append(frame)
        
        # Centrage
        center = ctk.CTkFrame(frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            center,
            text="🎬 Export Final",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=20)
        
        # Options
        options = ctk.CTkFrame(center, fg_color=styles.CARD, corner_radius=10)
        options.pack(pady=20, padx=30, ipadx=30, ipady=20)
        
        # Musique
        ctk.CTkLabel(
            options,
            text="🎵 Musique de fond",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.music_var = ctk.StringVar(value="none")
        self.music_combo = ctk.CTkOptionMenu(
            options,
            variable=self.music_var,
            values=self._get_music_files(),
            width=300
        )
        self.music_combo.pack(padx=20, pady=(0, 15))
        
        # Bouton export
        self.final_export_btn = ctk.CTkButton(
            center,
            text="🚀 Lancer l'export",
            height=50,
            width=250,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=styles.ACCENT,
            command=self._start_export
        )
        self.final_export_btn.pack(pady=20)
        
        # Barre de progression
        self.progress_bar = ctk.CTkProgressBar(center, width=300)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(
            center,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=styles.TEXT_MUTED
        )
        self.progress_label.pack()
    
    def _get_music_files(self) -> List[str]:
        """Liste les fichiers musicaux disponibles"""
        files = ["Aucune"]
        for ext in ["*.mp3", "*.wav", "*.m4a"]:
            for f in app_config.music_dir.glob(ext):
                files.append(f.name)
        return files
    
    def _show_step(self, step: int):
        """Affiche une étape"""
        for i, frame in enumerate(self.step_frames):
            if i == step:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        
        # Mettre à jour les indicateurs
        for i, indicator in enumerate(self.step_indicators):
            if i == step:
                indicator.configure(fg_color=styles.ACCENT, text_color=styles.TEXT)
            elif i < step:
                indicator.configure(fg_color="transparent", text_color=styles.SUCCESS)
            else:
                indicator.configure(fg_color="transparent", text_color=styles.TEXT_MUTED)
        
        self.current_step = step
    
    def _try_show_step(self, step: int):
        """Tente d'afficher une étape (vérifie les prérequis)"""
        if step <= self.current_step or step == 0:
            self._show_step(step)
    
    def log(self, message: str):
        """Ajoute un message au log"""
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        logger.info(message)
    
    # === VIDEO SELECTION ===
    
    def _select_video(self, video_path: Path):
        """Sélectionne une vidéo"""
        self.current_video = video_path
        self.log(f"✅ Sélection: {video_path.name}")
        
        # Nettoyer la vidéo
        try:
            self.clean_video = self.processor.sanitize(video_path)
            self.log(f"✨ Prêt: {self.clean_video.name}")
            
            # Charger dans le player
            if self.player1:
                self.player1.load(self.clean_video)
            
            self._show_step(1)
            
        except Exception as e:
            self.log(f"❌ Erreur: {e}")
    
    # === STEP 1: ANALYSIS ===
    
    def _analyze_video(self):
        """Lance l'analyse des silences"""
        if not self.clean_video:
            return
        
        self.analyze_btn.configure(state="disabled", text="🔍 Analyse...")
        
        def analyze_thread():
            try:
                self.segments = self.processor.analyze_silence(self.clean_video)
                duration = self.processor.get_duration(self.clean_video)
                
                self.after(0, lambda: self.timeline.set_segments(self.segments, duration))
                self.after(0, lambda: self.log(f"✅ {len(self.segments)} segments détectés"))
                
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Erreur: {e}"))
            finally:
                self.after(0, lambda: self.analyze_btn.configure(state="normal", text="🔍 Analyser"))
        
        threading.Thread(target=analyze_thread, daemon=True).start()
    
    def _toggle_play1(self):
        """Toggle lecture étape 1"""
        if self.player1:
            self.player1.toggle()
            self.play_btn1.configure(text="⏸️" if self.player1.playing else "▶️")
    
    def _on_frame1(self, time_sec: float):
        """Callback frame étape 1"""
        self.timeline.set_time(time_sec)
        if self.player1:
            m, s = divmod(int(time_sec), 60)
            total_m, total_s = divmod(int(self.player1.duration), 60)
            self.time_label1.configure(text=f"{m}:{s:02d} / {total_m}:{total_s:02d}")
    
    def _on_timeline_seek(self, time_sec: float):
        """Seek depuis la timeline"""
        if self.player1:
            self.player1.seek(time_sec)
    
    def _cut_and_transcribe(self):
        """Découpe et transcrit la vidéo"""
        if not self.segments:
            self.log("⚠️ Analysez d'abord la vidéo")
            return
        
        self.next_btn1.configure(state="disabled", text="⏳ En cours...")
        
        def process_thread():
            try:
                # Découpe
                self.after(0, lambda: self.log("✂️ Découpe en cours..."))
                self.cut_video = self.processor.cut_segments(self.clean_video, self.segments)
                self.after(0, lambda: self.log(f"✅ Découpe terminée"))
                
                # Transcription
                self.after(0, lambda: self.log("🧠 Transcription Whisper..."))
                segments = self.transcriber.transcribe(self.cut_video)
                self.subtitle_manager.load_from_whisper(segments)
                
                self.after(0, lambda: self.log(f"✅ {len(segments)} lignes transcrites"))
                
                # Générer ASS initial
                ass_path = app_config.temp_dir / "subs.ass"
                self.subtitle_manager.generate_ass(ass_path)
                
                # Charger l'étape 2
                self.after(0, self._setup_step2)
                self.after(0, lambda: self._show_step(2))
                
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Erreur: {e}"))
                import traceback
                traceback.print_exc()
            finally:
                self.after(0, lambda: self.next_btn1.configure(
                    state="normal", text="✂️ Découper & Transcrire →"
                ))
        
        threading.Thread(target=process_thread, daemon=True).start()
    
    # === STEP 2: SUBTITLES ===
    
    def _setup_step2(self):
        """Configure l'étape 2 après le traitement"""
        if self.player2 and self.cut_video:
            self.player2.load(self.cut_video)
        
        self.sub_editor.set_subtitles(self.subtitle_manager)
    
    def _toggle_play2(self):
        """Toggle lecture étape 2"""
        if self.player2:
            self.player2.toggle()
            self.play_btn2.configure(text="⏸️" if self.player2.playing else "▶️")
    
    def _on_frame2(self, time_sec: float):
        """Callback frame étape 2"""
        if self.player2:
            m, s = divmod(int(time_sec), 60)
            total_m, total_s = divmod(int(self.player2.duration), 60)
            self.time_label2.configure(text=f"{m}:{s:02d} / {total_m}:{total_s:02d}")
    
    def _on_sub_seek(self, time_sec: float):
        """Seek depuis l'éditeur de sous-titres"""
        if self.player2:
            self.player2.seek(time_sec)
    
    def _go_to_export(self):
        """Passe à l'étape export"""
        # Regénérer l'ASS avec les modifications
        ass_path = app_config.temp_dir / "subs.ass"
        self.subtitle_manager.generate_ass(ass_path)
        self.log("📝 Sous-titres sauvegardés")
        
        self._show_step(3)
    
    # === STEP 3: EXPORT ===
    
    def _start_export(self):
        """Lance l'export final"""
        self.final_export_btn.configure(state="disabled", text="⏳ Export...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Préparation...")
        
        def export_thread():
            try:
                self.after(0, lambda: self.progress_label.configure(text="Rendu en cours..."))
                self.after(0, lambda: self.progress_bar.set(0.3))
                
                # Musique
                music_choice = self.music_var.get()
                music_path = None
                if music_choice != "Aucune":
                    music_path = app_config.music_dir / music_choice
                
                # Chemins
                ass_path = app_config.temp_dir / "subs.ass"
                output_name = f"{self.current_video.stem}_VibeSlicer.mp4"
                output_path = app_config.output_dir / output_name
                
                # Rendu
                self.processor.render(
                    self.cut_video,
                    ass_path,
                    music_path,
                    output_path
                )
                
                self.after(0, lambda: self.progress_bar.set(1.0))
                self.after(0, lambda: self.progress_label.configure(
                    text=f"✅ Exporté: {output_name}"
                ))
                self.after(0, lambda: self.log(f"🎉 Export terminé: {output_path}"))
                
            except Exception as e:
                self.after(0, lambda: self.progress_label.configure(
                    text=f"❌ Erreur: {str(e)[:50]}"
                ))
                self.after(0, lambda: self.log(f"❌ Erreur export: {e}"))
                import traceback
                traceback.print_exc()
            finally:
                self.after(0, lambda: self.final_export_btn.configure(
                    state="normal", text="🚀 Lancer l'export"
                ))
        
        threading.Thread(target=export_thread, daemon=True).start()
    
    def on_closing(self):
        """Nettoyage à la fermeture"""
        if self.player1:
            self.player1.release()
        if self.player2:
            self.player2.release()
        self.destroy()
