"""
Lecteur vidéo avec synchronisation audio améliorée
Corrige le bug du son qui boucle
"""
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
import threading
import subprocess
import time

try:
    import cv2
    from PIL import Image, ImageTk
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from ...utils.logger import logger


class VideoPlayer:
    """
    Lecteur vidéo OpenCV avec lecture audio séparée via ffplay
    
    Fonctionnalités:
    - Lecture/Pause
    - Seek précis
    - Synchronisation audio améliorée
    - Callback sur chaque frame
    """
    
    def __init__(self, canvas: tk.Canvas, on_frame_callback: Callable = None):
        self.canvas = canvas
        self.on_frame = on_frame_callback
        
        # État vidéo
        self.cap = None
        self.video_path: Optional[Path] = None
        self.duration: float = 0
        self.fps: float = 30
        self.current_time: float = 0
        
        # État lecture
        self.playing: bool = False
        self._stop_flag: bool = False
        self._play_thread: Optional[threading.Thread] = None
        
        # Audio (ffplay)
        self._audio_process: Optional[subprocess.Popen] = None
        self._audio_lock = threading.Lock()
        
        # Photo reference (prevent garbage collection)
        self._photo_ref = None
    
    def load(self, video_path: Path) -> bool:
        """
        Charge une vidéo
        
        Returns:
            True si chargement réussi
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available")
            return False
        
        self.release()
        self.video_path = Path(video_path)
        
        try:
            self.cap = cv2.VideoCapture(str(self.video_path))
            
            if not self.cap.isOpened():
                logger.error(f"Cannot open video: {video_path}")
                return False
            
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            self.duration = frame_count / self.fps if self.fps > 0 else 0
            
            logger.info(f"Loaded video: {self.video_path.name} ({self.duration:.1f}s)")
            
            # Afficher la première frame
            self._show_frame()
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading video: {e}")
            return False
    
    def _show_frame(self):
        """Affiche la frame courante sur le canvas"""
        if self.cap is None:
            return
        
        ret, frame = self.cap.read()
        if not ret:
            return
        
        # Calculer le temps actuel
        frame_pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        self.current_time = frame_pos / self.fps if self.fps > 0 else 0
        
        # Redimensionner pour le canvas
        h, w = frame.shape[:2]
        cw = self.canvas.winfo_width() or 400
        ch = self.canvas.winfo_height() or 300
        
        scale = min(cw / w, ch / h)
        new_w, new_h = int(w * scale), int(h * scale)
        
        frame = cv2.resize(frame, (new_w, new_h))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convertir en image Tk
        img = Image.fromarray(frame)
        self._photo_ref = ImageTk.PhotoImage(img)
        
        # Afficher centré
        self.canvas.delete("all")
        x = cw // 2
        y = ch // 2
        self.canvas.create_image(x, y, image=self._photo_ref)
        
        # Callback
        if self.on_frame:
            self.on_frame(self.current_time)
    
    def play(self):
        """Démarre la lecture"""
        if not self.cap or self.playing:
            return
        
        self.playing = True
        self._stop_flag = False
        
        # Démarrer l'audio
        self._start_audio()
        
        # Thread de lecture vidéo
        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()
    
    def _play_loop(self):
        """Boucle de lecture vidéo"""
        frame_delay = 1.0 / self.fps if self.fps > 0 else 0.033
        
        while self.playing and not self._stop_flag:
            start_time = time.time()
            
            try:
                # Mettre à jour depuis le thread principal
                self.canvas.after(0, self._show_frame)
            except:
                break
            
            # Attendre pour maintenir le FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_delay - elapsed)
            time.sleep(sleep_time)
            
            # Vérifier si fin de vidéo
            if self.current_time >= self.duration - 0.1:
                self.playing = False
                self._stop_audio()
                break
    
    def _start_audio(self):
        """Démarre la lecture audio avec ffplay"""
        self._stop_audio()
        
        if not self.video_path:
            return
        
        with self._audio_lock:
            try:
                # ffplay avec démarrage à la position actuelle
                cmd = [
                    "ffplay", "-nodisp", "-autoexit",
                    "-ss", str(self.current_time),
                    "-i", str(self.video_path),
                    "-loglevel", "quiet"
                ]
                
                self._audio_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
            except Exception as e:
                logger.debug(f"Audio playback error: {e}")
    
    def _stop_audio(self):
        """Arrête la lecture audio"""
        with self._audio_lock:
            if self._audio_process:
                try:
                    self._audio_process.terminate()
                    self._audio_process.wait(timeout=0.5)
                except:
                    try:
                        self._audio_process.kill()
                    except:
                        pass
                self._audio_process = None
    
    def pause(self):
        """Met en pause"""
        self.playing = False
        self._stop_audio()
    
    def toggle(self):
        """Bascule lecture/pause"""
        if self.playing:
            self.pause()
        else:
            self.play()
    
    def seek(self, time_sec: float):
        """
        Seek à une position précise
        
        Args:
            time_sec: Position en secondes
        """
        if not self.cap:
            return
        
        was_playing = self.playing
        
        # Arrêter temporairement
        if was_playing:
            self.pause()
        
        # Calculer la frame
        frame_num = int(time_sec * self.fps)
        frame_num = max(0, min(frame_num, int(self.duration * self.fps)))
        
        # Seek
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        self.current_time = time_sec
        
        # Afficher la frame
        self._show_frame()
        
        # Reprendre si était en lecture
        if was_playing:
            self.play()
    
    def release(self):
        """Libère les ressources"""
        self._stop_flag = True
        self.playing = False
        
        self._stop_audio()
        
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.5)
        
        if self.cap:
            self.cap.release()
            self.cap = None
        
        self.video_path = None
        self.duration = 0
        self.current_time = 0
        self._photo_ref = None
