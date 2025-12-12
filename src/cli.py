#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    from playsound import playsound
    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False

try:
    from mutagen.easyid3 import EasyID3
    from mutagen.flac import FLAC
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from library.models.music_library import MusicLibrary
from library.core.playlist_generator import PlaylistGenerator


def chercher_fichier_partout(nom: str) -> Path | None:
    """
    Cherche un fichier par son nom dans tout le projet.

    Args:
        nom: Nom (ou chemin) du fichier recherché.

    Returns:
        Path du fichier trouvé, sinon None.
    """
    cible = Path(nom).name
    for f in PROJECT_DIR.rglob("*"):
        if f.is_file() and f.name == cible:
            return f
    return None


def charger_playlist_xspf(filepath: Path) -> list[Path]:
    """
    Lit un fichier XSPF et retourne la liste des chemins audio trouvés.

    Args:
        filepath: Chemin vers le fichier .xspf

    Returns:
        Liste de Path vers les fichiers audio.
    """
    if not filepath.exists():
        print(f"Le fichier {filepath} n'existe pas.")
        return []

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        ns = {"x": "http://xspf.org/ns/0/"}

        paths: list[Path] = []
        for track in root.findall(".//x:track", ns):
            location = track.find("x:location", ns)
            if location is not None and location.text:
                uri = location.text.replace("file://", "")
                paths.append(Path(uri))

        return paths
    except Exception as e:
        print(f"Erreur lors du chargement XSPF : {e}")
        return []


def jouer_fichier_audio(filepath: Path) -> None:
    """
    Lit un fichier audio.

    Contrôles (via input):
        q : stop
        espace : pause / reprise

    Note:
        L'espace est détecté comme " " (espace) après validation Entrée.
    """
    print(f"\nLecture du fichier : {filepath.name}")

    if HAS_PYGAME:
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(str(filepath))
            pygame.mixer.music.play()

            print("Lecture en cours...")
            print("q : arrêter")
            print("espace : pause / reprise")

            paused = False

            while True:
                cmd = input("> ")
                if cmd == "q":
                    break
                if cmd == " ":
                    if not paused:
                        pygame.mixer.music.pause()
                        paused = True
                        print("Pause")
                    else:
                        pygame.mixer.music.unpause()
                        paused = False
                        print("Reprise")

            pygame.mixer.music.stop()
        except Exception as e:
            print(f"Erreur pygame : {e}")
        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass

    elif HAS_PLAYSOUND:
        try:
            playsound(str(filepath))
        except Exception as e:
            print(f"Erreur playsound : {e}")
    else:
        print("Aucun module audio disponible.")
        print(f"Tu peux ouvrir le fichier manuellement : {filepath}")


def editer_tags(filepath: Path) -> None:
    """
    Modifie les tags d'un fichier MP3 ou FLAC (title, artist, album) via mutagen.

    Args:
        filepath: Chemin du fichier audio (.mp3 ou .flac)
    """
    if not HAS_MUTAGEN:
        print("La modification des tags nécessite le module 'mutagen'.")
        print("Installe-le avec : pip install mutagen")
        return

    ext = filepath.suffix.lower()

    try:
        if ext == ".mp3":
            audio = EasyID3(filepath)
        elif ext == ".flac":
            audio = FLAC(filepath)
        else:
            print("Format non supporté pour l'édition (seulement MP3 et FLAC).")
            return

        titre_actuel = audio.get("title", [""])[0]
        artiste_actuel = audio.get("artist", [""])[0]
        album_actuel = audio.get("album", [""])[0]

        print("\nModification des tags (laisser vide pour conserver la valeur actuelle)")
        titre = input(f"Nouveau titre [{titre_actuel}] : ").strip() or titre_actuel
        artiste = input(f"Nouvel artiste [{artiste_actuel}] : ").strip() or artiste_actuel
        album = input(f"Nouvel album [{album_actuel}] : ").strip() or album_actuel

        audio["title"] = titre
        audio["artist"] = artiste
        audio["album"] = album
        audio.save()

        print("\nTags mis à jour avec succès.")
    except Exception as e:
        print(f"Erreur lors de la modification des tags : {e}")


