"""
Wrapper Whisper pour la transcription
Gère le fallback CPU automatique si GPU échoue
"""
from pathlib import Path
from typing import List, Optional
import threading

from ..utils.logger import logger


class Transcriber:
    """Transcription audio avec Whisper"""
    
    def __init__(self, model_size: str = "base", language: str = "fr"):
        self.model_size = model_size
        self.language = language
        self._model = None
        self._model_lock = threading.Lock()
    
    def _load_model(self, force_cpu: bool = False):
        """Charge le modèle Whisper (lazy loading)"""
        if self._model is not None and not force_cpu:
            return
        
        with self._model_lock:
            try:
                from faster_whisper import WhisperModel
                
                if force_cpu:
                    logger.info("Loading Whisper (CPU mode)...")
                    self._model = WhisperModel(
                        self.model_size, 
                        device="cpu", 
                        compute_type="int8"
                    )
                else:
                    logger.info("Loading Whisper (GPU mode)...")
                    try:
                        self._model = WhisperModel(
                            self.model_size, 
                            device="cuda", 
                            compute_type="float16"
                        )
                    except Exception as e:
                        logger.warning(f"GPU failed ({e}), falling back to CPU...")
                        self._model = WhisperModel(
                            self.model_size, 
                            device="cpu", 
                            compute_type="int8"
                        )
                        
            except ImportError:
                logger.error("faster-whisper not installed!")
                raise
    
    def transcribe(self, audio_path: Path, 
                   word_timestamps: bool = True) -> List:
        """
        Transcrit un fichier audio
        
        Args:
            audio_path: Chemin vers le fichier audio/vidéo
            word_timestamps: Obtenir le timing par mot
            
        Returns:
            Liste de segments Whisper
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return []
        
        # Charge le modèle si nécessaire
        self._load_model()
        
        try:
            logger.info(f"Transcribing: {audio_path.name}...")
            
            segments, info = self._model.transcribe(
                str(audio_path),
                word_timestamps=word_timestamps,
                language=self.language
            )
            
            # Convertir le générateur en liste
            result = list(segments)
            logger.info(f"Transcribed {len(result)} segments")
            
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Si erreur GPU (DLL manquante), fallback CPU
            if any(kw in error_msg for kw in ["cublas", "dll", "library", "cuda"]):
                logger.warning(f"GPU runtime error: {e}")
                logger.info("Retrying with CPU...")
                
                self._model = None
                self._load_model(force_cpu=True)
                
                segments, info = self._model.transcribe(
                    str(audio_path),
                    word_timestamps=word_timestamps,
                    language=self.language
                )
                
                return list(segments)
            else:
                logger.error(f"Transcription failed: {e}")
                raise
    
    def unload_model(self):
        """Libère le modèle de la mémoire"""
        with self._model_lock:
            self._model = None
            logger.info("Whisper model unloaded")
