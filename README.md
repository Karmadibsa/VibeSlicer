# VibeSlicer Studio

VibeSlicer Studio est un éditeur vidéo avancé alimenté par l'IA, conçu pour accélérer votre flux de création de contenu. Il utilise la détection d'activité vocale (suppression des silences) et la transcription automatique pour vous aider à éditer vos vidéos 10 fois plus vite.

## Fonctionnalités

-   **Suppression Automatique des Silences** : Détecte et supprime les blancs de vos enregistrements.
-   **Transcription IA** : Transcrit automatiquement votre vidéo en utilisant Whisper (s'exécute localement).
-   **Génération de Sous-titres** : Crée des sous-titres précis que vous pouvez incruster directement dans la vidéo.
-   **Édition par le Texte** : Modifiez votre vidéo en double-cliquant sur les segments de texte transcrits.
-   **Sélection de Plage (Shift+Clic)** : Sélectionnez et désactivez facilement plusieurs segments à la fois.
-   **Découpe de Précision (Alt+Clic)** : Coupez n'importe quel segment sur la timeline avec une précision à l'image près.
-   **Mixage Musique** : Ajoutez une musique de fond avec "auto-ducking" (le volume baisse quand vous parlez).
-   **Titre d'Intro** : Ajoutez un titre d'intro rapide sur un arrêt sur image flouté.
-   **Sous-titres Personnalisables** : Changez la taille, la couleur et la position verticale des sous-titres avec un aperçu en direct.

## Installation

1.  **Installer Python 3.10 ou 3.11**.
2.  **Installer les Dépendances** :
    ```bash
    pip install -r requirements.txt
    ```
3.  **Installer FFmpeg** : Assurez-vous que `ffmpeg` est dans le PATH de votre système.
4.  **Installer les Bibliothèques NVIDIA (pour l'accélération GPU)** :
    ```bash
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
    ```
    *Note : Ceci est critique pour une transcription rapide. Sans cela, l'application utilisera le processeur (CPU) et sera très lente.*

## Utilisation

1.  **Lancer le Studio** :
    Exécutez le fichier batch fourni :
    ```bash
    start_vibeslicer_studio.bat
    ```
    Ou exécutez via python :
    ```bash
    python vibe_qt.py
    ```

2.  **Flux de Travail** :
    *   **Importer** : Cliquez sur "+" pour ajouter votre/vos fichier(s) vidéo.
    *   **Analyser** : Cliquez sur "Démarrer le Studio". L'IA traitera l'audio (VAD rapide, puis transcription en arrière-plan).
    *   **Éditer** :
        *   Les **segments rouges** sont des silences (supprimés). Les **segments verts** sont de la parole (conservés).
        *   **Basculer** : Cliquez sur un segment pour l'activer/désactiver.
        *   **Plage** : Shift+Clic pour basculer une plage de segments.
        *   **Éditer le Texte** : Double-cliquez sur un segment vert dans la liste pour corriger le texte du sous-titre si besoin.
        *   **Couper** : Alt+Clic sur la timeline (barre bleue) pour couper un segment en deux.
    *   **Exporter** :
        *   Définissez votre **Titre d'Intro** (optionnel).
        *   Ajustez la **Taille** et la **Position** des sous-titres (slider).
        *   Choisissez une **Musique de Fond**.
        *   Cliquez sur **TERMINER ->** pour générer la vidéo finale.

## Dépannage

-   **"Erreur CUDA" / Analyse Lente** :
    Assurez-vous d'avoir une carte graphique NVIDIA et d'avoir installé les bibliothèques requises (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`). L'application tente de corriger automatiquement les chemins manquants au lancement.
-   **L'Interface se Ferme Inopinément** :
    Vérifiez la sortie du terminal pour les messages d'erreur. Indique généralement un problème de mémoire ou une bibliothèque manquante.

## Crédits

Développé par **Antigravity**. Propulsé par `faster-whisper`, `PyQt6` et `ffmpeg`.
