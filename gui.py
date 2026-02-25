"""
VibeSlicer Pro — Interface PyQt6 professionnelle
Timeline + waveform + player vidéo intégré
"""
import os
import sys
import threading
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QSplitter, QVBoxLayout, QHBoxLayout, QFileDialog, QListWidget,
    QListWidgetItem, QTabWidget, QPlainTextEdit, QProgressBar, QStatusBar,
    QToolBar, QSizePolicy, QFrame, QScrollArea,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QRect, QPoint, QSize,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QPixmap, QImage, QLinearGradient, QPalette, QIcon,
    QAction,
)

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

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
    finished = pyqtSignal(object, list, object, object)  # video, silences, waveform_data, audio
    error    = pyqtSignal(str)

    def __init__(self, video_path, thresh, min_len):
        super().__init__()
        self.video_path = video_path
        self.thresh     = thresh
        self.min_len    = min_len

    def run(self):
        try:
            import reel_maker as rm
            from pydub import AudioSegment
            video, silences = rm.extract_and_detect_silences(
                self.video_path,
                silence_thresh=self.thresh,
                min_silence_len=self.min_len,
                progress_callback=lambda p, m: self.progress.emit(p, m)
            )
            # Load audio for waveform
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
            self.finished.emit(video, silences, samples, audio)
        except Exception as e:
            self.error.emit(str(e))


class AssemblyWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, video, silences, decisions, raw_cut_path):
        super().__init__()
        self._video       = video
        self._silences    = silences
        self._decisions   = decisions
        self._raw_cut_path = raw_cut_path

    def run(self):
        try:
            import reel_maker as rm
            cb = lambda p, m: self.progress.emit(p, m)
            cut_clip = rm.assemble_clips(self._video, self._silences, self._decisions, cb)
            if cut_clip is None:
                self.error.emit("Aucun contenu après les coupes.")
                return
            rm.save_raw_cut(cut_clip, self._raw_cut_path, cb)
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
            import reel_maker as rm
            import moviepy.editor as mp
            cut_clip = mp.VideoFileClip(self._path)
            cb = lambda p, m: self.progress.emit(p, m)
            words_data, txt_path = rm.transcribe(cut_clip, cb)
            cut_clip.close()
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
            import reel_maker as rm
            import moviepy.editor as mp
            cut_clip   = mp.VideoFileClip(self._raw_cut_path)
            final_words = rm.load_subs_from_file(self._txt_path)
            cb = lambda p, m: self.progress.emit(p, m)
            rm.burn_subtitles(cut_clip, final_words, self._out_path, cb)
            cut_clip.close()
            self.finished.emit(self._out_path)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────────────
