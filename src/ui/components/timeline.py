"""
Composant Timeline pour visualisation et édition des segments
"""
import tkinter as tk
import customtkinter as ctk
from typing import List, Callable, Optional

from .. import styles
from ...core.video_processor import Segment
from ...utils.logger import logger


class Timeline(ctk.CTkFrame):
    """
    Timeline interactive pour la gestion des segments
    
    Fonctionnalités:
    - Visualisation des segments (parole/silence)
    - Toggle keep/cut par clic
    - Playhead avec position actuelle
    - Callback on seek
    """
    
    def __init__(self, master, on_seek: Callable = None, height: int = 60, **kwargs):
        super().__init__(master, height=height, fg_color=styles.CARD, **kwargs)
        
        self.on_seek = on_seek
        self.segments: List[Segment] = []
        self.duration: float = 0
        self.current_time: float = 0
        
        # Canvas principal
        self.canvas = tk.Canvas(
            self,
            height=height,
            bg=styles.CARD,
            highlightthickness=0
        )
        self.canvas.pack(fill="x", expand=True)
        
        # Bindings
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
    
    def set_segments(self, segments: List[Segment], duration: float):
        """Définit les segments à afficher"""
        self.segments = segments
        self.duration = duration
        self.redraw()
    
    def set_time(self, time_sec: float):
        """Met à jour la position du playhead"""
        self.current_time = time_sec
        self._draw_playhead()
    
    def redraw(self):
        """Redessine la timeline complète"""
        self.canvas.delete("all")
        
        if not self.segments or self.duration <= 0:
            return
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width < 10:
            return
        
        # Dessiner chaque segment
        for seg in self.segments:
            x1 = (seg.start / self.duration) * width
            x2 = (seg.end / self.duration) * width
            
            if seg.segment_type == 'speech':
                color = styles.SPEECH_COLOR if seg.keep else styles.SPEECH_COLOR_DIM
            else:
                color = styles.SILENCE_COLOR_DIM if seg.keep else styles.SILENCE_COLOR
            
            # Rectangle du segment
            y1 = 5
            y2 = height - 15  # Espace pour les marqueurs de temps
            
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=color,
                outline=""
            )
            
            # Indicateur keep/cut
            if not seg.keep:
                # Croix pour les segments coupés
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                size = min(8, (x2 - x1) / 2)
                if size > 3:
                    self.canvas.create_line(
                        cx - size, cy - size, cx + size, cy + size,
                        fill=styles.TEXT_DIM, width=2
                    )
                    self.canvas.create_line(
                        cx - size, cy + size, cx + size, cy - size,
                        fill=styles.TEXT_DIM, width=2
                    )
        
        # Marqueurs de temps
        self._draw_time_markers(width, height)
        
        # Playhead
        self._draw_playhead()
    
    def _draw_time_markers(self, width: int, height: int):
        """Dessine les marqueurs de temps"""
        if self.duration <= 0:
            return
        
        # Espacement adaptatif
        if self.duration > 120:
            interval = 30
        elif self.duration > 60:
            interval = 15
        elif self.duration > 20:
            interval = 5
        else:
            interval = 2
        
        y = height - 10
        
        for t in range(0, int(self.duration) + 1, interval):
            x = (t / self.duration) * width
            
            # Format temps
            m = int(t // 60)
            s = int(t % 60)
            text = f"{m}:{s:02d}"
            
            self.canvas.create_text(
                x, y,
                text=text,
                fill=styles.TEXT_MUTED,
                font=("Segoe UI", 8),
                anchor="n"
            )
    
    def _draw_playhead(self):
        """Dessine le playhead"""
        self.canvas.delete("playhead")
        
        if self.duration <= 0:
            return
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        x = (self.current_time / self.duration) * width
        
        # Ligne verticale
        self.canvas.create_line(
            x, 0, x, height - 12,
            fill=styles.ACCENT,
            width=2,
            tags="playhead"
        )
        
        # Triangle en haut
        self.canvas.create_polygon(
            x - 6, 0,
            x + 6, 0,
            x, 8,
            fill=styles.ACCENT,
            tags="playhead"
        )
    
    def _on_click(self, event):
        """Gère le clic sur la timeline"""
        width = self.canvas.winfo_width()
        
        # Vérifier si clic sur un segment (partie haute)
        if event.y < self.canvas.winfo_height() - 15:
            # Trouver le segment cliqué
            for seg in self.segments:
                x1 = (seg.start / self.duration) * width
                x2 = (seg.end / self.duration) * width
                
                if x1 <= event.x <= x2:
                    # Toggle keep
                    seg.keep = not seg.keep
                    self.redraw()
                    logger.debug(f"Segment {seg.start:.1f}-{seg.end:.1f}: {'keep' if seg.keep else 'cut'}")
                    return
        
        # Sinon, seek
        self._seek_to(event.x)
    
    def _on_drag(self, event):
        """Gère le drag pour seek"""
        self._seek_to(event.x)
    
    def _seek_to(self, x: int):
        """Seek à une position X sur le canvas"""
        if self.duration <= 0:
            return
        
        width = self.canvas.winfo_width()
        time_sec = (x / width) * self.duration
        time_sec = max(0, min(time_sec, self.duration))
        
        self.current_time = time_sec
        self._draw_playhead()
        
        if self.on_seek:
            self.on_seek(time_sec)
