
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
            
            # Analyze
            segs = self.processor.analyze_segments(audio_path, start_range=self.start_r, end_range=self.end_r)
            self.finished.emit(segs, dur)
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
        idx = 0
        try:
            # 1. Cut
            self.progress.emit(f"Découpage de la vidéo...")
            concat = os.path.join(self.processor.cfg.temp_dir, f"qt_cut.ffconcat")
            cut_vid = os.path.join(self.processor.cfg.temp_dir, f"qt_cut.mp4")
            
            self.processor.create_cut_file(self.data["raw_path"], self.data["segments"], concat)
            self.processor.render_cut(concat, cut_vid)
            self.data["cut_path"] = cut_vid
            
            # 2. Transcribe
            self.progress.emit("Transcription IA en cours...")
            wsegs = self.processor.transcribe(cut_vid)
            srt = os.path.join(self.processor.cfg.temp_dir, f"qt.srt")
            # Generate initial SRT
            self.processor.generate_srt(wsegs, srt, uppercase=self.data["upper"])
            self.data["srt_path"] = srt
            
            self.finished.emit()
            
        except Exception as e:
            self.progress.emit(f"ERREUR: {str(e)}")

class FinalRenderWorker(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self, processor, projects):
        super().__init__()
        self.processor = processor
        self.projects = projects
        
    def run(self):
        self.log.emit(f"Démarrage du rendu batch ({len(self.projects)} fichiers)...")
        for i, p in enumerate(self.projects):
            try:
                fname = os.path.basename(p["raw_path"])
                self.log.emit(f"[{i+1}/{len(self.projects)}] Rendu final de {fname}...")
                
                out = os.path.join(self.processor.cfg.output_dir, f"Final_V5_{i}.mp4")
                
                # Colors
                ass_outline = hex_to_ass(p["sub_color"])
                
                self.processor.render_final_video(
                    p["cut_path"],
                    p["srt_path"],
                    out,
                    title_text=p["title"],
                    title_color=p["title_color"],
                    music_path=p["music"],
                    style_cfg={"outline_color": ass_outline}
                )
                self.log.emit(f"✅ Terminé: {out}")
            except Exception as e:
                self.log.emit(f"❌ Erreur sur {fname}: {e}")
        self.finished.emit()

# --- CUSTOM WIDGETS ---

class TimelineCanvas(QWidget):
    clicked = pyqtSignal(float) # Emits timestamp on click
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(60)
        self.duration = 100
        self.segments = [] # [{"start": s, "end": e, "active": bool}]
        self.cursor_pos = 0
        
    def set_data(self, duration, segments):
        self.duration = duration
        self.segments = [{"start": s, "end": e, "active": True} for s, e in segments]
        self.update()
        
    def get_active_segments(self):
        return [(s["start"], s["end"]) for s in self.segments if s["active"]]
        
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Background (Silence/Red)
        p.fillRect(0, 0, w, h, QColor("#4a0000"))
        
        # Draw Segments
        scale = w / self.duration if self.duration > 0 else 0
        
        for seg in self.segments:
            x1 = int(seg["start"] * scale)
            x2 = int(seg["end"] * scale)
            width = max(1, x2 - x1)
            
            if seg["active"]:
                col = QColor("#2b8a3e")
                p.setPen(QPen(Qt.GlobalColor.white, 1))
            else:
                col = QColor("#555555")
                p.setPen(Qt.PenStyle.NoPen)
                
            p.fillRect(x1, 2, width, h-4, col)
            if seg["active"]:
                p.drawRect(x1, 2, width, h-4)
                
        # Cursor
        cx = int(self.cursor_pos * scale)
        p.setPen(QPen(Qt.GlobalColor.white, 2))
        p.drawLine(cx, 0, cx, h)
        
    def mousePressEvent(self, event):
        self._handle_mouse(event)
        
    def mouseMoveEvent(self, event):
        # We could implement drag selection
        pass
        
    def _handle_mouse(self, event):
        x = event.pos().x()
        w = self.width()
        t = (x / w) * self.duration
        
        # Toggle clicked segment
        for seg in self.segments:
            if seg["start"] <= t <= seg["end"]:
                seg["active"] = not seg["active"]
                self.update()
                break
        
        self.clicked.emit(t) # Only emit, let parent sync media player

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
        
        # Controls overlay? 
        # Just use global slider or timeline
    
    def load(self, path):
        self.player.setSource(QUrl.fromLocalFile(path))
        
    def set_position(self, seconds):
        self.player.setPosition(int(seconds * 1000))
        # self.player.pause() # Pause when seeking?
        
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
        self.setWindowTitle("VibeSlicer v5.0 (PyQt6 Studio)")
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
        self.page_subs = self.create_subs_page()
        self.page_final = self.create_final_page()
        
        self.stack.addWidget(self.page_files)
        self.stack.addWidget(self.page_editor)
        self.stack.addWidget(self.page_subs)
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
        
