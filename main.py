#!/usr/bin/env python3
"""
VibeSlicer Studio v8.0
Automatisation de montage vidéo TikTok/Reels

Point d'entrée principal
"""
import sys
from pathlib import Path

# Ajouter le dossier parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

from src.ui.main_window import MainWindow
from src.utils.logger import logger


def main():
    """Point d'entrée principal"""
    print("=" * 50)
    print("  VibeSlicer Studio v8.0")
    print("  Automatisation Montage Video TikTok/Reels")
    print("=" * 50)
    print()
    
    try:
        app = MainWindow()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
