"""
Nettoyage automatique des fichiers temporaires.
Supprime les fichiers de plus de 24h dans le dossier temp_project/.
"""
import os
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_AGE_HOURS = 24


def clean_temp_folder(temp_dir: str = "temp_project"):
    """
    Supprime les fichiers temporaires de plus de 24h.
    Appelé au démarrage de l'application.
    """
    temp_path = Path(temp_dir)
    
    if not temp_path.exists():
        return
    
    now = time.time()
    max_age_sec = MAX_AGE_HOURS * 3600
    cleaned = 0
    freed_bytes = 0
    
    for file in temp_path.iterdir():
        if file.is_file():
            age = now - file.stat().st_mtime
            if age > max_age_sec:
                size = file.stat().st_size
                try:
                    file.unlink()
                    cleaned += 1
                    freed_bytes += size
                    logger.info(f"Supprimé: {file.name} ({size // 1024 // 1024}MB, {age / 3600:.0f}h)")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer {file.name}: {e}")
    
    if cleaned > 0:
        logger.info(f"Nettoyage: {cleaned} fichier(s) supprimé(s), {freed_bytes // 1024 // 1024}MB libéré(s)")
