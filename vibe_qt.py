
import sys
import os
import threading
import subprocess
import shutil
import re
import time

# Import core logic first (imports torch/faster_whisper) to avoid DLL conflicts with PyQt6
from vibe_core import VibeProcessor

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QListWidget,
                             QListWidgetItem, QFileDialog, QLineEdit, QCheckBox,
                             QProgressBar, QSlider, QStackedWidget, QTextEdit,
                             QColorDialog, QSplitter, QStyle, QGroupBox, QSpinBox, QMessageBox)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# --- STYLES ---
DARK_STYLESHEET = """
QMainWindow { background-color: #2b2b2b; color: white; }
QWidget { color: white; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
QGroupBox { font-weight: bold; border: 1px solid #555; margin-top: 10px; border-radius: 5px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QPushButton { background-color: #3e3e3e; border: 1px solid #555; padding: 8px; border-radius: 4px; }
QPushButton:hover { background-color: #505050; border-color: #888; }
QPushButton:pressed { background-color: #222; }
QPushButton:disabled { color: #777; background-color: #2a2a2a; border-color: #444; }
QLineEdit { background-color: #1e1e1e; border: 1px solid #444; padding: 4px; border-radius: 3px; color: #ddd; }
QListWidget { background-color: #1e1e1e; border: 1px solid #444; padding: 5px; }
QProgressBar { border: 1px solid #444; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background-color: #8A2BE2; width: 10px; }
QSlider::groove:horizontal { border: 1px solid #444; height: 8px; background: #222; margin: 2px 0; border-radius: 4px; }
QSlider::handle:horizontal { background: #8A2BE2; border: 1px solid #5c5c5c; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px; }
QTextEdit { background-color: #1e1e1e; color: #ddd; border: 1px solid #444; }
"""

# --- UTILS ---
def ms_to_timestamp(ms):
    s = ms / 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")

def hex_to_ass(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6: return "&HFFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}".upper()

# --- WORKER THREAD ---
# --- WORKER THREAD ---
# --- WORKER THREAD ---
class AnalysisWorker(QThread):
    finished = pyqtSignal(list, float)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    
    def __init__(self, processor, path, start_r=None, end_r=None):
        super().__init__()
        self.processor = processor
        self.path = path
        self.start_r = start_r
        self.end_r = end_r
        
    def run(self):
        try:
            self.progress.emit("Extraction Audio...")
            from pydub import AudioSegment
            audio_path = self.processor.extract_audio(self.path)
            audio = AudioSegment.from_wav(audio_path)
            dur = len(audio) / 1000.0
            
            self.progress.emit("Transcription IA en cours (Ceci permet l'édition)...")
            # Use Whisper to get text immediately
            # This returns list of Segment(start, end, text, ...)
            whisper_segs = self.processor.transcribe(audio_path)
            
            # Convert to our Block format
            full_blocks = []
            current_t = 0.0
            
            # Range filtering start
            if self.start_r:
                full_blocks.append({"start": 0, "end": self.start_r, "type": "silence", "text": "", "active": False})
                current_t = self.start_r

            for seg in whisper_segs:
                # If words are available, split by words
                if seg.words:
                    words = seg.words
                    # Group into chunks of ~5 words or specific duration? 
                    # Let's do max 6 words per block for readability.
                    MAX_WORDS = 6
                    
                    for i in range(0, len(words), MAX_WORDS):
                        chunk = words[i:i+MAX_WORDS]
                        c_start = chunk[0].start
                        c_end = chunk[-1].end
                        c_text = "".join([w.word for w in chunk]).strip()
                        
                        # Gap -> Silence
                        if c_start > current_t + 0.1:
                           full_blocks.append({"start": current_t, "end": c_start, "type": "silence", "text": "", "active": False})
                        
                        full_blocks.append({"start": c_start, "end": c_end, "type": "speech", "text": c_text, "active": True})
                        current_t = c_end
                else:
                    # Fallback to full segment if no words
                    s, e, text = seg.start, seg.end, seg.text.strip()
                    if s > current_t + 0.1:
                        full_blocks.append({"start": current_t, "end": s, "type": "silence", "text": "", "active": False})
                    
                    full_blocks.append({"start": s, "end": e, "type": "speech", "text": text, "active": True})
                    current_t = e
            
            # Final Gap
            effective_end = self.end_r if self.end_r else dur
            if current_t < effective_end - 0.1:
                full_blocks.append({"start": current_t, "end": effective_end, "type": "silence", "text": "", "active": False})
            
            self.finished.emit(full_blocks, dur)
        except Exception as e:
            self.error.emit(str(e))

class RenderWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, processor, project_data):
        super().__init__()
        self.processor = processor
        self.data = project_data
        
    def run(self):
        try:
            # 1. Cut
            self.progress.emit(f"Génération du Cut et des Sous-titres...")
            tmp_id = int(time.time())
            concat = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.ffconcat")
            cut_vid = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.mp4")
            
            # Filter active segments specifically
            # We already have active segments computed in 'segments' (tuples), 
            # BUT we need the TEXT for the SRT.
            # So we better rely on 'active_blocks' passed in project data.
            
            active_blocks = self.data["active_blocks_full"] # List of dicts
            
            # Create cut list
            cut_tuples = [(b["start"], b["end"]) for b in active_blocks]
            self.processor.create_cut_file(self.data["raw_path"], cut_tuples, concat)
            self.processor.render_cut(concat, cut_vid)
            self.data["cut_path"] = cut_vid
            
            # 2. Generate SRT from Blocks (No Re-Transcription)
            # We must shift timestamps: Block 0 starts at 0. Block 1 starts at len(Block 0).
            srt_path = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.srt")
            
            with open(srt_path, "w", encoding="utf-8") as f:
                curr_srt_time = 0.0
                idx = 1
                for b in active_blocks:
                    dur = b["end"] - b["start"]
                    # If it's a speech block AND has text, write it
                    if b["type"] == "speech" and b["text"]:
                        # Setup time
                        s_time = curr_srt_time
                        e_time = curr_srt_time + dur
                        
                        # Write SRT
                        from vibe_core import format_timestamp_srt
                        text = b["text"]
                        if self.data.get("upper"): text = text.upper()
                        
                        f.write(f"{idx}\n")
                        f.write(f"{format_timestamp_srt(s_time)} --> {format_timestamp_srt(e_time)}\n")
                        f.write(f"{text}\n\n")
                        idx += 1
                        
                    curr_srt_time += dur
            
            self.data["srt_path"] = srt_path
            
            self.finished.emit()
            
        except Exception as e:
            self.progress.emit(f"ERREUR Render: {str(e)}")