# TIMELINE WIDGET
# ──────────────────────────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    seek_requested = pyqtSignal(float)   # seconds
    silence_toggled = pyqtSignal(int)    # index in silences list

    RULER_H   = 22
    WAVE_H    = 60
    SEG_H     = 24
    TOTAL_H   = RULER_H + WAVE_H + SEG_H + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.TOTAL_H)
        self.setMaximumHeight(self.TOTAL_H + 10)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.duration_ms  = 0
        self.silences     = []      # [(start_ms, end_ms), ...]
        self.decisions    = []      # [True/False, ...]
        self.waveform     = None    # numpy array normalised 0-1
        self.playhead_ms  = 0
        self._zoom        = 1.0     # pixels per ms
        self._scroll_px   = 0       # horizontal scroll offset in pixels

    def load(self, duration_ms, silences, decisions, waveform):
        self.duration_ms = duration_ms
        self.silences    = silences
        self.decisions   = decisions[:]
        self.waveform    = waveform
        self._zoom       = max(0.05, (self.width() - 20) / max(duration_ms, 1))
        self.update()

    def set_playhead(self, ms):
        self.playhead_ms = ms
        self.update()

    def set_decision(self, idx, cut: bool):
        if 0 <= idx < len(self.decisions):
            self.decisions[idx] = cut
            self.update()

    def _ms_to_px(self, ms):
        return int(ms * self._zoom) - self._scroll_px + 10

    def _px_to_ms(self, px):
        return (px + self._scroll_px - 10) / max(self._zoom, 0.001)

    def _silence_at(self, px):
        """Return index of silence block at pixel x, or -1."""
        ms = self._px_to_ms(px)
        for i, (s, e) in enumerate(self.silences):
            if s <= ms <= e:
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

        # ── SEGMENTS ─────────────────────────────────────────────────────────
        p.fillRect(0, seg_y, w, self.SEG_H, C_BG)
        if self.silences:
            # Draw content segments (green)
            boundaries = [0] + [ms for pair in self.silences for ms in pair] + [self.duration_ms]
            for i in range(0, len(boundaries) - 1, 2):
                s, e = boundaries[i], boundaries[i + 1]
                x1 = self._ms_to_px(s)
                x2 = self._ms_to_px(e)
                r = QRect(x1, seg_y + 1, max(x2 - x1, 2), self.SEG_H - 2)
                p.fillRect(r, QColor("#1e3a2a"))
                p.setPen(QPen(C_GREEN, 1))
                p.drawRect(r)

            # Draw silence blocks
            p.setFont(QFont("Segoe UI", 8))
            for i, (s, e) in enumerate(self.silences):
                x1 = self._ms_to_px(s)
                x2 = self._ms_to_px(e)
                cut = self.decisions[i] if i < len(self.decisions) else True
                color = QColor("#3b0a0a") if cut else QColor("#0a2c1a")
                border = C_RED if cut else C_GREEN
                label  = "✂" if cut else "○"
                r = QRect(x1, seg_y + 1, max(x2 - x1, 4), self.SEG_H - 2)
                p.fillRect(r, color)
                p.setPen(QPen(border, 1))
                p.drawRect(r)
                if x2 - x1 > 18:
                    p.setPen(QPen(border))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

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
        if event.button() == Qt.MouseButton.LeftButton:
            px = event.position().x()
            idx = self._silence_at(px)
            if idx >= 0:
                self.silence_toggled.emit(idx)
            else:
                ms = max(0.0, self._px_to_ms(px))
                self.seek_requested.emit(ms / 1000.0)

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
    position_changed = pyqtSignal(float)  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video      = None
        self._duration   = 0.0
        self._pos        = 0.0
        self._playing    = False
        self._timer      = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._fps        = 25.0
        self._frame_cache = {}
        self._cache_size  = 30

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Display
        self._display = QLabel()
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setStyleSheet("background: #000; border-radius: 4px;")
        self._display.setMinimumSize(480, 270)
        self._display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._display.setText("Aucune vidéo chargée")
        self._display.setStyleSheet("background: #000; color: #444; font-size: 14px;")
        layout.addWidget(self._display, 1)

        # Seekbar
        self._seekbar = QSlider(Qt.Orientation.Horizontal)
        self._seekbar.setRange(0, 10000)
        self._seekbar.sliderMoved.connect(self._seek_from_slider)
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

    def load(self, video):
        self._video    = video
        self._duration = video.duration
        self._fps      = video.fps or 25.0
        self._pos      = 0.0
        self._frame_cache.clear()
        self._render_frame(0.0)
        self._update_time_label()

    def unload(self):
        self._stop()
        self._video = None
        self._frame_cache.clear()
        self._display.setPixmap(QPixmap())
        self._display.setText("Aucune vidéo chargée")
        self._seekbar.setValue(0)
        self._time_lbl.setText("00:00 / 00:00")

    def seek(self, seconds):
        seconds = max(0.0, min(seconds, self._duration))
        self._pos = seconds
        self._render_frame(seconds)
        self._update_seekbar()
        self._update_time_label()
        self.position_changed.emit(seconds)

    def toggle_play(self):
        if self._playing:
            self._stop()
        else:
            self._play()

    def _play(self):
        if self._video is None:
            return
        self._playing = True
        self._btn_play.setText("⏸")
        interval = max(20, int(1000 / self._fps))
        self._timer.start(interval)

    def _stop(self):
        self._playing = False
        self._btn_play.setText("▶")
        self._timer.stop()

    def _tick(self):
        if self._video is None:
            self._stop()
            return
        step = 1.0 / self._fps
        self._pos = min(self._pos + step, self._duration)
        self._render_frame(self._pos)
        self._update_seekbar()
        self._update_time_label()
        self.position_changed.emit(self._pos)
        if self._pos >= self._duration:
            self._stop()

    def _render_frame(self, t):
        if self._video is None or not PIL_OK:
            return
        # Round to nearest frame
        t = round(t * self._fps) / self._fps
        t = min(t, self._duration - 1 / self._fps)
        key = round(t * self._fps)
        if key in self._frame_cache:
            self._display.setPixmap(self._frame_cache[key])
            return
        try:
            frame = self._video.get_frame(t)  # numpy HxWx3
            h, w, _ = frame.shape
            qimg = QImage(frame.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
            # Scale to display size preserving ratio
            dw = self._display.width()
            dh = self._display.height()
            pix = QPixmap.fromImage(qimg).scaled(
                dw, dh, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            # Cache management
            if len(self._frame_cache) >= self._cache_size:
                oldest = next(iter(self._frame_cache))
                del self._frame_cache[oldest]
            self._frame_cache[key] = pix
            self._display.setPixmap(pix)
        except Exception:
            pass

    def _seek_from_slider(self, val):
        if self._duration > 0:
            t = val / 10000 * self._duration
            self.seek(t)

    def _update_seekbar(self):
        if self._duration > 0:
            val = int(self._pos / self._duration * 10000)
            self._seekbar.blockSignals(True)
            self._seekbar.setValue(val)
            self._seekbar.blockSignals(False)

    def _skip_back(self):
        self.seek(max(0, self._pos - 5))

    def _skip_fwd(self):
        self.seek(min(self._duration, self._pos + 5))

    def _update_time_label(self):
        def fmt(s):
            m = int(s // 60)
            return f"{m:02d}:{s % 60:05.2f}"
        self._time_lbl.setText(f"{fmt(self._pos)} / {fmt(self._duration)}")


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
        import reel_maker as rm
        folder = rm.CONFIG["OUTPUT_DIR"]
        if os.path.exists(folder):
            os.startfile(folder)


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
        self._video_path    = None
        self._video_obj     = None
        self._silences      = []
        self._raw_cut_path  = None
        self._txt_path      = None
        self._audio_obj     = None

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
        tl_lbl = QLabel("TIMELINE  —  clic sur un silence (rouge=couper / vert=garder)  |  scroll = zoom")
        tl_lbl.setStyleSheet("color: #6b6890; font-size: 11px; padding: 0;")
        tl_v.addWidget(tl_lbl)
        self._timeline = TimelineWidget()
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._timeline.silence_toggled.connect(self._on_silence_toggled)
        tl_v.addWidget(self._timeline)
        main_v.addWidget(timeline_frame)

        # Bottom bar: action buttons + progress
        bottom = self._build_bottom_bar()
        main_v.addWidget(bottom)

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
        self._statusbar.showMessage(msg)

    def _on_analysis_done(self, video, silences, waveform, audio):
        self._video_obj  = video
        self._silences   = silences
        self._audio_obj  = audio
        decisions = [True] * len(silences)

        # Update player
        self._player.load(video)

        # Update timeline
        self._timeline.load(
            int(video.duration * 1000),
            silences,
            decisions,
            waveform
        )

        # Update right panel
        self._right.load_silences(silences, decisions)

        self._btn_analyse.setEnabled(True)
        self._btn_assemble.setEnabled(True)
        self._progress.setValue(100)
        self._progress_lbl.setText(f"{len(silences)} silence(s) trouvé(s)")
        self._statusbar.showMessage(
            f"Analyse terminée — {len(silences)} silence(s) détecté(s). "
            "Cliquez sur la timeline ou la liste pour couper/garder."
        )

    def _on_analysis_error(self, err):
        self._btn_analyse.setEnabled(True)
        self._progress.setValue(0)
        self._progress_lbl.setText("Erreur !")
        self._statusbar.showMessage(f"❌ Erreur analyse : {err}")

    # ── SILENCE INTERACTIONS ──────────────────────────────────────────────────

    def _on_silence_toggled(self, idx):
        """Timeline clicked on a silence block."""
        self._right.toggle_silence(idx)
        # right panel emits decision_changed which calls _on_decision_changed

    def _on_decision_changed(self, idx, cut):
        self._timeline.set_decision(idx, cut)

    # ── PLAYER / TIMELINE SYNC ────────────────────────────────────────────────

    def _on_player_position(self, seconds):
        self._timeline.set_playhead(seconds * 1000)

    def _on_timeline_seek(self, seconds):
        self._player.seek(seconds)

    # ── ASSEMBLY ──────────────────────────────────────────────────────────────

    def _start_assemble(self):
        if not self._video_obj:
            return
        self._btn_assemble.setEnabled(False)
        self._progress.setValue(0)
        self._progress_lbl.setText("Assemblage en cours...")
        self._statusbar.showMessage("Assemblage de la vidéo coupée...")

        decisions = self._right.decisions
        name_root = os.path.splitext(os.path.basename(self._video_path))[0]

        import reel_maker as rm
        self._raw_cut_path = os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Raw_Cut_{name_root}.mp4")
        self._right.set_export_path(
            os.path.join(rm.CONFIG["OUTPUT_DIR"], f"Reel_Ready_{name_root}.mp4")
        )

        self._worker_assembly = AssemblyWorker(
            self._video_obj, self._silences, decisions, self._raw_cut_path
        )
        self._worker_assembly.progress.connect(self._on_assemble_progress)
        self._worker_assembly.finished.connect(self._on_assemble_done)
        self._worker_assembly.error.connect(self._on_assemble_error)
        self._worker_assembly.start()

    def _on_assemble_progress(self, p, msg):
        self._progress.setValue(int(p * 100))
        self._progress_lbl.setText(msg)
        self._statusbar.showMessage(msg)

    def _on_assemble_done(self, raw_cut_path):
        self._raw_cut_path = raw_cut_path
        self._progress.setValue(100)
        self._progress_lbl.setText("Montage brut sauvegardé !")
        self._statusbar.showMessage(f"✅ Raw_Cut sauvegardé → lancement de la transcription...")
        self._btn_assemble.setEnabled(True)
        self._right._tabs.setCurrentIndex(1)
        self._start_transcription()

    def _on_assemble_error(self, err):
        self._btn_assemble.setEnabled(True)
        self._statusbar.showMessage(f"❌ Erreur assemblage : {err}")

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
        self._statusbar.showMessage(f"Transcription : {msg}")

    def _on_transcribe_done(self, words_data, txt_path):
        self._txt_path = txt_path
        self._right.load_subs(txt_path)
        self._progress.setValue(100)
        self._progress_lbl.setText(f"{len(words_data)} mots transcrits")
        self._statusbar.showMessage(
            f"✅ Transcription terminée — {len(words_data)} mots. "
            "Éditez les sous-titres si besoin puis cliquez BRÛLER."
        )

    def _on_transcribe_error(self, err):
        self._statusbar.showMessage(f"❌ Erreur transcription : {err}")
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
        import reel_maker as rm
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
        self._statusbar.showMessage(f"Export : {msg}")

    def _on_export_done(self, out_path):
        self._right.set_export_done(out_path)
        self._statusbar.showMessage(f"✅ Vidéo finale prête : {out_path}")

    def _on_export_error(self, err):
        self._right.set_export_error(err)
        self._statusbar.showMessage(f"❌ Erreur export : {err}")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    app.setApplicationName("VibeSlicer Pro")
    win = VibeSlicer()
    win.show()
    sys.exit(app.exec())
