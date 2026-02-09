"""
Gestionnaire de sous-titres ASS/SRT
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from ..utils.logger import logger


@dataclass
class Subtitle:
    """Représente un sous-titre individuel"""
    start: float
    end: float
    text: str
    words: List[Any] = field(default_factory=list)
    
    @property
    def duration(self) -> float:
        return self.end - self.start
    
    def to_dict(self) -> Dict:
        return {
            'start': self.start,
            'end': self.end,
            'text': self.text,
            'words': self.words
        }
    
    @classmethod
    def from_whisper_segment(cls, segment) -> 'Subtitle':
        """Crée un Subtitle depuis un segment Whisper"""
        return cls(
            start=getattr(segment, 'start', 0),
            end=getattr(segment, 'end', 0),
            text=getattr(segment, 'text', '').strip(),
            words=list(getattr(segment, 'words', []) or [])
        )


class SubtitleManager:
    """Gestion des sous-titres (génération, édition, export)"""
    
    def __init__(self, highlight_words: List[str] = None):
        self.highlight_words = highlight_words or [
            "MDR", "FOU", "QUOI", "INCROYABLE", "MAIS", "NON", "OUI"
        ]
        self.subtitles: List[Subtitle] = []
    
    def load_from_whisper(self, segments: List) -> List[Subtitle]:
        """Charge les sous-titres depuis des segments Whisper"""
        self.subtitles = [Subtitle.from_whisper_segment(seg) for seg in segments]
        logger.info(f"Loaded {len(self.subtitles)} subtitles from Whisper")
        return self.subtitles
    
    def update_text(self, index: int, new_text: str) -> bool:
        """Met à jour le texte d'un sous-titre"""
        if 0 <= index < len(self.subtitles):
            self.subtitles[index].text = new_text.strip()
            # Clear words since text was manually edited
            self.subtitles[index].words = []
            logger.debug(f"Updated subtitle {index}: {new_text[:30]}...")
            return True
        return False
    
    def shift_times(self, offset: float):
        """Décale tous les sous-titres d'un offset"""
        for sub in self.subtitles:
            sub.start = max(0, sub.start + offset)
            sub.end = max(sub.start, sub.end + offset)
        logger.info(f"Shifted subtitles by {offset}s")
    
    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        """Formate le temps pour ASS (H:MM:SS.CC)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02}:{s:02}.{cs:02}"
    
    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Formate le temps pour SRT (HH:MM:SS,mmm)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    
    def _apply_highlights(self, text: str) -> str:
        """Applique les highlights aux mots-clés"""
        for kw in self.highlight_words:
            pattern = re.compile(f"({re.escape(kw)})", re.IGNORECASE)
            text = pattern.sub(r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}", text)
        return text
    
    def generate_ass(self, output_path: Path, 
                     font_name: str = "Poppins",
                     font_size: int = 60) -> Path:
        """
        Génère un fichier ASS avec style TikTok/Reels
        """
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00E22B8A,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,350,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        lines = []
        for sub in self.subtitles:
            if not sub.text:
                continue
            
            start = self._format_ass_time(sub.start)
            end = self._format_ass_time(sub.end)
            
            # Si on a des mots avec timing, on peut faire du word-by-word
            if sub.words:
                # Grouper par 2-3 mots
                chunks = []
                current_chunk = []
                for w in sub.words:
                    current_chunk.append(w)
                    if len(current_chunk) >= 2:
                        chunks.append(current_chunk)
                        current_chunk = []
                if current_chunk:
                    chunks.append(current_chunk)
                
                for chunk in chunks:
                    chunk_start = self._format_ass_time(chunk[0].start)
                    chunk_end = self._format_ass_time(chunk[-1].end)
                    
                    text_parts = []
                    for w in chunk:
                        word_text = w.word.strip()
                        if any(kw in word_text.upper() for kw in self.highlight_words):
                            word_text = f"{{\\c&H00FFFF&}}{word_text}{{\\c&HFFFFFF&}}"
                        text_parts.append(word_text)
                    
                    text = " ".join(text_parts)
                    lines.append(f"Dialogue: 0,{chunk_start},{chunk_end},Default,,0,0,0,,{text}")
            else:
                # Texte simple avec highlights
                text = self._apply_highlights(sub.text)
                lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write(header)
            f.write("\n".join(lines))
        
        logger.info(f"Generated ASS: {output_path}")
        return output_path
    
    def generate_srt(self, output_path: Path) -> Path:
        """Génère un fichier SRT"""
        lines = []
        for i, sub in enumerate(self.subtitles, 1):
            if not sub.text:
                continue
            
            start = self._format_srt_time(sub.start)
            end = self._format_srt_time(sub.end)
            
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(sub.text)
            lines.append("")
        
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info(f"Generated SRT: {output_path}")
        return output_path
