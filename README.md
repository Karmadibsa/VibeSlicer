# Mise en place du projet Reel-Maker

## 1. Installation des pré-requis

### Python & Bibliothèques
Assurez-vous d'avoir Python installé. Ouvrez un terminal dans ce dossier et lancez :

```powershell
pip install -r requirements.txt
```

### Outils externes obligatoires
Ce script utilise `MoviePy` et `pydub`, qui dépendent de logiciels tiers :

1. **ImageMagick** (Pour les sous-titres) :
   - Téléchargez et installez [ImageMagick](https://imagemagick.org/script/download.php#windows).
   - **Important** : Lors de l'installation, cochez la case "Install Legacy Utilities (e.g. convert)".
   - Si MoviePy ne le trouve pas, vous devrez peut-être modifier le fichier `config_defaults.py` de MoviePy ou définir la variable d'environnement `IMAGEMAGICK_BINARY`.

2. **FFmpeg** (Pour la manipulation vidéo/audio) :
   - Téléchargez et installez FFmpeg.
   - Ajoutez-le à votre PATH système (vérifiez en tapant `ffmpeg -version` dans un terminal).

## 2. Préparation des fichiers

Placez vos fichiers dans les dossiers correspondants :

- **input/** : Mettez votre ou vos vidéos sources (ex: `ma_video.mp4`). Le script prendra la première trouvée.
- **assets/** :
  - `outro.mp4` : Votre vidéo d'outro.
  - `Poppins-Bold.ttf` : La police d'écriture (ou une autre police .ttf).

## 3. Utilisation

Lancez le script :

```powershell
python reel_maker.py
```

Le script va :
1. Analyser les silences et ouvrir une fenêtre de prévisualisation pour chaque détection.
2. Vous demander de confirmer la suppression (Y/N).
3. Transcrire l'audio et créer un fichier `edit_subs.txt`.
4. **Pause** : Vous pouvez ouvrir `edit_subs.txt`, corriger le texte ou les temps, sauvegarder et fermer.
5. Appuyez sur **ENTRÉE** dans la console pour reprendre.
6. Générer la vidéo finale avec sous-titres animés dans `output/`.

## Configuration
Vous pouvez ajuster les paramètres (seuil de silence, couleurs, marges) directement au début du fichier `reel_maker.py` dans la section `CONFIG`.
