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
    start: float
    end: float
    segment_type: str = "speech"
    keep: bool = True
    
    @property
    def duration(self):
        return self.end - self.start

@dataclass
class Subtitle:
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)

class ProjectState:
    def __init__(self):
        self.source_video: Optional[Path] = None
        self.proxy_video: Optional[Path] = None
        self.project_dir: Path = Path("temp_project")
        self.segments: List[Segment] = []
        self.subtitles: List[Subtitle] = []
        self.current_time: float = 0.0
        self.is_playing: bool = False
        self.duration: float = 0.0
        self._listeners: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, callback: Callable):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
        
    def _notify(self, event_type: EventType, data: Any = None):
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in event listener {event_type}: {e}")

    def load_video(self, path: Path):
        self.source_video = Path(path)
        self.proxy_video = None
        self.segments = []
        self.subtitles = []
        self.current_time = 0.0
        self._notify(EventType.VIDEO_LOADED, self.source_video)
        
    def set_proxy(self, path: Path):
        self.proxy_video = Path(path)
        self._notify(EventType.PROXY_READY, self.proxy_video)
        
    def update_segments(self, segments: List[Segment]):
        self.segments = segments
        self._notify(EventType.SEGMENTS_CHANGED, self.segments)
        
    def update_subtitles(self, subtitles: List[Subtitle]):
        self.subtitles = subtitles
        self._notify(EventType.SUBTITLES_CHANGED, self.subtitles)
        
    def set_time(self, time: float):
        self.current_time = time
        self._notify(EventType.TIME_UPDATED, self.current_time)
        
    def set_playback_state(self, is_playing: bool):
        self.is_playing = is_playing
        self._notify(EventType.PLAYBACK_STATE_CHANGED, self.is_playing)
        
    def request_seek(self, time: float):
        self._notify(EventType.SEEK_REQUESTED, time)
        
    def request_export(self, output_path: Path):
        self._notify(EventType.EXPORT_REQUESTED, output_path)
