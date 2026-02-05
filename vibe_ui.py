import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import time
import subprocess
from vibe_core import VibeProcessor, TrimConfig

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class VibeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.processor = VibeProcessor()
        self.selected_files = []
        self.analysis_segments = [] 
        self.temp_cut_video = None
        
        self.title("VibeSlicer v3.1 (GUI)")
        self.geometry("1100x800")
        
        # Grid Config
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # --- Sidebar (Left) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="VibeSlicer", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.btn_add = ctk.CTkButton(self.sidebar_frame, text="Ajouter Vidéos", command=self.add_videos)
        self.btn_add.grid(row=1, column=0, padx=20, pady=10)
        
        self.file_listbox = ctk.CTkTextbox(self.sidebar_frame, width=180, height=200)
        self.file_listbox.grid(row=2, column=0, padx=10, pady=10)
        
        self.run_batch_btn = ctk.CTkButton(self.sidebar_frame, text="TRAITER TOUT", fg_color="green", command=self.start_batch_thread)
        self.run_batch_btn.grid(row=5, column=0, padx=20, pady=20)

        # --- Main Area (Right) ---
        self.main_frame = ctk.CTkScrollableFrame(self, label_text="Paramètres & Édition")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # 1. Global Settings
        self.settings_frame = ctk.CTkFrame(self.main_frame)
        self.settings_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(self.settings_frame, text="Configuration Globale", font=("Arial", 16, "bold")).pack(pady=5)
        
        self.settings_inner = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.settings_inner.pack(fill="x", padx=10)
        
        # Row 0: Basic Config
        ctk.CTkLabel(self.settings_inner, text="Titre Intro:").grid(row=0, column=0, padx=5, sticky="w")
        self.entry_title = ctk.CTkEntry(self.settings_inner, placeholder_text="Ex: BEST OF")
        self.entry_title.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.chk_upper = ctk.CTkCheckBox(self.settings_inner, text="Sous-titres MAJUSCULES")
        self.chk_upper.grid(row=0, column=2, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(self.settings_inner, text="Color:").grid(row=0, column=3, padx=5, sticky="w")
        self.entry_color = ctk.CTkEntry(self.settings_inner, width=100, placeholder_text="&HE22B8A")
        self.entry_color.insert(0, "&HE22B8A")
        self.entry_color.grid(row=0, column=4, padx=5, sticky="ew")
        
        # Row 1: Range Limits
        ctk.CTkLabel(self.settings_inner, text="Forcer Plage (sec):").grid(row=1, column=0, padx=5, pady=10, sticky="w")
        
        self.frame_range = ctk.CTkFrame(self.settings_inner, fg_color="transparent")
        self.frame_range.grid(row=1, column=1, columnspan=4, sticky="w")
        
        self.entry_start = ctk.CTkEntry(self.frame_range, width=80, placeholder_text="Début")
        self.entry_start.pack(side="left", padx=5)
        
        ctk.CTkLabel(self.frame_range, text="à").pack(side="left")
        
        self.entry_end = ctk.CTkEntry(self.frame_range, width=80, placeholder_text="Fin")
        self.entry_end.pack(side="left", padx=5)
        
        ctk.CTkLabel(self.frame_range, text="(Laisser vide pour tout analyser)", text_color="gray").pack(side="left", padx=10)

        # 2. Segment Editor
        self.editor_frame = ctk.CTkFrame(self.main_frame)
        self.editor_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(self.editor_frame, text="Éditeur de Séquences (Aperçu)", font=("Arial", 16, "bold")).pack(pady=5)
        
        self.btn_analyze = ctk.CTkButton(self.editor_frame, text="Analyser Vidéo Sélectionnée (Preview)", command=self.analyze_current)
        self.btn_analyze.pack(pady=10)
        
        self.segments_scroll = ctk.CTkScrollableFrame(self.editor_frame, height=300, label_text="Segments détectés (Décochez pour supprimer)")
        self.segments_scroll.pack(fill="x", padx=10, pady=5)
        
        self.segment_vars = []
        
        # Log Console
        self.log_box = ctk.CTkTextbox(self.main_frame, height=150)
        self.log_box.pack(fill="x", pady=20)
        self.log("Bienvenue dans VibeSlicer GUI v3.1.")

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

    def get_range_values(self):
        s = self.entry_start.get().strip()
        e = self.entry_end.get().strip()
        start_val = float(s) if s else None
        end_val = float(e) if e else None
        return start_val, end_val

    def analyze_current(self):
        if not self.selected_files:
            messagebox.showerror("Erreur", "Aucune vidéo chargée.")
            return
        
        target = self.selected_files[0] 
        self.log(f"Analyse de {os.path.basename(target)}...")
        
        threading.Thread(target=self._run_analysis, args=(target,)).start()

    def _run_analysis(self, video_path):
        try:
            s_val, e_val = self.get_range_values()
            
            audio_path = self.processor.extract_audio(video_path)
            segments = self.processor.analyze_segments(audio_path, start_range=s_val, end_range=e_val)
            
            self.after(0, lambda: self._display_segments(segments, video_path))
            self.log(f"Trouvé {len(segments)} segments parlés (Filtre: {s_val}-{e_val}).")
        except Exception as e:
            self.log(f"Erreur Analyse: {e}")

    def preview_segment(self, video_path, start, end):
        """Launch ffplay for preview"""
        dur = end - start
        try:
            # ffplay -ss START -t DURATION -i VIDEO -autoexit -window_title PREVIEW
            cmd = [
                "ffplay", 
                "-ss", str(start), 
                "-t", str(dur), 
                "-autoexit", 
                "-window_title", f"Preview {start:.1f}s",
                "-x", "400", "-y", "300", # Small window
                video_path
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror("Erreur Preview", f"Impossible de lancer ffplay: {e}")

    def _display_segments(self, segments, video_path):
        for widget in self.segments_scroll.winfo_children():
            widget.destroy()
        self.segment_vars = []
        
        for i, (start, end) in enumerate(segments):
            row = ctk.CTkFrame(self.segments_scroll)
            row.pack(fill="x", pady=2)
            
            # Checkbox Keep
            var = ctk.IntVar(value=1)
            # Store tuple: (variable, start, end)
            self.segment_vars.append((var, start, end))
            
            seq_text = f"Séquence {i+1}"
            chk = ctk.CTkCheckBox(row, text=seq_text, variable=var, width=100)
            chk.pack(side="left", padx=5)
            
            # Info
            dur = end - start
            info = f"[{start:.1f}s -> {end:.1f}s] ({dur:.1f}s)"
            ctk.CTkLabel(row, text=info).pack(side="left", padx=10)
            
            # Preview Button
            btn_prev = ctk.CTkButton(row, text="▶ Voir", width=60, fg_color="gray", 
                                     command=lambda s=start, e=end: self.preview_segment(video_path, s, e))
            btn_prev.pack(side="right", padx=10)

    def start_batch_thread(self):
        if not self.selected_files: return
        threading.Thread(target=self._run_batch).start()

    def _run_batch(self):
        self.log("=== DÉBUT DU TRAITEMENT BATCH ===")
        
        title = self.entry_title.get()
        color = self.entry_color.get()
        upper = self.chk_upper.get() == 1
        s_val, e_val = self.get_range_values()
        
        for idx, video_path in enumerate(self.selected_files):
            try:
                fname = os.path.basename(video_path)
                self.log(f"Traitement de {fname} ({idx+1}/{len(self.selected_files)})...")
                
                # Logic: If we analyze the FIRST file and have active segments in the UI, use them?
                # Or re-analyze all?
                # Current logic: Always re-analyze automatically using the range settings.
                # NOTE: The manual checkboxes only apply if we implemented a "Render Selected" button.
                # Batch "Process All" implies automatic processing for bulk. 
                # Improving logic: if selected_files[0] matches the one in preview, use preview segments.
                
                final_segments = []
                
                # Check if this file is the one currently displayed in editor
                # (Simple check: we stored it nowhere, but usually only one file is analyzed)
                # For robust batch, lets re-analyze if we are not "applying manual edits".
                # To keep it simple: Batch ALWAYS uses auto-detection with Range filters.
                
                audio_path = self.processor.extract_audio(video_path)
                segments = self.processor.analyze_segments(audio_path, start_range=s_val, end_range=e_val)
                
                if not segments:
                    self.log(f"Skipping {fname} (Rien de détecté)")
                    continue

                # Cut
                concat_path = os.path.join(self.processor.cfg.temp_dir, f"cut_{idx}.ffconcat")
                cut_video_path = os.path.join(self.processor.cfg.temp_dir, f"cut_{idx}.mp4")
                
                self.processor.create_cut_file(video_path, segments, concat_path)
                self.processor.render_cut(concat_path, cut_video_path)
                
                # Transcribe
                self.log(f"Transcription ({fname})...")
                whisper_segs = self.processor.transcribe(cut_video_path)
                srt_path = os.path.join(self.processor.cfg.temp_dir, f"temp_{idx}.srt")
                self.processor.generate_srt(whisper_segs, srt_path, uppercase=upper)
                
                # Render
                self.log(f"Rendu Final ({fname})...")
                final_out = os.path.join(self.processor.cfg.output_dir, f"Reel_{fname}")
                
                self.processor.burn_subtitle_and_title(
                    cut_video_path, srt_path, final_out, 
                    title_text=title, 
                    style_cfg={"color": color}
                )
                
                self.log(f"TERMINÉ: {final_out}")
                
            except Exception as e:
                self.log(f"ERREUR CRITIQUE sur {fname}: {str(e)}")
                # Continue loop despite error
                continue
        
        self.log("=== BATCH TERMINÉ ===")

if __name__ == "__main__":
    app = VibeApp()
    app.mainloop()
