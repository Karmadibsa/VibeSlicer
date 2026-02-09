import customtkinter as ctk
import tkinter as tk
from src.core.state import ProjectState, EventType

class Timeline(ctk.CTkFrame):
    """
    Timeline visuelle simple.
    - Dessine les segments (Vert=Parole, Rouge=Silence)
    - Affiche le curseur de lecture
    - Permet le SEEK (clic)
    """
    
    def __init__(self, master, state: ProjectState, **kwargs):
        super().__init__(master, **kwargs)
        self.state = state
        
        self.canvas_height = 80
        self.canvas = tk.Canvas(self, bg="#1e1e1e", height=self.canvas_height, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.canvas.bind("<Button-1>", self._on_click)
        
        # Abonnements State
        self.state.subscribe(EventType.SEGMENTS_CHANGED, self._redraw_segments)
        self.state.subscribe(EventType.TIME_UPDATED, self._update_cursor)
        
        self.cursor_line = None
        self.segments_items = []
        
    def _redraw_segments(self, segments):
        """Redessine tous les blocs Verts/Rouges"""
        self.canvas.delete("all")
        self.segments_items = []
        
        if not segments:
            return
            
        total_duration = segments[-1].end if segments else 100.0
        width = self.canvas.winfo_width()
        scale = width / total_duration if total_duration > 0 else 1.0
        
        for seg in segments:
            x1 = seg.start * scale
            x2 = seg.end * scale
            
            color = "#4caf50" if seg.keep else "#f44336" # Vert ou Rouge
            
            # Dessiner rectangle
            rect = self.canvas.create_rectangle(x1, 10, x2, self.canvas_height-10, fill=color, outline="")
            self.segments_items.append(rect)
            
        # Curseur (initialisation)
        self.cursor_line = self.canvas.create_line(0, 0, 0, self.canvas_height, fill="yellow", width=2)

    def _update_cursor(self, current_time):
        """Déplace la ligne jaune"""
        if not self.state.segments:
            return
            
        total_duration = self.state.segments[-1].end
        width = self.canvas.winfo_width()
        
        # Recalculer scale (au cas où resize)
        scale = width / total_duration if total_duration > 0 else 0
        
        x = current_time * scale
        
        if self.cursor_line:
            self.canvas.coords(self.cursor_line, x, 0, x, self.canvas_height)
        else:
             self.cursor_line = self.canvas.create_line(x, 0, x, self.canvas_height, fill="yellow", width=2)
             
    def _on_click(self, event):
        """Click sur la timeline -> Seek"""
        if not self.state.segments:
            return
            
        width = self.canvas.winfo_width()
        total_duration = self.state.segments[-1].end
        
        # x -> time
        ratio = event.x / width
        target_time = ratio * total_duration
        
        print(f"Timeline Seek: {target_time:.2f}s")
        # On dit au State de changer le temps (ce qui va trigger le Player pour seek)
        # Mais le Player VLC doit écouter TIME_UPDATED ? Non, Player SET time_updated.
        # Il faut une commande explicite "SEEK" dans le State ou une méthode directe ?
        # Dans ProjectState, set_time est une notification "ça a changé".
        # Il faudrait une méthode `request_seek(time)` qui notifie `SEEK_REQUESTED`.
        # Pour faire simple, on va notifier via set_time et le Player (s'il est malin) va voir la différence ?
        # Mieux : On ajoute un événement `SEEK_REQUESTED` dans ProjectState.
        
        # Pour l'instant, hack rapide : on accède au player via main_window ? Non, pas propre.
        # On va ajouter `request_seek` au State.
        self.state.request_seek(target_time)
