
import tkinter as tk
import sys
import os
import platform
import time
from typing import Callable, Optional
from pathlib import Path

# Tentative d'import de vlc
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    print("VLC non disponible : Module python-vlc manquant.")

class VLCPlayer:
    """
    Lecteur vidéo basé sur python-vlc pour Tkinter.
    Gère l'affichage dans une Frame via le HWND (Windows) ou XID (Linux).
    """
    def __init__(self, parent_container: tk.Widget, on_time_update: Callable[[float], None] = None):
        self.parent = parent_container
        self.on_time_update = on_time_update
        self.instance = None
        self.player = None
        self.is_loaded = False
        self._timer_id = None
        
        if not VLC_AVAILABLE:
            print("Erreur: VLC Player initialisé sans le module vlc.")
            return

        # 1. Initialisation de l'instance VLC
        # Options : --no-xlib (Linux), --quiet (Log), --no-video-title (Overlay)
        args = ["--no-xlib", "--quiet", "--no-video-title-show"]
        try:
            self.instance = vlc.Instance(args)
            self.player = self.instance.media_player_new()
        except Exception as e:
            print(f"Erreur init VLC: {e}")
            self.player = None
            return

        # 2. Création de la zone d'affichage (Canvas noir)
        # On utilise un Canvas ou Frame Tkinter qui servira de "fenêtre" pour VLC
        self.video_frame = tk.Frame(self.parent, bg="black")
        self.video_frame.pack(fill="both", expand=True)
        
        # Astuce : Forcer la création de la fenêtre OS pour récupérer son ID
        self.video_frame.update_idletasks()
        
        # 3. Liaison VLC <-> Fenêtre OS
        self._attach_window()
        
    def _attach_window(self):
        """Attache le lecteur VLC à la fenêtre Tkinter via son ID système"""
        if not self.player: return
        
        window_id = self.video_frame.winfo_id()
        system = platform.system()
        
        if system == "Windows":
            self.player.set_hwnd(window_id)
        elif system == "Darwin": # macOS
            # Sur macOS, c'est plus complexe, souvent besoin d'un NSView
            # Pour l'instant, on tente le standard, mais ça peut nécessiter des tweaks
            try:
                self.player.set_nsobject(window_id)
            except:
                pass
        else: # Linux / X11
            self.player.set_xwindow(window_id)

    def load(self, video_path: Path):
        """Charge une vidéo"""
        if not self.instance or not video_path.exists():
            return False

        # Création du média
        media = self.instance.media_new(str(video_path))
        self.player.set_media(media)
        
        # Parse pour récupérer la durée (Asynchrone normalement, mais on force un peu)
        media.parse() 
        self.is_loaded = True
        
        # Lancer le timer de suivi du temps
        self._start_timer()
        return True

    def play(self):
        if self.player:
            self.player.play()
            
    def pause(self):
        if self.player:
            self.player.pause()
            
    def toggle(self):
        if self.player:
            if self.player.is_playing():
                self.pause()
            else:
                self.play()

    def stop(self):
        if self.player:
            self.player.stop()
            self._stop_timer()

    def seek(self, time_sec: float):
        """Déplace la lecture à time_sec (secondes)"""
        if self.player and self.is_loaded:
            # VLC utilise des millisecondes
            ms = int(time_sec * 1000)
            self.player.set_time(ms)

    def get_time(self) -> float:
        """Retourne la position actuelle en secondes"""
        if self.player:
            return self.player.get_time() / 1000.0
        return 0.0
        
    def get_duration(self) -> float:
        """Retourne la durée totale en secondes"""
        if self.player and self.player.get_media():
            return self.player.get_media().get_duration() / 1000.0
        return 0.0

    def is_playing(self) -> bool:
        return self.player.is_playing() == 1 if self.player else False

    def _start_timer(self):
        self._stop_timer()
        self._update_time()

    def _stop_timer(self):
        if self._timer_id:
            try:
                self.parent.after_cancel(self._timer_id)
            except:
                pass
            self._timer_id = None

    def _update_time(self):
        """Boucle de mise à jour du temps pour l'UI"""
        if self.player and self.is_playing():
            t = self.get_time()
            if self.on_time_update:
                self.on_time_update(t)
        
        # Rappel dans 100ms (10fps pour l'UI, suffisant)
        # On utilise une référence à self._update_time qui est une méthode bound
        # donc pas de lambda pour éviter les soucis de référence
        self._timer_id = self.parent.after(100, self._update_time)

    def release(self):
        """Libère les ressources VLC proprement"""
        self._stop_timer()
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()
