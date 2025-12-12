# Projet Python – Gestion et Lecture de Fichiers Audio (CLI + GUI)

## 1. Informations générales
- Nom : Yacine Brahimi  | Soumeya Dahmen | Lekhal Douaa
- UE : Mineure Python: un langage Multipass 
- Projet : Application de gestion et lecture de fichiers audio  
- Formation : L3 Informatique  
- Date  : Décembre-2025  

---

## 2. Présentation générale du projet

Ce projet a pour objectif d’implémenter une application Python capable de :

- lire des fichiers audio (MP3 / FLAC),
- extraire et afficher leurs métadonnées,
- modifier les tags directement dans les fichiers,
- parcourir un dossier audio complet,
- générer une playlist au format XSPF,
- lire les playlists en mode interactif (piste suivante / précédente),
- offrir une interface graphique (GUI) et inerface console  (CLI).

Le projet est construit selon une **architecture modulaire**, séparant :

- **l’interface utilisateur (CLI et GUI)**,  
- **la logique métier** (playlist, bibliothèque audio),  
- **la représentation des fichiers audio** (MP3, FLAC, etc.).

Cette organisation rend le projet plus clair, maintenable et évolutif.

---

## 3. Structure du projet

L’arborescence du projet est la suivante :
```

Projet_Python/
│
├── doc/
│  │
│  ├── diaporama
│  ├── documentation
│  └── rapport
│
├── src/
│ │
│ ├── audio/ # Fichiers audio de test
│ ├── cli.py # Interface en ligne de commande (CLI)
│ ├── gui.py # Interface graphique (GUI)
│ │
│ └── library/ # Modules internes du projet
│    │
│    ├── models/ # Classes représentant les fichiers audio
│    │  ├── audio_file.py
│    │  ├── mp3_file.py
│    │  ├── flac_file.py
│    │  └── music_library.py
│    │
│    └── core/ # Logique métier (génération et gestion de playlists)
│      ├── lyricsresolver.py 
│      ├── metadatafetcher.py 
│      ├── playlist_generator.py 
│      └── file_explorer.py
│      
│
│
└── README.md
```


## 4. Description détaillée des fichiers du projet

Cette section présente l’ensemble des fichiers Python du projet, organisés par dossiers, avec une description de leurs rôles et de leurs principales fonctions.

---

## 4.1 Dossier library/models/ — Représentation des fichiers audio

### 4.1.1 audio_file.py
Fichier contenant la classe abstraite `AudioFile`.  
Elle représente la structure minimale d’un fichier audio.

Fonctionnalités principales :
- attributs communs : `filepath`, `metadata`, `extension`
- méthode `load_metadata()` (à surcharger)  
- base pour les classes MP3File et FLACFile

Objectif : fournir une interface commune à tous les types de fichiers audio.

---

### 4.1.2 mp3_file.py
Fichier contenant la classe `MP3File(AudioFile)`.

Fonctionnalités principales :
- extraction des métadonnées ID3 (via mutagen)
- gestion du format MP3
- lecture des tags : `title`, `artist`, `album`

Méthodes importantes :
- `load_metadata()` : lit les informations ID3 du fichier

---

### 4.1.3 flac_file.py
Fichier contenant la classe `FLACFile(AudioFile)`.

Fonctionnalités principales :
- extraction des métadonnées propres au format FLAC
- utilisation de `mutagen.FLAC`

Méthodes importantes :
- `load_metadata()` : lit les tags VorbisComment du fichier

---

### 4.1.4 music_library.py
Classe centrale responsable du chargement et du stockage des fichiers audio.

Fonctionnalités principales :
- `load_file(path)` : charge un fichier MP3/FLAC et crée l’objet correspondant  
- `load_directory(path)` : explore un dossier et charge tous les fichiers audio  
- gestion interne d’une liste : `self.files`

Rôle général : fournir une bibliothèque audio exploitable dans le CLI.

---

## 4.2 Dossier library/core/ — Logique interne

### 4.2.1 playlist_generator.py
Crée un fichier playlist au format XSPF.

Fonctionnalités principales :
- exploration d’un dossier audio
- filtrage des fichiers valides
- construction d'un fichier XML XSPF
- méthode `generer_playlist()`

### 4.2.2 file_explorer.py
Fichier utilitaire facilitant la recherche de fichiers.

