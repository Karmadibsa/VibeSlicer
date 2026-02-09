import sys
import os
import customtkinter as ctk

# Ajouter le chemin courant au path pour les imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.state import ProjectState
from src.core.video_processor import VideoProcessor
from src.ui.main_window import MainWindow

def main():
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    print("🚀 VibeSlicer Studio v8.0 (Refactored) Starting...")
    
    # 1. Créer le State Unique
    state = ProjectState()
    
    # 2. Démarrer le processeur de fond (Proxy, Export)
    processor = VideoProcessor(state)
    
    # 3. Créer l'UI et lui injecter le state
    app = MainWindow(state)
    
    # 3. Lancer la boucle principale
    app.mainloop()

if __name__ == "__main__":
    main()