class FinalRenderWorker(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, processor, projects):
        super().__init__()
        self.processor = processor
        self.projects = projects
        
    def run(self):
        try:
            for i, proj in enumerate(self.projects):
                title = proj.get("title", f"Projet_{i+1}")
                self.log.emit(f"--- Traitement: {title} ---")
                
                # We have 'cut_path' and 'srt_path' ready from previous step
                cut_vid = proj["cut_path"]
                srt_path = proj["srt_path"]
                
                # Output path
                ts = int(time.time())
                final_out = os.path.join(self.processor.cfg.output_dir, f"{title}_{ts}.mp4")
                
                # 1. Burn Subtitles
                self.log.emit("Incrustation des sous-titres...")
                # Style override?
                style_opts = {}
                if "title_color" in proj:
                    style_opts["PrimaryColour"] = hex_to_ass(proj["title_color"])
                if "sub_size" in proj:
                    style_opts["Fontsize"] = str(proj["sub_size"])
                if "sub_pos" in proj:
                    style_opts["MarginV"] = str(proj["sub_pos"])
                
                # If music is added, we burn to temp first, else final
                burn_out = final_out if not proj.get("music") else final_out.replace(".mp4", "_burned.mp4")
                
                self.processor.burn_subtitles(cut_vid, srt_path, burn_out, style=style_opts)
                
                # 2. Add Music?
                if proj.get("music"):
                    self.log.emit(f"Mixage Audio: {os.path.basename(proj['music'])}")
                    self.processor.add_background_music(burn_out, proj["music"], final_out, volume=0.15)
                    # Cleanup temp burned
                    if os.path.exists(burn_out) and burn_out != final_out:
                        os.remove(burn_out)
                    
                self.log.emit(f"OK -> {final_out}")
            
            self.finished.emit()
            
        except Exception as e:
            self.log.emit(f"CRITICAL ERROR: {str(e)}")

