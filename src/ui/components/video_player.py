"""
Lecteur vidéo Haute Précision (Basé sur ffpyplayer)
Remplace l'implémentation instable cv2 + ffplay
"""
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
import threading
import time
import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    from PIL import Image, ImageTk
    # IMPORT CRITIQUE : ffpyplayer gère la sync A/V
    from ffpyplayer.player import MediaPlayer 
    FFPY_AVAILABLE = True
except ImportError:
    FFPY_AVAILABLE = False
    print("ERREUR: Installez ffpyplayer (pip install ffpyplayer) pour la sync audio/vidéo.")


class VideoPlayer:
    """
    Lecteur vidéo synchrone utilisant ffpyplayer pour le décodage A/V.
    Respecte l'interface originale pour VibeSlicer.
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
        
        # Gestion Threading UI
        self._stop_flag: bool = False
        self._play_thread: Optional[threading.Thread] = None
        self._photo_ref = None  # Anti-Garbage Collection
    
    def load(self, video_path: Path) -> bool:
        """Charge une vidéo et prépare le lecteur"""
        if not FFPY_AVAILABLE:
            logger.error("ffpyplayer manquant")
            return False
        
        self.release()
        self.video_path = Path(video_path)
        
        try:
            # Création du lecteur FFmpeg (ffpyplayer)
            # ff_opts={'paused': True} permet de charger sans lancer le son tout de suite
            # loop=0 : Pas de boucle automatique
            self.player = MediaPlayer(
                str(self.video_path),
                ff_opts={'paused': True, 'loop': 0} 
            )
            
            # Attente active des métadonnées (durée, taille)
            max_retries = 10
            while max_retries > 0:
                meta = self.player.get_metadata()
                if meta and 'duration' in meta:
                    self.duration = meta['duration']
                    break
                time.sleep(0.1)
                max_retries -= 1
            
            logger.info(f"Vidéo chargée: {self.video_path.name} ({self.duration:.2f}s)")
            
            # Afficher la première frame (seek à 0 pour forcer le décodage)
            self.seek(0)
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur chargement vidéo: {e}")
            return False

    def play(self):
        """Démarre la lecture"""
        if not self.player:
            return
            
        self.player.set_pause(False)
        
        # Si le thread n'existe pas ou est mort, on le lance
        if self._play_thread is None or not self._play_thread.is_alive():
            self._stop_flag = False
            self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
            self._play_thread.start()

    def pause(self):
        """Met en pause"""
        if self.player:
            self.player.set_pause(True)
        
    def toggle(self):
        """Bascule lecture/pause"""
        if not self.player:
            return
        
        # get_pause() renvoie True si c'est en pause
        is_paused = self.player.get_pause()
        if is_paused:
            self.play()
        else:
            self.pause()

    def seek(self, time_sec: float):
        """Saut temporel précis"""
        if not self.player:
            return
            
        # relative=False signifie "temps absolu"
        # accurate=True force le décodage précis (plus lent mais exact)
        self.player.seek(time_sec, relative=False, accurate=True)
        self.current_time = time_sec
        
        # On force la lecture d'une frame pour mettre à jour l'affichage immédiatement
        time.sleep(0.05)
        self._display_current_frame()

    def is_playing(self) -> bool:
        """Vérifie si le lecteur est en lecture"""
        if self.player:
            return not self.player.get_pause()
        return False

    def get_time(self) -> float:
        """Retourne la position actuelle en secondes"""
        return self.current_time

    def get_duration(self) -> float:
        """Retourne la durée totale en secondes"""
        return self.duration

    def _play_loop(self):
        """Boucle principale de synchronisation"""
        while not self._stop_flag:
            if not self.player:
                break
                
            # get_frame() retourne (frame, val)
            # val != 'eof' tant qu'il y a de la vidéo
            # val est le temps à attendre avant d'afficher cette frame (SYNC !)
            frame, val = self.player.get_frame()
            
            if val == 'eof':
                self.pause()
                break
            
            if frame is None:
                # Pas de nouvelle frame dispo, on dort un peu et on réessaie
                time.sleep(0.01)
                continue
            
            # Si val > 0, on est en avance, il faut attendre
            # C'est ça qui fait la sync audio/vidéo
            if val > 0:
                time.sleep(val)
                
            # Traitement de l'image
            img_data, size = frame
            
            # Conversion pour PIL/Tkinter
            image = Image.frombytes("RGB", size, bytes(img_data))
            
            # Mise à jour UI
            try:
                self._update_ui_image(image)
                
                # Mise à jour du temps courant
                self.current_time = self.player.get_pts()
                if self.on_frame:
                    self.on_frame(self.current_time)
            except Exception as e:
                print(f"Erreur UI: {e}")
                break

    def _display_current_frame(self):
        """Force l'affichage de la frame courante (utile pour le seek/pause)"""
        if not self.player:
            return
        frame, val = self.player.get_frame(show=False)
        if frame:
            img_data, size = frame
            image = Image.frombytes("RGB", size, bytes(img_data))
            self._update_ui_image(image)

    def _update_ui_image(self, image: Image):
        """Redimensionne et affiche l'image sur le Canvas"""
        if not self.canvas.winfo_exists():
            return

        cw = self.canvas.winfo_width() or 400
        ch = self.canvas.winfo_height() or 300
        
        # Ratio aspect
        w, h = image.size
        scale = min(cw / w, ch / h)
        new_w, new_h = int(w * scale), int(h * scale)
        
        if new_w > 0 and new_h > 0:
            image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
        self._photo_ref = ImageTk.PhotoImage(image)
        
        self.canvas.delete("all")
        # Centrage
        x = cw // 2
        y = ch // 2
        self.canvas.create_image(x, y, image=self._photo_ref)

    def release(self):
        """Nettoyage"""
        self._stop_flag = True
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.5)
            
        if self.player:
            self.player.close_player()
            self.player = None
            
        self.video_path = None
        self._photo_ref = None
