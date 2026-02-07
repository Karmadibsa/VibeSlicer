
import sys
import os
import threading
import subprocess
import shutil
import re

# Import core logic first (imports torch/faster_whisper) to avoid DLL conflicts with PyQt6
from vibe_core import VibeProcessor

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QListWidget,
                             QListWidgetItem, QFileDialog, QLineEdit, QCheckBox,
                             QProgressBar, QSlider, QStackedWidget, QTextEdit,
                             QColorDialog, QSplitter, QStyle, QGroupBox, QSpinBox, QMessageBox)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal, QObject, QThread
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
class AnalysisWorker(QThread):
    finished = pyqtSignal(list, float)
    error = pyqtSignal(str)
    
    def __init__(self, processor, path, start_r=None, end_r=None):
        super().__init__()
        self.processor = processor
        self.path = path
        self.start_r = start_r
        self.end_r = end_r
        
    def run(self):
        try:
            # Get duration
            from pydub import AudioSegment
            audio_path = self.processor.extract_audio(self.path)
            audio = AudioSegment.from_wav(audio_path)
            dur = len(audio) / 1000.0
            
            # Analyze Speech
            speech_segs = self.processor.analyze_segments(audio_path, start_range=self.start_r, end_range=self.end_r)
            
            # PARTITION TIMELINE: Fill gaps with "Silence"
            # Result: [{"start": 0, "end": 5, "type": "speech"}, {"start": 5, "end": 10, "type": "silence"}, ...]
            full_blocks = []
            current_t = 0.0
            
            # If start_r is set, silence before it?
            if self.start_r:
                full_blocks.append({"start": 0, "end": self.start_r, "type": "silence"})
                current_t = self.start_r

            for s, e in speech_segs:
                # Gap before speech?
                if s > current_t + 0.1: # 100ms tolerance
                    full_blocks.append({"start": current_t, "end": s, "type": "silence"})
                
                # Speech block
                full_blocks.append({"start": s, "end": e, "type": "speech"})
                current_t = e
            
            # Gap after last speech?
            effective_end = self.end_r if self.end_r else dur
            if current_t < effective_end - 0.1:
                full_blocks.append({"start": current_t, "end": effective_end, "type": "silence"})
            
            self.finished.emit(full_blocks, dur)
        except Exception as e:
            self.error.emit(str(e))

class RenderWorker(QThread):
    progress = pyqtSignal(str) # Log message
    finished = pyqtSignal()
    
    def __init__(self, processor, project_data):
        super().__init__()
        self.processor = processor
        self.data = project_data
        
    def run(self):
        try:
            # 1. Cut
            self.progress.emit(f"Génération du Cut intermédiaire...")
            # Unique temp name to avoid overwrite in batch if parallel (not parallel here but safe)
            tmp_id = int(time.time())
            concat = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.ffconcat")
            cut_vid = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.mp4")
            
            self.processor.create_cut_file(self.data["raw_path"], self.data["segments"], concat)
            self.processor.render_cut(concat, cut_vid)
            self.data["cut_path"] = cut_vid
            
            # 2. Transcribe
            self.progress.emit("Transcription IA (pour le Rendu Final)...")
            wsegs = self.processor.transcribe(cut_vid)
            srt = os.path.join(self.processor.cfg.temp_dir, f"qt_{tmp_id}.srt")
            self.processor.generate_srt(wsegs, srt, uppercase=self.data["upper"])
            self.data["srt_path"] = srt
            
            self.finished.emit()
            
        except Exception as e:
            self.progress.emit(f"ERREUR: {str(e)}")

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
        
        # Check SHIFT key
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
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
            "segments": [] # will be filled
        }
        
        self.player_preview.load(path)
        self.segment_list.clear() # Clear UI
        self.stack.setCurrentWidget(self.page_editor)
        
        # Start Analysis
        self.worker = AnalysisWorker(self.processor, path, self.spin_start.value() or None, self.spin_end.value() or None)
        self.worker.finished.connect(self.on_analysis_done)
        self.worker.start()
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat("Analyse VAD & Transcription Preview... %p%")

    def on_segment_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        # Seek player to start
        self.player_preview.set_position(data["start"])
        self.player_preview.play()

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

# --- PAGE 2: STUDIO (Unified) ---
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
        p_layout.addWidget(self.timeline)
        upper.addWidget(player_container)
        
        # RIGHT: List & Tools
        list_container = QWidget()
        l_layout = QVBoxLayout(list_container)
        l_layout.addWidget(QLabel("Zones (Vert=Parole, Bleu=Silence)"))
        
        self.segment_list = QListWidget()
        self.segment_list.itemClicked.connect(self.on_segment_clicked)
        l_layout.addWidget(self.segment_list)
        
        btn_toggle = QPushButton("Activer / Désactiver Zone")
        btn_toggle.clicked.connect(self.toggle_segment_state)
        l_layout.addWidget(btn_toggle)
        upper.addWidget(list_container)
        
        upper.setSizes([800, 400])
        main_layout.addWidget(upper, stretch=1)
        
        # BOTTOM: Export
        bottom = QGroupBox("Export Rapide")
        b_layout = QHBoxLayout(bottom)
        
        b_layout.addWidget(QLabel("Titre:"))
        self.line_title = QLineEdit()
        b_layout.addWidget(self.line_title)
        
        self.btn_col_t = QPushButton("Couleur")
        self.btn_col_t.clicked.connect(self.pick_title_col)
        b_layout.addWidget(self.btn_col_t)
        
        b_layout.addWidget(QLabel("Musique:"))
        self.combo_music = QComboBox() # Replaces line_music
        self.combo_music.setMinimumWidth(150)
        self.refresh_music_library()
        b_layout.addWidget(self.combo_music)
        
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self.browse_music_add)
        b_layout.addWidget(btn_browse)
        
        btn_finish = QPushButton("TERMINER CE FICHIER ->")
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
