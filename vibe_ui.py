import customtkinter as ctk
from tkinter import filedialog, messagebox, colorchooser
import threading
import os
import time
import subprocess
import re
from vibe_core import VibeProcessor, TrimConfig

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- UTILS ---
def hex_to_ass(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return "&HFFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}".upper()

# --- TIMELINE WIDGET ---
class InteractiveTimeline(ctk.CTkFrame):
    def __init__(self, master, height=60, workflow_callback=None, **kwargs):
        super().__init__(master, height=height, **kwargs)
        self.workflow_callback = workflow_callback # func(segments)
        self.canvas = ctk.CTkCanvas(self, height=height, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)
        self.canvas.bind("<Button-1>", self.on_click)
        
        self.duration = 100
        # format: list of {"start": s, "end": e, "active": bool}
        self.blocks = [] 
        
    def load_data(self, duration, segments):
        self.duration = duration
        self.blocks = []
        
        # Convert raw segments [(s,e), (s,e)] to blocks covering the whole timeline?
        # No, just represent the speech segments as blocks.
        # But user might want to restore silence?
        # For simplicity V1: Only show detected speech blocks.
        # Detecting silence user wants to restore is harder without re-running VAD.
        # Let's visualize the "Kept" segments.
        
        for s, e in segments:
            self.blocks.append({"start": s, "end": e, "active": True})
            
        self.redraw()
        
    def redraw(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10: w = 800 # fallback
        
        # Draw background (Red/Silence)
        self.canvas.create_rectangle(0, 0, w, h, fill="#3a1b1b", outline="")
        
        # Draw segments (Green/Speech)
        scale = w / self.duration if self.duration > 0 else 1
        
        for i, b in enumerate(self.blocks):
            x1 = b["start"] * scale
            x2 = b["end"] * scale
            color = "#2b8a3e" if b["active"] else "#5c5c5c" # Green if kept, Gray if discarded
            
            # Tags to identify block
            tag = f"block_{i}"
            self.canvas.create_rectangle(x1, 2, x2, h-2, fill=color, outline="white" if b["active"] else "", tags=tag)
            
    def on_click(self, event):
        w = self.canvas.winfo_width()
        scale = self.duration / w if w > 0 else 0
        click_time = event.x * scale
        
        # Find which block was clicked
        toggled = False
        for i, b in enumerate(self.blocks):
            if b["start"] <= click_time <= b["end"]:
                b["active"] = not b["active"]
                toggled = True
                # Preview toggle?
                break
        
        if toggled:
            self.redraw()
            # Notify parent to update segments
            valid_segs = [(b["start"], b["end"]) for b in self.blocks if b["active"]]
            if self.workflow_callback: self.workflow_callback(valid_segs)

# --- SUBTITLE EDITOR WINDOW (Keep previous logic) ---
class SubtitleEditorWindow(ctk.CTkToplevel):
    def __init__(self, master, srt_path, video_path):
        super().__init__(master)
        self.title("Éditeur de Sous-titres (Vérification)")
        self.geometry("900x600")
        self.srt_path = srt_path
        self.video_path = video_path
        self.entries = []
        self.load_srt()
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(top_frame, text="Modifiez le texte. [▶] pour prévisualiser.", text_color="gray").pack()
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=5)
        self.populate_ui()
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Sauvegarder & Fermer", fg_color="green", command=self.save_and_close).pack(side="right")
    def load_srt(self):
        with open(self.srt_path, "r", encoding="utf-8") as f: content = f.read()
        blocks = content.strip().split('\n\n')
        self.parsed_data = []
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                times = lines[1]
                text = "\n".join(lines[2:])
                t_match = re.search(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', times)
                start, dur = 0, 2
                if t_match:
                    h, m, s, ms = map(int, t_match.groups()[0:4])
                    start = h*3600 + m*60 + s + ms/1000.0
                    h2, m2, s2, ms2 = map(int, t_match.groups()[4:8])
                    end = h2*3600 + m2*60 + s2 + ms2/1000.0
                    dur = end - start
                self.parsed_data.append({"idx": lines[0], "times": times, "text": text, "start": start, "duration": dur})
    def populate_ui(self):
        for data in self.parsed_data:
            row = ctk.CTkFrame(self.scroll)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=data["times"], width=130, font=("Consolas", 11)).pack(side="left", padx=2)
            txt_var = ctk.StringVar(value=data["text"])
            ctk.CTkEntry(row, textvariable=txt_var).pack(side="left", fill="x", expand=True, padx=5)
            cmd = lambda s=data["start"], d=data["duration"]: self.preview(s, d)
            ctk.CTkButton(row, text="▶", width=30, command=cmd).pack(side="right", padx=5)
            self.entries.append((data, txt_var))
    def preview(self, start, dur):
        cmd = ["ffplay", "-ss", str(start), "-t", str(dur), "-autoexit", "-window_title", "Preview", "-x", "400", "-y", "300", self.video_path]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def save_and_close(self):
        with open(self.srt_path, "w", encoding="utf-8") as f:
            for i, (data, var) in enumerate(self.entries):
                f.write(f"{i+1}\n{data['times']}\n{var.get().strip()}\n\n")
        self.destroy()

# --- MAIN APP ---
class VibeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.processor = VibeProcessor()
        self.file_data = {} # { "abs_path": { "segments": [], "duration": 0, "status": "analyzed" } }
        self.current_edit_file = None
        
        self.title("VibeSlicer v4.0 (Timeline Edition)")
        self.geometry("1100x850")
        
        # Colors
        self.title_color_hex = "#8A2BE2" 
        self.sub_color_hex = "#E22B8A"   
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="VibeSlicer", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)
        
        ctk.CTkButton(self.sidebar, text="Ajouter Vidéos", command=self.add_videos).pack(pady=10)
        
        # Listbox (using simplified Text widget, but ideally CTkListbox)
        # We will use a clickable frame list for better UX
        self.files_scroll = ctk.CTkScrollableFrame(self.sidebar, label_text="Fichiers (Cliquer pour éditer)")
        self.files_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkButton(self.sidebar, text="TRAITER TOUT 🚀", fg_color="green", height=40, command=self.start_batch_thread).pack(pady=20, padx=20)

        # Main Area
        self.main_frame = ctk.CTkScrollableFrame(self, label_text="Espace de Travail")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # 1. Timeline
        self.timeline_frame = ctk.CTkFrame(self.main_frame)
        self.timeline_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(self.timeline_frame, text="Timeline Visuelle (Vert = Gardé, Rouge = Coupé)", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        self.timeline = InteractiveTimeline(self.timeline_frame, height=60, workflow_callback=self.on_timeline_edit)
        self.timeline.pack(fill="x", padx=10, pady=10)
        
        self.lbl_current_file = ctk.CTkLabel(self.timeline_frame, text="Aucun fichier sélectionné", text_color="gray")
        self.lbl_current_file.pack(pady=5)
        
        self.btn_analyze = ctk.CTkButton(self.timeline_frame, text="Analyser ce fichier", command=self.analyze_current_ui)
        self.btn_analyze.pack(pady=5)

        # 2. Settings
        self.setup_settings_ui()
        
        # 3. Log
        self.log_box = ctk.CTkTextbox(self.main_frame, height=150)
        self.log_box.pack(fill="x", pady=20)
        self.log("Bienvenue! Ajoutez des vidéos. Cliquez sur une vidéo dans la liste pour voir sa Timeline.")

    def setup_settings_ui(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.pack(fill="x", pady=10)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=10)
        
        # Config Grid
        ctk.CTkLabel(inner, text="Titre:").grid(row=0, column=0, sticky="w")
        self.entry_title = ctk.CTkEntry(inner, placeholder_text="Mon Titre")
        self.entry_title.grid(row=0, column=1, sticky="ew", padx=5)
        
        self.btn_col_t = ctk.CTkButton(inner, text="Couleur Titre", width=80, fg_color=self.title_color_hex, command=self.pick_title_col)
        self.btn_col_t.grid(row=0, column=2, padx=5)
        
        self.chk_upper = ctk.CTkCheckBox(inner, text="MAJ")
        self.chk_upper.grid(row=0, column=3, padx=5)
        
        ctk.CTkLabel(inner, text="Musique:").grid(row=1, column=0, sticky="w", pady=10)
        self.entry_music = ctk.CTkEntry(inner)
        self.entry_music.grid(row=1, column=1, sticky="ew", padx=5)
        ctk.CTkButton(inner, text="...", width=30, command=self.browse_music).grid(row=1, column=2, padx=5)
        
        self.chk_verify = ctk.CTkCheckBox(inner, text="Vérifier SRT")
        self.chk_verify.grid(row=1, column=3, padx=5)
        
        # Colors
        self.btn_col_s = ctk.CTkButton(inner, text="Couleur Subs", width=80, fg_color=self.sub_color_hex, command=self.pick_sub_col)
        self.btn_col_s.grid(row=0, column=4, padx=5)
        
        # Trim params
        bg_trim = ctk.CTkFrame(self.main_frame)
        bg_trim.pack(fill="x", pady=5)
        ctk.CTkLabel(bg_trim, text="Paramètres Analyse Auto:").pack(side="left", padx=10)
        self.entry_start = ctk.CTkEntry(bg_trim, width=60, placeholder_text="Debut")
        self.entry_start.pack(side="left", padx=5)
        self.entry_end = ctk.CTkEntry(bg_trim, width=60, placeholder_text="Fin")
        self.entry_end.pack(side="left", padx=5)

    # --- LOGIC ---
    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def pick_title_col(self):
        c = colorchooser.askcolor(initialcolor=self.title_color_hex)[1]
        if c: 
            self.title_color_hex = c
            self.btn_col_t.configure(fg_color=c)

    def pick_sub_col(self):
        c = colorchooser.askcolor(initialcolor=self.sub_color_hex)[1]
        if c: 
            self.sub_color_hex = c
            self.btn_col_s.configure(fg_color=c)
            
    def browse_music(self):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav")])
        if f: 
            self.entry_music.delete(0, "end")
            self.entry_music.insert(0, f)

    def add_videos(self):
        files = filedialog.askopenfilenames(filetypes=[("Video files", "*.mp4 *.mov *.mkv")])
        for f in files:
            norm_f = os.path.normpath(f)
            if norm_f not in self.file_data:
                self.file_data[norm_f] = {"segments": [], "duration": 0, "analyzed": False}
                self.add_file_btn(norm_f)
        self.log(f"Ajouté {len(files)} fichiers.")
        
    def add_file_btn(self, path):
        name = os.path.basename(path)
        btn = ctk.CTkButton(self.files_scroll, text=name, fg_color="transparent", border_width=1, 
                            text_color=("gray10", "gray90"), anchor="w",
                            command=lambda p=path: self.load_video_editor(p))
        btn.pack(fill="x", pady=2)

    def load_video_editor(self, path):
        self.current_edit_file = path
        self.lbl_current_file.configure(text=f"Fichier: {os.path.basename(path)}")
        data = self.file_data[path]
        
        # If analyzed, show timeline
        if data["analyzed"]:
            self.timeline.load_data(data["duration"], data["segments"])
        else:
            # Clear timeline or show empty
            self.timeline.load_data(100, [])
            self.log("Ce fichier n'est pas encore analysé. Cliquez sur 'Analyser ce fichier'.")

    def on_timeline_edit(self, new_segments):
        if self.current_edit_file:
            self.file_data[self.current_edit_file]["segments"] = new_segments
            # self.log(f"Mise à jour segments pour {os.path.basename(self.current_edit_file)}")

    def analyze_current_ui(self):
        if not self.current_edit_file: return
        threading.Thread(target=self._run_single_analysis, args=(self.current_edit_file,)).start()

    def _run_single_analysis(self, path):
        self.log(f"Analyse de {os.path.basename(path)}...")
        try:
            # use global trim settings for this initial analysis
            s = self.entry_start.get(); e = self.entry_end.get()
            s_val = float(s) if s else None
            e_val = float(e) if e else None
            
            # Extract duration (hacky: use pydub)
            audio_path = self.processor.extract_audio(path)
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(audio_path)
            dur_sec = len(audio) / 1000.0
            
            segments = self.processor.analyze_segments(audio_path, start_range=s_val, end_range=e_val)
            
            # Store
            self.file_data[path]["duration"] = dur_sec
            self.file_data[path]["segments"] = segments
            self.file_data[path]["analyzed"] = True
            
            # Update UI
            if self.current_edit_file == path:
                 self.after(0, lambda: self.timeline.load_data(dur_sec, segments))
            self.log(f"Terminé: {len(segments)} segments.")
            
        except Exception as e:
            self.log(f"Erreur: {e}")

    def start_batch_thread(self):
        if not self.file_data: return
        threading.Thread(target=self._run_batch).start()

    def _run_batch(self):
        self.log("=== DÉBUT BATCH ===")
        
        # Globals
        title = self.entry_title.get()
        upper = self.chk_upper.get() == 1
        s_val_g = float(self.entry_start.get()) if self.entry_start.get() else None
        e_val_g = float(self.entry_end.get()) if self.entry_end.get() else None
        music = self.entry_music.get()
        verify = self.chk_verify.get() == 1
        title_col = self.title_color_hex
        outline_ass = hex_to_ass(self.sub_color_hex)
        
        idx = 0
        for fpath, data in self.file_data.items():
            idx += 1
            fname = os.path.basename(fpath)
            self.log(f"> Processing {fname}...")
            
            try:
                # 1. Get Segments (Manual or Auto)
                if data["analyzed"] and data["segments"]:
                    segments = data["segments"] # User approved/edited
                else:
                    self.log(f"  (Analyse auto...)")
                    audio_path = self.processor.extract_audio(fpath)
                    segments = self.processor.analyze_segments(audio_path, start_range=s_val_g, end_range=e_val_g)
                
                if not segments:
                    self.log("  ⚠️ Aucun segment. Skip.")
                    continue

                # 2. Cut
                concat = os.path.join(self.processor.cfg.temp_dir, f"batch_{idx}.ffconcat")
                cut_vid = os.path.join(self.processor.cfg.temp_dir, f"batch_{idx}.mp4")
                self.processor.create_cut_file(fpath, segments, concat)
                self.processor.render_cut(concat, cut_vid)
                
                # 3. Transcribe
                self.log("  Transcription...")
                wsegs = self.processor.transcribe(cut_vid)
                srt = os.path.join(self.processor.cfg.temp_dir, f"batch_{idx}.srt")
                self.processor.generate_srt(wsegs, srt, uppercase=upper)
                
                # 4. Verify
                if verify:
                    self.log("  🛑 Vérification requise...")
                    editor_closed = threading.Event()
                    self.after(0, lambda: SubtitleEditorWindow(self, srt, cut_vid).wait_window() or editor_closed.set())
                    editor_closed.wait()
                    
                # 5. Render
                self.log("  Rendu final...")
                out = os.path.join(self.processor.cfg.output_dir, f"Reel_{fname}")
                self.processor.render_final_video(
                    cut_vid, srt, out,
                    title_text=title,
                    title_color=title_col,
                    music_path=music,
                    style_cfg={"outline_color": outline_ass}
                )
                self.log(f"  ✅ Succès: {out}")
                
            except Exception as e:
                self.log(f"  ❌ Erreur: {e}")
                
        self.log("=== BATCH TERMINÉ ===")

if __name__ == "__main__":
    app = VibeApp()
    app.mainloop()
