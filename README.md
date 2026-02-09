# 🎬 VibeSlicer Studio v3.0 (Bulletproof Engine)

VibeSlicer est un outil professionnel de découpe vidéo automatique ("Jumpcut") optimisé pour les créateurs de contenu (Twitch VODs, YouTube).

## 🚀 Nouveautés v3.0 (Architecture "Bulletproof")

Cette version est une réécriture complète du moteur vidéo pour résoudre définitivement les problèmes de synchronisation audio/vidéo (Drift) liés aux enregistrements OBS en frame rate variable (VFR).

### Fonctionnalités Clés :
*   **🛡️ Sanitization-First Architecture** : Toute vidéo entrante est immédiatement convertie en **CFR 30fps / Audio 44.1kHz** avant analyse. Cela garantit une précision au millième de seconde pour la découpe, peu importe la source (OBS, iPhone, etc.).
*   **⚡ Native FFmpeg Silence Detection** : Abandon de pydub (lent) au profit du filtre `silencedetect` de FFmpeg (10x plus rapide).
*   **📝 Sous-titres .ASS Robustes** : Utilisation du format Advanced Substation Alpha (.ass) pour un positionnement et un style parfaits. Finis les problèmes de police introuvable ou de chemins Windows cassés.
*   **🔊 Audio Broadcast Standard** : Normalisation automatique via `loudnorm` (I=-16 LUFS) pour un son professionnel.

## 🛠️ Installation

1.  **Pré-requis** :
    *   Python 3.10+
    *   FFmpeg (ajouté au PATH système)
    *   CUDA (Optionnel, pour accélération GPU Whisper)

2.  **Installation des dépendances** :
    ```bash
    pip install customtkinter opencv-python pillow faster-whisper pydub
    ```
    *(Note : pydub est gardé pour compatibilité legacy mais n'est plus utilisé par le moteur principal)*

3.  **Lancement** :
    ```bash
    python app.py
    ```

## 📂 Structure du Projet

*   `app.py` : Interface Graphique (CustomTkinter) v3.0.
*   `vibe_engine.py` : Le cerveau. Contient toute la logique FFmpeg remasterisée.
*   `input/` : Déposez vos vidéos brutes ici.
*   `output/` : Récupérez vos montages ici.
*   `temp/` : Fichiers intermédiaires (vidéos nettoyées, segments). Peut être vidé sans risque.
*   `assets/` : Contient les polices (Poppins-Bold.ttf) et la musique.

## ⚠️ Notes Importantes pour les Développeurs

*   N'éditez PAS `backend_v2.py` ou `app_v2.py` (Archives). Tout se passe dans `vibe_engine.py`.
*   Le moteur utilise des chemins relatifs via `os.chdir(temp)` pour contourner les limitations de longueur de chemin et de caractères spéciaux sous Windows dans les filtres complexes FFmpeg.

---
*Conçu pour la performance et la stabilité. Fini le désynchro.*
