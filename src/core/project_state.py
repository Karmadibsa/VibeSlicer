from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
import enum
import logging

logger = logging.getLogger(__name__)

class EventType(enum.Enum):
    VIDEO_LOADED = "VIDEO_LOADED"
    PROXY_READY = "PROXY_READY"
    SEGMENTS_CHANGED = "SEGMENTS_CHANGED"
    SUBTITLES_CHANGED = "SUBTITLES_CHANGED"
    TIME_UPDATED = "TIME_UPDATED"
    PLAYBACK_STATE_CHANGED = "PLAYBACK_STATE_CHANGED"
    SEEK_REQUESTED = "SEEK_REQUESTED"
    EXPORT_REQUESTED = "EXPORT_REQUESTED"
    
@dataclass
class Segment:
    """Structure de données immuable pour un segment"""
    start: float
    end: float
    segment_type: str = "speech"  # speech | silence
    keep: bool = True
    
    @property
    def duration(self):
        return self.end - self.start

@dataclass
class Subtitle:
    """Structure de données pour un sous-titre"""
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)

class ProjectState:
    """
    SINGLE SOURCE OF TRUTH
    Contient toutes les données du projet.
    L'UI ne stocke RIEN. Elle ne fait qu'afficher ProjectState.
    """
    
    def __init__(self):
        # --- Données ---
        self.source_video: Optional[Path] = None
        self.proxy_video: Optional[Path] = None
        self.project_dir: Path = Path("temp_project")
        
        # Données de montage
        self.segments: List[Segment] = []
        self.subtitles: List[Subtitle] = []
        
        # État lecteur
        self.current_time: float = 0.0
        self.is_playing: bool = False
        self.duration: float = 0.0
        
        # Système d'événements (Observer Pattern)
        self._listeners: Dict[EventType, List[Callable]] = {}

    # --- Gestion des Événements ---
    
    def subscribe(self, event_type: EventType, callback: Callable):
        """S'abonner à un changement d'état"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
        
    def _notify(self, event_type: EventType, data: Any = None):
        """Notifier les abonnés (UI)"""
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in event listener {event_type}: {e}")

    # --- Actions (Seules méthodes autorisées à modifier l'état) ---

    def load_video(self, path: Path):
        """Charge une nouvelle vidéo source"""
        self.source_video = Path(path)
        self.proxy_video = None # Reset proxy
        self.segments = []
        self.subtitles = []
        self.current_time = 0.0
        self._notify(EventType.VIDEO_LOADED, self.source_video)
        
    def set_proxy(self, path: Path):
        """Définit le fichier proxy (basse résolution)"""
        self.proxy_video = Path(path)
        self._notify(EventType.PROXY_READY, self.proxy_video)
        
    def update_segments(self, segments: List[Segment]):
        """Met à jour la liste des segments"""
        self.segments = segments
        self._notify(EventType.SEGMENTS_CHANGED, self.segments)
        
    def update_subtitles(self, subtitles: List[Subtitle]):
        """Met à jour les sous-titres"""
        self.subtitles = subtitles
        self._notify(EventType.SUBTITLES_CHANGED, self.subtitles)
        
    def set_time(self, time: float):
        """Met à jour la position de lecture"""
        self.current_time = time
        self._notify(EventType.TIME_UPDATED, self.current_time)
        
    def set_playback_state(self, is_playing: bool):
        """Met à jour l'état lecture/pause"""
        self.is_playing = is_playing
        self._notify(EventType.PLAYBACK_STATE_CHANGED, self.is_playing)
        
    def request_seek(self, time: float):
        """Demande un saut temporel (UI -> Player)"""
        self._notify(EventType.SEEK_REQUESTED, time)
        
    def request_export(self, output_path: Path):
        """Demande d'export (UI -> Processor)"""
        self._notify(EventType.EXPORT_REQUESTED, output_path)
