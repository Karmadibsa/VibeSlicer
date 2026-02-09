import customtkinter as ctk
import tkinter as tk
from src.core.project_state import ProjectState, EventType
from src.ui.components.vlc_player import VLCPlayer, VLC_AVAILABLE

class MainWindow(ctk.CTk):
    """
    Fenêtre principale VibeSlicer (Nouvelle Architecture).
    Intègre le VLCPlayer et répond aux événements du ProjectState.
    """
    
    def __init__(self, state: ProjectState):
        super().__init__()
        
        self.state = state
        self.title("VibeSlicer Studio v8.0 (Legacy Free)")
        self.geometry("1400x900")
        
        # Configuration Grille
        self.grid_rowconfigure(0, weight=1)  # Zone Vidéo (Expand)
        self.grid_rowconfigure(1, weight=0)  # Zone Timeline/Contrôles (Fixe)
        self.grid_columnconfigure(0, weight=1)
        
        # --- 1. Zone Vidéo (VLC) ---
        self.video_container = ctk.CTkFrame(self, fg_color="black")
        self.video_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.player = None
        if VLC_AVAILABLE:
            # On passe le container. VLCPlayer créera sa propre frame `tk.Frame` dedans.
            # On connecte le callback de temps pour mettre à jour le State.
            self.player = VLCPlayer(self.video_container, on_time_update=self._on_player_time_update)
        else:
            self.error_label = ctk.CTkLabel(self.video_container, text="⚠️ VLC non détecté\nInstallez VLC 64-bit", text_color="red")
            self.error_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # --- 2. Zone Contrôles ---
        self.controls_frame = ctk.CTkFrame(self, height=150, fg_color="#2b2b2b")
        self.controls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        # Layout Contrôles
        self.controls_frame.grid_columnconfigure(1, weight=1) # Spacer
        
        # Bouton Import
        self.btn_import = ctk.CTkButton(self.controls_frame, text="📂 Importer", width=100, command=self._on_import_click)
        self.btn_import.grid(row=0, column=0, padx=20, pady=20)
        
        # Bouton Play/Pause
        self.btn_play = ctk.CTkButton(self.controls_frame, text="▶ Play", width=100, command=self._on_play_click)
        self.btn_play.grid(row=0, column=1, padx=20, pady=20)
        
        # Label Temps
        self.time_label = ctk.CTkLabel(self.controls_frame, text="00:00.00", font=("Consolas", 16))
        self.time_label.grid(row=0, column=2, padx=20, pady=20)
        
        # --- Abonnements aux Événements State ---
        self.state.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded_state)
        # On pourrait s'abonner à TIME_UPDATED pour mettre à jour d'autres widgets (timeline graphique)
        self.state.subscribe(EventType.TIME_UPDATED, self._update_time_display)

    # --- Actions UI -> State ---

    def _on_import_click(self):
        """Click Import -> Dialog -> State.load_video"""
        file_path = tk.filedialog.askopenfilename(filetypes=[("Vidéo", "*.mp4 *.mov *.mkv *.avi")])
        if file_path:
            print(f"UI: Fichier sélectionné {file_path}")
            self.state.load_video(file_path)

    def _on_play_click(self):
        """Click Play/Pause -> Player Action"""
        if self.player:
            self.player.toggle()
            # Mettre à jour le texte du bouton (simple feedback)
            if self.player.is_playing():
                self.btn_play.configure(text="⏸ Pause")
            else:
                self.btn_play.configure(text="▶ Play")

    def _on_player_time_update(self, time_sec):
        """Callback venant du Player (Thread VLC) -> State"""
        # Le player nous dit "on est à t=X". On le dit au State.
        # Le State va ensuite notifier tout le monde (y compris nous-mêmes via _update_time_display)
        self.state.set_time(time_sec)

    # --- Réactions State -> UI ---

    def _on_video_loaded_state(self, video_path):
        """Le State dit qu'une vidéo est chargée -> On la charge dans le Player"""
        if self.player:
            success = self.player.load(video_path)
            if success:
                print("UI: Vidéo chargée dans VLC avec succès")
                self.btn_play.configure(text="▶ Play")
            else:
                print("UI: Erreur chargement VLC")

    def _update_time_display(self, current_time):
        """Le State dit que le temps a changé -> On met à jour le label"""
        # Formatage mm:ss.ms
        mins = int(current_time // 60)
        secs = int(current_time % 60)
        cents = int((current_time % 1) * 100)
        self.time_label.configure(text=f"{mins:02}:{secs:02}.{cents:02}")
