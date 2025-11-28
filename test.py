import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.append(str(SRC_DIR))

from library.models.music_library import MusicLibrary
from library.core.playlist_generator import PlaylistGenerator

if __name__ == "__main__":
    dossier_musique = Path("audioProjet")

    lib = MusicLibrary()
    print("\n=== Chargement des fichiers audio ===")
    lib.load_directory(dossier_musique)

    print(f"\nNombre total de fichiers chargés : {len(lib)}")

    print("\n=== Liste des fichiers ===")
    for f in lib:
        titre = f.metadata.get("title", f.filepath.stem)
        artiste = f.metadata.get("artist", "Inconnu")
        print(f"🎵 {titre} — {artiste}")

    print("\n=== Statistiques ===")
    stats = lib.get_statistics()
    for k, v in stats.items():
        print(f"{k}: {v}")

    print("\n=== Génération de la playlist par défaut ===")
    playlist = PlaylistGenerator(dossier_musique)
    playlist_path = playlist.generer_playlist("test_playlist.xspf")
    print(f"Playlist générée : {playlist_path}")
