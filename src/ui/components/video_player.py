"""
Lecteur vidéo Haute Précision (Basé sur ffpyplayer)
Version : Thread-Safe & Low-Latency
"""
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
import threading
import time
import logging
import queue  # CRITIQUE pour la thread-safety

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageTk
    # ffpyplayer gère la sync A/V interne
    from ffpyplayer.player import MediaPlayer 
    FFPY_AVAILABLE = True
except ImportError:
    FFPY_AVAILABLE = False
    print("ERREUR: Installez ffpyplayer (pip install ffpyplayer)")

class VideoPlayer:
    """
    Lecteur vidéo synchrone et Thread-Safe.
    Utilise une Queue pour passer les frames du thread de décodage vers l'UI.
    """
    
    def __init__(self, canvas: tk.Canvas, on_frame_callback: Callable = None):
        self.canvas = canvas
        self.on_frame = on_frame_callback
        
        # État interne
        self.player: Optional[MediaPlayer] = None
        self.video_path: Optional[Path] = None
        
        # Métadonnées
        self.duration: float = 0
        self.current_time: float = 0
        
        # Gestion Threading & Queue
        self._stop_flag: bool = False
        self._play_thread: Optional[threading.Thread] = None
        self._photo_ref = None
        
        # Queue de taille 1 : Si l'UI est lente, on écrase la vieille frame 
        # pour toujours afficher la plus récente (Drop Frame logic)
        self.frame_queue = queue.Queue(maxsize=1)
        
        # Démarrage de la boucle de consommation UI
        self._check_queue_loop()
    
    def _check_queue_loop(self):
        """
        Consomme la queue dans le MainThread pour mettre à jour l'UI.
        C'est la SEULE méthode qui a le droit de toucher au Canvas.
        """
        try:
            # On vide la queue pour ne traiter que la dernière image dispo
            # (Si l'ordi rame, on saute des images pour garder le son synchro)
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
            # Rappel dans 10ms (approx 100fps check rate)
            # Utilisation de .after() garantit qu'on reste dans le MainThread
            if not self._stop_flag:
                self.canvas.after(5, self._check_queue_loop)

    def load(self, video_path: Path) -> bool:
        """Charge une vidéo et prépare le lecteur"""
        if not FFPY_AVAILABLE:
            return False
        
        self.release()
        self.video_path = Path(video_path)
        
        try:
            # loop=0 important pour ne pas repartir au début à la fin
            self.player = MediaPlayer(
                str(self.video_path),
                ff_opts={'paused': True, 'loop': 0} 
            )
            
            # Attente métadonnées (avec timeout)
            timeout = 1.0
            start = time.time()
            while time.time() - start < timeout:
                meta = self.player.get_metadata()
                if meta and 'duration' in meta:
                    self.duration = meta['duration']
                    break
                time.sleep(0.05)
            
            logger.info(f"Vidéo chargée: {self.duration:.2f}s")
            
            # Afficher la première frame
            self.seek(0)
            return True
            
        except Exception as e:
            logger.error(f"Erreur chargement: {e}")
            return False

    def play(self):
        if not self.player: return
        self.player.set_pause(False)
        
        if self._play_thread is None or not self._play_thread.is_alive():
            self._stop_flag = False
            self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
            self._play_thread.start()

    def pause(self):
        if self.player:
            self.player.set_pause(True)
        
    def toggle(self):
        if not self.player: return
        if self.player.get_pause():
            self.play()
        else:
            self.pause()

    def seek(self, time_sec: float):
        if not self.player: return
        self.player.seek(time_sec, relative=False, accurate=True)
        self.current_time = time_sec
        # Petit délai pour laisser ffpyplayer décoder la frame cible
        time.sleep(0.05)
        self._display_current_frame_immediate()

    def is_playing(self) -> bool:
        return not self.player.get_pause() if self.player else False

    def get_time(self) -> float:
        return self.current_time

    def get_duration(self) -> float:
        return self.duration

    def _play_loop(self):
        """Thread secondaire : Décodage pur (Pas d'UI ici !)"""
        while not self._stop_flag:
            if not self.player: break
            
            frame, val = self.player.get_frame()
            
            if val == 'eof':
                self.pause()
                break
            
            if frame is None:
                time.sleep(0.01)
                continue
            
            # val = temps à attendre pour la sync audio
            if val > 0:
                time.sleep(val)
                
            # Extraction des données brutes
            img_data, size = frame.get_byte_buffer()
            
            # Conversion PIL (Rapide)
            image = Image.frombytes("RGB", size, bytes(img_data))
            pts = self.player.get_pts()
            
            # On pousse dans la queue (Thread-Safe)
            # Si la queue est pleine (UI lente), on ne bloque pas le décodage audio
            if not self.frame_queue.full():
                self.frame_queue.put((image, pts))
            
            # Si on a droppé la frame précédente car queue pleine, 
            # ce n'est pas grave, ffpyplayer garde le rythme audio.

    def _display_current_frame_immediate(self):
        """Force l'affichage pour le Seek (appel direct, bypass queue pour réactivité)"""
        # Note: Cette méthode est généralement appelée par le MainThread (via click bouton),
        # donc on peut toucher à l'UI.
        if not self.player: return
        frame, val = self.player.get_frame(show=False)
        if frame:
            img_data, size = frame.get_byte_buffer()
            image = Image.frombytes("RGB", size, bytes(img_data))
            self._update_ui_image(image)

    def _update_ui_image(self, image: Image):
        """Mise à jour réelle du Canvas (MainThread uniquement)"""
        if not self.canvas.winfo_exists(): return

        # Dimensions actuelles du canvas
        cw = self.canvas.winfo_width() or 400
        ch = self.canvas.winfo_height() or 300
        
        # Optimisation : On ne redimensionne que si nécessaire
        if cw > 1 and ch > 1:
            w, h = image.size
            scale = min(cw / w, ch / h)
            new_w, new_h = int(w * scale), int(h * scale)
            
            # CRITIQUE : BILINEAR pour la fluidité (LANCZOS est trop lent pour 30fps)
            if new_w != w or new_h != h:
                image = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
            
        self._photo_ref = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        # Centrage
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo_ref)

    def release(self):
        self._stop_flag = True
        
        # On vide la queue pour éviter des références fantômes
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.2)
            
        if self.player:
            self.player.close_player()
            self.player = None
            
        self.video_path = None
        self._photo_ref = None