Fonctionnalités principales :

- exploration récursive des dossiers
- filtrage des extensions audio
- fonctions utilisées par music_library ou par d’autres modules

Rôle : offrir une couche d’accès au système de fichiers.

### 4.2.3 metadatafetcher.py
Fichier pour enrichir automatique des métadonnées via API externes.

Fonctionnalités principales:

- Récupération des tags (Album, Année) via Spotify.
- Téléchargement de cover haute qualité via Deezer.
- Sauvegarde physique des nouvelles données dans les fichiers audio.

Rôle : Connecter la bibliothèque locale aux bases de données musicales en ligne.

### 4.2.4 lyricsresolver.py
Fichier pour la recherche et le nettoyage des paroles.

Fonctionnalités :

- Recherche multi-sources : LRCLIB (principal) et Lyrics.ovh (secours).
- Nettoyage intelligent des titres (suppression des mentions parasites) via Regex.
- Validation des titres via Spotify pour optimiser la recherche.

Rôle : Fournir le texte des chansons à l'interface utilisateur.

## 5. Interface CLI — Détails techniques

Le fichier cli.py constitue l’interface principale du projet.
Toutes les interactions de l’utilisateur passent par ce fichier.

Il contient :

- les imports essentiels,
- les outils de lecture audio,
- les outils de modification des tags,
- la gestion des playlists,
- l'exploration du projet,
- le parseur d’arguments (argparse),
- la logique principale (main).

Toutes les commandes suivent la forme :
python3 src/cli.py [options]


## 5.1 Fonctions internes du fichier cli.py

Cette section décrit les fonctions internes utilisées par l’interface en ligne de commande.  
Elles assurent la lecture, l’analyse, la modification et la navigation dans les fichiers audio et playlists.

---

### 5.1.1 chercher_fichier_partout(nom)

Rôle :
- rechercher un fichier portant un nom donné dans tout le projet,
- retourner son chemin absolu dès qu’un fichier correspondant est trouvé.

Fonctionnalités principales :
- exploration récursive du projet,
- comparaison du nom fourni avec chaque fichier rencontré.

Utilisation :
- utilisée par `-p fichier` pour retrouver un fichier audio,
- utilisée par `-f fichier` lorsqu’un fichier est introuvable au chemin donné.

---

### 5.1.2 charger_playlist_xspf(path)

Rôle :
- lire un fichier playlist au format XSPF,
- extraire la liste des chemins complets des fichiers audio qu’il contient.

Fonctionnement :
- analyse du fichier XML via `xml.etree.ElementTree`,
- récupération des balises `<location>` dans les éléments `<track>`,
- conversion de la valeur de chaque `<location>` en objet `Path`.

Utilisation :
- nécessaire pour l’option `-l playlist.xspf`.

---

### 5.1.3 jouer_fichier_audio(path)

Rôle :
- effectuer la lecture simple d’un fichier audio via `pygame.mixer`.

Fonctionnalités principales :
- initialisation du module audio,
- chargement et lecture du fichier,
- boucle bloquante attendant la commande « q » pour arrêter la lecture.

Caractéristiques :
- lecture mono-fichier,
- arrêt manuel par l’utilisateur,
- affichage du nom du fichier en cours.

---

### 5.1.4 editer_tags(path)

Rôle :
- modifier les métadonnées (titre, artiste, album) d’un fichier audio.

Fonctionnement :
- extraction des métadonnées existantes via `mutagen`,
- affichage des valeurs actuelles et saisie utilisateur,
- mise à jour et sauvegarde des tags dans le fichier audio.

Support :
- MP3 via ID3 (mutagen.easyid3),
- FLAC via VorbisComment (mutagen.FLAC).

Utilisation :
- appelée lors de l’option `-f fichier -e`.

---

### 5.1.5 lecteur_interactif(lib)

Rôle :
- permettre la lecture interactive d’une playlist (XSPF ou dossier chargé).

Commandes utilisateur :
- `n` : passer immédiatement au fichier suivant,
- `p` : revenir au fichier précédent,
- `q` : arrêter la lecture.

Fonctionnement :
- lecture non bloquante grâce à `pygame.mixer`,
- chargement dynamique de chaque piste selon la commande saisie,
- gestion d’un index interne dans la bibliothèque `MusicLibrary`,
- boucle continue tant que l’utilisateur ne quitte pas.

