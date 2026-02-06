import customtkinter as ctk
from tkinter import filedialog, messagebox, colorchooser
import threading
import os
import time
import subprocess
import re
from PIL import Image
from vibe_core import VibeProcessor

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- UTILS ---
def hex_to_ass(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return "&HFFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}".upper()

def ms_to_timestamp(ms):
    s = ms / 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")

def get_frame_at_time(video_path, time_sec):
    """Extract a frame object using FFmpeg"""
    try:
        cmd = [
            "ffmpeg", "-ss", str(time_sec), "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-f", "image2pipe", "-"
        ]
        # Hide console
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=creationflags)
        out, _ = pipe.communicate()
        if not out: return None
        
        # Load into PIL
        import io
        return Image.open(io.BytesIO(out))
    except:
        return None

# --- WIDGETS ---

class VideoPreview(ctk.CTkFrame):
    def __init__(self, master, video_path, **kwargs):
        super().__init__(master, **kwargs)
        self.video_path = video_path
        self.image_label = ctk.CTkLabel(self, text="Chargement...", corner_radius=10)
        self.image_label.pack(fill="both", expand=True)
        self.last_img = None
        
    def show_time(self, time_sec):
        # Run in thread to avoid UI freeze? 
        threading.Thread(target=self._update_img, args=(time_sec,)).start()
        
    def _update_img(self, time_sec):
        pil_img = get_frame_at_time(self.video_path, time_sec)
        if pil_img:
            # Resize
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 100: w=300; h=200
            
            # Maintain aspect ratio
            ratio = pil_img.width / pil_img.height
            new_h = h
            new_w = int(h * ratio)
            if new_w > w:
                new_w = w
                new_h = int(w / ratio)
                
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
            
            self.after(0, lambda: self.image_label.configure(text="", image=ctk_img))

