import customtkinter as ctk
import tkinter as tk
from src.core.state import ProjectState, EventType
from src.ui.components.timeline import Timeline
from src.ui.components.vlc_player import VLCPlayer, VLC_AVAILABLE

class MainWindow(ctk.CTk):
    """
    Fenêtre principale VibeSlicer (Nouvelle Architecture).
    Intègre le VLCPlayer et répond aux événements du ProjectState.
    """
    
    def __init__(self, state: ProjectState):
        super().__init__()
        
        self.project = state
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
            self.player = VLCPlayer(self.video_container, on_time_update=self._on_player_time_update)
        else:
            self.error_label = ctk.CTkLabel(self.video_container, text="⚠️ VLC non détecté\nInstallez VLC 64-bit", text_color="red")
            self.error_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # --- 2. Zone Contrôles ---
        self.controls_frame = ctk.CTkFrame(self, height=200, fg_color="#2b2b2b")
        self.controls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        self.controls_frame.grid_columnconfigure(1, weight=1) # Spacer
        
        # Timeline (Tout en haut des contrôles)
        self.timeline = Timeline(self.controls_frame, state=self.project, height=80)
        self.timeline.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        
        # Bouton Import
        self.btn_import = ctk.CTkButton(self.controls_frame, text="📂 Importer", width=100, command=self._on_import_click)
        self.btn_import.grid(row=1, column=0, padx=20, pady=10)
        
        # Bouton Play/Pause
        self.btn_play = ctk.CTkButton(self.controls_frame, text="▶ Play", width=100, command=self._on_play_click)
        self.btn_play.grid(row=1, column=1, padx=20, pady=10)
        
        # Label Temps
        self.time_label = ctk.CTkLabel(self.controls_frame, text="00:00.00", font=("Consolas", 16))
        self.time_label.grid(row=1, column=2, padx=20, pady=10)
        
        # Bouton Export
        self.btn_export = ctk.CTkButton(self.controls_frame, text="💿 Exporter", width=100, fg_color="green", command=self._on_export_click)
        self.btn_export.grid(row=1, column=3, padx=20, pady=10)
        
        # --- Abonnements aux Événements State ---
        self.project.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded_state)
        # On peut écouter le chargement du proxy aussi
        self.project.subscribe(EventType.PROXY_READY, self._on_proxy_ready)
        self.project.subscribe(EventType.TIME_UPDATED, self._update_time_display)
        self.project.subscribe(EventType.SEEK_REQUESTED, self._on_seek_requested)

    # --- Actions UI -> State ---

    def _on_import_click(self):
        """Click Import -> Dialog -> State.load_video"""
        file_path = tk.filedialog.askopenfilename(filetypes=[("Vidéo", "*.mp4 *.mov *.mkv *.avi")])
        if file_path:
            print(f"UI: Fichier sélectionné {file_path}")
            self.project.load_video(file_path)
            
    def _on_export_click(self):
        """Click Export -> Dialog -> State.request_export"""
        if not self.project.source_video:
            return
            
        file_path = tk.filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if file_path:
            print(f"UI: Export demandé vers {file_path}")
            self.project.request_export(file_path)

    def _on_play_click(self):
        """Click Play/Pause -> Player Action"""
        if self.player:
            self.player.toggle()
            if self.player.is_playing():
                self.btn_play.configure(text="⏸ Pause")
            else:
                self.btn_play.configure(text="▶ Play")

    def _on_player_time_update(self, time_sec):
        """Callback venant du Player (Thread VLC) -> State"""
        self.project.set_time(time_sec)

    # --- Réactions State -> UI ---
    
    def _on_seek_requested(self, time_sec):
        """Demande de saut temporel (ex: clic timeline)"""
        if self.player:
            self.player.seek(time_sec)

    def _on_video_loaded_state(self, video_path):
        """Le State dit qu'une vidéo est chargée -> On la charge dans le Player (Source HD temporaire)"""
        if self.player:
            self.player.load(video_path)
            self.btn_play.configure(text="▶ Play")
            
    def _on_proxy_ready(self, proxy_path):
        """Le proxy est prêt ! On recharge le player avec le fichier léger"""
        print(f"UI: Proxy prêt ! Bascule sur {proxy_path}")
        # Mémoriser la position actuelle
        current_time = self.player.get_time()
        was_playing = self.player.is_playing()
        
        # Charger proxy
        self.player.load(proxy_path)
        
        # Restaurer position et état
        self.player.seek(current_time)
        if was_playing:
            self.player.play()
        else:
            self.player.pause()

    def _update_time_display(self, current_time):
        """Le State dit que le temps a changé -> On met à jour le label"""
        # Formatage mm:ss.ms
        mins = int(current_time // 60)
        secs = int(current_time % 60)
        cents = int((current_time % 1) * 100)
        self.time_label.configure(text=f"{mins:02}:{secs:02}.{cents:02}")
