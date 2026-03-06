"""
VibeSlicer Pro — Interface PyQt6 professionnelle
Timeline + waveform + player vidéo intégré
"""
import os
import sys
import time
import threading

# ── Vérification précoce des dépendances critiques ────────────────────────────
# On fait ça AVANT d'importer PyQt6, pour pouvoir afficher une vraie erreur.
def _check_deps():
    missing = []
    try:
        import PyQt6
    except ImportError:
        missing.append("PyQt6  →  pip install PyQt6")
    try:
        import numpy
    except ImportError:
        missing.append("numpy  →  pip install numpy")
    try:
        import pydub
    except ImportError:
        missing.append("pydub  →  pip install pydub")
    if missing:
        msg = "Dépendances manquantes :\n\n" + "\n".join(missing)
        msg += "\n\nLancez le .bat pour les installer automatiquement."
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "VibeSlicer — Erreur de dépendances", 0x10)
        except Exception:
            print(msg)
        sys.exit(1)

_check_deps()

# ── Imports PyQt6 (garantis disponibles après _check_deps) ───────────────────
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QSplitter, QVBoxLayout, QHBoxLayout, QFileDialog, QListWidget,
    QListWidgetItem, QTabWidget, QPlainTextEdit, QProgressBar, QStatusBar,
    QToolBar, QSizePolicy, QFrame, QScrollArea, QMessageBox,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QRect, QPoint, QSize, QUrl,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPixmap, QImage, QLinearGradient, QPalette, QIcon,
    QAction,
)
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    QMEDIA_OK = True
except ImportError:
    QMEDIA_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Import du moteur de traitement vidéo (FFmpeg, zéro moviepy) ──────────────
import reel_maker as rm
from pydub import AudioSegment

# ──────────────────────────────────────────────────────────────────────────────
# PALETTE COULEURS
# ──────────────────────────────────────────────────────────────────────────────
C_BG        = QColor("#0f0e17")
C_BG2       = QColor("#1a1928")
C_BG3       = QColor("#242336")
C_ACCENT    = QColor("#8A2BE2")
C_ACCENT2   = QColor("#a855f7")
C_FG        = QColor("#f0eeff")
C_FG2       = QColor("#9896b8")
C_GREEN     = QColor("#22c55e")
C_RED       = QColor("#ef4444")
C_YELLOW    = QColor("#facc15")
C_ORANGE    = QColor("#f97316")
C_WAVE      = QColor("#6d28d9")
C_SILENCE   = QColor("#1e1c2e")
C_PLAYHEAD  = QColor("#facc15")

STYLE_MAIN = """
QMainWindow, QWidget {
    background-color: #0f0e17;
    color: #f0eeff;
    font-family: "Segoe UI", Arial, sans-serif;
}
QSplitter::handle { background: #242336; width: 3px; height: 3px; }
QTabWidget::pane { border: 1px solid #242336; background: #1a1928; }
QTabBar::tab {
    background: #242336; color: #9896b8;
    padding: 8px 18px; border: none;
}
QTabBar::tab:selected { background: #1a1928; color: #f0eeff; border-bottom: 2px solid #8A2BE2; }
QTabBar::tab:hover { color: #f0eeff; }
QListWidget {
    background: #1a1928; border: none; color: #f0eeff;
    font-family: Consolas, monospace; font-size: 12px;
}
QListWidget::item:selected { background: #8A2BE2; color: white; }
QListWidget::item:hover { background: #242336; }
QPlainTextEdit {
    background: #1a1928; color: #f0eeff;
    font-family: Consolas, monospace; font-size: 12px;
    border: 1px solid #242336;
}
QScrollBar:vertical {
    background: #1a1928; width: 8px; border: none;
}
QScrollBar::handle:vertical { background: #242336; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal {
    background: #1a1928; height: 8px; border: none;
}
QScrollBar::handle:horizontal { background: #242336; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QSlider::groove:horizontal {
    background: #242336; height: 4px; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #8A2BE2; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}
QSlider::sub-page:horizontal { background: #8A2BE2; border-radius: 2px; }
QProgressBar {
    background: #242336; border: none; border-radius: 3px;
    text-align: center; color: #f0eeff; height: 6px;
}
QProgressBar::chunk { background: #8A2BE2; border-radius: 3px; }
QStatusBar { background: #0f0e17; color: #9896b8; font-size: 12px; }
QToolBar { background: #1a1928; border-bottom: 1px solid #242336; spacing: 6px; }
QToolBar QToolButton {
    color: #f0eeff; background: transparent; padding: 6px 12px;
    border: none; border-radius: 4px; font-size: 13px;
}
QToolBar QToolButton:hover { background: #242336; }
QToolBar QToolButton:pressed { background: #8A2BE2; }
"""

