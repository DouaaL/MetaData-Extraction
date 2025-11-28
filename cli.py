#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# ==========================
#  Imports optionnels audio
# ==========================
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

# ==========================
#   Pour accéder à src/
# ==========================
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.append(str(SRC_DIR))

from library.models.music_library import MusicLibrary
from library.core.playlist_generator import PlaylistGenerator
from library.core.metadata_fetcher import MetadataFetcher


def chercher_fichier_partout(nom: str) -> Path | None:
    cible = Path(nom).name
    for f in Path(".").rglob("*"):
        if f.is_file() and f.name == cible:
            return f
    return None


def afficher_paroles_locale(filepath: Path) -> None:
    """
    Affiche les paroles si un .lrc ou .txt existe à côté du fichier.
    """
    lyrics_file = None
    for ext in (".lrc", ".txt"):
        candidate = filepath.with_suffix(ext)
        if candidate.exists():
            lyrics_file = candidate
            break

    if not lyrics_file:
        print("\n Aucune parole locale trouvée.\n")
        return

    print(f"\n Paroles locales : {lyrics_file.name}\n")
    try:
        text = lyrics_file.read_text(encoding="utf-8", errors="ignore")
        print(text)
        print()
    except Exception as e:
        print(f" Impossible de lire les paroles : {e}")


def main():
    parser = argparse.ArgumentParser(
        description="PyMetaPlay – Analyse de fichiers audio et génération de playlists XSPF (CLI)."
    )
    parser.add_argument("-d", "--directory", help="Dossier avec fichiers audio (.mp3/.flac)")
    parser.add_argument("-f", "--file", help="Fichier audio unique à analyser")
    parser.add_argument(
        "-o",
        "--output",
        help="Nom du fichier XSPF à générer (utilisé avec -d)",
    )
    parser.add_argument(
        "-p",
        "--play",
        help="Lire un fichier audio (recherche dans tout le projet si besoin)",
    )
    parser.add_argument(
        "-e",
        "--edit",
        action="store_true",
        help="Modifier les tags (titre / artiste / album) du fichier passé avec -f",
    )
    parser.add_argument(
        "-a",
        "--api-search",
        action="store_true",
        help="Rechercher et mettre à jour les métadonnées via l'API (Spotify) pour -f",
    )
    parser.add_argument(
        "-l",
        "--lyrics",
        action="store_true",
        help="Récupérer les paroles via une API Web pour -f",
    )

    args = parser.parse_args()

    # Aucun paramètre utile → message d’erreur
    if not (args.directory or args.file or args.play):
        print(" Aucun paramètre fourni. Utilisez -h pour l’aide.")
        return

    lib = MusicLibrary()

    # ===== 1) MODE DOSSIER (-d) =====
    if args.directory:
        dossier = Path(args.directory)

        if not dossier.exists():
            print(f" Le dossier {dossier} n'existe pas.")
            return

        if args.output:
            # génération playlist XSPF
            print(f"\n Génération de playlist depuis : {dossier}")
            pg = PlaylistGenerator(dossier)
            outfile = Path(args.output)
            pg.generer_playlist(outfile)
            print(f"💾 Playlist sauvegardée dans {outfile}")
            return

        # analyse simple du dossier
        print(f"\n Analyse du dossier : {dossier}")
        lib.load_directory(dossier)
        print(f"\n {len(lib)} fichiers audio chargés depuis {dossier}")
        return

    # ===== 2) MODE FICHIER (-f) =====
    if args.file:
        filename = args.file
        filepath = Path(filename)

        if not filepath.exists():
            print(f"🔍 Recherche du fichier {filename} dans le projet...")
            found = chercher_fichier_partout(filename)
            if not found:
                print(f"Le fichier {filename} est introuvable dans le projet.")
                return
            filepath = found
            print(f" Fichier trouvé automatiquement : {filepath}")

        print(f"\n🎵 Analyse du fichier : {filepath.name}")
        lib.load_file(filepath)

        if not lib.files:
            return

        audio_obj = lib.files[-1]
        metadata = audio_obj.metadata

        # paroles locales éventuelles
        afficher_paroles_locale(filepath)

        fetcher = MetadataFetcher()

        # API Spotify (update métadonnées)
        if args.api_search:
            enriched = fetcher.update_audio_file_metadata(audio_obj)
            if enriched:
                print("\n✅ Métadonnées après mise à jour API Spotify :")
                audio_obj.extract_metadata()
                print(f"  Titre   : {audio_obj.metadata.get('title')}")
                print(f"  Artiste : {audio_obj.metadata.get('artist')}")
                print(f"  Album   : {audio_obj.metadata.get('album')}")
                print(f"  Année   : {audio_obj.metadata.get('year')}")
            else:
                print("❌ Aucune métadonnée trouvée via Spotify.")

        # API lyrics
        if args.lyrics:
            lyrics = fetcher.fetch_lyrics_for_audio(audio_obj)
            if lyrics:
                print("\n📜 Paroles via API :\n")
                print(lyrics)
            else:
                print("\n❌ Impossible de récupérer les paroles via l’API.\n")

        # Mode édition de tags
        if args.edit:
            print("\n🛠 Modification des tags (laisser vide pour ne pas changer) :")

            nouveau_titre = input(
                f"→ Nouveau titre [{metadata.get('title', '')}] : "
            ).strip()
            nouveau_artiste = input(
                f"→ Nouvel artiste [{metadata.get('artist', '')}] : "
            ).strip()
            nouveau_album = input(
                f"→ Nouvel album [{metadata.get('album', '')}] : "
            ).strip()

            if nouveau_titre:
                audio_obj.metadata["title"] = nouveau_titre
            if nouveau_artiste:
                audio_obj.metadata["artist"] = nouveau_artiste
            if nouveau_album:
                audio_obj.metadata["album"] = nouveau_album

            try:
                audio_obj.save_metadata()
                print(" Métadonnées mises à jour et sauvegardées.")
            except Exception as e:
                print(f" Erreur lors de la sauvegarde : {e}")

        return

    # ===== 3) MODE LECTURE (-p) =====
    if args.play:
        filename = args.play
        filepath = Path(filename)

        if not filepath.exists():
            print(f" Recherche du fichier {filename} dans le projet...")
            found = chercher_fichier_partout(filename)
            if not found:
                print(f" Le fichier {filename} est introuvable dans le projet.")
                return
            filepath = found
            print(f" Fichier trouvé automatiquement : {filepath}")

        print(f"\n▶ Lecture du fichier : {filepath.name}")

        if HAS_PYGAME:
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(str(filepath))
                pygame.mixer.music.play()
                print("💿 Lecture en cours... Appuyez sur Entrée pour arrêter.")
                input()
                pygame.mixer.music.stop()
                print(" Lecture arrêtée.")
            except Exception as e:
                print(f" Erreur pendant la lecture avec pygame : {e}")
            finally:
                try:
                    pygame.mixer.quit()
                except Exception:
                    pass
        elif HAS_PLAYSOUND:
            try:
                playsound(str(filepath))
                print("Lecture terminée.")
            except Exception as e:
                print(f" Erreur pendant la lecture : {e}")
        else:
            print(" Aucun module audio ('pygame' ou 'playsound') n’est disponible.")
            print(f"Tu peux ouvrir le fichier manuellement : {filepath}")

        return


if __name__ == "__main__":
    main()
