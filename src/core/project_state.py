"""
Project State - Données centralisées du projet
Pattern MVC : Cette classe contient UNIQUEMENT les données, pas de logique d'affichage
"""
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from pathlib import Path
from enum import Enum
import threading


class AppStep(Enum):
    """Étapes de l'application"""
    SELECT = 0
    ANALYZE = 1
    SUBTITLES = 2
    EXPORT = 3


@dataclass
class Segment:
    """Segment de vidéo (parole ou silence)"""
    start: float
    end: float
    segment_type: str  # 'speech' ou 'silence'
    keep: bool = True
    
    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Subtitle:
    """Sous-titre avec timing"""
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)
    
    @property
    def duration(self) -> float:
        return self.end - self.start


class EventBus:
    """
    Bus d'événements simple (Observer Pattern)
    Permet aux composants de communiquer sans couplage direct
    """
    
    def __init__(self):
        self._listeners: dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
    
    def subscribe(self, event_type: str, callback: Callable):
        """S'abonner à un type d'événement"""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Se désabonner"""
        with self._lock:
            if event_type in self._listeners:
                self._listeners[event_type].remove(callback)
    
    def emit(self, event_type: str, data=None):
        """Émettre un événement"""
        with self._lock:
            listeners = self._listeners.get(event_type, []).copy()
        
        for callback in listeners:
            try:
                callback(data)
            except Exception as e:
                print(f"Event handler error: {e}")


# Types d'événements
class Events:
    """Constantes pour les types d'événements"""
    TIME_UPDATED = "time_updated"           # Temps de lecture changé
    SEGMENT_TOGGLED = "segment_toggled"     # Segment keep/cut changé
    SUBTITLE_UPDATED = "subtitle_updated"   # Sous-titre modifié
    STEP_CHANGED = "step_changed"           # Étape changée
    VIDEO_LOADED = "video_loaded"           # Vidéo chargée
    ANALYSIS_COMPLETE = "analysis_complete" # Analyse terminée
    EXPORT_PROGRESS = "export_progress"     # Progression export
    LOG_MESSAGE = "log_message"             # Message de log


class ProjectState:
    """
    État centralisé du projet
    Contient toutes les données, notifie les changements via EventBus
    """
    
    def __init__(self):
        self.events = EventBus()
        
        # Fichiers
        self.source_video: Optional[Path] = None
        self.clean_video: Optional[Path] = None
        self.cut_video: Optional[Path] = None
        self.proxy_video: Optional[Path] = None  # Version basse résolution
        
        # Métadonnées
        self.duration: float = 0
        self.fps: float = 30
        self.width: int = 0
        self.height: int = 0
        
        # Données de travail
        self.segments: List[Segment] = []
        self.subtitles: List[Subtitle] = []
        
        # État
        self.current_step: AppStep = AppStep.SELECT
        self.current_time: float = 0
        self.is_playing: bool = False
        
        # Export
        self.music_path: Optional[Path] = None
    
    def set_source_video(self, path: Path):
        """Définit la vidéo source"""
        self.source_video = Path(path)
        self.events.emit(Events.VIDEO_LOADED, self.source_video)
    
    def set_segments(self, segments: List[Segment]):
        """Définit les segments"""
        self.segments = segments
        self.events.emit(Events.ANALYSIS_COMPLETE, len(segments))
    
    def toggle_segment(self, index: int):
        """Toggle keep/cut d'un segment"""
        if 0 <= index < len(self.segments):
            self.segments[index].keep = not self.segments[index].keep
            self.events.emit(Events.SEGMENT_TOGGLED, index)
    
    def set_subtitles(self, subtitles: List[Subtitle]):
        """Définit les sous-titres"""
        self.subtitles = subtitles
    
    def update_subtitle(self, index: int, new_text: str):
        """Met à jour le texte d'un sous-titre"""
        if 0 <= index < len(self.subtitles):
            self.subtitles[index].text = new_text.strip()
            self.subtitles[index].words = []  # Clear words car édité manuellement
            self.events.emit(Events.SUBTITLE_UPDATED, index)
    
    def set_time(self, time_sec: float):
        """Met à jour le temps courant"""
        self.current_time = time_sec
        self.events.emit(Events.TIME_UPDATED, time_sec)
    
    def set_step(self, step: AppStep):
        """Change l'étape"""
        self.current_step = step
        self.events.emit(Events.STEP_CHANGED, step)
    
    def log(self, message: str):
        """Émet un message de log"""
        self.events.emit(Events.LOG_MESSAGE, message)
    
    def get_keep_segments(self) -> List[tuple]:
        """Retourne les segments à garder comme tuples (start, end)"""
        return [(s.start, s.end) for s in self.segments if s.keep]
    
    def get_subtitles_as_dicts(self) -> List[dict]:
        """Retourne les sous-titres comme dictionnaires"""
        return [
            {
                'start': s.start,
                'end': s.end,
                'text': s.text,
                'words': s.words
            }
            for s in self.subtitles
        ]


# Instance globale
project_state = ProjectState()
