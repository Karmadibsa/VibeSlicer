# VibeSlicer Pro ✂

**Éditeur vidéo automatisé pour créer des Reels / TikToks / Shorts**
Interface graphique PyQt6 • Moteur FFmpeg pur • Transcription Whisper IA

---

## À quoi ça sert ?

VibeSlicer Pro transforme une vidéo brute (talking-head, podcast, screen-record…)
en un Reel prêt à poster en **3 clics** :

1. **Analyser** — Détecte automatiquement tous les silences et pauses de la vidéo
2. **Assembler** — Coupe les silences choisis et recolle les séquences parlées
3. **Transcrire** — Génère les sous-titres automatiquement via Whisper (IA)
4. **Exporter** — Grave les sous-titres en surimpression et livre le fichier final

---

## Fonctionnalités

### Interface visuelle
| Fonctionnalité | Description |
|---|---|
| **Timeline interactive** | Visualisation de la waveform audio + segments colorés (vert = garder, rouge = couper) |
| **Player vidéo intégré** | Lecture A/V native via QtMultimedia, seekbar, contrôles play/pause/skip |
| **Mode Coupe (Razor)** | Clic sur la timeline = coupe manuelle précise à n'importe quel point |
| **Points In/Out** | Sélection manuelle d'une zone à couper avec marqueurs visuels |
| **Panel Debug** | Journal interne affichant toutes les étapes et erreurs (activable via toolbar) |

### Traitement vidéo (moteur FFmpeg)
| Fonctionnalité | Description |
|---|---|
| **Normalisation CFR** | Conversion automatique en 30 fps constant avant analyse (élimine les désynchros) |
| **Détection des silences** | Via pydub — seuil et durée minimum ajustables avec sliders |
| **Assemblage sans perte de sync** | FFmpeg Concat Demuxer — rapide, aucune saturation RAM, 0 désynchronisation |
| **Transcription Whisper** | Modèle `small` par défaut, GPU CUDA si disponible, fallback CPU automatique |
| **Gravure sous-titres** | Filtre `subtitles` natif FFmpeg — style TikTok (Poppins, contour violet) |
| **Détection NVENC** | Utilise le GPU NVIDIA pour l'encodage si disponible, sinon CPU libx264 |

### Workflow
```
Vidéo source
    ↓ [ANALYSER]
Waveform + liste des silences
    ↓ Clic sur segments pour décider couper/garder
    ↓ [ASSEMBLER]
Raw_Cut_<nom>.mp4   ← vidéo coupée sans sous-titres
    ↓ Transcription Whisper automatique
Éditeur de sous-titres (format START | END | MOT)
    ↓ Édition manuelle possible
    ↓ [BRÛLER LES SOUS-TITRES]
Reel_Ready_<nom>.mp4   ← vidéo finale prête à poster
```

---

## Prérequis

### 1. FFmpeg (obligatoire)
Télécharger sur **https://ffmpeg.org/download.html** (build Windows recommandé : gyan.dev)
→ Extraire et ajouter le dossier `bin/` à la variable d'environnement `PATH`

Vérification : `ffmpeg -version` dans un terminal doit répondre

### 2. Python 3.10+
Télécharger sur **https://www.python.org**

### 3. PyTorch (pour la transcription Whisper)
Choisir selon votre machine :

```bash
# GPU NVIDIA (CUDA 12.x) — recommandé si vous avez une carte NVIDIA
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# CPU uniquement — fonctionne sur toutes les machines, plus lent
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

---

## Installation

```bash
# 1. Cloner ou télécharger le projet
cd C:\...\EditVideo

# 2. Installer les dépendances (hors PyTorch)
pip install -r requirements.txt

# 3. Lancer (Windows)
LANCER_VIBESLICER.bat

# Ou directement :
python gui.py
```

---

## Dossiers

```
EditVideo/
├── input/          ← Placez vos vidéos sources ici
├── output/         ← Vidéos exportées (Raw_Cut + Reel_Ready)
├── temp/           ← Fichiers temporaires (WAV, CFR, SRT…)
├── assets/         ← Police Poppins-Bold.ttf
├── gui.py          ← Interface graphique (PyQt6)
├── reel_maker.py   ← Moteur de traitement (FFmpeg, Whisper)
├── karmakut_v2.py  ← Script CLI alternatif (ligne de commande)
└── requirements.txt
```

---

## Raccourcis clavier (timeline)

| Touche | Action |
|---|---|
| **Scroll molette** | Zoom in/out sur la timeline |
| **Clic règle** | Seek (déplacer la tête de lecture) |
| **Clic segment** | Basculer couper / garder |
| **Échap** | Désactiver le Mode Coupe |

---

## Paramètres ajustables

Dans la barre sous le player :

| Paramètre | Valeur par défaut | Description |
|---|---|---|
| **Seuil silence** | -35 dB | Plus bas = détecte les sons très faibles comme des silences |
| **Durée min** | 500 ms | Ignorer les pauses inférieures à cette durée |

Dans `reel_maker.py > CONFIG` :

| Clé | Valeur | Description |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `"small"` | Modèle Whisper : `tiny`, `base`, `small`, `medium`, `large` |
| `SUB_STYLE` | (voir code) | Style des sous-titres : police, taille, couleur, position |
| `MAX_WORDS_PER_SUB` | `4` | Nombre de mots par sous-titre (style TikTok) |

---

## Architecture technique

**Ce projet utilise exclusivement FFmpeg** pour toutes les opérations vidéo — aucune dépendance à moviepy, ImageMagick ou Pillow pour le traitement vidéo.

| Opération | Outil |
|---|---|
| Normalisation CFR | `ffmpeg -r 30 -c:v libx264` |
| Extraction audio | `ffmpeg -vn -acodec pcm_s16le` |
| Détection silences | `pydub.silence.detect_silence()` |
| Assemblage | `ffmpeg -f concat` (Concat Demuxer) |
| Transcription | `faster-whisper` (ctranslate2) |
| Gravure sous-titres | `ffmpeg -vf subtitles=...` |
| Encodage final | `h264_nvenc` (GPU) ou `libx264` (CPU) |

---

## Dépannage

**"FFmpeg introuvable"** → Installez FFmpeg et ajoutez son dossier `bin/` au PATH Windows

**"Prévisualisation vidéo indisponible"** → Le backend QtMultimedia ne se charge pas.
Solution : `pip install PyQt6-Qt6==6.7.3` puis relancer

**Transcription échoue (DLL error)** → Réinstallez PyTorch CPU-only :
`pip install torch --index-url https://download.pytorch.org/whl/cpu`

**Vidéo désynchronisée** → La normalisation CFR règle ce problème automatiquement.
Si la vidéo source est déjà en CFR, le résultat sera parfait.