class TimelineWidget(ctk.CTkFrame):
    def __init__(self, master, duration, segments, on_seek_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.duration = duration
        self.segments = [{"start": s, "end": e, "active": True} for s,e in segments]
        self.on_seek_callback = on_seek_callback
        
        self.canvas = ctk.CTkCanvas(self, height=60, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="x", expand=True, padx=5, pady=5)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.cursor_pos = 0 # seconds
        self.draw()
        
    def draw(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10: w = 600
        
        scale = w / self.duration if self.duration > 0 else 1
        
        # Base (Silence)
        self.canvas.create_rectangle(0, 0, w, h, fill="#4a0000", outline="")
        
        # Segments
        for seg in self.segments:
            x1 = seg["start"] * scale
            x2 = seg["end"] * scale
            col = "#00cc44" if seg["active"] else "#555555"
            self.canvas.create_rectangle(x1, 2, x2, h-2, fill=col, outline="white" if seg["active"] else "", tags="seg")
            
        # Cursor
        cx = self.cursor_pos * scale
        self.canvas.create_line(cx, 0, cx, h, fill="white", width=2)
        
    def on_click(self, event):
        self._input(event)
        w = self.canvas.winfo_width()
        scale = self.duration / w if w > 0 else 0
        t = event.x * scale
        
        # Toggle segment if clicked
        for seg in self.segments:
            if seg["start"] <= t <= seg["end"]:
                seg["active"] = not seg["active"]
                break
        self.draw()

    def on_drag(self, event):
        self._input(event)
        
    def _input(self, event):
        w = self.canvas.winfo_width()
        if w == 0: return
        t = (event.x / w) * self.duration
        t = max(0, min(t, self.duration))
        self.cursor_pos = t
        if self.on_seek_callback: self.on_seek_callback(t)
        self.draw()
        
    def get_active_segments(self):
        return [(s["start"], s["end"]) for s in self.segments if s["active"]]


# --- APP WIZARD PAGES ---

class VibeWizardApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VibeSlicer v4.1 (Studio Mode)")
        self.geometry("1200x800")
        
        self.processor = VibeProcessor()
        self.files_to_process = [] # list of paths
        self.projects_data = [] # list of dicts with all info for render
        
        # Container
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        
        self.show_file_selection()

    # STEP 1: SELECT FILES
    def show_file_selection(self):
        self.clear_container()
        
        lbl = ctk.CTkLabel(self.container, text="1. Sélectionnez vos Rushs", font=("Arial", 25, "bold"))
        lbl.pack(pady=30)
        
        btn_add = ctk.CTkButton(self.container, text="+ Ajouter Vidéos", command=self.add_files, width=200, height=50, font=("Arial", 16))
        btn_add.pack(pady=10)
        
        self.list_frame = ctk.CTkScrollableFrame(self.container, width=600, height=350)
        self.list_frame.pack(pady=10)
        
        self.btn_next = ctk.CTkButton(self.container, text="Commencer l'Édition ->", fg_color="green", height=50, width=200,
                                      state="disabled", command=self.start_editing_flow, font=("Arial", 16, "bold"))
        self.btn_next.pack(pady=30)
        
    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.mov *.mkv")])
        for p in paths:
            if p not in self.files_to_process:
                self.files_to_process.append(p)
                lbl = ctk.CTkLabel(self.list_frame, text=os.path.basename(p), font=("Arial", 14))
                lbl.pack(pady=2)
        
        if self.files_to_process:
            self.btn_next.configure(state="normal")

    def start_editing_flow(self):
        self.current_idx = 0
        self.projects_data = [] # Reset
        self.edit_next_video()

    # STEP 2: LOOP PER VIDEO
    def edit_next_video(self):
        if self.current_idx >= len(self.files_to_process):
            # All done
            self.show_final_batch_render()
            return
            
        path = self.files_to_process[self.current_idx]
        self.show_cut_editor(path)

    # 2A: CUT EDITOR
    def show_cut_editor(self, video_path):
        self.clear_container()
        fname = os.path.basename(video_path)
        
        # Header
        top = ctk.CTkFrame(self.container, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(top, text=f"Édition: {fname}", font=("Arial", 20, "bold")).pack(side="left")
        step_lbl = f"Vidéo {self.current_idx + 1} sur {len(self.files_to_process)}"
        ctk.CTkLabel(top, text=step_lbl, text_color="gray", font=("Arial", 14)).pack(side="right")
        
        # Content
        ctk.CTkLabel(self.container, text="Ajustez les coupes (Vert = Gardé, Rouge = Coupé)", font=("Arial", 14)).pack(pady=(10,5))
        
        # Preview Area
        preview_frame = VideoPreview(self.container, video_path, width=600, height=350)
        preview_frame.pack(pady=10)
        
        # Info
        lbl_info = ctk.CTkLabel(self.container, text="Analyse audio en cours...", text_color="orange")
        lbl_info.pack()
        self.update() # Force paint
        
        # Run Analyze
        threading.Thread(target=self._async_analyze, args=(video_path, lbl_info, preview_frame)).start()

    def _async_analyze(self, video_path, lbl_info, preview_frame):
        try:
            # Extract Audio duration
            from pydub import AudioSegment
            audio_path = self.processor.extract_audio(video_path)
            audio = AudioSegment.from_wav(audio_path)
            dur = len(audio) / 1000.0
            
            # Auto Segments
            segs = self.processor.analyze_segments(audio_path)
            
            # UI Update needs to be on main thread
            self.after(0, lambda: self._setup_timeline(video_path, dur, segs, lbl_info, preview_frame))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Erreur Analyse", str(e)))

    def _setup_timeline(self, video_path, dur, segs, lbl_info, preview_frame):
        lbl_info.configure(text="Cliquez sur la timeline pour couper/garder. Glissez pour prévisualiser.", text_color="silver")
        
        timeline = TimelineWidget(self.container, dur, segs, 
                                  on_seek_callback=lambda t: preview_frame.show_time(t),
                                  height=80)
        timeline.pack(fill="x", padx=40, pady=20)
        
        # Params (Start/End trim optional) could be here but timeline handles it visually better.
        
        def confirm_cuts():
            kept = timeline.get_active_segments()
            if not kept:
                messagebox.showerror("Erreur", "Aucun segment sélectionné (tout est rouge) !")
                return
            
            project = {
                "raw_path": video_path,
                "segments": kept,
                "duration": dur
            }
            self.process_cuts_and_transcribe(project)
            
        ctk.CTkButton(self.container, text="Valider & Transcrire ->", command=confirm_cuts, 
                      fg_color="green", width=200, height=40).pack(pady=20)


    # 2B: PROCESSING (Hidden)
    def process_cuts_and_transcribe(self, project):
        self.clear_container()
        ctk.CTkLabel(self.container, text="Création de la séquence...", font=("Arial", 25)).pack(pady=50)
        
        log = ctk.CTkLabel(self.container, text="Patientez...", text_color="gray")
        log.pack()
        
        bar = ctk.CTkProgressBar(self.container, width=400)
        bar.pack(pady=20)
        bar.configure(mode="indeterminate")
        bar.start()
        
        def _work():
            try:
                # 1. Cut Video
                idx = self.current_idx
                concat_path = os.path.join(self.processor.cfg.temp_dir, f"wiz_{idx}.ffconcat")
                cut_path = os.path.join(self.processor.cfg.temp_dir, f"wiz_{idx}.mp4")
                
                self.after(0, lambda: log.configure(text="Découpage & Assemblage..."))
                self.processor.create_cut_file(project["raw_path"], project["segments"], concat_path)
                self.processor.render_cut(concat_path, cut_path)
                project["cut_path"] = cut_path
                
                # 2. Transcribe
                self.after(0, lambda: log.configure(text="Transcription IA..."))
                wsegs = self.processor.transcribe(cut_path)
                
                srt_path = os.path.join(self.processor.cfg.temp_dir, f"wiz_{idx}.srt")
                self.processor.generate_srt(wsegs, srt_path, uppercase=True) # Default
                project["srt_path"] = srt_path
                
                self.after(0, lambda: self.show_subtitle_editor(project))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur Process", str(e)))
            
        threading.Thread(target=_work).start()

    # 2C: SUBTITLE EDITOR
    def show_subtitle_editor(self, project):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text=f"Sous-titres: {os.path.basename(project['raw_path'])}", font=("Arial", 20, "bold")).pack(pady=10)
        ctk.CTkLabel(self.container, text="Corrigez le texte ci-dessous.", text_color="gray").pack()

        # Load SRT
        with open(project["srt_path"], "r", encoding="utf-8") as f:
            raw_srt = f.read()
            
        scroll = ctk.CTkScrollableFrame(self.container, height=400, width=800)
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        
        blocks = raw_srt.strip().split('\n\n')
        entries = []
        
        for b in blocks:
            lines = b.split('\n')
            if len(lines) >= 3:
                times = lines[1]
                txt = "\n".join(lines[2:])
                
                row = ctk.CTkFrame(scroll)
                row.pack(fill="x", pady=2)
                
                # Play button logic? A bit complex without reloading cut video in preview.
                # Just Text entry for now.
                
                ctk.CTkLabel(row, text=times, font=("Consolas", 11), width=150).pack(side="left", padx=5)
                v = ctk.StringVar(value=txt)
                ctk.CTkEntry(row, textvariable=v).pack(side="left", fill="x", expand=True, padx=5)
                entries.append(v)
        
        def confirm_subs():
            # Save SRT back
            with open(project["srt_path"], "w", encoding="utf-8") as f:
                new_blocks = raw_srt.strip().split('\n\n')
                for i, b in enumerate(new_blocks):
                    lines = b.split('\n')
                    if len(lines) >= 3 and i < len(entries):
                        f.write(f"{lines[0]}\n{lines[1]}\n{entries[i].get()}\n\n")
            
            self.show_final_settings(project)

        ctk.CTkButton(self.container, text="Valider Sous-titres ->", command=confirm_subs, fg_color="green").pack(pady=10)
    
    # 2D: FINAL SETTINGS for this file
    def show_final_settings(self, project):
        self.clear_container()
        ctk.CTkLabel(self.container, text=f"Finitions: {os.path.basename(project['raw_path'])}", font=("Arial", 20, "bold")).pack(pady=20)
        
        f = ctk.CTkFrame(self.container)
        f.pack(pady=10, padx=50)
        
        # Title
        ctk.CTkLabel(f, text="Titre Intro:").grid(row=0, column=0, pady=10, padx=10, sticky="e")
        e_title = ctk.CTkEntry(f, width=250, placeholder_text="Ex: MEP CLIPS #1")
        e_title.grid(row=0, column=1, pady=10, padx=10)
        
        ctk.CTkLabel(f, text="Couleur Titre:").grid(row=1, column=0, pady=10, padx=10, sticky="e")
        e_col_t = ctk.CTkButton(f, text="     ", fg_color="#8A2BE2", width=50, command=lambda: self._pick_col(e_col_t))
        e_col_t.grid(row=1, column=1, sticky="w", padx=10)
        
        # Music
        ctk.CTkLabel(f, text="Musique:").grid(row=2, column=0, pady=10, padx=10, sticky="e")
        e_music = ctk.CTkEntry(f, width=250)
        e_music.grid(row=2, column=1, pady=10, padx=10)
        ctk.CTkButton(f, text="Browse", width=60, command=lambda: self._browse_music(e_music)).grid(row=2, column=2, padx=5)
        
        # Subs style
        ctk.CTkLabel(f, text="Couleur Subs:").grid(row=3, column=0, pady=10, padx=10, sticky="e")
        e_col_s = ctk.CTkButton(f, text="     ", fg_color="#E22B8A", width=50, command=lambda: self._pick_col(e_col_s))
        e_col_s.grid(row=3, column=1, sticky="w", padx=10)

        def finish_video():
            project["title"] = e_title.get()
            project["title_color"] = e_col_t.cget("fg_color")
            project["music"] = e_music.get()
            project["sub_color"] = e_col_s.cget("fg_color")
            
            self.projects_data.append(project)
            self.current_idx += 1
            self.edit_next_video()
            
        ctk.CTkButton(self.container, text="Terminer ce fichier ->", fg_color="green", height=50, width=200, command=finish_video).pack(pady=30)
        
    def _pick_col(self, btn):
        c = colorchooser.askcolor(initialcolor=btn.cget("fg_color"))[1]
        if c: btn.configure(fg_color=c)

    def _browse_music(self, entry):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav")])
        if f: 
            entry.delete(0, "end")
            entry.insert(0, f)

    # STEP 3: BATCH RENDER
    def show_final_batch_render(self):
        self.clear_container()
        ctk.CTkLabel(self.container, text="Tout est prêt ! 🎬", font=("Arial", 30, "bold")).pack(pady=30)
        ctk.CTkLabel(self.container, text=f"{len(self.projects_data)} vidéos prêtes à être exportées.", font=("Arial", 16)).pack()
        
        btn = ctk.CTkButton(self.container, text="LANCER LE RENDU FINAL", height=60, width=300, fg_color="red", font=("Arial", 18, "bold"), command=self.run_final_render)
        btn.pack(pady=40)
        
        self.console = ctk.CTkTextbox(self.container, height=300, width=800)
        self.console.pack(fill="x", padx=40)

    def run_final_render(self):
        threading.Thread(target=self._render_job).start()
        
    def _render_job(self):
        for i, proj in enumerate(self.projects_data):
            self.log(f"Rendu {i+1}/{len(self.projects_data)}: {os.path.basename(proj['raw_path'])}...")
            try:
                out = os.path.join(self.processor.cfg.output_dir, f"Final_V4_{i}.mp4")
                
                ass_outline = hex_to_ass(proj["sub_color"])
                
                self.processor.render_final_video(
                    proj["cut_path"],
                    proj["srt_path"],
                    out,
                    title_text=proj["title"],
                    title_color=proj["title_color"],
                    music_path=proj["music"] if proj["music"] else None,
                    style_cfg={"outline_color": ass_outline} 
                )
                self.log(f"✅ Terminé: {out}")
            except Exception as e:
                self.log(f"❌ Erreur: {e}")
        self.log("\n✨ TOUS LES RENDUS SONT TERMINÉS !")
        self.log("Vous pouvez fermer l'application.")

    def log(self, t):
        self.console.insert("end", t + "\n")
        self.console.see("end")

    def clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()

if __name__ == "__main__":
    app = VibeWizardApp()
    app.mainloop()
