"""
Lecteur Vidéo VLC - Synchronisation A/V native
Remplace OpenCV+ffplay qui ne peut pas synchroniser correctement
"""
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional
import threading
import time
import sys
import os

# Ajouter le chemin VLC si nécessaire (Windows)
if sys.platform == 'win32':
    # Chemins courants pour VLC sur Windows
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
        os.path.expanduser(r"~\AppData\Local\Programs\VideoLAN\VLC")
    ]
    for path in vlc_paths:
        if os.path.exists(path):
            os.add_dll_directory(path)
            break

try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError) as e:
    print(f"VLC not available: {e}")
    VLC_AVAILABLE = False


class VLCPlayer:
    """
    Lecteur vidéo utilisant libVLC
    
    Avantages vs OpenCV+ffplay:
    - Synchronisation A/V native et précise
    - Seek instantané sans glitch audio
    - Gestion des codecs par VLC
    - Pas de processus séparé à gérer
    """
    
    def __init__(self, parent_frame: tk.Frame, on_time_update: Callable = None):
        """
        Args:
            parent_frame: Frame Tkinter où intégrer le lecteur
            on_time_update: Callback appelé à chaque mise à jour du temps (ms)
        """
        self.parent = parent_frame
        self.on_time_update = on_time_update
        
        self.video_path: Optional[Path] = None
        self.duration: float = 0  # En secondes
        self._update_job = None
        
        if not VLC_AVAILABLE:
            raise RuntimeError("VLC n'est pas installé. Installez VLC 64-bit depuis videolan.org")
        
        # Créer l'instance VLC avec options optimisées
        self.instance = vlc.Instance([
            '--no-xlib',           # Pas de X11 (Windows)
            '--quiet',             # Moins de logs
            '--no-video-title-show',  # Pas de titre sur la vidéo
        ])
        
        self.player = self.instance.media_player_new()
        
        # Intégrer dans le frame Tkinter
        self._setup_video_frame()
        
        # État
        self.is_loaded = False
    
    def _setup_video_frame(self):
        """Configure le frame pour afficher la vidéo"""
        # Créer un canvas noir pour le fond
        self.video_frame = tk.Frame(self.parent, bg='black')
        self.video_frame.pack(fill='both', expand=True)
        
        # Obtenir le handle de fenêtre Windows (HWND)
        self.video_frame.update_idletasks()
        
        if sys.platform == 'win32':
            self.player.set_hwnd(self.video_frame.winfo_id())
        elif sys.platform == 'darwin':  # macOS
            self.player.set_nsobject(self.video_frame.winfo_id())
        else:  # Linux
            self.player.set_xwindow(self.video_frame.winfo_id())
    
    def load(self, video_path: Path) -> bool:
        """
        Charge une vidéo
        
        Returns:
            True si chargement réussi
        """
        self.video_path = Path(video_path)
        
        if not self.video_path.exists():
            print(f"Video not found: {video_path}")
            return False
        
        try:
            # Créer le media
            media = self.instance.media_new(str(self.video_path))
            self.player.set_media(media)
            
            # Parser pour obtenir la durée (async)
            media.parse_with_options(vlc.MediaParseFlag.local, 0)
            
            # Attendre le parsing (max 2 sec)
            for _ in range(20):
                if media.get_parsed_status() == vlc.MediaParsedStatus.done:
                    break
                time.sleep(0.1)
            
            # Obtenir la durée
            self.duration = media.get_duration() / 1000.0  # ms -> sec
            
            # Afficher la première frame (play puis pause immédiat)
            self.player.play()
            time.sleep(0.1)
            self.player.pause()
            
            self.is_loaded = True
            self._start_time_updates()
            
            return True
            
        except Exception as e:
            print(f"Error loading video: {e}")
            return False
    
    def _start_time_updates(self):
        """Démarre les mises à jour périodiques du temps"""
        self._stop_time_updates()
        self._update_loop()
    
    def _stop_time_updates(self):
        """Arrête les mises à jour"""
        if self._update_job:
            self.parent.after_cancel(self._update_job)
            self._update_job = None
    
    def _update_loop(self):
        """Boucle de mise à jour du temps"""
        if self.is_loaded and self.on_time_update:
            current_time = self.player.get_time() / 1000.0  # ms -> sec
            if current_time >= 0:
                self.on_time_update(current_time)
        
        # Prochain update dans 100ms
        self._update_job = self.parent.after(100, self._update_loop)
    
    def play(self):
        """Démarre la lecture"""
        if self.is_loaded:
            self.player.play()
    
    def pause(self):
        """Met en pause"""
        if self.is_loaded:
            self.player.pause()
    
    def toggle(self):
        """Bascule lecture/pause"""
        if self.is_loaded:
            if self.player.is_playing():
                self.pause()
            else:
                self.play()
    
    def is_playing(self) -> bool:
        """Retourne True si en lecture"""
        return self.player.is_playing() == 1
    
    def seek(self, time_sec: float):
        """
        Seek à une position (en secondes)
        VLC gère le seek de manière native et synchronisée
        """
        if self.is_loaded:
            time_ms = int(time_sec * 1000)
            self.player.set_time(time_ms)
    
    def get_time(self) -> float:
        """Retourne le temps actuel en secondes"""
        if self.is_loaded:
            return self.player.get_time() / 1000.0
        return 0
    
    def get_duration(self) -> float:
        """Retourne la durée totale en secondes"""
        return self.duration
    
    def set_volume(self, volume: int):
        """
        Définit le volume (0-100)
        """
        self.player.audio_set_volume(max(0, min(100, volume)))
    
    def release(self):
        """Libère les ressources"""
        self._stop_time_updates()
        if self.player:
            self.player.stop()
            self.player.release()
        if self.instance:
            self.instance.release()


class FallbackPlayer:
    """
    Lecteur de secours si VLC n'est pas disponible
    Affiche juste un message et utilise ffplay en arrière-plan
    """
    
    def __init__(self, parent_frame: tk.Frame, on_time_update: Callable = None):
        self.parent = parent_frame
        self.on_time_update = on_time_update
        self.is_loaded = False
        self.duration = 0
        self.video_path = None
        
        # Message d'erreur
        label = tk.Label(
            parent_frame,
            text="⚠️ VLC non installé\nInstallez VLC 64-bit depuis videolan.org",
            bg='black',
            fg='white',
            font=('Segoe UI', 12)
        )
        label.pack(expand=True)
    
    def load(self, video_path): return False
    def play(self): pass
    def pause(self): pass
    def toggle(self): pass
    def seek(self, t): pass
    def is_playing(self): return False
    def get_time(self): return 0
    def get_duration(self): return 0
    def set_volume(self, v): pass
    def release(self): pass


def create_video_player(parent_frame: tk.Frame, on_time_update: Callable = None):
    """
    Factory function pour créer le bon type de lecteur
    """
    if VLC_AVAILABLE:
        try:
            return VLCPlayer(parent_frame, on_time_update)
        except Exception as e:
            print(f"VLC init failed: {e}")
    
    return FallbackPlayer(parent_frame, on_time_update)
