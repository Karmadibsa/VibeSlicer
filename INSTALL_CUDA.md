# GUIDE D'INSTALLATION CUDA (Accélération NVIDIA)

Pour que VibeSlicer utilise votre carte graphique (GPU) et soit ultra-rapide, vous devez installer deux outils NVIDIA :

## 1. NVIDIA CUDA Toolkit 12
C'est la base. Sans ça, le fichier `cublas64_12.dll` est manquant.

1.  Allez sur : [Télécharger CUDA Toolkit 12.3](https://developer.nvidia.com/cuda-downloads?target_os=Windows&target_arch=x86_64&target_version=11&target_type=exe_local)
    *   (Le lien pointe vers la dernière version 12.x, prenez la version pour Windows 11/10).
2.  Téléchargez l'installateur (c'est gros, environ 3 Go).
3.  Installez-le en mode "Express" (par défaut).

## 2. NVIDIA cuDNN (Bibliothèques de Deep Learning)
C'est le moteur pour les modèles IA comme Whisper.

1.  Allez sur : [Télécharger cuDNN](https://developer.nvidia.com/cudnn-downloads)
2.  Téléchargez la version pour **CUDA 12.x**.
3.  Décompressez le dossier zip.
4.  Copiez **tous les fichiers** qui sont dans les dossiers `bin`, `include`, et `lib` du zip vers, respectivement, les dossiers `bin`, `include`, et `lib` de votre installation CUDA (généralement dans `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\`).

### Vérification
Une fois installé :
1.  **Redémarrez votre ordinateur** (important pour que le PATH se mette à jour).
2.  Relancez `LANCER_VIBESLICER.bat`.

Si c'est bien fait, vous verrez "Loading Whisper on cuda..." et ça ira très vite !