def lecteur_interactif(lib: MusicLibrary) -> None:
    """
    Lecture interactive d'une liste de morceaux (playlist).

    Commandes:
        n : morceau suivant
        p : morceau précédent
        q : quitter
        espace : pause / reprise

    Note:
        L'espace est détecté comme " " (espace) après validation Entrée.
    """
    if not lib.files:
        print("Aucun fichier à lire.")
        return

    if not HAS_PYGAME:
        print("Le mode interactif nécessite pygame.")
        print("Installe pygame ou utilise la lecture simple.")
        return

    def lancer_piste(idx: int) -> None:
        audio_file = lib.files[idx]
        md = getattr(audio_file, "metadata", {}) or {}
        titre = md.get("title", audio_file.filepath.name)
        artiste = md.get("artist", "Inconnu")

        print(f"\nLecture : {titre} — {artiste}")
        pygame.mixer.music.load(str(audio_file.filepath))
        pygame.mixer.music.play()

    print("\nMode interactif")
    print("n = suivant | p = précédent | q = quitter | espace = pause/reprise\n")

    index = 0
    paused = False

    try:
        pygame.mixer.init()
        lancer_piste(index)

        while True:
            cmd = input("Commande (n/p/espace/q) : ")

            if cmd == " ":
                if not paused:
                    pygame.mixer.music.pause()
                    paused = True
                    print("Pause")
                else:
                    pygame.mixer.music.unpause()
                    paused = False
                    print("Reprise")
                continue

            cmd = cmd.strip().lower()

            if cmd == "n":
                paused = False
                index = (index + 1) % len(lib.files)
                pygame.mixer.music.stop()
                lancer_piste(index)

            elif cmd == "p":
                paused = False
                index = (index - 1) % len(lib.files)
                pygame.mixer.music.stop()
                lancer_piste(index)

            elif cmd == "q":
                pygame.mixer.music.stop()
                print("Lecture terminée.")
                break

            else:
                print("Commande invalide. Utilise n, p, espace ou q.")

    except Exception as e:
        print(f"Erreur lors de la lecture interactive : {e}")
    finally:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass


def main() -> None:
    """
    Point d'entrée CLI.
    Gère les options:
        -l : lire une playlist XSPF
        -d/-o : générer une playlist XSPF depuis un dossier
        -d : analyser un dossier
        -p : lire un fichier
        -f : analyser un fichier
        -f -e : modifier les tags
    """
    parser = argparse.ArgumentParser(
        description="Analyse audio, création de playlist et lecteur interactif."
    )

    parser.add_argument("-d", "--directory", help="Dossier contenant des fichiers audio")
    parser.add_argument("-f", "--file", help="Analyser ou éditer un fichier audio")
    parser.add_argument("-o", "--output", help="Créer une playlist XSPF (avec -d)")
    parser.add_argument("-p", "--play", help="Lire un fichier audio")
    parser.add_argument("-l", "--playlist", help="Lire une playlist XSPF")
    parser.add_argument("-e", "--edit", action="store_true", help="Modifier les tags du fichier passé avec -f")

    args = parser.parse_args()
    lib = MusicLibrary()

    if args.playlist:
        xspf = Path(args.playlist)
        print(f"\nChargement de la playlist : {xspf}")

        files = charger_playlist_xspf(xspf)
        if not files:
            print("Aucun fichier dans la playlist.")
            return

        for p in files:
            lib.load_file(p)

        lecteur_interactif(lib)
        return

    if args.directory:
        folder = Path(args.directory)

        if not folder.exists():
            print("Dossier introuvable.")
            return

        if args.output:
            pg = PlaylistGenerator(folder, fichier_sortie=args.output)
            pg.generer_playlist()
            print(f"Playlist générée : {args.output}")
            return

        lib.load_directory(folder)
        print("\nFichiers trouvés :")
        for f in lib.files:
            print(" -", f.filepath.name)
        return

    if args.play:
        path = Path(args.play)
        if not path.exists():
            found = chercher_fichier_partout(args.play)
            if not found:
                print("Fichier introuvable.")
                return
            path = found

        jouer_fichier_audio(path)
        return

    if args.file:
        path = Path(args.file)
        if not path.exists():
            found = chercher_fichier_partout(args.file)
            if not found:
                print("Fichier introuvable.")
                return
            path = found

        if args.edit:
            editer_tags(path)
            return

        lib.load_file(path)
        print("Fichier analysé.")
        return

    print("Aucun paramètre fourni. Utilisez -h pour l'aide.")


if __name__ == "__main__":
    main()
