"""
Configuration centralisée pour VibeSlicer Studio
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class AppConfig:
    """Configuration principale de l'application"""
    
    # Chemins
    base_dir: Path = field(default_factory=lambda: Path.cwd())
    input_dir: Path = field(default_factory=lambda: Path.cwd() / "input")
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "output")
    temp_dir: Path = field(default_factory=lambda: Path.cwd() / "temp")
    assets_dir: Path = field(default_factory=lambda: Path.cwd() / "assets")
    music_dir: Path = field(default_factory=lambda: Path.cwd() / "assets" / "music")
    
    # Whisper
    whisper_model: str = "base"
    whisper_language: str = "fr"
    
    # Audio
    silence_threshold_db: int = -40
    min_silence_duration: float = 0.5
    background_music_volume: float = 0.1
    
    # Video
    target_fps: int = 30
    video_preset: str = "medium"
    video_crf: int = 23
    
    # Sous-titres - mots à mettre en surbrillance
    highlight_words: List[str] = field(default_factory=lambda: [
        "MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI", "WOW"
    ])
    
    def __post_init__(self):
        """Crée les dossiers nécessaires"""
        for d in [self.input_dir, self.output_dir, self.temp_dir, self.assets_dir]:
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class UIConfig:
    """Configuration de l'interface utilisateur"""
    
    # Couleurs
    BG: str = "#0f0f0f"
    CARD: str = "#1a1a1a"
    ACCENT: str = "#E22B8A"
    SUCCESS: str = "#22c55e"
    ERROR: str = "#ef4444"
    TEXT: str = "#ffffff"
    TEXT_MUTED: str = "#888888"
    
    # Timeline
    SPEECH_COLOR: str = "#22c55e"
    SPEECH_COLOR_DIM: str = "#0f3320"
    SILENCE_COLOR: str = "#f97316"
    SILENCE_COLOR_DIM: str = "#3d1c0a"
    
    # Fenêtre
    window_title: str = "VibeSlicer Studio v8.0"
    window_geometry: str = "1500x900"
    window_min_size: tuple = (1300, 800)


# Instances globales
app_config = AppConfig()
ui_config = UIConfig()
