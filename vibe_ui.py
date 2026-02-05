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
    """Convert #RRGGBB to &HBBGGRR"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return "&HFFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}".upper()

# --- SUBTITLE EDITOR WINDOW ---
class SubtitleEditorWindow(ctk.CTkToplevel):
    def __init__(self, master, srt_path, video_path):
        super().__init__(master)
        self.title("Éditeur de Sous-titres (Vérification)")
        self.geometry("900x600")
        self.srt_path = srt_path
        self.video_path = video_path
        
        self.entries = []
        self.load_srt()
        
        # UI
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(top_frame, text="Modifiez le texte ci-dessous. Cliquez sur 'Sauvegarder & Continuer' pour finir.", text_color="gray").pack()
        
        # Scroll Area
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.populate_ui()
        
        # Bottom
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Sauvegarder & Continuer", fg_color="green", command=self.save_and_close).pack(side="right")

    def load_srt(self):
        """Simple SRT Parser"""
        with open(self.srt_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Regex to split blocks
        # Block format: 1 \n 00:00:00 -> 00:00:00 \n Text
        pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.|[\r\n])*)')
        # This regex is tricky for blocks separated by \n\n. Let's split by double newline.
        blocks = content.strip().split('\n\n')
        
        self.parsed_data = []
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                idx = lines[0]
                times = lines[1]
                text = "\n".join(lines[2:])
                
                # Parse times for preview
                t_match = re.search(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', times)
                start_sec = 0
                if t_match:
                    h, m, s, ms = map(int, t_match.groups()[0:4])
                    start_sec = h*3600 + m*60 + s + ms/1000.0
                    
                    h2, m2, s2, ms2 = map(int, t_match.groups()[4:8])
                    end_sec = h2*3600 + m2*60 + s2 + ms2/1000.0
                    duration = end_sec - start_sec
                else:
                    duration = 2
                
                self.parsed_data.append({
                    "idx": idx,
                    "times": times,
                    "text": text,
                    "start": start_sec,
                    "duration": duration
                })

    def populate_ui(self):
        for data in self.parsed_data:
            row = ctk.CTkFrame(self.scroll)
            row.pack(fill="x", pady=2)
            
            # Times
            ctk.CTkLabel(row, text=data["times"], width=150, font=("Consolas", 12)).pack(side="left", padx=5)
            
            # Text Entry
            txt_var = ctk.StringVar(value=data["text"])
            entry = ctk.CTkEntry(row, textvariable=txt_var)
            entry.pack(side="left", fill="x", expand=True, padx=5)
            
            # Preview Button
            cmd = lambda s=data["start"], d=data["duration"]: self.preview(s, d)
            ctk.CTkButton(row, text="▶", width=30, command=cmd).pack(side="right", padx=5)
            
            self.entries.append((data, txt_var))
            
    def preview(self, start, dur):
        # ffplay
        cmd = [
            "ffplay", 
            "-ss", str(start), 
            "-t", str(dur), 
            "-autoexit", 
            "-window_title", "Preview Sub",
            "-x", "400", "-y", "300",
            self.video_path
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def save_and_close(self):
        with open(self.srt_path, "w", encoding="utf-8") as f:
            for i, (data, var) in enumerate(self.entries):
                f.write(f"{i+1}\n")
                f.write(data["times"] + "\n")
                f.write(var.get().strip() + "\n\n")
        self.destroy()

# --- MAIN APP ---
class VibeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.processor = VibeProcessor()
        self.selected_files = []
        
        # Colors state
        self.title_color_hex = "#8A2BE2" # Violet
        self.sub_color_hex = "#E22B8A"   # Pinkish default outline
        
        self.title("VibeSlicer v3.3 (Pro)")
        self.geometry("1100x850")
        
        # Grid Config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        ctk.CTkLabel(self.sidebar_frame, text="VibeSlicer", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, padx=20, pady=(20, 10))
        ctk.CTkButton(self.sidebar_frame, text="Ajouter Vidéos", command=self.add_videos).grid(row=1, column=0, padx=20, pady=10)
        self.file_listbox = ctk.CTkTextbox(self.sidebar_frame, width=180, height=200)
        self.file_listbox.grid(row=2, column=0, padx=10, pady=10)
        self.run_batch_btn = ctk.CTkButton(self.sidebar_frame, text="TRAITER TOUT", fg_color="green", command=self.start_batch_thread)
        self.run_batch_btn.grid(row=5, column=0, padx=20, pady=20)

        # --- Main Area ---
        self.main_frame = ctk.CTkScrollableFrame(self, label_text="Paramètres & Édition")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # 1. Global Settings
        self.settings_frame = ctk.CTkFrame(self.main_frame)
        self.settings_frame.pack(fill="x", pady=10)
        
        self.settings_inner = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_inner.pack(fill="x", padx=10, pady=10)
        
        # Row 0: Title & Colors
        ctk.CTkLabel(self.settings_inner, text="Titre Intro:").grid(row=0, column=0, padx=5, sticky="w")
        self.entry_title = ctk.CTkEntry(self.settings_inner, placeholder_text="Ex: BEST OF")
        self.entry_title.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Color Pickers
        self.btn_color_title = ctk.CTkButton(self.settings_inner, text="Couleur Titre", width=100, fg_color=self.title_color_hex, command=self.pick_title_color)
        self.btn_color_title.grid(row=0, column=2, padx=5)
        
        self.btn_color_sub = ctk.CTkButton(self.settings_inner, text="Couleur Subs", width=100, fg_color=self.sub_color_hex, command=self.pick_sub_color)
        self.btn_color_sub.grid(row=0, column=3, padx=5)
        
        self.chk_upper = ctk.CTkCheckBox(self.settings_inner, text="MAJUSCULES")
        self.chk_upper.grid(row=0, column=4, padx=5)

        # Row 1: Range Limits
        ctk.CTkLabel(self.settings_inner, text="Forcer Plage (sec):").grid(row=1, column=0, padx=5, pady=10, sticky="w")
        self.frame_range = ctk.CTkFrame(self.settings_inner, fg_color="transparent")
        self.frame_range.grid(row=1, column=1, columnspan=4, sticky="w")
        self.entry_start = ctk.CTkEntry(self.frame_range, width=80, placeholder_text="Début")
        self.entry_start.pack(side="left", padx=5)
        ctk.CTkLabel(self.frame_range, text="à").pack(side="left")
        self.entry_end = ctk.CTkEntry(self.frame_range, width=80, placeholder_text="Fin")
        self.entry_end.pack(side="left", padx=5)
        
        # Row 2: Music & Verify
        ctk.CTkLabel(self.settings_inner, text="Musique de fond:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_music = ctk.CTkEntry(self.settings_inner, placeholder_text="Chemin vers mp3/wav...")
        self.entry_music.grid(row=2, column=1, columnspan=2, padx=5, sticky="ew")
        ctk.CTkButton(self.settings_inner, text="...", width=30, command=self.browse_music).grid(row=2, column=3, padx=5)
        
        self.chk_verify = ctk.CTkCheckBox(self.settings_inner, text="Éditeur de Sous-titres (Avancé)")
        self.chk_verify.grid(row=2, column=4, padx=5, sticky="w")

        # 2. Segment Editor (Preview)
        self.editor_frame = ctk.CTkFrame(self.main_frame)
        self.editor_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(self.editor_frame, text="Aperçu des Séquences", font=("Arial", 16, "bold")).pack(pady=5)
        ctk.CTkButton(self.editor_frame, text="Analyser Vidéo Sélectionnée", command=self.analyze_current).pack(pady=10)
        self.segments_scroll = ctk.CTkScrollableFrame(self.editor_frame, height=250, label_text="Segments détectés")
        self.segments_scroll.pack(fill="x", padx=10, pady=5)
        
        self.log_box = ctk.CTkTextbox(self.main_frame, height=150)
        self.log_box.pack(fill="x", pady=20)
        self.log("VibeSlicer v3.3 (Pro) Ready.")
        
        self.segment_vars = []
        self.preview_file_path = None

    # --- ACTIONS ---
    def pick_title_color(self):
        color = colorchooser.askcolor(initialcolor=self.title_color_hex)[1]
        if color:
            self.title_color_hex = color
            self.btn_color_title.configure(fg_color=color)

    def pick_sub_color(self):
        color = colorchooser.askcolor(initialcolor=self.sub_color_hex)[1]
        if color:
            self.sub_color_hex = color
            self.btn_color_sub.configure(fg_color=color)

    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def add_videos(self):
        files = filedialog.askopenfilenames(filetypes=[("Video files", "*.mp4 *.mov *.mkv")])
        for f in files:
            if f not in self.selected_files:
                self.selected_files.append(f)
                self.file_listbox.insert("end", os.path.basename(f) + "\n")
        self.log(f"Ajouté {len(files)} fichiers.")
        
    def browse_music(self):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav")])
        if f:
            self.entry_music.delete(0, "end")
            self.entry_music.insert(0, f)

    def get_range_values(self):
        s = self.entry_start.get().strip()
        e = self.entry_end.get().strip()
        start_val = float(s) if s else None
        end_val = float(e) if e else None
        return start_val, end_val

    def analyze_current(self):
        if not self.selected_files: return
        target = self.selected_files[0] 
        self.log(f"Analyse de {os.path.basename(target)}...")
        self.preview_file_path = target
        threading.Thread(target=self._run_analysis, args=(target,)).start()

    def _run_analysis(self, video_path):
        try:
            s_val, e_val = self.get_range_values()
            audio_path = self.processor.extract_audio(video_path)
            segments = self.processor.analyze_segments(audio_path, start_range=s_val, end_range=e_val)
            self.after(0, lambda: self._display_segments(segments, video_path))
            self.log(f"Trouvé {len(segments)} segments.")
        except Exception as e:
            self.log(f"Erreur Analyse: {e}")

    def preview_segment(self, video_path, start, end):
        dur = end - start
        cmd = ["ffplay", "-ss", str(start), "-t", str(dur), "-autoexit", "-window_title", 
               f"Preview {start:.1f}s", "-x", "400", "-y", "300", video_path]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _display_segments(self, segments, video_path):
        for widget in self.segments_scroll.winfo_children(): widget.destroy()
        
        self.segment_vars = [] # Reset
        
        for i, (start, end) in enumerate(segments):
            row = ctk.CTkFrame(self.segments_scroll)
            row.pack(fill="x", pady=2)
            
            # Checkbox Keep
            var = ctk.IntVar(value=1)
            self.segment_vars.append((var, start, end)) # Store var to check later if needed
            
            dur = end - start
            seq_text = f"Sq {i+1} ({dur:.1f}s)"
            
            # Checkbox with text
            chk = ctk.CTkCheckBox(row, text=seq_text, variable=var, width=80)
            chk.pack(side="left", padx=5)
            
            # Time Label
            ctk.CTkLabel(row, text=f"{start:.1f}s->{end:.1f}s").pack(side="left", padx=5)
            
            # Preview
            ctk.CTkButton(row, text="▶", width=30, fg_color="gray", 
                          command=lambda s=start, e=end: self.preview_segment(video_path, s, e)).pack(side="right", padx=10)

    def start_batch_thread(self):
        if not self.selected_files: return
        threading.Thread(target=self._run_batch).start()

    def _run_batch(self):
        self.log("=== DÉBUT BATCH ===")
        
        title = self.entry_title.get()
        upper = self.chk_upper.get() == 1
        s_val, e_val = self.get_range_values()
        music_file = self.entry_music.get()
        do_verify = self.chk_verify.get() == 1
        
        # Colors
        title_col = self.title_color_hex
        # Convert outline color to ASS format for backend
        ass_outline = hex_to_ass(self.sub_color_hex)
        
        for idx, video_path in enumerate(self.selected_files):
            try:
                fname = os.path.basename(video_path)
                self.log(f"> Processing {fname}...")
                
                # Check if this is the manually edited file
                use_manual = False
                manual_segments = []
                
                # We need to access self.segment_vars which is a GUI element, but we are in a thread.
                # However, IntVar.get() usually works from threads in simple cases, or we can assume user didn't change it *during* batch.
                if video_path == self.preview_file_path and self.segment_vars:
                    self.log("Utilisation des segments modifiés manuellement...")
                    for var, s, e in self.segment_vars:
                        if var.get() == 1:
                            manual_segments.append((s,e))
                    segments = manual_segments
                    use_manual = True
                else:
                    audio_path = self.processor.extract_audio(video_path)
                    segments = self.processor.analyze_segments(audio_path, start_range=s_val, end_range=e_val)
                
                if not segments:
                    self.log("Skipping (No segments)")
                    continue

                # Cut
                concat_path = os.path.join(self.processor.cfg.temp_dir, f"cut_{idx}.ffconcat")
                cut_video_path = os.path.join(self.processor.cfg.temp_dir, f"cut_{idx}.mp4")
                self.processor.create_cut_file(video_path, segments, concat_path)
                self.processor.render_cut(concat_path, cut_video_path)
                
                # Transcribe
                self.log("Transcription...")
                whisper_segs = self.processor.transcribe(cut_video_path)
                srt_path = os.path.join(self.processor.cfg.temp_dir, f"temp_{idx}.srt")
                self.processor.generate_srt(whisper_segs, srt_path, uppercase=upper)
                
                # VERIFY (Advanced Editor)
                if do_verify:
                    self.log("Vérification requise (GUI)...")
                    # We must run UI code in main thread, but block this batch thread until done.
                    # Use a Event or simple wait loop.
                    
                    editor_closed = threading.Event()
                    
                    def open_editor():
                        top = SubtitleEditorWindow(self, srt_path, cut_video_path)
                        # When top is destroyed, set event
                        top.protocol("WM_DELETE_WINDOW", lambda: (top.destroy(), editor_closed.set()))
                        # Also hook the save button logic to destroy (already does)
                        # We need to wait for 'top' to close.
                        # Actually top.wait_window() blocks the main thread, which is bad if called from main thread?
                        # No, we are calling from _run_batch thread. We cannot call new Toplevel directly from thread easily in tkinter safety.
                        # We must schedule it in mainloop.
                        
                        # Fix: use wait_visibility etc?
                        # Better: self.after/thread sync.
                        
                    # Standard Tkinter thread safety pattern:
                    self.after(0, lambda: SubtitleEditorWindow(self, srt_path, cut_video_path).wait_window() or editor_closed.set())
                    
                    # BLOCK batch thread until editor signals done
                    editor_closed.wait()
                    self.log("Vérification terminée.")
                
                # Render
                self.log("Rendu Final...")
                final_out = os.path.join(self.processor.cfg.output_dir, f"Reel_{fname}")
                
                self.processor.render_final_video(
                    cut_video_path, srt_path, final_out, 
                    title_text=title, 
                    title_color=title_col,
                    music_path=music_file if music_file else None,
                    style_cfg={"outline_color": ass_outline}
                )
                
                self.log(f"SUCCESS: {final_out}")
                
            except Exception as e:
                self.log(f"ERREUR: {str(e)}")
        
        self.log("=== BATCH TERMINÉ ===")

if __name__ == "__main__":
    app = VibeApp()
    app.mainloop()