def btn(text, color="#8A2BE2", min_w=120):
    b = QPushButton(text)
    b.setMinimumWidth(min_w)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {color}; color: white;
            border: none; border-radius: 5px;
            padding: 8px 16px; font-size: 13px; font-weight: bold;
        }}
        QPushButton:hover {{ background: #a855f7; }}
        QPushButton:disabled {{ background: #2a2840; color: #5a5870; }}
    """)
    return b


# ──────────────────────────────────────────────────────────────────────────────
# WORKER THREADS
# ──────────────────────────────────────────────────────────────────────────────

class AnalysisWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object, list, object, object, str)  # video, silences, waveform, audio, working_path
    error    = pyqtSignal(str)

    def __init__(self, video_path, thresh, min_len):
        super().__init__()
        self.video_path = video_path
        self.thresh     = thresh
        self.min_len    = min_len

    def run(self):
        try:
            video_info, silences, working_path = rm.extract_and_detect_silences(
                self.video_path,
                silence_thresh=self.thresh,
                min_silence_len=self.min_len,
                progress_callback=lambda p, m: self.progress.emit(p, m)
            )
            # Génération de la waveform depuis le WAV extrait
            self.progress.emit(0.85, "Génération de la waveform...")
            audio_path = os.path.join(rm.CONFIG["TEMP_DIR"], "temp_audio.wav")
            audio = AudioSegment.from_wav(audio_path)
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            if audio.channels == 2:
                samples = samples.reshape(-1, 2).mean(axis=1)
            # Downsample to ~4000 points for display
            n_display = 4000
            if len(samples) > n_display:
                step = len(samples) // n_display
                samples = np.abs(samples[:step * n_display].reshape(-1, step)).max(axis=1)
            else:
                samples = np.abs(samples)
            if samples.max() > 0:
                samples = samples / samples.max()
            self.progress.emit(1.0, f"{len(silences)} silence(s) détecté(s).")
            self.finished.emit(video_info, silences, samples, None, working_path)
        except Exception as e:
            self.error.emit(str(e))


class AssemblyWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, video_path, silences, decisions, raw_cut_path):
        super().__init__()
        self._video_path   = video_path   # pass path, not object — moviepy not thread-safe
        self._silences     = silences
        self._decisions    = decisions
        self._raw_cut_path = raw_cut_path

    def run(self):
        try:
            cb = lambda p, m: self.progress.emit(p, m)
            rm.assemble_clips(
                self._video_path,
                self._silences,
                self._decisions,
                self._raw_cut_path,
                cb,
            )
            self.finished.emit(self._raw_cut_path)
        except Exception as e:
            self.error.emit(str(e))


class TranscriptionWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(list, str)
    error    = pyqtSignal(str)

    def __init__(self, raw_cut_path):
        super().__init__()
        self._path = raw_cut_path

    def run(self):
        try:
            cb = lambda p, m: self.progress.emit(p, m)
            words_data, txt_path = rm.transcribe(self._path, cb)
            self.finished.emit(words_data, txt_path)
        except Exception as e:
            self.error.emit(str(e))


class ExportWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, raw_cut_path, txt_path, out_path):
        super().__init__()
        self._raw_cut_path = raw_cut_path
        self._txt_path     = txt_path
        self._out_path     = out_path

    def run(self):
        try:
            final_words = rm.load_subs_from_file(self._txt_path)
            cb = lambda p, m: self.progress.emit(p, m)
            rm.burn_subtitles(self._raw_cut_path, final_words, self._out_path, cb)
            self.finished.emit(self._out_path)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────────────
# TIMELINE WIDGET
# ──────────────────────────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    seek_requested         = pyqtSignal(float)  # seconds — click on ruler
    segment_toggled        = pyqtSignal(int)    # segment index clicked (toggle keep/cut)
    cut_placed             = pyqtSignal(float)  # ms — razor cut placed here
    cut_mode_exit_requested = pyqtSignal()      # Escape pressed in cut mode

    RULER_H   = 22
    WAVE_H    = 60
    SEG_H     = 24
    TOTAL_H   = RULER_H + WAVE_H + SEG_H + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.TOTAL_H)
        self.setMaximumHeight(self.TOTAL_H + 10)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.duration_ms  = 0
        self.waveform     = None    # numpy array normalised 0-1
        self.playhead_ms  = 0
        self._zoom        = 1.0     # pixels per ms
        self._scroll_px   = 0       # horizontal scroll offset in pixels
        self.in_ms        = None    # manual In point
        self.out_ms       = None    # manual Out point
        # Segment model: boundaries divide video into independently toggleable segments
        self._boundaries  = []      # sorted ms positions [0, ..., duration_ms]
        self._seg_keep    = []      # True=keep  False=cut  (one per interval)
        # Cut Tool
        self._cut_mode    = False

    def load(self, duration_ms, silences, decisions, waveform):
        """Load from silence-list model — converts internally to segment model."""
        self.duration_ms = duration_ms
        self.waveform    = waveform
        self._init_segments(silences, decisions, duration_ms)
        self._zoom = max(0.05, (self.width() - 20) / max(duration_ms, 1))
        self.update()

    def _init_segments(self, silences, decisions, duration_ms):
        """Convert silence list into boundary/segment model."""
        bset = {0, int(duration_ms)}
        for s, e in silences:
            bset.add(int(s)); bset.add(int(e))
        self._boundaries = sorted(bset)
        self._seg_keep = []
        for i in range(len(self._boundaries) - 1):
            ss, se = self._boundaries[i], self._boundaries[i + 1]
            keep = True
            for j, (s, e) in enumerate(silences):
                if ss >= s and se <= e:
                    keep = not (decisions[j] if j < len(decisions) else True)
                    break
            self._seg_keep.append(keep)

    def set_playhead(self, ms):
        self.playhead_ms = ms
        self.update()

    def set_in_out(self, in_ms, out_ms):
        self.in_ms  = in_ms
        self.out_ms = out_ms
        self.update()

    # ── Segment model helpers ─────────────────────────────────────────────────

    def toggle_segment(self, idx):
        if 0 <= idx < len(self._seg_keep):
            self._seg_keep[idx] = not self._seg_keep[idx]
            self.update()

    def set_segment_keep(self, idx, keep: bool):
        if 0 <= idx < len(self._seg_keep):
            self._seg_keep[idx] = keep
            self.update()

    def add_boundary_at(self, ms):
        """Razor-cut: split the segment at ms. Both halves inherit parent decision."""
        ms = int(round(ms))
        if ms in self._boundaries:
            return
        for i in range(len(self._boundaries) - 1):
            if self._boundaries[i] < ms < self._boundaries[i + 1]:
                keep = self._seg_keep[i]
                self._boundaries.insert(i + 1, ms)
                self._seg_keep.insert(i + 1, keep)
                self.update()
                return

    def set_cut_mode(self, enabled: bool):
        self._cut_mode = enabled
        self.setCursor(Qt.CursorShape.SplitHCursor if enabled
                       else Qt.CursorShape.PointingHandCursor)
        self.update()

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _ms_to_px(self, ms):
        return int(ms * self._zoom) - self._scroll_px + 10

    def _px_to_ms(self, px):
        return (px + self._scroll_px - 10) / max(self._zoom, 0.001)

    def _segment_at(self, px):
        """Return segment index at pixel x, or -1."""
        ms = self._px_to_ms(px)
        for i in range(len(self._boundaries) - 1):
            if self._boundaries[i] <= ms <= self._boundaries[i + 1]:
                return i
        return -1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, C_BG2)

        if self.duration_ms == 0:
            p.setPen(QPen(C_FG2))
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "Ouvrez une vidéo et cliquez ANALYSER")
            return

        ruler_y = 0
        wave_y  = self.RULER_H
        seg_y   = self.RULER_H + self.WAVE_H + 4

        # ── RULER ────────────────────────────────────────────────────────────
        p.fillRect(0, ruler_y, w, self.RULER_H, C_BG3)
        p.setPen(QPen(C_FG2))
        p.setFont(QFont("Segoe UI", 8))
        step_ms = self._pick_step()
        t = 0
        while t <= self.duration_ms:
            x = self._ms_to_px(t)
            if 0 <= x <= w:
                p.drawLine(x, ruler_y + 14, x, ruler_y + self.RULER_H)
                label = self._fmt(t)
                p.drawText(x + 2, ruler_y + 13, label)
            t += step_ms

        # ── WAVEFORM ─────────────────────────────────────────────────────────
        p.fillRect(0, wave_y, w, self.WAVE_H, C_BG)
        if self.waveform is not None:
            mid_y = wave_y + self.WAVE_H // 2
            n = len(self.waveform)
            dur = max(self.duration_ms, 1)
            pen_wave = QPen(C_WAVE, 1)
            p.setPen(pen_wave)
            prev_x = None
            for i, amp in enumerate(self.waveform):
                ms_pos = i / n * dur
                x = self._ms_to_px(ms_pos)
                if x < 0 or x > w:
                    prev_x = x
                    continue
                amp_h = int(amp * (self.WAVE_H // 2 - 2))
                p.drawLine(x, mid_y - amp_h, x, mid_y + amp_h)

        # ── SEGMENTS (all toggleable: green=keep, red=cut) ───────────────────
        p.fillRect(0, seg_y, w, self.SEG_H, C_BG)
        if self._boundaries:
            p.setFont(QFont("Segoe UI", 8))
            for i in range(len(self._boundaries) - 1):
                x1 = self._ms_to_px(self._boundaries[i])
                x2 = self._ms_to_px(self._boundaries[i + 1])
                keep   = self._seg_keep[i] if i < len(self._seg_keep) else True
                color  = QColor("#1e3a2a") if keep else QColor("#3b0a0a")
                border = C_GREEN if keep else C_RED
                label  = "○" if keep else "✂"
                r = QRect(x1, seg_y + 1, max(x2 - x1, 4), self.SEG_H - 2)
                p.fillRect(r, color)
                p.setPen(QPen(border, 1))
                p.drawRect(r)
                if x2 - x1 > 18:
                    p.setPen(QPen(border))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
            # Razor cut markers (boundaries that aren't 0 or duration)
            p.setPen(QPen(C_FG2, 1))
            for ms in self._boundaries[1:-1]:
                bx = self._ms_to_px(ms)
                if 0 <= bx <= w:
                    p.drawLine(bx, seg_y, bx, seg_y + self.SEG_H)

        # ── CUT MODE INDICATOR ────────────────────────────────────────────────
        if self._cut_mode:
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.setPen(QPen(QColor("#f97316")))
            p.drawText(QRect(0, wave_y + 2, w - 4, 18),
                       Qt.AlignmentFlag.AlignRight,
                       "✂  MODE COUPE  —  clic = couper ici  |  Échap : désactiver")

        # ── IN/OUT SELECTION ─────────────────────────────────────────────────
        if self.in_ms is not None and self.out_ms is not None and self.in_ms < self.out_ms:
            ix1 = self._ms_to_px(self.in_ms)
            ix2 = self._ms_to_px(self.out_ms)
            sel = QRect(ix1, wave_y, ix2 - ix1, self.WAVE_H)
            p.fillRect(sel, QColor(59, 130, 246, 45))   # semi-transparent blue
        if self.in_ms is not None:
            ix = self._ms_to_px(self.in_ms)
            if 0 <= ix <= w:
                p.setPen(QPen(QColor("#3b82f6"), 2))    # blue — In
                p.drawLine(ix, ruler_y, ix, seg_y + self.SEG_H)
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(ix + 3, ruler_y + 12, "IN")
        if self.out_ms is not None:
            ox = self._ms_to_px(self.out_ms)
            if 0 <= ox <= w:
                p.setPen(QPen(QColor("#f97316"), 2))    # orange — Out
                p.drawLine(ox, ruler_y, ox, seg_y + self.SEG_H)
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(ox + 3, ruler_y + 12, "OUT")

        # ── PLAYHEAD ─────────────────────────────────────────────────────────
        ph_x = self._ms_to_px(self.playhead_ms)
        if 0 <= ph_x <= w:
            p.setPen(QPen(C_PLAYHEAD, 2))
            p.drawLine(ph_x, ruler_y, ph_x, seg_y + self.SEG_H)
            # Triangle at top
            tri = [QPoint(ph_x - 5, ruler_y),
                   QPoint(ph_x + 5, ruler_y),
                   QPoint(ph_x,     ruler_y + 8)]
            p.setBrush(QBrush(C_PLAYHEAD))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(*tri)

        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        px = event.position().x()
        py = event.position().y()

        if self._cut_mode:
            # ── CUT TOOL (razor) ──────────────────────────────────────────────
            # Single click = place a razor cut at this position
            ms = max(0.0, min(float(self.duration_ms), self._px_to_ms(px)))
            self.cut_placed.emit(ms)
        else:
            # ── NORMAL MODE ───────────────────────────────────────────────────
            if py <= self.RULER_H:
                # Click on ruler → seek
                ms = max(0.0, self._px_to_ms(px))
                self.seek_requested.emit(ms / 1000.0)
            else:
                # Click on segment area → toggle keep/cut
                idx = self._segment_at(px)
                if idx >= 0:
                    self.segment_toggled.emit(idx)
                else:
                    ms = max(0.0, self._px_to_ms(px))
                    self.seek_requested.emit(ms / 1000.0)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.SplitHCursor if self._cut_mode
                       else Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._cut_mode:
            self.cut_mode_exit_requested.emit()
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.87
        self._zoom = max(0.01, min(self._zoom * factor, 50.0))
        self.update()

    def resizeEvent(self, event):
        if self.duration_ms > 0:
            self._zoom = max(0.05, (self.width() - 20) / max(self.duration_ms, 1))
        self.update()

    def _pick_step(self):
        """Choose a nice ruler step in ms."""
        steps = [500, 1000, 2000, 5000, 10000, 30000, 60000]
        for s in steps:
            px = s * self._zoom
            if px >= 60:
                return s
        return steps[-1]

    @staticmethod
    def _fmt(ms):
        s = ms / 1000
        m = int(s // 60)
        s = s % 60
        if m > 0:
            return f"{m}:{s:04.1f}"
        return f"{s:.1f}s"


# ──────────────────────────────────────────────────────────────────────────────
# VIDEO PLAYER WIDGET
# ──────────────────────────────────────────────────────────────────────────────

class VideoPlayerWidget(QWidget):
    """
    Lecteur vidéo basé sur QMediaPlayer — synchronisation A/V native.
    Plus de QTimer, plus de ffplay, plus de get_frame() bloquant.
    """
    position_changed = pyqtSignal(float)  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration        = 0.0
        self._slider_dragging = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if QMEDIA_OK:
            # ── QVideoWidget : rendu matériel natif ───────────────────────────
            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumSize(480, 270)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._video_widget.setStyleSheet("background: #000; border-radius: 4px;")
            layout.addWidget(self._video_widget, 1)

            # ── QMediaPlayer : A/V sync géré nativement par Qt ───────────────
            self._media = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._audio_out.setVolume(1.0)
            self._media.setAudioOutput(self._audio_out)
            self._media.setVideoOutput(self._video_widget)

            self._media.positionChanged.connect(self._on_position_changed)
            self._media.durationChanged.connect(self._on_duration_changed)
            self._media.playbackStateChanged.connect(self._on_state_changed)
        else:
            # Fallback : QLabel si QtMultimedia non disponible
            self._media = None
            lbl = QLabel("⚠ QtMultimedia non disponible\npip install PyQt6")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background:#000; color:#ef4444; font-size:13px;")
            lbl.setMinimumSize(480, 270)
            layout.addWidget(lbl, 1)

        # Seekbar
        self._seekbar = QSlider(Qt.Orientation.Horizontal)
        self._seekbar.setRange(0, 10000)
        self._seekbar.sliderPressed.connect(self._on_slider_pressed)
        self._seekbar.sliderReleased.connect(self._on_slider_released)
        self._seekbar.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._seekbar)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(0, 0, 0, 0)
        self._btn_prev = QPushButton("⏮")
        self._btn_play = QPushButton("▶")
        self._btn_next = QPushButton("⏭")
        for b in [self._btn_prev, self._btn_play, self._btn_next]:
            b.setFixedSize(36, 36)
            b.setStyleSheet("""
                QPushButton { background: #242336; color: white; border: none;
                              border-radius: 4px; font-size: 14px; }
                QPushButton:hover { background: #8A2BE2; }
            """)
        self._btn_prev.clicked.connect(self._skip_back)
        self._btn_play.clicked.connect(self.toggle_play)
        self._btn_next.clicked.connect(self._skip_fwd)

        self._time_lbl = QLabel("00:00 / 00:00")
        self._time_lbl.setStyleSheet("color: #9896b8; font-size: 12px;")

        ctrl.addWidget(self._btn_prev)
        ctrl.addWidget(self._btn_play)
        ctrl.addWidget(self._btn_next)
        ctrl.addSpacing(8)
        ctrl.addWidget(self._time_lbl)
        ctrl.addStretch()
        layout.addLayout(ctrl)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, video, video_path=None):
        """Charge la vidéo dans QMediaPlayer. `video` sert pour la durée fallback."""
        if not QMEDIA_OK or self._media is None:
            return
        self._media.stop()
        if video_path:
            self._media.setSource(QUrl.fromLocalFile(os.path.abspath(video_path)))
        if video:
            self._duration = video.duration  # updated by durationChanged signal
        self._update_time_label(0.0)

    def unload(self):
        if self._media:
            self._media.stop()
            self._media.setSource(QUrl())
        self._duration = 0.0
        self._seekbar.setValue(0)
        self._time_lbl.setText("00:00 / 00:00")

    def seek(self, seconds):
        if not self._media:
            return
        ms = max(0, min(int(seconds * 1000), int(self._duration * 1000)))
        self._media.setPosition(ms)

    def toggle_play(self):
        if not self._media:
            return
        if self._media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media.pause()
        else:
            self._media.play()

    @property
    def _pos(self):
        """Position actuelle en secondes (compatibilité avec VibeSlicer._on_set_in/out)."""
        if self._media is None:
            return 0.0
        return self._media.position() / 1000.0

    # ── QMediaPlayer signal handlers ──────────────────────────────────────────

    def _on_position_changed(self, ms):
        seconds = ms / 1000.0
        if not self._slider_dragging and self._duration > 0:
            val = int(ms / (self._duration * 1000) * 10000)
            self._seekbar.blockSignals(True)
            self._seekbar.setValue(val)
            self._seekbar.blockSignals(False)
        self._update_time_label(seconds)
        self.position_changed.emit(seconds)

    def _on_duration_changed(self, ms):
        if ms > 0:
            self._duration = ms / 1000.0

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._btn_play.setText("⏸")
        else:
            self._btn_play.setText("▶")

    # ── Seekbar ───────────────────────────────────────────────────────────────

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_moved(self, val):
        if self._duration > 0:
            self._update_time_label(val / 10000 * self._duration)

    def _on_slider_released(self):
        self._slider_dragging = False
        if self._media and self._duration > 0:
            ms = int(self._seekbar.value() / 10000 * self._duration * 1000)
            self._media.setPosition(ms)

    def _skip_back(self):
        self.seek(max(0.0, self._pos - 5.0))

    def _skip_fwd(self):
        self.seek(min(self._duration, self._pos + 5.0))

    def _update_time_label(self, seconds):
        def fmt(s):
            m = int(s // 60)
            return f"{m:02d}:{s % 60:05.2f}"
        self._time_lbl.setText(f"{fmt(seconds)} / {fmt(self._duration)}")


# ──────────────────────────────────────────────────────────────────────────────
# PANNEAU DROIT — SILENCES + SOUS-TITRES + EXPORT
# ──────────────────────────────────────────────────────────────────────────────

class RightPanel(QWidget):
    decision_changed = pyqtSignal(int, bool)   # index, cut

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Tab 1 — Silences
        self._tab_silences = self._build_tab_silences()
        self._tabs.addTab(self._tab_silences, "✂  Silences")

        # Tab 2 — Subtitles
        self._tab_subs = self._build_tab_subs()
        self._tabs.addTab(self._tab_subs, "💬  Sous-titres")

        # Tab 3 — Export
        self._tab_export = self._build_tab_export()
        self._tabs.addTab(self._tab_export, "🚀  Export")

    # ── Tab Silences ──────────────────────────────────────────────────────────

    def _build_tab_silences(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)

        self._silence_count = QLabel("Aucun silence détecté")
        self._silence_count.setStyleSheet("color: #9896b8; font-size: 12px; padding: 4px;")
        v.addWidget(self._silence_count)

        self._silence_list = QListWidget()
        self._silence_list.itemClicked.connect(self._on_list_click)
        v.addWidget(self._silence_list, 1)

        row = QHBoxLayout()
        self._btn_cut_sel  = btn("✂  Couper",    "#ef4444", 100)
        self._btn_keep_sel = btn("○  Garder",    "#22c55e", 100)
        self._btn_cut_all  = btn("⏩  Tout couper", "#f97316", 120)
        self._btn_keep_all = btn("✓  Tout garder",  "#1d4ed8", 120)
        self._btn_cut_sel.clicked.connect(lambda: self._decide_selected(True))
        self._btn_keep_sel.clicked.connect(lambda: self._decide_selected(False))
        self._btn_cut_all.clicked.connect(lambda: self._decide_all(True))
        self._btn_keep_all.clicked.connect(lambda: self._decide_all(False))
        row.addWidget(self._btn_cut_sel)
        row.addWidget(self._btn_keep_sel)
        row.addStretch()
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self._btn_cut_all)
        row2.addWidget(self._btn_keep_all)
        row2.addStretch()
        v.addLayout(row2)
        return w

    def load_silences(self, silences, decisions):
        self._silences  = silences
        self._decisions = decisions[:]
        self._refresh_list()
        self._silence_count.setText(f"{len(silences)} silence(s) détecté(s)")

    def _refresh_list(self, select=-1):
        self._silence_list.blockSignals(True)
        self._silence_list.clear()
        for i, ((s, e), cut) in enumerate(zip(self._silences, self._decisions)):
            icon   = "✂" if cut else "○"
            color  = "#ef4444" if cut else "#22c55e"
            dur_ms = e - s
            item = QListWidgetItem(f"  {icon}  #{i+1:02d}   {self._fmt(s)} → {self._fmt(e)}   ({dur_ms}ms)")
            item.setForeground(QColor(color))
            self._silence_list.addItem(item)
        if 0 <= select < self._silence_list.count():
            self._silence_list.setCurrentRow(select)
        self._silence_list.blockSignals(False)

    def _on_list_click(self, item):
        idx = self._silence_list.row(item)
        # Don't change decision here, just highlight
        pass

    def _decide_selected(self, cut):
        idx = self._silence_list.currentRow()
        if idx < 0:
            return
        self._decisions[idx] = cut
        self._refresh_list(select=idx + 1)
        self.decision_changed.emit(idx, cut)

    def _decide_all(self, cut):
        for i in range(len(self._decisions)):
            self._decisions[i] = cut
        self._refresh_list()
        for i in range(len(self._decisions)):
            self.decision_changed.emit(i, cut)

    def toggle_silence(self, idx):
        if 0 <= idx < len(self._decisions):
            self._decisions[idx] = not self._decisions[idx]
            self._refresh_list(select=idx)
            self.decision_changed.emit(idx, self._decisions[idx])

    @property
    def decisions(self):
        return self._decisions[:]

    @staticmethod
    def _fmt(ms):
        s = ms / 1000
        m = int(s // 60)
        return f"{m:02d}:{s % 60:05.2f}"

    # ── Tab Sous-titres ───────────────────────────────────────────────────────

    def _build_tab_subs(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)

        lbl = QLabel("Format : START | END | MOT   (temps en secondes)")
        lbl.setStyleSheet("color: #9896b8; font-size: 11px; padding: 2px;")
        v.addWidget(lbl)

        self._sub_editor = QPlainTextEdit()
        self._sub_editor.setPlaceholderText("Les sous-titres apparaîtront ici après la transcription...")
        v.addWidget(self._sub_editor, 1)

        row = QHBoxLayout()
        self._btn_save_subs   = btn("💾  Sauvegarder", "#242336", 130)
        self._btn_reload_subs = btn("🔁  Recharger",   "#242336", 130)
        self._btn_save_subs.clicked.connect(self._save_subs)
        self._btn_reload_subs.clicked.connect(self._reload_subs)
        row.addWidget(self._btn_save_subs)
        row.addWidget(self._btn_reload_subs)
        row.addStretch()
        v.addLayout(row)
        return w

    def load_subs(self, txt_path):
        self._txt_path = txt_path
        self._reload_subs()
        self._tabs.setCurrentIndex(1)

    def _reload_subs(self):
        if hasattr(self, "_txt_path") and self._txt_path and os.path.exists(self._txt_path):
            with open(self._txt_path, "r", encoding="utf-8") as f:
                self._sub_editor.setPlainText(f.read())

    def _save_subs(self):
        if hasattr(self, "_txt_path") and self._txt_path:
            with open(self._txt_path, "w", encoding="utf-8") as f:
                f.write(self._sub_editor.toPlainText())

    def get_txt_path(self):
        return getattr(self, "_txt_path", None)

    # ── Tab Export ────────────────────────────────────────────────────────────

    def _build_tab_export(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        self._export_out_lbl = QLabel("Fichier de sortie : (défini automatiquement)")
        self._export_out_lbl.setStyleSheet("color: #9896b8; font-size: 12px;")
        self._export_out_lbl.setWordWrap(True)
        v.addWidget(self._export_out_lbl)

        self._btn_export = btn("🔥  BRÛLER LES SOUS-TITRES", "#8A2BE2", 240)
        v.addWidget(self._btn_export)

        self._export_progress = QProgressBar()
        self._export_progress.setValue(0)
        v.addWidget(self._export_progress)

        self._export_status = QLabel("")
        self._export_status.setStyleSheet("font-size: 12px;")
        self._export_status.setWordWrap(True)
        v.addWidget(self._export_status)

        v.addStretch()

        self._btn_open_folder = btn("📂  Ouvrir le dossier output", "#242336", 220)
        self._btn_open_folder.clicked.connect(self._open_output)
        v.addWidget(self._btn_open_folder)
        return w

    def set_export_path(self, path):
        self._export_path = path
        self._export_out_lbl.setText(f"Sortie : {path}")

    def set_export_progress(self, p, msg):
        self._export_progress.setValue(int(p * 100))
        self._export_status.setText(msg)
        self._export_status.setStyleSheet("color: #f0eeff; font-size: 12px;")

    def set_export_done(self, path):
        self._export_progress.setValue(100)
        self._export_status.setText(f"✅ Vidéo prête !\n{path}")
        self._export_status.setStyleSheet("color: #22c55e; font-size: 12px;")
        self._btn_export.setEnabled(True)

    def set_export_error(self, err):
        self._export_status.setText(f"❌ {err}")
        self._export_status.setStyleSheet("color: #ef4444; font-size: 12px;")
        self._btn_export.setEnabled(True)

    def _open_output(self):
        folder = rm.CONFIG["OUTPUT_DIR"]
        if os.path.exists(folder):
            os.startfile(folder)


# ──────────────────────────────────────────────────────────────────────────────
# DEBUG PANEL
# ──────────────────────────────────────────────────────────────────────────────

class DebugPanel(QWidget):
    """Collapsible log panel shown at the bottom of the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 4)
        layout.setSpacing(2)

        header = QHBoxLayout()
        lbl = QLabel("🪲  DEBUG LOG")
        lbl.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")
        header.addWidget(lbl)

        self._clear_btn = QPushButton("Vider")
        self._clear_btn.setFixedSize(52, 20)
        self._clear_btn.setStyleSheet("""
            QPushButton { background: #242336; color: #9896b8; border: none;
                          border-radius: 3px; font-size: 10px; }
            QPushButton:hover { background: #3a3858; color: white; }
        """)
        self._clear_btn.clicked.connect(self._clear)
        header.addWidget(self._clear_btn)
        header.addStretch()
        layout.addLayout(header)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        self._log.setStyleSheet("""
            QPlainTextEdit {
                background: #08071a; color: #22c55e;
                font-family: Consolas, monospace; font-size: 11px;
                border: 1px solid #1e1c2e; border-radius: 3px;
            }
        """)
        self._log.setFixedHeight(120)
        layout.addWidget(self._log)

    def log(self, msg: str, level: str = "INFO"):
        ts    = time.strftime("%H:%M:%S")
        icons = {"INFO": "·", "WARN": "⚠", "ERROR": "✖", "DEBUG": "›", "OK": "✔"}
        icon  = icons.get(level, "·")
        self._log.appendPlainText(f"[{ts}] {icon} {msg}")
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self):
        self._log.clear()


# ──────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────

class VibeSlicer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VibeSlicer Pro  ✂  Reel Maker")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 780)

        # State
        self._video_path    = None   # original file chosen by user
        self._working_path  = None   # CFR-normalized file used for analysis/assembly
        self._video_obj     = None
        self._raw_cut_path  = None
        self._txt_path      = None
        self._audio_obj     = None
        # Manual cut In/Out points (ms)
        self._in_ms         = None
        self._out_ms        = None

        self._build_ui()
        self.setStyleSheet(STYLE_MAIN)

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_v = QVBoxLayout(central)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(0)

        # Top splitter: player | right panel
        top_split = QSplitter(Qt.Orientation.Horizontal)
        top_split.setHandleWidth(3)

        # Left: player
        left_w = QWidget()
        left_v = QVBoxLayout(left_w)
        left_v.setContentsMargins(12, 12, 8, 8)
        self._player = VideoPlayerWidget()
        self._player.position_changed.connect(self._on_player_position)
        left_v.addWidget(self._player)

        # Silence & analysis params (below player)
        params = self._build_params_bar()
        left_v.addWidget(params)

        top_split.addWidget(left_w)

        # Right panel
        self._right = RightPanel()
        self._right.decision_changed.connect(self._on_decision_changed)
        self._right._btn_export.clicked.connect(self._start_export)
        self._right._silence_list.currentRowChanged.connect(
            lambda row: self._btn_del_zone.setEnabled(row >= 0 and self._timeline.duration_ms > 0)
        )
        top_split.addWidget(self._right)

        top_split.setSizes([720, 380])
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)
        main_v.addWidget(top_split, 1)

        # Timeline
        timeline_frame = QFrame()
        timeline_frame.setStyleSheet("background: #12111e; border-top: 2px solid #242336;")
        tl_v = QVBoxLayout(timeline_frame)
        tl_v.setContentsMargins(8, 4, 8, 4)
        tl_v.setSpacing(2)

        tl_header = QHBoxLayout()
        tl_lbl = QLabel("TIMELINE  —  scroll = zoom  |  clic segment = couper/garder  |  Mode Coupe : clic = razor cut")
        tl_lbl.setStyleSheet("color: #6b6890; font-size: 11px;")
        tl_header.addWidget(tl_lbl)
        tl_header.addStretch()

        # Cut Tool toggle button
        self._btn_cut_mode = QPushButton("✂ Mode Coupe")
        self._btn_cut_mode.setCheckable(True)
        self._btn_cut_mode.setChecked(False)
        self._btn_cut_mode.setFixedHeight(24)
        self._btn_cut_mode.setToolTip(
            "Activer l'outil coupe :\n"
            "  • Clic 1 : marquer le début de la zone\n"
            "  • Clic 2 : marquer la fin → zone créée\n"
            "  • Clic droit : annuler le 1er marqueur\n"
            "  • Échap : désactiver le mode"
        )
        self._btn_cut_mode.setStyleSheet("""
            QPushButton {
                background: #242336; color: #f97316;
                border: 1px solid #3a3858; border-radius: 3px;
                font-size: 11px; font-weight: bold; padding: 0 10px;
            }
            QPushButton:checked {
                background: #f97316; color: white;
                border: 1px solid #f97316;
            }
            QPushButton:hover { background: #3a3858; color: #ffffff; }
        """)
        self._btn_cut_mode.toggled.connect(self._on_toggle_cut_mode)
        tl_header.addWidget(self._btn_cut_mode)

        # In/Out manual cut buttons
        self._btn_in  = QPushButton("[ In")
        self._btn_out = QPushButton("Out ]")
        self._btn_add = QPushButton("➕ Ajouter zone")
        self._btn_del_zone = QPushButton("✖ Supprimer zone sélectionnée")
        for b, tip in [
            (self._btn_in,  "Marquer le début de la zone à couper (position playhead)"),
            (self._btn_out, "Marquer la fin de la zone à couper (position playhead)"),
            (self._btn_add, "Ajouter la zone In→Out comme coupe manuelle"),
            (self._btn_del_zone, "Supprimer la zone sélectionnée dans la liste"),
        ]:
            b.setFixedHeight(24)
            b.setToolTip(tip)
            b.setStyleSheet("""
                QPushButton { background: #242336; color: #9896b8; border: none;
                              border-radius: 3px; font-size: 11px; padding: 0 8px; }
                QPushButton:hover { background: #3a3858; color: white; }
                QPushButton:disabled { color: #3a3858; }
            """)
        self._btn_in.setStyleSheet(self._btn_in.styleSheet().replace("#9896b8", "#3b82f6"))
        self._btn_out.setStyleSheet(self._btn_out.styleSheet().replace("#9896b8", "#f97316"))
        self._btn_add.setStyleSheet(self._btn_add.styleSheet().replace("#9896b8", "#22c55e"))
        self._btn_del_zone.setStyleSheet(self._btn_del_zone.styleSheet().replace("#9896b8", "#ef4444"))
        self._btn_add.setEnabled(False)
        self._btn_del_zone.setEnabled(False)
        self._btn_in.clicked.connect(self._on_set_in)
        self._btn_out.clicked.connect(self._on_set_out)
        self._btn_add.clicked.connect(self._on_add_manual_zone)
        self._btn_del_zone.clicked.connect(self._on_delete_selected_zone)
        tl_header.addWidget(self._btn_in)
        tl_header.addWidget(self._btn_out)
        tl_header.addWidget(self._btn_add)
        tl_header.addWidget(self._btn_del_zone)
        tl_v.addLayout(tl_header)

        self._timeline = TimelineWidget()
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._timeline.segment_toggled.connect(self._on_segment_toggled)
        self._timeline.cut_placed.connect(self._on_cut_placed)
        self._timeline.cut_mode_exit_requested.connect(
            lambda: self._btn_cut_mode.setChecked(False)
        )
        tl_v.addWidget(self._timeline)
        main_v.addWidget(timeline_frame)

        # Bottom bar: action buttons + progress
        bottom = self._build_bottom_bar()
        main_v.addWidget(bottom)

        # Debug panel (hidden by default)
        self._debug_panel = DebugPanel()
        self._debug_panel.setVisible(False)
        main_v.addWidget(self._debug_panel)

        # Status bar
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Prêt — Ouvrez une vidéo pour commencer.")

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)

        title = QLabel("  ✂  VibeSlicer Pro")
        title.setStyleSheet("color: #a855f7; font-size: 15px; font-weight: bold; padding: 0 12px;")
        tb.addWidget(title)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        open_btn = QAction("📂  Ouvrir vidéo", self)
        open_btn.triggered.connect(self._pick_file)
        tb.addAction(open_btn)

        self._debug_btn = QAction("🪲  Debug", self)
        self._debug_btn.setCheckable(True)
        self._debug_btn.setChecked(False)
        self._debug_btn.triggered.connect(self._toggle_debug)
        tb.addAction(self._debug_btn)

    def _build_params_bar(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 0)
        h.setSpacing(16)

        # Silence threshold
        h.addWidget(QLabel("Seuil silence :"))
        self._thresh_sl = QSlider(Qt.Orientation.Horizontal)
        self._thresh_sl.setRange(-60, -10)
        self._thresh_sl.setValue(-35)
        self._thresh_sl.setFixedWidth(120)
        self._thresh_lbl = QLabel("-35 dB")
        self._thresh_lbl.setStyleSheet("color: #a855f7; min-width: 50px;")
        self._thresh_sl.valueChanged.connect(lambda v: self._thresh_lbl.setText(f"{v} dB"))
        h.addWidget(self._thresh_sl)
        h.addWidget(self._thresh_lbl)

        # Min silence duration
        h.addWidget(QLabel("Durée min :"))
        self._minlen_sl = QSlider(Qt.Orientation.Horizontal)
        self._minlen_sl.setRange(100, 3000)
        self._minlen_sl.setValue(500)
        self._minlen_sl.setFixedWidth(120)
        self._minlen_lbl = QLabel("500 ms")
        self._minlen_lbl.setStyleSheet("color: #a855f7; min-width: 60px;")
        self._minlen_sl.valueChanged.connect(lambda v: self._minlen_lbl.setText(f"{v} ms"))
        h.addWidget(self._minlen_sl)
        h.addWidget(self._minlen_lbl)

        h.addStretch()
        return w

    def _build_bottom_bar(self):
        w = QWidget()
        w.setStyleSheet("background: #12111e; border-top: 1px solid #242336;")
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        self._btn_analyse  = btn("▶  ANALYSER",   "#8A2BE2", 130)
        self._btn_assemble = btn("🎬  ASSEMBLER",  "#1d4ed8", 130)
        self._btn_assemble.setEnabled(False)

        self._btn_analyse.clicked.connect(self._start_analysis)
        self._btn_assemble.clicked.connect(self._start_assemble)

        h.addWidget(self._btn_analyse)
        h.addWidget(self._btn_assemble)
        h.addSpacing(16)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(260)
        self._progress.setValue(0)
        h.addWidget(self._progress)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet("color: #9896b8; font-size: 12px;")
        h.addWidget(self._progress_lbl)
        h.addStretch()
        return w

    # ── FILE PICKING ──────────────────────────────────────────────────────────

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir une vidéo", "",
            "Vidéo (*.mp4 *.mov *.mkv);;Tous (*.*)"
        )
        if path:
            self._video_path = path
            self.setWindowTitle(f"VibeSlicer Pro  ✂  {os.path.basename(path)}")
            self._statusbar.showMessage(f"Fichier chargé : {path}")
            self._player.unload()
            self._timeline.duration_ms = 0
            self._timeline.update()
            self._btn_assemble.setEnabled(False)
            # Lancer l'analyse automatiquement dès qu'un fichier est choisi
            self._start_analysis()

    # ── ANALYSIS ──────────────────────────────────────────────────────────────

    def _start_analysis(self):
        if not self._video_path or not os.path.exists(self._video_path):
            self._statusbar.showMessage("⚠ Sélectionnez d'abord une vidéo.")
            return
        self._btn_analyse.setEnabled(False)
        self._btn_assemble.setEnabled(False)
        self._progress.setValue(0)
        self._progress_lbl.setText("Analyse en cours...")

        self._worker_analysis = AnalysisWorker(
            self._video_path,
            self._thresh_sl.value(),
            self._minlen_sl.value()
        )
        self._worker_analysis.progress.connect(self._on_analysis_progress)
        self._worker_analysis.finished.connect(self._on_analysis_done)
        self._worker_analysis.error.connect(self._on_analysis_error)
        self._worker_analysis.start()

    def _on_analysis_progress(self, p, msg):
        self._progress.setValue(int(p * 100))
        self._progress_lbl.setText(msg)
        self._dbg(f"[Analyse {int(p*100)}%] {msg}")

    def _on_analysis_done(self, video, silences, waveform, audio, working_path):
        self._dbg(f"Analyse terminée — {len(silences)} silence(s)", "OK")
        self._video_obj    = video
        self._working_path = working_path
        self._audio_obj    = audio
        decisions = [True] * len(silences)

        self._player.load(video, self._video_path)
        self._timeline.load(int(video.duration * 1000), silences, decisions, waveform)
        self._sync_right_panel()

        self._btn_analyse.setEnabled(True)
        self._btn_assemble.setEnabled(True)
        self._progress.setValue(100)
        n_cut = sum(1 for k in self._timeline._seg_keep if not k)
        self._progress_lbl.setText(f"{n_cut} segment(s) à couper")
        self._statusbar.showMessage(
            f"Analyse terminée — {len(silences)} silence(s) détecté(s). "
            "Cliquez sur un segment pour couper/garder. Mode Coupe = razor cuts manuels."
        )

    # ── Segment model helpers (VibeSlicer level) ──────────────────────────────

    def _get_assembly_data(self):
        """Derive silences + decisions from the timeline's segment model for assembly."""
        silences, decisions = [], []
        b = self._timeline._boundaries
        sk = self._timeline._seg_keep
        for i in range(len(b) - 1):
            if not sk[i]:   # cut segment
                silences.append((b[i], b[i + 1]))
                decisions.append(True)
        return silences, decisions

    def _sync_right_panel(self):
        """Refresh right-panel silence list from current segment model."""
        silences, decisions = self._get_assembly_data()
        self._right.load_silences(silences, decisions)

    def _on_analysis_error(self, err):
        self._btn_analyse.setEnabled(True)
        self._progress.setValue(0)
        self._progress_lbl.setText("Erreur !")
        self._dbg(f"Erreur analyse : {err}", "ERROR")
        self._statusbar.showMessage(f"❌ {err}")

    # ── SEGMENT / CUT INTERACTIONS ────────────────────────────────────────────

    def _on_segment_toggled(self, idx):
        """Timeline: user clicked on a segment to toggle keep/cut."""
        self._timeline.toggle_segment(idx)
        self._sync_right_panel()
        if 0 <= idx < len(self._timeline._boundaries) - 1:
            s = self._timeline._boundaries[idx]
            e = self._timeline._boundaries[idx + 1]
            keep = self._timeline._seg_keep[idx]
            self._dbg(f"Segment {s}ms→{e}ms : {'○ gardé' if keep else '✂ coupé'}", "DEBUG")

    def _on_cut_placed(self, ms):
        """Cut Tool: user clicked to place a razor cut at ms."""
        if self._timeline.duration_ms == 0:
            self._dbg("Analysez d'abord la vidéo.", "WARN")
            return
        self._timeline.add_boundary_at(ms)
        self._sync_right_panel()
        self._dbg(f"Coupe razor : {ms:.0f}ms", "OK")

    def _on_decision_changed(self, panel_idx, cut):
        """Right-panel list: user changed a cut zone's decision."""
        # panel shows only cut segments → find corresponding segment index
        cut_idxs = [i for i, k in enumerate(self._timeline._seg_keep) if not k]
        if 0 <= panel_idx < len(cut_idxs):
            seg_idx = cut_idxs[panel_idx]
            self._timeline.set_segment_keep(seg_idx, not cut)
            self._sync_right_panel()

    # ── PLAYER / TIMELINE SYNC ────────────────────────────────────────────────

    def _on_player_position(self, seconds):
        self._timeline.set_playhead(seconds * 1000)

    def _on_timeline_seek(self, seconds):
        self._player.seek(seconds)

    # ── DEBUG TOGGLE ──────────────────────────────────────────────────────────

    def _toggle_debug(self, checked):
        self._debug_panel.setVisible(checked)

    def _dbg(self, msg, level="INFO"):
        self._debug_panel.log(msg, level)
        self._statusbar.showMessage(msg)

    # ── MANUAL IN/OUT CUT ZONES ───────────────────────────────────────────────

    def _on_set_in(self):
        pos_ms = int(self._player._pos * 1000)
        self._in_ms = pos_ms
        self._timeline.set_in_out(self._in_ms, self._out_ms)
        self._update_inout_btn()
        self._dbg(f"In point : {pos_ms}ms ({self._player._pos:.2f}s)", "DEBUG")

    def _on_set_out(self):
        pos_ms = int(self._player._pos * 1000)
        self._out_ms = pos_ms
        self._timeline.set_in_out(self._in_ms, self._out_ms)
        self._update_inout_btn()
        self._dbg(f"Out point : {pos_ms}ms ({self._player._pos:.2f}s)", "DEBUG")

    def _update_inout_btn(self):
        ok = (self._in_ms is not None and self._out_ms is not None
              and self._in_ms < self._out_ms
              and self._video_obj is not None)
        self._btn_add.setEnabled(ok)

    def _on_add_manual_zone(self):
        if self._in_ms is None or self._out_ms is None or self._in_ms >= self._out_ms:
            return
        if self._timeline.duration_ms == 0:
            return
        in_ms, out_ms = self._in_ms, self._out_ms
        # Add boundaries, then mark every segment inside as cut
        self._timeline.add_boundary_at(in_ms)
        self._timeline.add_boundary_at(out_ms)
        b = self._timeline._boundaries
        for i in range(len(b) - 1):
            if b[i] >= in_ms and b[i + 1] <= out_ms:
                self._timeline.set_segment_keep(i, False)
        self._sync_right_panel()
        self._dbg(f"Zone manuelle coupée : {in_ms}ms → {out_ms}ms", "OK")
        self._in_ms  = None
        self._out_ms = None
        self._timeline.set_in_out(None, None)
        self._btn_add.setEnabled(False)

    def _on_delete_selected_zone(self):
        """Restore the cut zone selected in the right-panel list (mark as keep)."""
        idx = self._right._silence_list.currentRow()
        if idx < 0:
            return
        cut_idxs = [i for i, k in enumerate(self._timeline._seg_keep) if not k]
        if 0 <= idx < len(cut_idxs):
            seg_idx = cut_idxs[idx]
            s = self._timeline._boundaries[seg_idx]
            e = self._timeline._boundaries[seg_idx + 1]
            self._timeline.set_segment_keep(seg_idx, True)
            self._sync_right_panel()
            self._dbg(f"Zone restaurée (○ gardée) : {s}ms → {e}ms", "WARN")

    # ── CUT TOOL TOGGLE ───────────────────────────────────────────────────────

    def _on_toggle_cut_mode(self, checked):
        self._timeline.set_cut_mode(checked)
        if checked:
            self._dbg("Mode Coupe ON — clic = razor cut | clic segment = couper/garder", "INFO")
            self._statusbar.showMessage("✂ Mode Coupe : clic sur la timeline = couper ici | Échap : désactiver")
        else:
            self._dbg("Mode Coupe désactivé", "INFO")
            self._statusbar.showMessage("Mode normal — clic sur un segment = couper/garder | règle = seek")

    # ── ASSEMBLY ──────────────────────────────────────────────────────────────

    def _start_assemble(self):
        if not self._video_obj:
            return
        self._btn_assemble.setEnabled(False)
        self._progress.setValue(0)
        self._progress_lbl.setText("Assemblage en cours...")
        self._statusbar.showMessage("Assemblage de la vidéo coupée...")

        silences, decisions = self._get_assembly_data()
        name_root = os.path.splitext(os.path.basename(self._video_path))[0]

        self._raw_cut_path = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Raw_Cut_{name_root}.mp4")
        self._right.set_export_path(
            os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")
        )

        # Use working_path (CFR-normalized) so timestamps match the analyzed file
        self._worker_assembly = AssemblyWorker(
            self._working_path or self._video_path,
            silences, decisions, self._raw_cut_path
        )
        self._worker_assembly.progress.connect(self._on_assemble_progress)
        self._worker_assembly.finished.connect(self._on_assemble_done)
        self._worker_assembly.error.connect(self._on_assemble_error)
        self._worker_assembly.start()

    def _on_assemble_progress(self, p, msg):
        self._progress.setValue(int(p * 100))
        self._progress_lbl.setText(msg)
        self._dbg(f"[Assemblage {int(p*100)}%] {msg}")

    def _on_assemble_done(self, raw_cut_path):
        self._raw_cut_path = raw_cut_path
        self._progress.setValue(100)
        self._progress_lbl.setText("Montage brut sauvegardé !")
        self._dbg(f"Assemblage OK → {raw_cut_path}", "OK")
        self._btn_assemble.setEnabled(True)
        self._right._tabs.setCurrentIndex(1)
        self._start_transcription()

    def _on_assemble_error(self, err):
        self._btn_assemble.setEnabled(True)
        self._dbg(f"Erreur assemblage : {err}", "ERROR")
        self._statusbar.showMessage(f"❌ {err}")

    # ── TRANSCRIPTION ─────────────────────────────────────────────────────────

    def _start_transcription(self):
        self._progress.setValue(0)
        self._progress_lbl.setText("Transcription Whisper...")

        self._worker_transcription = TranscriptionWorker(self._raw_cut_path)
        self._worker_transcription.progress.connect(self._on_transcribe_progress)
        self._worker_transcription.finished.connect(self._on_transcribe_done)
        self._worker_transcription.error.connect(self._on_transcribe_error)
        self._worker_transcription.start()

    def _on_transcribe_progress(self, p, msg):
        self._progress.setValue(int(p * 100))
        self._progress_lbl.setText(msg)
        self._dbg(f"[Transcription {int(p*100)}%] {msg}")

    def _on_transcribe_done(self, words_data, txt_path):
        self._txt_path = txt_path
        self._right.load_subs(txt_path)
        self._progress.setValue(100)
        self._progress_lbl.setText(f"{len(words_data)} mots transcrits")
        self._dbg(f"Transcription OK — {len(words_data)} mots → {txt_path}", "OK")
        self._statusbar.showMessage(
            f"✅ {len(words_data)} mots transcrits. Éditez si besoin puis BRÛLER.")

    def _on_transcribe_error(self, err):
        self._dbg(f"Erreur transcription : {err}", "ERROR")
        self._statusbar.showMessage(f"❌ {err}")
        self._progress_lbl.setText("Erreur transcription")

    # ── EXPORT ────────────────────────────────────────────────────────────────

    def _start_export(self):
        if not self._raw_cut_path or not os.path.exists(self._raw_cut_path):
            self._statusbar.showMessage("⚠ Assemblez la vidéo d'abord.")
            return
        if not self._txt_path:
            self._statusbar.showMessage("⚠ Les sous-titres ne sont pas encore générés.")
            return

        # Save current editor state
        self._right._save_subs()

        name_root = os.path.splitext(os.path.basename(self._video_path))[0]
        out_path = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")

        self._right._btn_export.setEnabled(False)
        self._right.set_export_progress(0.0, "Export en cours...")
        self._statusbar.showMessage("Export de la vidéo finale...")

        self._worker_export = ExportWorker(self._raw_cut_path, self._txt_path, out_path)
        self._worker_export.progress.connect(self._on_export_progress)
        self._worker_export.finished.connect(self._on_export_done)
        self._worker_export.error.connect(self._on_export_error)
        self._worker_export.start()

    def _on_export_progress(self, p, msg):
        self._right.set_export_progress(p, msg)
        self._dbg(f"[Export {int(p*100)}%] {msg}")

    def _on_export_done(self, out_path):
        self._right.set_export_done(out_path)
        self._dbg(f"Export OK → {out_path}", "OK")
        self._statusbar.showMessage(f"✅ Vidéo finale prête : {out_path}")

    def _on_export_error(self, err):
        self._right.set_export_error(err)
        self._dbg(f"Erreur export : {err}", "ERROR")
        self._statusbar.showMessage(f"❌ {err}")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Se placer dans le dossier du script (chemins relatifs input/output/assets)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = QApplication(sys.argv)
    app.setApplicationName("VibeSlicer Pro")

    # Handler global pour les exceptions non rattrapées → boîte d'erreur visible
    def _global_exception_hook(exc_type, exc_value, exc_tb):
        import traceback
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(tb_str, file=sys.stderr)
        box = QMessageBox()
        box.setWindowTitle("VibeSlicer — Erreur critique")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(f"<b>Une erreur s'est produite :</b><br><br>{exc_type.__name__}: {exc_value}")
        box.setDetailedText(tb_str)
        box.exec()

    sys.excepthook = _global_exception_hook

    # reel_maker est déjà importé en haut du fichier.
    # On vérifie juste que FFmpeg est accessible sur ce système.
    try:
        import subprocess as _sp
        _r = _sp.run(
            ["ffmpeg", "-version"],
            stdout=_sp.PIPE, stderr=_sp.PIPE,
            creationflags=_sp.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if _r.returncode != 0:
            raise RuntimeError("ffmpeg -version a retourné une erreur.")
    except FileNotFoundError:
        box = QMessageBox()
        box.setWindowTitle("VibeSlicer — FFmpeg introuvable")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(
            "<b>FFmpeg n'est pas installé ou n'est pas dans le PATH.</b><br><br>"
            "VibeSlicer nécessite FFmpeg pour toutes ses opérations vidéo.<br><br>"
            "<b>Solution :</b><br>"
            "1. Téléchargez FFmpeg sur <b>ffmpeg.org</b><br>"
            "2. Ajoutez le dossier <code>bin/</code> à votre variable PATH Windows.<br>"
            "3. Relancez l'application."
        )
        box.exec()
        sys.exit(1)
    except Exception as e:
        pass  # FFmpeg présent mais version étrange — on continue

    win = VibeSlicer()
    win.show()
    sys.exit(app.exec())
