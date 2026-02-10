import customtkinter as ctk
import tkinter as tk
from src.core.state import ProjectState, EventType
from src.ui.components.timeline import Timeline
from src.ui.components.video_player import VideoPlayer, FFPY_AVAILABLE

class MainWindow(ctk.CTk):
    """
    Interface VibeSlicer Studio (Style Montage Pro)
    Structure : Sidebar (Gauche) + Viewer (Haut) + Timeline (Bas)
    """
    
    def __init__(self, state: ProjectState):
        super().__init__()
        
        self.project = state
        self.title("VibeSlicer Studio v8.0 - Pro Edition")
        self.geometry("1600x900")
        
        # --- Layout Principal (Grille 2 colonnes) ---
        # Colonne 0 : Sidebar (Fixe)
        # Colonne 1 : Workspace (Extensible)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === A. SIDEBAR (Gauche) ===
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Spacer vers le bas

        # Titre
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="VibeSlicer", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Boutons Sidebar
        self.btn_import = ctk.CTkButton(self.sidebar_frame, text="📂 Importer Vidéo", command=self._on_import_click)
        self.btn_import.grid(row=1, column=0, padx=20, pady=10)

        self.btn_export = ctk.CTkButton(self.sidebar_frame, text="💿 Exporter Rendu", fg_color="green", command=self._on_export_click)
        self.btn_export.grid(row=2, column=0, padx=20, pady=10)

        self.label_status = ctk.CTkLabel(self.sidebar_frame, text="Statut: Prêt", text_color="gray")
        self.label_status.grid(row=5, column=0, padx=20, pady=20)


        # === B. WORKSPACE (Droite) ===
        self.workspace_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Le workspace est divisé en 2 : Viewer (Haut) et Timeline/Contrôles (Bas)
        self.workspace_frame.grid_rowconfigure(0, weight=1) # Viewer prend la place
        self.workspace_frame.grid_rowconfigure(1, weight=0) # Timeline fixe
        self.workspace_frame.grid_columnconfigure(0, weight=1)

        # --- 1. Viewer Vidéo (Cadre Noir) ---
        self.video_container = ctk.CTkFrame(self.workspace_frame, fg_color="black")
        self.video_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        # Canvas TKinter pour le lecteur (car CTk n'a pas de surface de rendu vidéo native)
        self.video_canvas = tk.Canvas(self.video_container, bg="black", highlightthickness=0)
        self.video_canvas.pack(fill="both", expand=True)

        # Initialisation Moteur Vidéo
        self.player = None
        if FFPY_AVAILABLE:
            self.player = VideoPlayer(self.video_canvas, on_frame_callback=self._on_player_time_update)
        else:
            self._show_error("ffpyplayer manquant")

        # --- 2. Zone Timeline & Contrôles ---
        self.bottom_panel = ctk.CTkFrame(self.workspace_frame, fg_color="#2b2b2b")
        self.bottom_panel.grid(row=1, column=0, sticky="ew")
        
        # Timeline
        self.timeline = Timeline(self.bottom_panel, state=self.project, height=100)
        self.timeline.pack(fill="x", padx=10, pady=10)
        
        # Barre de Transport (Boutons Play, Timecode)
        self.transport_frame = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        self.transport_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.btn_play = ctk.CTkButton(self.transport_frame, text="▶ Play", width=80, command=self._on_play_click)
        self.btn_play.pack(side="left", padx=10)
        
        self.time_label = ctk.CTkLabel(self.transport_frame, text="00:00.00 / 00:00.00", font=("Consolas", 14))
        self.time_label.pack(side="left", padx=20)

        # --- Abonnements State ---
        self.project.subscribe(EventType.VIDEO_LOADED, self._on_video_loaded_state)
        self.project.subscribe(EventType.PROXY_READY, self._on_proxy_ready)
        self.project.subscribe(EventType.TIME_UPDATED, self._update_time_display)
        self.project.subscribe(EventType.SEEK_REQUESTED, self._on_seek_requested)


    # --- Callbacks UI ---

    def _on_import_click(self):
        path = tk.filedialog.askopenfilename(filetypes=[("Vidéo", "*.mp4 *.mov *.mkv *.avi")])
        if path:
            self.label_status.configure(text="Chargement...")
            self.project.load_video(path)

    def _on_export_click(self):
        if not self.project.source_video: return
        path = tk.filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if path:
            self.project.request_export(path)
            self.label_status.configure(text="Export en cours...")

    def _on_play_click(self):
        if self.player:
            self.player.toggle()
            txt = "⏸ Pause" if self.player.is_playing() else "▶ Play"
            self.btn_play.configure(text=txt)

    def _on_player_time_update(self, t):
        self.project.set_time(t)

    # --- Réactions State ---

    def _on_video_loaded_state(self, path):
        if self.player:
            self.player.load(path)
            # Mise à jour de la durée dans l'interface
            dur = self.player.get_duration()
            self.label_status.configure(text=f"Source chargée : {dur:.1f}s")
            self.btn_play.configure(text="▶ Play")

    def _on_proxy_ready(self, path):
        self.label_status.configure(text="✅ Proxy Optimisé Prêt (60fps)")
        # Recharger le lecteur avec le proxy fluide sans perdre la position
        if self.player:
            pos = self.player.get_time()
            was_playing = self.player.is_playing()
            self.player.load(path)
            self.player.seek(pos)
            if was_playing: self.player.play()

    def _update_time_display(self, t):
        # Affichage propre mm:ss:ms
        dur = self.player.get_duration() if self.player else 0
        def fmt(x):
            m, s = divmod(x, 60)
            return f"{int(m):02}:{int(s):02}.{int((x%1)*100):02}"
        
        self.time_label.configure(text=f"{fmt(t)} / {fmt(dur)}")

    def _on_seek_requested(self, t):
        if self.player: self.player.seek(t)

    def _show_error(self, msg):
        err = ctk.CTkLabel(self.video_container, text=msg, text_color="red")
        err.place(relx=0.5, rely=0.5, anchor="center")
