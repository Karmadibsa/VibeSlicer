"""
Lecteur vidéo Haute Précision (Basé sur ffpyplayer)
Version : Thread-Safe & Low-Latency
Correctif : Gestion robuste des métadonnées None
"""
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
import threading
import time
import logging
import queue

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageTk
    from ffpyplayer.player import MediaPlayer 
    FFPY_AVAILABLE = True
except ImportError:
    FFPY_AVAILABLE = False
    print("ERREUR: Installez ffpyplayer (pip install ffpyplayer)")

class VideoPlayer:
    def __init__(self, canvas: tk.Canvas, on_frame_callback: Callable = None):
        self.canvas = canvas
        self.on_frame = on_frame_callback
        
        self.player: Optional[MediaPlayer] = None
        self.video_path: Optional[Path] = None
        
        # Initialisation à 0.0 pour éviter le crash "NoneType"
        self.duration: float = 0.0
        self.current_time: float = 0.0
        
        self._stop_flag: bool = False
        self._play_thread: Optional[threading.Thread] = None
        self._photo_ref = None
        self.frame_queue = queue.Queue(maxsize=1)
        
        self._check_queue_loop()
    
    def _check_queue_loop(self):
        try:
            frame_data = None
            while not self.frame_queue.empty():
                frame_data = self.frame_queue.get_nowait()
            
            if frame_data:
                image, pts = frame_data
                self._update_ui_image(image)
                self.current_time = pts
                if self.on_frame:
                    self.on_frame(self.current_time)
        except queue.Empty:
            pass
        finally:
            if not self._stop_flag:
                self.canvas.after(5, self._check_queue_loop)

    def load(self, video_path: Path) -> bool:
        if not FFPY_AVAILABLE: return False
        
        self.release()
        self.video_path = Path(video_path)
        self.duration = 0.0 # Reset duration
        
        try:
            self.player = MediaPlayer(
                str(self.video_path),
                ff_opts={'paused': True, 'loop': 0} 
            )
            
            # Attente métadonnées sécurisée
            timeout = 2.0
            start = time.time()
            while time.time() - start < timeout:
                meta = self.player.get_metadata()
                if meta and 'duration' in meta:
                    self.duration = float(meta['duration'])
                    break
                time.sleep(0.05)
            
            # CORRECTION DU CRASH ICI : On vérifie si self.duration est valide
            d_str = f"{self.duration:.2f}" if self.duration is not None else "?"
            logger.info(f"Vidéo chargée: {d_str}s")
            
            self.seek(0)
            return True
            
        except Exception as e:
            logger.error(f"Erreur chargement lecteur: {e}")
            return False

    def play(self):
        if not self.player: return
        self.player.set_pause(False)
        if self._play_thread is None or not self._play_thread.is_alive():
            self._stop_flag = False
            self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
            self._play_thread.start()

    def pause(self):
        if self.player: self.player.set_pause(True)
        
    def toggle(self):
        if not self.player: return
        if self.player.get_pause(): self.play()
        else: self.pause()

    def seek(self, time_sec: float):
        if not self.player: return
        self.player.seek(time_sec, relative=False, accurate=True)
        self.current_time = time_sec
        time.sleep(0.05)
        self._display_current_frame_immediate()

    def is_playing(self) -> bool:
        return not self.player.get_pause() if self.player else False

    def get_time(self) -> float:
        return self.current_time or 0.0

    def get_duration(self) -> float:
        return self.duration or 0.0

    def _play_loop(self):
        while not self._stop_flag:
            if not self.player: break
            frame, val = self.player.get_frame()
            if val == 'eof':
                self.pause()
                break
            if frame is None:
                time.sleep(0.01)
                continue
            if val > 0: time.sleep(val)
            
            img_data, size = frame.get_byte_buffer()
            image = Image.frombytes("RGB", size, bytes(img_data))
            pts = self.player.get_pts()
            
            if not self.frame_queue.full():
                self.frame_queue.put((image, pts))

    def _display_current_frame_immediate(self):
        if not self.player: return
        frame, val = self.player.get_frame(show=False)
        if frame:
            img_data, size = frame.get_byte_buffer()
            image = Image.frombytes("RGB", size, bytes(img_data))
            self._update_ui_image(image)

    def _update_ui_image(self, image: Image):
        if not self.canvas.winfo_exists(): return
        cw = self.canvas.winfo_width() or 1
        ch = self.canvas.winfo_height() or 1
        if cw > 1 and ch > 1:
            w, h = image.size
            scale = min(cw / w, ch / h)
            new_w, new_h = int(w * scale), int(h * scale)
            if new_w != w or new_h != h:
                image = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
        self._photo_ref = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo_ref)

    def release(self):
        self._stop_flag = True
        with self.frame_queue.mutex: self.frame_queue.queue.clear()
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.2)
        if self.player:
            self.player.close_player()
            self.player = None
