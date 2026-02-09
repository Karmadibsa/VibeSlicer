# 🎬 VibeSlicer Studio v2.0 - Projet Nettoyé

## � Structure du Projet

```
KarmaKut/
├── 🎯 app.py                          # Application principale (Interface)
├── ⚙️  karmakut_backend.py            # Logique de traitement vidéo
│
├── 📚 README.md                       # Documentation principale
├── 📚 GUIDE_DEMARRAGE.md              # Guide utilisateur
├── 📚 DOCUMENTATION_TECHNIQUE.md      # Documentation développeur
│
├── � requirements.txt                # Dépendances Python
├── 🚀 start_vibeslicer_studio.bat    # Lanceur (double-clic pour démarrer)
├── 📝 .gitignore                      # Configuration Git
│
├── 📂 input/                          # Placez vos vidéos ici
├── 📂 output/                         # Vidéos finales générées
├── 📂 temp/                           # Fichiers temporaires
└── 📂 assets/
    ├── Poppins-*.ttf                  # Polices pour sous-titres
    └── music/                         # (Optionnel) Musiques de fond
```

## 🚀 Démarrage Rapide

### **Méthode 1 : Double-clic (Recommandé)**
```
Double-cliquez sur : start_vibeslicer_studio.bat
```

### **Méthode 2 : Terminal**
```bash
python app.py
```

## 📝 Installation (Première fois)

```bash
# Installer les dépendances
pip install -r requirements.txt
```

## 💡 Utilisation

1. **Ajouter vos vidéos** dans le dossier `input/`
2. **Lancer** l'application (double-clic sur `.bat`)
3. **Sélectionner** une vidéo dans la bibliothèque
4. **Configurer** (sensibilité, musique optionnelle)
5. **Analyser & Transcrire** (2-5 min)
6. **Éditer** les sous-titres si besoin
7. **Rendre** la vidéo finale → dans `output/`

## 🎨 Fonctionnalités

- ✂️ Suppression automatique des silences
- 🎤 Transcription automatique (Whisper AI)
- 📝 Sous-titres stylisés avec mots-clés en JAUNE
- 🎵 Musique de fond (10% volume) optionnelle
- � Normalisation audio professionnelle
- ✏️ Éditeur de sous-titres intégré

## ⚠️ Prérequis

- **Python 3.9+** (avec pip)
- **FFmpeg** (dans le PATH système)
- **(Optionnel) GPU NVIDIA** pour accélération

## 📊 Performance

| Configuration | Temps pour 1 min vidéo |
|---------------|------------------------|
| GPU NVIDIA    | ~2-3 minutes          |
| CPU           | ~5-10 minutes         |

## � Dépannage

### "FFmpeg non détecté"
→ Installer FFmpeg et l'ajouter au PATH Windows

### "Transcription lente"
→ Normal sur CPU. GPU NVIDIA accélère x3-5

### "Aucune vidéo trouvée"
→ Vérifier que les vidéos sont bien dans `input/`

## � Documentation

- **README.md** - Ce fichier
- **GUIDE_DEMARRAGE.md** - Guide détaillé pas à pas
- **DOCUMENTATION_TECHNIQUE.md** - Pour développeurs

---

**Bon montage ! 🎬**