Utilisation :
- option `-l playlist.xspf`,
- option de lecture interactive après la création d’une playlist.

## 5.2 Options disponibles dans le CLI

L’interface en ligne de commande repose sur le module `argparse`.  
Chaque option active une fonctionnalité spécifique du projet.  
Le tableau ci-dessous regroupe l’ensemble des options et leur rôle.

| Option | Rôle   |
|--------|--------|
| `-p fichier`    | Lire un fichier audio |
| `-f fichier`    | Analyser un fichier audio (métadonnées) |
| `-f fichier -e` | Modifier les métadonnées (titre, artiste, album) |
| `-d dossier`    | Charger et analyser tous les fichiers audio d’un dossier |
| `-d dossier -o playlist.xspf` | Générer une playlist XSPF à partir d’un dossier |
| `-l playlist.xspf` | Lire une playlist XSPF en mode interactif (n/p/q) |

### Détails des options

#### `-p fichier`
- lance la lecture d’un fichier audio unique,
- utilise la fonction `jouer_fichier_audio()`.

#### `-f fichier`
- charge un fichier audio via `MusicLibrary.load_file()`,
- analyse et affiche les métadonnées.

#### `-f fichier -e`
- active en plus la modification des tags via `editer_tags()`.

#### `-d dossier`
- charge tous les fichiers audio du dossier,
- utilise `MusicLibrary.load_directory()`.

#### `-d dossier -o playlist.xspf`
- génère une playlist XSPF via `PlaylistGenerator.generer_playlist()`.

#### `-l playlist.xspf`
- charge une playlist existante,
- lit chaque piste via `lecteur_interactif()`.

## 5.3 Logique interne de la fonction main()

La fonction `main()` constitue le cœur du fichier `cli.py`.  
Elle effectue :

1. la création du parseur d’arguments,
2. la lecture des options fournies par l'utilisateur,
3. la résolution de chaque fonctionnalité selon l’option activée,
4. les contrôles nécessaires (existence des fichiers, formats valides…).

L'ordre de traitement est volontairement structuré pour éviter les conflits entre options.

### Ordre de traitement des options

1. **Lecture d’une playlist XSPF (`-l`)**  
   - chargement du fichier XSPF,  
   - lecture interactive par commandes `n`, `p`, `q`.

2. **Création d’une playlist (`-d dossier -o fichier.xspf`)**  
   - parcours du dossier,  
   - génération d’un fichier XSPF via PlaylistGenerator.

3. **Analyse d’un dossier (`-d dossier`)**  
   - chargement de tous les fichiers audio,  
   - affichage des métadonnées.

4. **Lecture d’un fichier audio (`-p fichier`)**  
   - lecture simple via pygame.

5. **Modification des tags (`-f fichier -e`)**  
   - extraction, saisie utilisateur, écriture des modifications.

6. **Analyse d’un fichier (`-f fichier`)**  
   - lecture et affichage des métadonnées.

### Rôle principal de main()

- s'assurer que seule l’option demandée est exécutée,
- fournir un point d'entrée unique aux fonctionnalités du projet,
- gérer les erreurs classiques : fichier introuvable, dossier vide, mauvais format,
- garantir une utilisation intuitive et cohérente du programme.

Ainsi, `main()` agit comme un routeur logique entre les différentes fonctionnalités du projet.


## 6. Exemples complets d’utilisation du CLI

Cette section présente des cas d’utilisation concrets du programme, afin de faciliter la prise en main de l’interface en ligne de commande.

---

### 6.1 help
```bash
python3  src/cli.py -h
```

### 6.2 Analyser un fichier audio
```bash
python3  src/cli.py -f audio/musique.mp3
```
Affiche :
- le titre,
- l’artiste,
- l’album,
- le format,
- la durée (selon métadonnées disponibles).

### 6.3 Analyser un dossier complet
```bash
python3  src/cli.py -d .
```
Tous les fichiers audio du dossier sont chargés et affichés.


### 6.4 Générer une playlist XSPF
```bash
python3 src/cli.py -d audio/ -o playlist.xspf
```
 

### 6.5 Lire un fichier audio
```bash
python3 src/cli.py -p audio/musique.mp3
```