# --- CUSTOM WIDGETS ---

class TimelineCanvas(QWidget):
    clicked = pyqtSignal(float) # Emits timestamp
    split_requested = pyqtSignal(float) # Emits timestamp for split
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(80)
        self.duration = 100
        # [{"start": s, "end": e, "type": "speech"|"silence", "active": bool}]
        self.blocks = [] 
        self.cursor_pos = 0
        
    def set_data(self, duration, blocks):
        self.duration = duration
        self.blocks = blocks
        # Default: Activate Speech, Deactivate Silence
        for b in self.blocks:
            b["active"] = (b["type"] == "speech")
        self.update()
        
    def get_active_segments(self):
        return [(b["start"], b["end"]) for b in self.blocks if b["active"]]
        
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Base Background
        p.fillRect(0, 0, w, h, QColor("#111"))
        
        scale = w / self.duration if self.duration > 0 else 0
        
        for b in self.blocks:
            x1 = int(b["start"] * scale)
            x2 = int(b["end"] * scale)
            width = max(1, x2 - x1)
            
            # Colors
            if b["type"] == "speech":
                if b["active"]: col = QColor("#2b8a3e") # Green (Kept)
                else: col = QColor("#1e3a25") # Dim Green (Discarded)
            else: # Silence
                if b["active"]: col = QColor("#2b4a8a") # Blue (Kept Silence)
                else: col = QColor("#1e253a") # Dim Blue (Discarded Silence)
            
            # Discarded Visuals: Cross-hatch? Just dim is cleaner.
            
            # Draw
            p.fillRect(x1, 0, width, h, col)
            
            # Outline
            if b["active"]:
                p.setPen(QPen(QColor("white"), 1))
                p.drawRect(x1, 0, width, h)
            else:
                p.setPen(QPen(QColor("#555"), 1))
                p.drawRect(x1, 0, width, h)
                # Draw X
                p.drawLine(x1, 0, x2, h)
                p.drawLine(x1, h, x2, 0)

        # Cursor
        cx = int(self.cursor_pos * scale)
        p.setPen(QPen(QColor("red"), 2))
        p.drawLine(cx, 0, cx, h)
        
    def mousePressEvent(self, event):
        x = event.pos().x()
        w = self.width()
        t = (x / w) * self.duration
        
        # Check ALT key for splitting
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.AltModifier:
            self.split_requested.emit(t)
            return

        # Normal Click: Toggle block
        for b in self.blocks:
            if b["start"] <= t <= b["end"]:
                b["active"] = not b["active"]
                self.update()
                break
        
        self.clicked.emit(t)

# --- MAIN WINDOW ---

class PreviewPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        
        self.video_widget = QVideoWidget()
        self.layout.addWidget(self.video_widget)
        
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
    
    def load(self, path):
        self.player.setSource(QUrl.fromLocalFile(path))
        
    def set_position(self, seconds):
        self.player.setPosition(int(seconds * 1000))
        
    def play(self):
        self.player.play()
        
    def pause(self):
        self.player.pause()
        
    def get_time(self):
        return self.player.position() / 1000.0

# --- MAIN WINDOW ---

class VibeQtApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeSlicer v5.4 (Studio Pro)")
        self.resize(1280, 800)
        self.processor = VibeProcessor()
        
        # Data
        self.files = [] # Paths
        self.current_file_idx = 0
        self.projects_done = [] # Completed configs
        self.current_project = {}
        
        # UI Setup
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.stack = QStackedWidget()
        
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.addWidget(self.stack)
        
        # Pages
        self.page_files = self.create_files_page()
        self.page_editor = self.create_editor_page()
        self.page_final = self.create_final_page()
        
        self.stack.addWidget(self.page_files)
        self.stack.addWidget(self.page_editor)
        self.stack.addWidget(self.page_final)
        
        self.apply_styles()
        
    def apply_styles(self):
        self.setStyleSheet(DARK_STYLESHEET)
        
    # --- PAGE 1: FILES ---
    def create_files_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        
        lbl = QLabel("1. Importation des Rushs")
        lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #8A2BE2;")
        layout.addWidget(lbl)
        
        # List
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)
        
        btns = QHBoxLayout()
        btn_add = QPushButton("+ Ajouter Vidéos")
        btn_add.clicked.connect(self.add_files)
        btns.addWidget(btn_add)
        
        btn_clear = QPushButton("Effacer Tout")
        btn_clear.clicked.connect(self.file_list.clear)
        btns.addWidget(btn_clear)
        layout.addLayout(btns)
        
        # Global Params (Trim)
        grp = QGroupBox("Paramètres Globaux (Optionnel)")
        gl = QHBoxLayout()
        gl.addWidget(QLabel("Début (sec):"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 99999)
        gl.addWidget(self.spin_start)
        gl.addWidget(QLabel("Fin (sec):"))
        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 99999)
        self.spin_end.setValue(0) # 0 means unlimited
        gl.addWidget(self.spin_end)
        
        self.chk_upper = QCheckBox("Forcer Subs MAJUSCULES")
        gl.addWidget(self.chk_upper)
        
        grp.setLayout(gl)
        layout.addWidget(grp)
        
        # Next
        btn_next = QPushButton("Démarrer le Studio ->")
        btn_next.setStyleSheet("background-color: #2b8a3e; padding: 15px; font-size: 16px;")
        btn_next.clicked.connect(self.start_workflow)
        layout.addWidget(btn_next)
        
        return w
    
    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choisir Vidéos", "", "Video Files (*.mp4 *.mov *.mkv)")
        for p in paths:
            self.file_list.addItem(p)
            self.files.append(p)

    def start_workflow(self):
        if not self.files:
            QMessageBox.warning(self, "Erreur", "Ajoutez au moins une vidéo !")
            return
        
        self.projects_done = []
        self.current_file_idx = 0
        self.load_editor_for_current()
        
    def load_editor_for_current(self):
        path = self.files[self.current_file_idx]
        fname = os.path.basename(path)
        self.lbl_editor_title.setText(f"Projet: {fname} ({self.current_file_idx+1}/{len(self.files)})")
        
        # Init Data
        self.current_project = {
            "raw_path": path,
            "title": "",
            "title_color": "#8A2BE2",
            "upper": self.chk_upper.isChecked(),
            "music": "",
            "sub_color": "#E22B8A",
            "sub_size": 24,
            "sub_pos": 30, # Default margin
            "segments": [],
            "active_blocks_full": [] 
        }
        
        self.player_preview.load(path)
        self.segment_list.clear() # Clear UI
        self.stack.setCurrentWidget(self.page_editor)
        
        # Start Analysis
        self.worker = AnalysisWorker(self.processor, path, self.spin_start.value() or None, self.spin_end.value() or None)
        self.worker.finished.connect(self.on_analysis_done)
        self.worker.progress.connect(lambda s: self.progress_bar.setFormat(s))
        self.worker.start()
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat("Démarrage de l'analyse...")

    def on_analysis_done(self, blocks, dur):
        self.progress_bar.setVisible(False)
        self.current_project["duration"] = dur
        self.timeline.set_data(dur, blocks)
        self.rebuild_segment_list(blocks)

    def rebuild_segment_list(self, blocks):
        self.segment_list.clear()
        for i, b in enumerate(blocks):
            start_fmt = ms_to_timestamp(b["start"]*1000)
            end_fmt = ms_to_timestamp(b["end"]*1000)
            
            Type = "🗣️" if b["type"] == "speech" else "🤫"
            Text = f" - {b['text'][:30]}..." if b.get('text') else ""
            
            item = QListWidgetItem(f"#{i+1} {Type} [{start_fmt} -> {end_fmt}]{Text}")
            item.setData(Qt.ItemDataRole.UserRole, b) # Store block ref
            self.segment_list.addItem(item)
            self.update_list_item_visual(item)

    def update_list_item_visual(self, item):
        b = item.data(Qt.ItemDataRole.UserRole)
        if b["active"]:
            item.setForeground(Qt.GlobalColor.white)
            if b["type"] == "speech":
                item.setBackground(QColor("#1e3a25"))
            else:
                item.setBackground(QColor("#1e253a"))
        else:
            item.setForeground(Qt.GlobalColor.gray)
            item.setBackground(Qt.GlobalColor.transparent)

    def on_segment_double_clicked(self, item):
        # Allow editing text
        from PyQt6.QtWidgets import QInputDialog
        b = item.data(Qt.ItemDataRole.UserRole)
        if b["type"] == "speech":
            text, ok = QInputDialog.getMultiLineText(self, "Editer Sous-titre", "Texte:", b["text"])
            if ok:
                b["text"] = text
                self.rebuild_segment_list(self.timeline.blocks) # Refresh list display

    def on_segment_clicked(self, item):
        row = self.segment_list.row(item)
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers == Qt.KeyboardModifier.ShiftModifier and hasattr(self, 'last_clicked_row'):
            start_row = min(self.last_clicked_row, row)
            end_row = max(self.last_clicked_row, row)
            target_state = not self.timeline.blocks[row]["active"]
            for i in range(start_row, end_row + 1):
                b = self.timeline.blocks[i]
                b["active"] = target_state
                list_item = self.segment_list.item(i)
                self.update_list_item_visual(list_item)
            self.timeline.update()
        else:
            data = item.data(Qt.ItemDataRole.UserRole)
            self.player_preview.set_position(data["start"])
            self.player_preview.play()
            self.last_clicked_row = row

    def toggle_play_preview(self):
        if self.player_preview.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player_preview.pause()
        else:
            self.player_preview.play()

    def update_ui_timer(self):
        # Update timeline cursor and time label based on player position
        if self.stack.currentWidget() == self.page_editor:
            t = self.player_preview.get_time()
            self.timeline.cursor_pos = t
            self.timeline.update()
            self.lbl_time.setText(ms_to_timestamp(t*1000))

    def on_timeline_click(self, t):
        self.player_preview.set_position(t)
        self.timeline.cursor_pos = t
        self.timeline.update()

    def on_timeline_split(self, t):
        # User wants to split a block at time t
        # Find which block contains t
        for i, b in enumerate(self.timeline.blocks):
            if b["start"] < t < b["end"]:
                # SPLIT IT!
                # Block A: start -> t
                new_a = b.copy()
                new_a["end"] = t
                
                # Block B: t -> end
                new_b = b.copy()
                new_b["start"] = t
                
                # Replace in list (and timeline blocks)
                self.timeline.blocks[i] = new_a
                self.timeline.blocks.insert(i+1, new_b)
                
                self.timeline.update()
                self.rebuild_segment_list(self.timeline.blocks)
                break

    def pick_title_col(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.current_project["title_color"] = c.name()
            self.btn_col_t.setStyleSheet(f"background-color: {c.name()}")
            
    def toggle_segment_state(self):
        row = self.segment_list.currentRow()
        if row < 0: return
        
        # Original block ref in timeline?
        b = self.timeline.blocks[row] # Assuming 1:1 mapping
        b["active"] = not b["active"]
        
        self.timeline.update()
        
        # Update list item
        item = self.segment_list.item(row)
        self.update_list_item_visual(item)

    def process_and_finish(self):
        # 1. Gather active blocks fully
        active_blocks_full = [b for b in self.timeline.blocks if b["active"]]
        active_segs = [(b["start"], b["end"]) for b in active_blocks_full]
        
        if not active_segs:
            QMessageBox.warning(self, "Attention", "Tout est rouge ! Vous allez générer une vidéo vide.")
            return

        self.current_project["segments"] = active_segs
        self.current_project["active_blocks_full"] = active_blocks_full
        self.current_project["title"] = self.line_title.text()
        self.current_project["music"] = self.combo_music.currentData()
        self.current_project["sub_size"] = self.spin_font_size.value()
        self.current_project["sub_pos"] = self.slider_pos.value() # Vertical Position
        
        self.progress_bar.setVisible(True)
        self.setEnabled(False)
        self.render_worker = RenderWorker(self.processor, self.current_project)
        self.render_worker.finished.connect(self.on_intermediate_done)
        self.render_worker.progress.connect(lambda s: self.progress_bar.setFormat(s))
        self.render_worker.start()

    # ...

    def create_editor_page(self):
        from PyQt6.QtWidgets import QComboBox
        w = QWidget()
        main_layout = QVBoxLayout(w)
        
        # Upper Splitter
        upper = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT: Player
        player_container = QWidget()
        p_layout = QVBoxLayout(player_container)
        self.lbl_editor_title = QLabel("Studio")
        p_layout.addWidget(self.lbl_editor_title)
        
        self.player_preview = PreviewPlayer()
        p_layout.addWidget(self.player_preview, stretch=1)
        
        ctrls = QHBoxLayout()
        btn_play = QPushButton("Play/Pause (Espace)")
        btn_play.clicked.connect(self.toggle_play_preview)
        ctrls.addWidget(btn_play)
        self.lbl_time = QLabel("00:00.000")
        ctrls.addWidget(self.lbl_time)
        p_layout.addLayout(ctrls)
        
        self.timeline = TimelineCanvas()
        self.timeline.clicked.connect(self.on_timeline_click)
        self.timeline.split_requested.connect(self.on_timeline_split)
        p_layout.addWidget(self.timeline)
        upper.addWidget(player_container)
        
        # RIGHT: List
        list_container = QWidget()
        l_layout = QVBoxLayout(list_container)
        l_layout.addWidget(QLabel("Zones (Double-clic pour éditer texte)"))
        
        self.segment_list = QListWidget()
        self.segment_list.itemClicked.connect(self.on_segment_clicked)
        self.segment_list.itemDoubleClicked.connect(self.on_segment_double_clicked)
        l_layout.addWidget(self.segment_list)
        
        btn_toggle = QPushButton("Activer / Désactiver Zone")
        btn_toggle.clicked.connect(self.toggle_segment_state)
        l_layout.addWidget(btn_toggle)
        upper.addWidget(list_container)
        
        upper.setSizes([800, 400])
        main_layout.addWidget(upper, stretch=1)
        
        # BOTTOM: Export
        bottom = QGroupBox("Export Rapide & Sous-titres")
        b_layout = QHBoxLayout(bottom)
        
        b_layout.addWidget(QLabel("Titre Intro:"))
        self.line_title = QLineEdit()
        b_layout.addWidget(self.line_title)
        
        self.btn_col_t = QPushButton("🎨 Couleur Subs")
        self.btn_col_t.clicked.connect(self.pick_title_col)
        b_layout.addWidget(self.btn_col_t)
        
        # Font Size
        b_layout.addWidget(QLabel("Taille:"))
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 100)
        self.spin_font_size.setValue(24)
        b_layout.addWidget(self.spin_font_size)
        
        # Font Pos
        b_layout.addWidget(QLabel("Hauteur:"))
        self.slider_pos = QSlider(Qt.Orientation.Horizontal)
        self.slider_pos.setRange(0, 1080) # MarginV from bottom (0 to full height)
        self.slider_pos.setValue(640) # Default ~1/3 from bottom (1920/3)
        self.slider_pos.setToolTip("Hauteur Sous-titres (Marge du bas)")
        b_layout.addWidget(self.slider_pos)
        
        b_layout.addWidget(QLabel("Musique:"))
        self.combo_music = QComboBox() 
        self.combo_music.setMinimumWidth(150)
        self.refresh_music_library()
        b_layout.addWidget(self.combo_music)
        
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self.browse_music_add)
        b_layout.addWidget(btn_browse)
        
        btn_finish = QPushButton("TERMINER ->")
        btn_finish.setStyleSheet("background-color: green; font-weight: bold; padding: 10px;")
        btn_finish.clicked.connect(self.process_and_finish)
        b_layout.addWidget(btn_finish)
        
        main_layout.addWidget(bottom)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.timer = QTimer()
        self.timer.interval = 50
        self.timer.timeout.connect(self.update_ui_timer)
        self.timer.start()
        
        return w

    def refresh_music_library(self):
        self.combo_music.clear()
        self.combo_music.addItem("Aucune Musique", None)
        
        music_dir = os.path.join(os.getcwd(), "assets", "music")
        if os.path.exists(music_dir):
            for f in os.listdir(music_dir):
                if f.lower().endswith(('.mp3', '.wav')):
                    self.combo_music.addItem(f, os.path.join(music_dir, f))

    def browse_music_add(self):
        # Open dialog, copy file to library? Or just select.
        # User said "rajoute un dossier ... choisir dans cette bibliothèque".
        # Let's copy to library if selected from elsewhere, or just add to list.
        # Simple: Just select logic for now.
        p, _ = QFileDialog.getOpenFileName(self, "Musique", "", "Audio (*.mp3 *.wav)")
        if p:
            # Check if in library, if not copy? No, just use path.
            self.combo_music.addItem(os.path.basename(p), p)
            self.combo_music.setCurrentIndex(self.combo_music.count()-1)

    def on_analysis_done(self, blocks, dur):
        self.progress_bar.setVisible(False)
        self.current_project["duration"] = dur
        self.timeline.set_data(dur, blocks)
        self.rebuild_segment_list(blocks)

    def rebuild_segment_list(self, blocks):
        self.segment_list.clear()
        for i, b in enumerate(blocks):
            start_fmt = ms_to_timestamp(b["start"]*1000)
            end_fmt = ms_to_timestamp(b["end"]*1000)
            
            Type = "🗣️ Parole" if b["type"] == "speech" else "🤫 Silence"
            
            item = QListWidgetItem(f"#{i+1} {Type} [{start_fmt} -> {end_fmt}]")
            item.setData(Qt.ItemDataRole.UserRole, b) # Store block ref
            self.segment_list.addItem(item)
            self.update_list_item_visual(item)

    def update_list_item_visual(self, item):
        b = item.data(Qt.ItemDataRole.UserRole)
        # We need to fetch 'active' from the block ref which is shared with Timeline
        # Wait, setData stores a COPY usually in C++. In Python it stores ref?
        # Let's check. safely rely on timeline blocks being the source of truth if needed.
        # Actually Timeline blocks are the source.
        
        if b["active"]:
            item.setForeground(Qt.GlobalColor.white)
            if b["type"] == "speech":
                item.setBackground(QColor("#1e3a25"))
            else:
                item.setBackground(QColor("#1e253a"))
        else:
            item.setForeground(Qt.GlobalColor.gray)
            item.setBackground(Qt.GlobalColor.transparent)

    def toggle_segment_state(self):
        row = self.segment_list.currentRow()
        if row < 0: return
        
        # Original block ref in timeline?
        b = self.timeline.blocks[row] # Assuming 1:1 mapping
        b["active"] = not b["active"]
        
        self.timeline.update()
        
        # Update list item
        item = self.segment_list.item(row)
        self.update_list_item_visual(item)

    def process_and_finish(self):
        # 1. Gather active segments from TIMELINE blocks
        active_segs = self.timeline.get_active_segments()
        
        if not active_segs:
            QMessageBox.warning(self, "Attention", "Tout est rouge ! Vous allez générer une vidéo vide.")
            return

        self.current_project["segments"] = active_segs
        self.current_project["title"] = self.line_title.text()
        self.current_project["music"] = self.combo_music.currentData() # Path
        self.current_project["sub_size"] = self.spin_font_size.value()
        
        # 2. RUN INTERMEDIATE RENDER (Fix for missing cut_path)
        self.progress_bar.setVisible(True)
        self.setEnabled(False)
        self.render_worker = RenderWorker(self.processor, self.current_project)
        self.render_worker.finished.connect(self.on_intermediate_done)
        self.render_worker.progress.connect(lambda s: self.progress_bar.setFormat(s)) # Show logs
        self.render_worker.start()

    def on_intermediate_done(self):
        self.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.projects_done.append(self.current_project)
        
        self.current_file_idx += 1
        if self.current_file_idx < len(self.files):
            self.load_editor_for_current()
        else:
            self.load_final_page()
    
    # Remove old browse_music as it is replaced


    # --- PAGE 4: FINAL ---
    def create_final_page(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Tout est prêt !"))
        
        self.btn_render = QPushButton("LANCER LE RENDU FINAL")
        self.btn_render.setStyleSheet("background-color: #d63031; font-size: 20px; padding: 20px;")
        self.btn_render.clicked.connect(self.start_final_render)
        l.addWidget(self.btn_render)
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        l.addWidget(self.log_area)
        
        return w

    def load_final_page(self):
        self.stack.setCurrentWidget(self.page_final)
        self.log_area.append(f"{len(self.projects_done)} projets prêts.")

    def start_final_render(self):
        self.btn_render.setEnabled(False)
        self.final_worker = FinalRenderWorker(self.processor, self.projects_done)
        self.final_worker.log.connect(self.log_area.append)
        self.final_worker.finished.connect(lambda: QMessageBox.information(self, "Succès", "Traitement terminé !"))
        self.final_worker.start()

# --- ENTRY POINT ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Increase font size globally
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    
    window = VibeQtApp()
    window.show()
    sys.exit(app.exec())