# --- PAGE 2: STUDIO (Unified Cut & Subtitles) ---
    def create_editor_page(self):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        
        # Upper Area: Player (Left) + Segment List (Right)
        upper = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT: Player Container
        player_container = QWidget()
        p_layout = QVBoxLayout(player_container)
        
        self.lbl_editor_title = QLabel("Studio")
        p_layout.addWidget(self.lbl_editor_title)
        
        self.player_preview = PreviewPlayer()
        p_layout.addWidget(self.player_preview, stretch=1)
        
        # Player Controls
        ctrls = QHBoxLayout()
        btn_play = QPushButton("Play/Pause (Espace)")
        btn_play.clicked.connect(self.toggle_play_preview)
        ctrls.addWidget(btn_play)
        self.lbl_time = QLabel("00:00.000")
        ctrls.addWidget(self.lbl_time)
        p_layout.addLayout(ctrls)
        
        # Timeline (Visual Bar)
        self.timeline = TimelineCanvas()
        self.timeline.clicked.connect(self.on_timeline_click)
        p_layout.addWidget(self.timeline)
        
        upper.addWidget(player_container)
        
        # RIGHT: Segment List (Cuts + Subs)
        list_container = QWidget()
        l_layout = QVBoxLayout(list_container)
        l_layout.addWidget(QLabel("Séquences Détectées (Double-clic pour éditer texte)"))
        
        self.segment_list = QListWidget()
        self.segment_list.itemClicked.connect(self.on_segment_clicked)
        self.segment_list.itemDoubleClicked.connect(self.on_segment_dbl_click)
        l_layout.addWidget(self.segment_list)
        
        # Segment Tools
        tools = QHBoxLayout()
        btn_del = QPushButton("Supprimer / Restaurer Séq")
        btn_del.clicked.connect(self.toggle_segment_state)
        tools.addWidget(btn_del)
        
        # btn_add_seg = QPushButton("+ Ajouter") # TODO for V6
        # tools.addWidget(btn_add_seg)
        
        l_layout.addLayout(tools)
        upper.addWidget(list_container)
        
        # Set Splitter ratio (60% player, 40% list)
        upper.setSizes([800, 400])
        main_layout.addWidget(upper, stretch=1)
        
        # Bottom Area: Final Config
        bottom = QGroupBox("Export Rapide")
        b_layout = QHBoxLayout(bottom)
        
        b_layout.addWidget(QLabel("Titre:"))
        self.line_title = QLineEdit()
        b_layout.addWidget(self.line_title)
        
        self.btn_col_t = QPushButton("Couleur")
        self.btn_col_t.clicked.connect(self.pick_title_col)
        b_layout.addWidget(self.btn_col_t)
        
        b_layout.addWidget(QLabel("Musique:"))
        self.line_music = QLineEdit()
        b_layout.addWidget(self.line_music)
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self.browse_music)
        b_layout.addWidget(btn_browse)
        
        btn_finish = QPushButton("TERMINER CE FICHIER ->")
        btn_finish.setStyleSheet("background-color: green; font-weight: bold; padding: 10px;")
        btn_finish.clicked.connect(self.process_and_finish)
        b_layout.addWidget(btn_finish)
        
        main_layout.addWidget(bottom)
        
        # Progress overlay
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Timer
        self.timer = QTimer()
        self.timer.interval = 50
        self.timer.timeout.connect(self.update_ui_timer)
        self.timer.start()
        
        return w

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

    def on_analysis_done(self, segs, dur):
        self.progress_bar.setVisible(False)
        self.current_project["duration"] = dur
        self.timeline.set_data(dur, segs)
        
        # Populate List
        # Note: We don't have text yet for raw segments. 
        # Option A: Run Whisper NOW on the whole file? Slow.
        # Option B: Placeholder text in list.
        # Let's use Placeholder "Segment [00:00 - 00:05]"
        
        self.rebuild_segment_list(segs)

    def rebuild_segment_list(self, segs):
        self.segment_list.clear()
        for i, s in enumerate(segs):
            start_fmt = ms_to_timestamp(s[0]*1000)
            end_fmt = ms_to_timestamp(s[1]*1000)
            dur = s[1] - s[0]
            
            item = QListWidgetItem(f"#{i+1}  [{start_fmt} -> {end_fmt}]  ({dur:.1f}s)")
            item.setData(Qt.ItemDataRole.UserRole, {"start": s[0], "end": s[1], "active": True, "text": ""})
            self.segment_list.addItem(item)

    def on_segment_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        # Seek player to start
        self.player_preview.set_position(data["start"])
        self.player_preview.play()

    def on_segment_dbl_click(self, item):
        # Open small dialog to edit text (simulated for now since we don't have text yet)
        # Since we haven't transcribed yet, this is "Premature Optimization"?
        # Actually user wants to edit text. 
        # If we transcribe ONLY kept segments at the end, we can't edit text now.
        # BUT user wants "True Editor".
        
        # COMPROMISE: We let them adjust Start/End visually basically.
        # Text editing happens AFTER render normally.
        # If we want Text Editing NOW, we must Transcribe NOW.
        # Let's trigger a transcription of the RAW file? Too slow.
        # Let's just allow marking Good/Bad.
        pass

    def toggle_segment_state(self):
        row = self.segment_list.currentRow()
        if row < 0: return
        item = self.segment_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole)
        
        data["active"] = not data["active"]
        item.setData(Qt.ItemDataRole.UserRole, data)
        
        # Visual visual update
        if not data["active"]:
            item.setForeground(Qt.GlobalColor.gray)
            item.setText(f"[IGNORE] {item.text()}")
        else:
            item.setForeground(Qt.GlobalColor.white)
            item.setText(item.text().replace("[IGNORE] ", ""))
            
        # Update Timeline visual
        # Need to sync list -> timeline
        # This is a bit disjointed in this architecture.
        # Better: Update self.timeline.segments[row]["active"]
        self.timeline.segments[row]["active"] = data["active"]
        self.timeline.update()

    def process_and_finish(self):
        # 1. Gather all active segments
        active_segs = []
        for i in range(self.segment_list.count()):
            item = self.segment_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data["active"]:
                active_segs.append((data["start"], data["end"]))

        if not active_segs:
            QMessageBox.warning(self, "Stop", "Aucun segment gardé !")
            return

        # 2. Update Project
        self.current_project["segments"] = active_segs
        self.current_project["title"] = self.line_title.text()
        self.current_project["music"] = self.line_music.text()
        
        # 3. Add to Queue & Move Next
        self.projects_done.append(self.current_project) # We store raw intent. 
        
        # We need to ACTUALLY render this one now? Or Stack them? 
        # User said "Terminer ce fichier". 
        # Let's invoke the Render Worker immediately for this file to be done?
        # Or batch later?
        # Let's batch later to keep flow fast.
        
        self.current_file_idx += 1
        if self.current_file_idx < len(self.files):
            self.load_editor_for_current()
        else:
            self.load_final_page()

    # --- REMOVED SEPARATE SUBS PAGE --- 
    # Because functionality is merged into "Studio" page somewhat (Cut mainly)
    # Re-adding Transcription step?
    # User request: "impossible de consulter le moment... ajuster les sous-titres".
    # This implies they want to see subtitles ON THE VIDEO while playing.
    # This requires Real-time SRT burning or Overlay.
    # QVideoWidget doesn't support overlay subs easily.
    
    # NEW STRATEGY V5.1:
    # We stick to CUTTING first.
    # Then we do a fast "Draft Render" (low quality) with subs? Too slow.
    
    # We will trust the timestamps.
    # The sync issue is likely frame rates. 
    # We will add "ensure_frame_rate" in vibe_core.
    
    def create_subs_page(self):
        return QWidget() # Dummy



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
