"""
VibeSlicer — Interface graphique Tkinter
Thème sombre, dark purple accent (#8A2BE2)
"""
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np

# PIL pour le player vidéo intégré (dépendance transitive de moviepy)
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ==================================================================================
# COULEURS & STYLE
# ==================================================================================
BG        = "#12111a"
BG2       = "#1e1c2e"
BG3       = "#2a2840"
ACCENT    = "#8A2BE2"
ACCENT2   = "#a855f7"
FG        = "#f0eeff"
FG2       = "#a09dc0"
GREEN     = "#22c55e"
RED       = "#ef4444"
YELLOW    = "#facc15"
FONT_LG   = ("Segoe UI", 15, "bold")
FONT_MD   = ("Segoe UI", 11)
FONT_SM   = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 10)


def styled_button(parent, text, command=None, color=ACCENT, width=18, **kw):
    btn = tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", activebackground=ACCENT2, activeforeground="white",
        font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
        padx=12, pady=6, width=width, **kw
    )
    return btn


def styled_label(parent, text="", font=FONT_MD, fg=FG, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=BG2, **kw)


# ==================================================================================
# MAIN APPLICATION
# ==================================================================================

class VibeSlicer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VibeSlicer  ✂  Reel Maker")
        self.geometry("960x680")
        self.minsize(820, 580)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Shared state
        self.video_path     = tk.StringVar()
        self.silence_thresh = tk.IntVar(value=-35)
        self.min_silence    = tk.IntVar(value=500)
        self.gui_queue      = queue.Queue()

        # Processing state
        self._video_obj    = None   # moviepy VideoFileClip (phase 1a result)
        self._silences     = []     # list of (start_ms, end_ms)
        self._decisions    = []     # list of bool (True=cut)
        self._cut_clip     = None   # assembled clip
        self._raw_cut_path = None
        self._words_data   = []
        self._txt_path     = None

        # Player state
        self._frames       = []
        self._frame_idx    = 0
        self._player_job   = None

        self._build_ui()
        self.after(100, self._poll_queue)

    # ==================
    # UI BUILD
    # ==================

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=ACCENT, height=48)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  ✂  VibeSlicer", font=("Segoe UI", 16, "bold"),
                 fg="white", bg=ACCENT).pack(side="left", padx=16, pady=8)

        # Main container with notebook-style frames
        self._container = tk.Frame(self, bg=BG)
        self._container.pack(fill="both", expand=True, padx=0, pady=0)

        # Build all screens
        self._screen_setup      = self._build_screen_setup(self._container)
        self._screen_silences   = self._build_screen_silences(self._container)
        self._screen_transcribe = self._build_screen_transcribe(self._container)

        # Step indicator bar
        self._build_step_bar()

        self._show_screen(self._screen_setup)

    def _build_step_bar(self):
        bar = tk.Frame(self, bg=BG3, height=36)
        bar.pack(fill="x", side="bottom")
        self._step_labels = []
        steps = ["1. Fichier & Paramètres", "2. Validation Silences", "3. Transcription & Export"]
        for i, s in enumerate(steps):
            lbl = tk.Label(bar, text=s, font=FONT_SM, fg=FG2, bg=BG3, padx=16, pady=8)
            lbl.pack(side="left")
            self._step_labels.append(lbl)
        self._set_active_step(0)

    def _set_active_step(self, idx):
        for i, lbl in enumerate(self._step_labels):
            if i == idx:
                lbl.configure(fg=ACCENT2, font=("Segoe UI", 9, "bold"))
            else:
                lbl.configure(fg=FG2, font=FONT_SM)

    def _show_screen(self, screen):
        for w in self._container.winfo_children():
            w.pack_forget()
        screen.pack(fill="both", expand=True)

    # ==================
    # SCREEN 1 — SETUP
    # ==================

    def _build_screen_setup(self, parent):
        frame = tk.Frame(parent, bg=BG)

        # Left panel — file + params
        left = tk.Frame(frame, bg=BG2, width=420)
        left.pack(side="left", fill="both", expand=True, padx=(24, 8), pady=24)
        left.pack_propagate(False)

        tk.Label(left, text="Vidéo source", font=FONT_LG, fg=ACCENT2, bg=BG2).pack(anchor="w", padx=16, pady=(20, 4))

        # Drop zone / file picker
        drop = tk.Frame(left, bg=BG3, height=110, cursor="hand2")
        drop.pack(fill="x", padx=16, pady=4)
        drop.pack_propagate(False)
        self._drop_label = tk.Label(
            drop,
            text="📁  Cliquez pour choisir une vidéo\n(.mp4  .mov  .mkv)",
            font=FONT_MD, fg=FG2, bg=BG3, cursor="hand2"
        )
        self._drop_label.pack(expand=True)
        drop.bind("<Button-1>", lambda e: self._pick_file())
        self._drop_label.bind("<Button-1>", lambda e: self._pick_file())

        self._file_lbl = tk.Label(left, text="Aucun fichier sélectionné",
                                   font=FONT_SM, fg=FG2, bg=BG2, wraplength=380)
        self._file_lbl.pack(anchor="w", padx=16, pady=(4, 12))

        # Separator
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=16, pady=8)

        # Parameters
        tk.Label(left, text="Paramètres de détection", font=FONT_LG, fg=ACCENT2, bg=BG2).pack(anchor="w", padx=16, pady=(8, 4))

        self._build_slider(left, "Seuil de silence (dB)",
                           self.silence_thresh, -60, -10, -35, self._fmt_thresh)
        self._build_slider(left, "Durée minimale (ms)",
                           self.min_silence, 100, 2000, 500, self._fmt_ms)

        # Right panel — info / preview placeholder
        right = tk.Frame(frame, bg=BG, width=480)
        right.pack(side="right", fill="both", expand=True, padx=(8, 24), pady=24)

        tk.Label(right, text="Comment ça marche ?", font=FONT_LG, fg=ACCENT2, bg=BG).pack(anchor="w", pady=(20, 8))
        steps_txt = (
            "① Sélectionnez votre vidéo brute.\n\n"
            "② Ajustez les paramètres de détection des silences.\n\n"
            "③ Cliquez ANALYSER — l'app détecte les silences.\n\n"
            "④ Validez chaque silence (couper / garder) avec prévisualisation intégrée.\n\n"
            "⑤ L'app transcrit automatiquement votre voix (Whisper AI).\n\n"
            "⑥ Éditez les sous-titres si besoin, puis exportez votre Reel."
        )
        tk.Label(right, text=steps_txt, font=FONT_MD, fg=FG2, bg=BG,
                 justify="left", wraplength=400).pack(anchor="w", padx=8)

        # Launch button
        btn_frame = tk.Frame(left, bg=BG2)
        btn_frame.pack(fill="x", padx=16, pady=(16, 20))
        self._btn_analyse = styled_button(btn_frame, "▶  ANALYSER LA VIDÉO",
                                          command=self._start_analysis, width=28)
        self._btn_analyse.pack(pady=4)

        # Status + progress
        self._setup_status = tk.Label(left, text="", font=FONT_SM, fg=FG2, bg=BG2)
        self._setup_status.pack(anchor="w", padx=16)
        self._setup_progress = ttk.Progressbar(left, mode="determinate", length=360)
        self._setup_progress.pack(padx=16, pady=(4, 8))

        return frame

    def _build_slider(self, parent, label, var, from_, to, default, fmt_fn):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", padx=16, pady=6)
        tk.Label(row, text=label, font=FONT_SM, fg=FG, bg=BG2).pack(anchor="w")
        inner = tk.Frame(row, bg=BG2)
        inner.pack(fill="x")
        val_lbl = tk.Label(inner, text=fmt_fn(default), font=FONT_SM, fg=ACCENT2, bg=BG2, width=10)
        val_lbl.pack(side="right")
        sl = tk.Scale(
            inner, variable=var, from_=from_, to=to,
            orient="horizontal", bg=BG2, fg=FG, troughcolor=BG3,
            highlightthickness=0, activebackground=ACCENT,
            showvalue=False, command=lambda v, l=val_lbl, f=fmt_fn: l.configure(text=f(int(v)))
        )
        sl.pack(side="left", fill="x", expand=True)

    @staticmethod
    def _fmt_thresh(v): return f"{v} dB"
    @staticmethod
    def _fmt_ms(v): return f"{v} ms"

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Choisir une vidéo",
            filetypes=[("Vidéo", "*.mp4 *.mov *.mkv"), ("Tous", "*.*")]
        )
        if path:
            self.video_path.set(path)
            name = os.path.basename(path)
            self._drop_label.configure(text=f"✅  {name}", fg=GREEN)
            self._file_lbl.configure(text=path)

    # ==================
    # SCREEN 2 — SILENCES
    # ==================

    def _build_screen_silences(self, parent):
        frame = tk.Frame(parent, bg=BG)

        # Left: silence list
        left = tk.Frame(frame, bg=BG2, width=360)
        left.pack(side="left", fill="both", padx=(24, 8), pady=20)
        left.pack_propagate(False)

        tk.Label(left, text="Silences détectés", font=FONT_LG, fg=ACCENT2, bg=BG2).pack(anchor="w", padx=16, pady=(16, 4))
        self._silence_count_lbl = tk.Label(left, text="", font=FONT_SM, fg=FG2, bg=BG2)
        self._silence_count_lbl.pack(anchor="w", padx=16)

        # Listbox
        lb_frame = tk.Frame(left, bg=BG2)
        lb_frame.pack(fill="both", expand=True, padx=16, pady=8)
        sb = tk.Scrollbar(lb_frame)
        sb.pack(side="right", fill="y")
        self._silence_lb = tk.Listbox(
            lb_frame, bg=BG3, fg=FG, selectbackground=ACCENT,
            font=FONT_MONO, yscrollcommand=sb.set, activestyle="none",
            borderwidth=0, highlightthickness=0
        )
        self._silence_lb.pack(side="left", fill="both", expand=True)
        sb.configure(command=self._silence_lb.yview)
        self._silence_lb.bind("<<ListboxSelect>>", self._on_silence_select)

        # Action buttons
        btn_row = tk.Frame(left, bg=BG2)
        btn_row.pack(fill="x", padx=16, pady=(0, 8))
        self._btn_cut   = styled_button(btn_row, "✂  Couper",  command=lambda: self._decide(True),  color=RED,   width=10)
        self._btn_keep  = styled_button(btn_row, "○  Garder",  command=lambda: self._decide(False), color=GREEN, width=10)
        self._btn_cut.pack(side="left", padx=(0, 6))
        self._btn_keep.pack(side="left")

        btn_row2 = tk.Frame(left, bg=BG2)
        btn_row2.pack(fill="x", padx=16, pady=(0, 8))
        self._btn_autocut = styled_button(btn_row2, "⏩  Tout couper", command=self._autocut_all, color=YELLOW, width=16)
        self._btn_autocut.pack(side="left")

        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=16, pady=8)

        self._btn_assemble = styled_button(left, "🎬  ASSEMBLER LA VIDÉO",
                                            command=self._start_assemble, width=28)
        self._btn_assemble.pack(padx=16, pady=4)

        self._silence_status = tk.Label(left, text="", font=FONT_SM, fg=FG2, bg=BG2)
        self._silence_status.pack(anchor="w", padx=16)
        self._silence_progress = ttk.Progressbar(left, mode="determinate", length=300)
        self._silence_progress.pack(padx=16, pady=(4, 8))

        # Right: player
        right = tk.Frame(frame, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(8, 24), pady=20)

        tk.Label(right, text="Prévisualisation", font=FONT_LG, fg=ACCENT2, bg=BG).pack(anchor="w", pady=(16, 4))

        self._player_canvas = tk.Label(right, bg="#000000", text="Sélectionnez un silence\npour prévisualiser",
                                        fg=FG2, font=FONT_MD, width=55, height=15)
        self._player_canvas.pack(fill="both", expand=True, pady=(0, 8))

        player_ctrl = tk.Frame(right, bg=BG)
        player_ctrl.pack(fill="x")
        self._btn_preview = styled_button(player_ctrl, "▶  Prévisualiser", command=self._preview_selected, width=18)
        self._btn_preview.pack(side="left", padx=4)

        self._preview_info = tk.Label(right, text="", font=FONT_SM, fg=FG2, bg=BG)
        self._preview_info.pack(anchor="w", pady=4)

        return frame

    def _on_silence_select(self, event):
        sel = self._silence_lb.curselection()
        if sel:
            idx = sel[0]
            if idx < len(self._silences):
                s, e = self._silences[idx]
                self._preview_info.configure(
                    text=f"Silence #{idx+1}  |  {self._fmt_time(s)} → {self._fmt_time(e)}  ({e-s} ms)"
                )

    def _decide(self, cut: bool):
        sel = self._silence_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self._decisions[idx] = cut
        self._refresh_silence_list(select=idx + 1)

    def _autocut_all(self):
        for i in range(len(self._decisions)):
            self._decisions[i] = True
        self._refresh_silence_list()
        self._silence_status.configure(text=f"Tous les silences marqués à couper.")

    def _refresh_silence_list(self, select=None):
        self._silence_lb.delete(0, tk.END)
        for i, ((s, e), dec) in enumerate(zip(self._silences, self._decisions)):
            icon = "✂" if dec else "○"
            color_tag = "cut" if dec else "keep"
            self._silence_lb.insert(tk.END, f"  {icon}  #{i+1:02d}  {self._fmt_time(s)} → {self._fmt_time(e)}  ({e-s}ms)")
        self._silence_lb.configure(fg=FG)
        # Auto-select next
        if select is not None and select < self._silence_lb.size():
            self._silence_lb.selection_clear(0, tk.END)
            self._silence_lb.selection_set(select)
            self._silence_lb.see(select)
            self._silence_lb.event_generate("<<ListboxSelect>>")

    @staticmethod
    def _fmt_time(ms):
        total_s = ms / 1000.0
        minutes = int(total_s // 60)
        seconds = total_s % 60
        return f"{minutes:02d}:{seconds:05.2f}"

    def _preview_selected(self):
        sel = self._silence_lb.curselection()
        if not sel or not PIL_AVAILABLE or self._video_obj is None:
            if not PIL_AVAILABLE:
                messagebox.showwarning("PIL manquant", "Pillow n'est pas installé. Pip install Pillow")
            return
        idx = sel[0]
        if idx >= len(self._silences):
            return

        start_ms, end_ms = self._silences[idx]
        ctx = 1000
        prev_start = max(0, start_ms - ctx) / 1000.0
        prev_end   = min(self._video_obj.duration, (end_ms + ctx) / 1000.0)

        self._btn_preview.configure(state="disabled", text="⏳ Chargement...")
        self.after(50, lambda: self._load_preview_frames(prev_start, prev_end))

    def _load_preview_frames(self, start_s, end_s):
        """Extract frames in background thread."""
        def _worker():
            try:
                clip = self._video_obj.subclip(start_s, end_s)
                fps  = min(clip.fps, 24)  # cap at 24fps for display
                times = np.arange(0, clip.duration, 1.0 / fps)
                frames = []
                for t in times:
                    frame = clip.get_frame(t)
                    img = Image.fromarray(frame)
                    # Scale to fit 550×300
                    img.thumbnail((550, 300), Image.LANCZOS)
                    frames.append(ImageTk.PhotoImage(img))
                clip.close()
                self.gui_queue.put(("preview_ready", frames, fps))
            except Exception as ex:
                self.gui_queue.put(("preview_error", str(ex)))

        threading.Thread(target=_worker, daemon=True).start()

    def _play_preview(self, frames, fps):
        self._stop_player()
        self._frames    = frames
        self._frame_idx = 0
        self._fps       = fps
        self._btn_preview.configure(state="normal", text="▶  Prévisualiser")
        self._next_frame()

    def _next_frame(self):
        if not self._frames:
            return
        if self._frame_idx < len(self._frames):
            self._player_canvas.configure(image=self._frames[self._frame_idx], text="")
            self._frame_idx += 1
            delay = int(1000 / self._fps)
            self._player_job = self.after(delay, self._next_frame)
        else:
            # Loop once
            self._frame_idx = 0

    def _stop_player(self):
        if self._player_job:
            self.after_cancel(self._player_job)
            self._player_job = None
        self._frames = []

    # ==================
    # SCREEN 3 — TRANSCRIBE & EXPORT
    # ==================

    def _build_screen_transcribe(self, parent):
        frame = tk.Frame(parent, bg=BG)

        # Left — subtitle editor
        left = tk.Frame(frame, bg=BG2, width=480)
        left.pack(side="left", fill="both", expand=True, padx=(24, 8), pady=20)
        left.pack_propagate(False)

        tk.Label(left, text="Sous-titres (éditable)", font=FONT_LG, fg=ACCENT2, bg=BG2).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(left, text="Format : START | END | MOT   (temps en secondes)",
                 font=FONT_SM, fg=FG2, bg=BG2).pack(anchor="w", padx=16)

        txt_frame = tk.Frame(left, bg=BG2)
        txt_frame.pack(fill="both", expand=True, padx=16, pady=8)
        txt_sb = tk.Scrollbar(txt_frame)
        txt_sb.pack(side="right", fill="y")
        self._sub_editor = tk.Text(
            txt_frame, bg=BG3, fg=FG, insertbackground=ACCENT2,
            font=FONT_MONO, yscrollcommand=txt_sb.set, borderwidth=0,
            relief="flat", wrap="none"
        )
        self._sub_editor.pack(side="left", fill="both", expand=True)
        txt_sb.configure(command=self._sub_editor.yview)

        btn_row = tk.Frame(left, bg=BG2)
        btn_row.pack(fill="x", padx=16, pady=(0, 4))
        styled_button(btn_row, "🔁  Recharger", command=self._reload_subs, width=14).pack(side="left", padx=(0, 6))
        styled_button(btn_row, "💾  Sauvegarder", command=self._save_subs, width=14, color=BG3).pack(side="left")

        # Right — export
        right = tk.Frame(frame, bg=BG, width=400)
        right.pack(side="right", fill="both", padx=(8, 24), pady=20)
        right.pack_propagate(False)

        tk.Label(right, text="Export final", font=FONT_LG, fg=ACCENT2, bg=BG).pack(anchor="w", pady=(16, 8))

        tk.Label(right, text="Fichier de sortie :", font=FONT_SM, fg=FG2, bg=BG).pack(anchor="w", padx=4)
        self._export_path_lbl = tk.Label(right, text="(sera défini automatiquement)",
                                          font=FONT_SM, fg=FG, bg=BG, wraplength=340, justify="left")
        self._export_path_lbl.pack(anchor="w", padx=4, pady=(0, 16))

        self._btn_export = styled_button(right, "🔥  BRÛLER LES SOUS-TITRES",
                                          command=self._start_export, width=30)
        self._btn_export.pack(padx=4, pady=4)

        self._export_status = tk.Label(right, text="", font=FONT_SM, fg=FG2, bg=BG, wraplength=340, justify="left")
        self._export_status.pack(anchor="w", padx=4, pady=4)
        self._export_progress = ttk.Progressbar(right, mode="determinate", length=340)
        self._export_progress.pack(padx=4, pady=4)

        ttk.Separator(right, orient="horizontal").pack(fill="x", padx=4, pady=16)

        self._btn_open_folder = styled_button(right, "📂  Ouvrir le dossier de sortie",
                                               command=self._open_output_folder,
                                               color=BG3, width=30)
        self._btn_open_folder.pack(padx=4)

        # Transcription progress (shown at top of right)
        self._transcribe_status  = tk.Label(right, text="", font=FONT_SM, fg=YELLOW, bg=BG, wraplength=340)
        self._transcribe_status.pack(anchor="w", padx=4, pady=(16, 2))
        self._transcribe_progress = ttk.Progressbar(right, mode="determinate", length=340)
        self._transcribe_progress.pack(padx=4, pady=2)

        return frame

    def _reload_subs(self):
        if self._txt_path and os.path.exists(self._txt_path):
            with open(self._txt_path, "r", encoding="utf-8") as f:
                content = f.read()
            self._sub_editor.delete("1.0", tk.END)
            self._sub_editor.insert("1.0", content)

    def _save_subs(self):
        if not self._txt_path:
            messagebox.showwarning("Pas de fichier", "Aucun sous-titre généré pour l'instant.")
            return
        content = self._sub_editor.get("1.0", tk.END)
        with open(self._txt_path, "w", encoding="utf-8") as f:
            f.write(content)
        self._export_status.configure(text="✅ Sous-titres sauvegardés.", fg=GREEN)

    def _open_output_folder(self):
        import reel_maker as rm
        folder = rm.CONFIG["OUTPUT_DIR"]
        if os.path.exists(folder):
            os.startfile(folder)

    # ==================
    # QUEUE POLLING
    # ==================

    def _poll_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]

        if kind == "progress_setup":
            _, p, text = msg
            self._setup_progress["value"] = p * 100
            self._setup_status.configure(text=text)

        elif kind == "silences_ready":
            _, video_obj, silences = msg
            self._video_obj  = video_obj
            self._silences   = silences
            self._decisions  = [True] * len(silences)  # default: cut all
            self._silence_count_lbl.configure(text=f"{len(silences)} silence(s) détecté(s)")
            self._refresh_silence_list()
            self._set_active_step(1)
            self._show_screen(self._screen_silences)
            self._btn_analyse.configure(state="normal", text="▶  ANALYSER LA VIDÉO")
            self._setup_progress["value"] = 0

        elif kind == "error_setup":
            _, err = msg
            self._setup_status.configure(text=f"❌ Erreur : {err}", fg=RED)
            self._btn_analyse.configure(state="normal", text="▶  ANALYSER LA VIDÉO")

        elif kind == "progress_assemble":
            _, p, text = msg
            self._silence_progress["value"] = p * 100
            self._silence_status.configure(text=text)

        elif kind == "assemble_ready":
            _, raw_cut_path = msg
            self._raw_cut_path = raw_cut_path
            self._silence_progress["value"] = 0
            self._silence_status.configure(text="✅ Montage brut sauvegardé !")
            self._btn_assemble.configure(state="normal", text="🎬  ASSEMBLER LA VIDÉO")
            # Auto-start transcription
            self._set_active_step(2)
            self._show_screen(self._screen_transcribe)
            self._start_transcription()

        elif kind == "error_assemble":
            _, err = msg
            self._silence_status.configure(text=f"❌ {err}", fg=RED)
            self._btn_assemble.configure(state="normal", text="🎬  ASSEMBLER LA VIDÉO")

        elif kind == "progress_transcribe":
            _, p, text = msg
            self._transcribe_progress["value"] = p * 100
            self._transcribe_status.configure(text=text)

        elif kind == "transcribe_ready":
            _, words_data, txt_path = msg
            self._words_data = words_data
            self._txt_path   = txt_path
            self._transcribe_progress["value"] = 100
            self._transcribe_status.configure(text=f"✅ {len(words_data)} mots transcrits.", fg=GREEN)
            self._reload_subs()
            # Set export path label
            import reel_maker as rm
            video_name = os.path.basename(self.video_path.get())
            name_root  = os.path.splitext(video_name)[0]
            out = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")
            self._export_path_lbl.configure(text=out)

        elif kind == "error_transcribe":
            _, err = msg
            self._transcribe_status.configure(text=f"❌ {err}", fg=RED)

        elif kind == "progress_export":
            _, p, text = msg
            self._export_progress["value"] = p * 100
            self._export_status.configure(text=text, fg=FG2)

        elif kind == "export_ready":
            _, out_path = msg
            self._export_progress["value"] = 100
            self._export_status.configure(text=f"✅ Vidéo prête !\n{out_path}", fg=GREEN)
            self._btn_export.configure(state="normal", text="🔥  BRÛLER LES SOUS-TITRES")

        elif kind == "error_export":
            _, err = msg
            self._export_status.configure(text=f"❌ {err}", fg=RED)
            self._btn_export.configure(state="normal", text="🔥  BRÛLER LES SOUS-TITRES")

        elif kind == "preview_ready":
            _, frames, fps = msg
            self._play_preview(frames, fps)

        elif kind == "preview_error":
            _, err = msg
            self._btn_preview.configure(state="normal", text="▶  Prévisualiser")
            self._preview_info.configure(text=f"❌ Preview error: {err}", fg=RED)

    # ==================
    # WORKER THREADS
    # ==================

    def _start_analysis(self):
        path = self.video_path.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Fichier manquant", "Veuillez sélectionner un fichier vidéo.")
            return
        self._btn_analyse.configure(state="disabled", text="⏳ Analyse en cours...")
        self._setup_status.configure(text="Démarrage...", fg=FG2)
        thresh  = self.silence_thresh.get()
        min_len = self.min_silence.get()

        def _worker():
            try:
                import reel_maker as rm
                def cb(p, msg):
                    self.gui_queue.put(("progress_setup", p, msg))
                video, silences = rm.extract_and_detect_silences(
                    path, silence_thresh=thresh, min_silence_len=min_len,
                    progress_callback=cb
                )
                self.gui_queue.put(("silences_ready", video, silences))
            except Exception as ex:
                self.gui_queue.put(("error_setup", str(ex)))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_assemble(self):
        if not self._silences:
            messagebox.showwarning("Pas de silences", "Aucun silence à traiter.")
            return
        self._btn_assemble.configure(state="disabled", text="⏳ Assemblage...")
        self._stop_player()

        video_name = os.path.basename(self.video_path.get())
        name_root  = os.path.splitext(video_name)[0]

        def _worker():
            try:
                import reel_maker as rm
                def cb(p, msg):
                    self.gui_queue.put(("progress_assemble", p, msg))

                cut_clip = rm.assemble_clips(
                    self._video_obj, self._silences, self._decisions,
                    progress_callback=cb
                )
                if cut_clip is None:
                    self.gui_queue.put(("error_assemble", "Aucun contenu après les coupes."))
                    return
                raw_cut_path = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Raw_Cut_{name_root}.mp4")
                self._cut_clip = rm.save_raw_cut(cut_clip, raw_cut_path, progress_callback=cb)
                self.gui_queue.put(("assemble_ready", raw_cut_path))
            except Exception as ex:
                self.gui_queue.put(("error_assemble", str(ex)))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_transcription(self):
        self._transcribe_status.configure(text="⏳ Transcription en cours (Whisper AI)...", fg=YELLOW)

        def _worker():
            try:
                import reel_maker as rm
                def cb(p, msg):
                    self.gui_queue.put(("progress_transcribe", p, msg))
                words_data, txt_path = rm.transcribe(self._cut_clip, progress_callback=cb)
                self.gui_queue.put(("transcribe_ready", words_data, txt_path))
            except Exception as ex:
                self.gui_queue.put(("error_transcribe", str(ex)))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_export(self):
        if not self._cut_clip:
            messagebox.showwarning("Pas de vidéo", "Assemblez la vidéo d'abord.")
            return
        # Save editor content first
        self._save_subs()
        if not self._txt_path:
            messagebox.showwarning("Pas de sous-titres", "Les sous-titres ne sont pas générés.")
            return

        self._btn_export.configure(state="disabled", text="⏳ Export en cours...")

        def _worker():
            try:
                import reel_maker as rm
                final_words = rm.load_subs_from_file(self._txt_path)
                video_name  = os.path.basename(self.video_path.get())
                name_root   = os.path.splitext(video_name)[0]
                out_path    = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")

                def cb(p, msg):
                    self.gui_queue.put(("progress_export", p, msg))

                result = rm.burn_subtitles(self._cut_clip, final_words, out_path, progress_callback=cb)
                self.gui_queue.put(("export_ready", result))
            except Exception as ex:
                self.gui_queue.put(("error_export", str(ex)))

        threading.Thread(target=_worker, daemon=True).start()


# ==================================================================================
# ENTRY POINT
# ==================================================================================

if __name__ == "__main__":
    # Make sure working directory is the script folder so relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = VibeSlicer()

    # Apply ttk style
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure("TProgressbar",
                    troughcolor=BG3,
                    background=ACCENT,
                    bordercolor=BG,
                    lightcolor=ACCENT2,
                    darkcolor=ACCENT)
    style.configure("TSeparator", background=BG3)

    app.mainloop()
