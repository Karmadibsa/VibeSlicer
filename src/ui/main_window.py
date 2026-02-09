import customtkinter as ctk
from src.core.project_state import ProjectState, EventType
import tkinter as tk

class MainWindow(ctk.CTk):
    """
    Fenêtre principale VibeSlicer (Nouvelle Architecture).
    Seule responsabilité : Afficher ProjectState.
    """
    
    def __init__(self, state: ProjectState):
        super().__init__()
        
        self.state = state
        self.title("VibeSlicer Studio v8.0 (Refactored)")
        self.geometry("1400x900")
        
        # Configuration Grille
        self.grid_rowconfigure(0, weight=1)  # Zone Vidéo (Haut)
        self.grid_rowconfigure(1, weight=0)  # Zone Timeline (Bas)
        self.grid_columnconfigure(0, weight=1)
        
        # --- 1. Zone Vidéo (Placeholder pour VLC) ---
        self.video_frame = ctk.CTkFrame(self, fg_color="#1a1a1a")
        self.video_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.placeholder_label = ctk.CTkLabel(self.video_frame, text="Zone Vidéo (VLC)", font=("Arial", 24))
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # --- 2. Zone Contrôles & Timeline ---
        self.controls_frame = ctk.CTkFrame(self, height=200, fg_color="#2b2b2b")
        self.controls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        
        # Bouton Import
        self.btn_import = ctk.CTkButton(self.controls_frame, text="Importer Vidéo", command=self._on_import_click)
        self.btn_import.pack(pady=20)
        
        # S'abonner aux événements du State
        self.state.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded)

    def _on_import_click(self):
        """Action UI pure : Ouvre dialogue et modifie le State"""
        file_path = tk.filedialog.askopenfilename(filetypes=[("Vidéo", "*.mp4 *.mov *.mkv")])
        if file_path:
            self.state.load_video(file_path)
            
    def _on_video_loaded(self, video_path):
        """Réaction à un changement d'état (venant du State)"""
        self.placeholder_label.configure(text=f"Vidéo chargée : {video_path.name}")
        print(f"UI update: Vidéo chargée {video_path}")