### 6.6 Modifier les tags d’un fichier MP3/FLAC
```bash
python3 src/cli.py -f audio/musique.mp3 -e
```
Le programme affiche les valeurs existantes et demande :
Nouveau titre [...]
Nouvel artiste [...]
Nouvel album [...]
Les changements sont sauvegardés directement dans le fichier.


### 6.7 Lire une playlist de manière interactive
```bash
python3 src/cli.py -l playlist.xspf
```
Commandes disponibles :
- n : piste suivante,
- p : piste précédente,
- q : quitter.
La lecture utilise pygame et permet un changement instantané de piste.

### 6.8 Interface Graphique (GUI) — Détails techniques
Le fichier src/gui.py propose une interface utilisateur graphique moderne basée sur Tkinter. Elle permet de bénéficier de toutes les fonctionnalités du projet (lecture, gestion, édition) dans un environnement visuel ergonomique.

- L'interface repose sur plusieurs bibliothèques clés :
- Tkinter & TTL : Pour la structure de base.
- Sun Valley TTK (sv_ttk) : Pour l'application d'un thème moderne (Windows 11 style).
- TkinterDnD : Pour la gestion du glisser-déposer (Drag & Drop).
- Pillow (PIL) : Pour la gestion et l'affichage des pochettes d'album.
- Pygame : Pour le moteur audio (backend de lecture).

### 6.1 Architecture de l'interface (MusicLibraryGUI)
La classe principale MusicLibraryGUI orchestre l'ensemble de l'affichage. Elle est divisée en trois zones principales :

## La Sidebar (Barre latérale) :

- Barre de recherche dynamique (filtre les pistes en temps réel).
  
- Boutons d'importation (Dossier, Playlist XSPF).
  
- Liste des pistes (Treeview) affichant Titre, Artiste et Durée.
  
- Gestion du tri par colonnes.
  
## La Zone Principale (Main Content) :

- Affichage de la pochette d'album (extraite des tags ou image locale).

- Affichage des métadonnées détaillées (Titre, Artiste, Album, Année).

- Module de Paroles : Zone de texte scrollable pour afficher les paroles récupérées.

- Boutons d'édition : Permet de modifier les tags manuellement ou de lancer une requête API pour mise à jour automatique.

## La Barre de Lecture (Player Bar) :

- Contrôles de lecture : Play/Pause, Suivant, Précédent.

- Fonctions avancées : Mode Aléatoire (Shuffle), Répétition (Repeat).

- Barre de progression interactive (cliquable pour naviguer dans la piste).

- Contrôle du volume et bouton Mute.

- Sélecteur de thème (Jour / Nuit).


### 6.2 Fonctionnalités spécifiques au GUI
## Gestion des Thèmes
  L'application intègre un système de thèmes dynamique (Clair / Sombre). Le changement de thème met à jour instantanément les couleurs de fond, les polices, les boutons et le style des listes grâce à la méthode _apply_theme().

## Glisser-Déposer (Drag & Drop)
  Grâce à tkinterdnd2, l'utilisateur peut glisser des fichiers audio ou des dossiers directement depuis son explorateur de fichiers vers la fenêtre de l'application pour les ajouter à la liste de lecture courante.

## Édition des métadonnées
Contrairement au CLI qui procède par arguments, le GUI offre deux modes d'édition :

- Manuel : Une fenêtre modale permet de saisir les tags (Titre, Artiste, Album, Année).

- Automatique (API) : Un bouton dédié lance la recherche de métadonnées via MetadataFetcher et met à jour l'affichage et le fichier automatiquement.

### 7. Installation du projet
L’installation recommandée s’appuie sur un environnement virtuel Python.

---

### 7.1 Cloner ou télécharger le projet

Placez le dossier du projet sur votre machine (Windows, Linux ou macOS).

---

### 7.2 Créer un environnement virtuel

Sur macOS / Linux :
```bash
python3 -m venv venv
source venv/bin/activate
```

Sur Windows :
```bash
python -m venv venv
venv\Scripts\activate
```
### 7.3 Installer les dépendances
Pour le CLI:
- pip install pygame
- pip install mutagen
- pip install playsound
  
Pour le GUI:
- pip install sv_ttk 
- pip install tkinterdnd2 
- pip install Pillow 
- pip install requests

### 7.5 Désactiver l’environnement virtuel

deactivate