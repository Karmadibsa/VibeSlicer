"""
Éditeur de sous-titres avec prévisualisation vidéo
"""
import tkinter as tk
import customtkinter as ctk
from typing import List, Callable, Optional

from .. import styles
from ...core.subtitle_manager import Subtitle, SubtitleManager
from ...utils.logger import logger


class SubtitleEditor(ctk.CTkFrame):
    """
    Éditeur de sous-titres interactif
    
    Fonctionnalités:
    - Liste des sous-titres éditables
    - Click sur timestamp pour seek
    - Sauvegarde automatique des modifications
    """
    
    def __init__(self, master, on_seek: Callable = None, **kwargs):
        super().__init__(master, fg_color=styles.CARD, **kwargs)
        
        self.on_seek = on_seek
        self.subtitle_manager: Optional[SubtitleManager] = None
        self._entries: List[ctk.CTkEntry] = []
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configure l'interface"""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=40)
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            header,
            text="📝 Sous-titres",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")
        
        # Compteur
        self.count_label = ctk.CTkLabel(
            header,
            text="0 lignes",
            font=ctk.CTkFont(size=11),
            text_color=styles.TEXT_MUTED
        )
        self.count_label.pack(side="right")
        
        # Liste scrollable
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=styles.BG,
            corner_radius=8
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    
    def set_subtitles(self, manager: SubtitleManager):
        """Charge les sous-titres depuis un SubtitleManager"""
        self.subtitle_manager = manager
        self._refresh_list()
    
    def _refresh_list(self):
        """Rafraîchit la liste des sous-titres"""
        # Nettoyer
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self._entries.clear()
        
        if not self.subtitle_manager:
            return
        
        subs = self.subtitle_manager.subtitles
        self.count_label.configure(text=f"{len(subs)} lignes")
        
        for i, sub in enumerate(subs):
            self._create_subtitle_row(i, sub)
    
    def _create_subtitle_row(self, index: int, subtitle: Subtitle):
        """Crée une ligne d'édition de sous-titre"""
        row = ctk.CTkFrame(
            self.scroll_frame,
            fg_color="#1a1a1a",
            corner_radius=6,
            height=40
        )
        row.pack(fill="x", pady=2, padx=2)
        row.pack_propagate(False)
        
        # Bouton timestamp (click to seek)
        time_btn = ctk.CTkButton(
            row,
            text=f"{subtitle.start:.1f}s",
            font=ctk.CTkFont(size=10, weight="bold"),
            width=55,
            height=30,
            fg_color="#2a2a2a",
            hover_color=styles.ACCENT,
            corner_radius=4,
            command=lambda t=subtitle.start: self._on_time_click(t)
        )
        time_btn.pack(side="left", padx=5, pady=5)
        
        # Champ d'édition
        entry = ctk.CTkEntry(
            row,
            font=ctk.CTkFont(size=11),
            fg_color=styles.BG,
            height=30,
            corner_radius=4
        )
        entry.insert(0, subtitle.text)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=5)
        
        # Bind pour sauvegarde
        entry.bind("<FocusOut>", lambda e, idx=index: self._on_text_change(idx, entry.get()))
        entry.bind("<Return>", lambda e, idx=index: self._on_text_change(idx, entry.get()))
        
        self._entries.append(entry)
    
    def _on_time_click(self, time_sec: float):
        """Gestion du click sur un timestamp"""
        if self.on_seek:
            self.on_seek(time_sec)
    
    def _on_text_change(self, index: int, new_text: str):
        """Gestion de la modification de texte"""
        if self.subtitle_manager:
            old_text = self.subtitle_manager.subtitles[index].text
            if new_text.strip() != old_text:
                self.subtitle_manager.update_text(index, new_text)
                logger.debug(f"Subtitle {index} updated")
    
    def get_subtitles(self) -> List[Subtitle]:
        """Retourne les sous-titres avec les modifications"""
        if self.subtitle_manager:
            return self.subtitle_manager.subtitles
        return []


class SubtitlePanel(ctk.CTkFrame):
    """
    Panel complet avec prévisualisation vidéo et éditeur de sous-titres
    """
    
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=styles.CARD, **kwargs)
        
        self.video_player = None  # Set externally
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configure l'interface"""
        # Zone vidéo (gauche)
        video_frame = ctk.CTkFrame(self, fg_color="#0a0a0a", corner_radius=8)
        video_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Canvas vidéo
        self.video_canvas = tk.Canvas(
            video_frame,
            bg="#0a0a0a",
            highlightthickness=0
        )
        self.video_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Contrôles vidéo
        controls = ctk.CTkFrame(video_frame, fg_color="transparent", height=40)
        controls.pack(fill="x", padx=5, pady=(0, 5))
        
        self.play_btn = ctk.CTkButton(
            controls,
            text="▶️ Play",
            width=80,
            height=30,
            command=self._toggle_play
        )
        self.play_btn.pack(side="left", padx=5)
        
        self.time_label = ctk.CTkLabel(
            controls,
            text="0:00 / 0:00",
            font=ctk.CTkFont(size=11)
        )
        self.time_label.pack(side="left", padx=10)
        
        # Éditeur sous-titres (droite)
        self.editor = SubtitleEditor(
            self,
            on_seek=self._on_seek,
            width=350
        )
        self.editor.pack(side="right", fill="y", padx=(0, 10), pady=10)
    
    def set_video_player(self, player):
        """Définit le lecteur vidéo"""
        self.video_player = player
    
    def set_subtitles(self, manager: SubtitleManager):
        """Charge les sous-titres"""
        self.editor.set_subtitles(manager)
    
    def _toggle_play(self):
        """Toggle lecture/pause"""
        if self.video_player:
            self.video_player.toggle()
            is_playing = self.video_player.playing
            self.play_btn.configure(text="⏸️ Pause" if is_playing else "▶️ Play")
    
    def _on_seek(self, time_sec: float):
        """Seek dans la vidéo"""
        if self.video_player:
            self.video_player.seek(time_sec)
    
    def update_time(self, current: float, total: float):
        """Met à jour l'affichage du temps"""
        def fmt(t):
            m = int(t // 60)
            s = int(t % 60)
            return f"{m}:{s:02d}"
        
        self.time_label.configure(text=f"{fmt(current)} / {fmt(total)}")
