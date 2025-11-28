from pathlib import Path
from typing import List, Dict, Optional, Set

from library.core.file_explorer import FileExplorer
from .audio_file import AudioFile
from .mp3_file import MP3File
from .flac_file import FLACFile


class MusicLibrary:
    """
    Bibliothèque musicale en mémoire.
    Gère :
    - liste d'AudioFile (MP3/FLAC)
    - détection de doublons par hash
    - stats simples
    """

    def __init__(self):
        self.files: List[AudioFile] = []
        self._file_hashes: Set[str] = set()
        self._filepath_index: Dict[str, AudioFile] = {}
        self.explorer = FileExplorer()

    def ajouter_fichier(self, audio_file: AudioFile, check_duplicates: bool = True) -> bool:
        """
        Ajoute un fichier à la bibliothèque, avec option de détection de doublons.
        """
        if check_duplicates:
            file_hash = audio_file.get_file_hash()
            if file_hash in self._file_hashes:
                print(f"Doublon ignoré : {audio_file.filepath.name}")
                return False
            self._file_hashes.add(file_hash)

        self.files.append(audio_file)
        self._filepath_index[str(audio_file.filepath)] = audio_file
        return True

    def load_directory(self, directory: Path, recursive: bool = True):
        """
        Charge tous les fichiers audio d'un répertoire et les affiche dans la console.
        """
        audio_paths = self.explorer.explore_directory(directory, recursive)

        print(f"\n Exploration de {directory}")
        print(f"{len(audio_paths)} fichiers audio trouvés.\n")

        loaded_count = 0
        error_count = 0

        for filepath in audio_paths:
            try:
                if not self.explorer._is_valid_audio_file(filepath):
                    continue

                if filepath.suffix.lower() == ".mp3":
                    audio_file = MP3File(filepath)
                elif filepath.suffix.lower() == ".flac":
                    audio_file = FLACFile(filepath)
                else:
                    continue

                audio_file.extract_metadata()
                if self.ajouter_fichier(audio_file):
                    loaded_count += 1

                    titre = audio_file.metadata.get("title", filepath.stem)
                    artiste = audio_file.metadata.get("artist", "Inconnu")
                    print(f" Nom fichier :({filepath.name}) - Titre :{titre} - Artiste : {artiste} ")

            except Exception as e:
                error_count += 1
                print(f" Erreur avec {filepath.name}: {e}")

        print(f"\n {loaded_count} fichiers chargés.")
        if error_count > 0:
            print(f" {error_count} fichiers en erreur.")

    def load_file(self, filepath: Path | str):
        """
        Charge un seul fichier audio, affiche ses métadonnées et l’ajoute à la bibliothèque.
        Si le fichier n’existe pas, le cherche dans tout le projet.
        """
        filepath = Path(filepath)

        if filepath.exists():
            print(f"📄 Fichier trouvé : {filepath}")
        else:
            print(f"🔍 Recherche du fichier {filepath.name} dans le projet...")
            found = None
            for f in Path(".").rglob("*"):
                if f.name == filepath.name:
                    found = f
                    break
            if found:
                filepath = found
                print(f" Fichier trouvé automatiquement : {filepath}")
            else:
                print(f" Le fichier {filepath.name} est introuvable dans le projet.")
                return

        if not self.explorer._is_valid_audio_file(filepath):
            print(f" Le fichier {filepath.name} n’est pas un fichier audio supporté.")
            return

        if filepath.suffix.lower() == ".mp3":
            audio_file = MP3File(filepath)
        elif filepath.suffix.lower() == ".flac":
            audio_file = FLACFile(filepath)
        else:
            print(f" Format non supporté : {filepath.suffix}")
            return

        try:
            audio_file.extract_metadata()
            self.ajouter_fichier(audio_file)

            md = getattr(audio_file, "metadata", {})

            titre = md.get("title") or filepath.stem
            artiste = md.get("artist") or "Artiste inconnu"
            album = md.get("album") or "Album non spécifié"
            duree = md.get("duration")

            if not duree or duree == "Inconnue":
                duree_affiche = "Durée non disponible"
            else:
                try:
                    duree_affiche = f"{int(round(float(duree)))} secondes"
                except (ValueError, TypeError):
                    duree_affiche = "Durée non disponible"

            print(f"\n Fichier analysé : {filepath.name}")
            print(f"    • Titre   : {titre}")
            print(f"    • Artiste : {artiste}")
            print(f"    • Album   : {album}")
            print(f"    • Durée   : {duree_affiche}\n")

        except Exception as e:
            print(f"Erreur pendant l’analyse du fichier {filepath.name} : {e}")

    def get_file_by_path(self, filepath: str) -> Optional[AudioFile]:
        return self._filepath_index.get(filepath)

    def filter_by_artist(self, artist: str) -> List[AudioFile]:
        return [
            f for f in self.files
            if f.metadata.get("artist", "").lower() == artist.lower()
        ]

    def get_statistics(self) -> Dict[str, any]:
        total_duration = sum(f.get_duration() for f in self.files)
        formats: Dict[str, int] = {}
        for f in self.files:
            fmt = f.metadata.get("format", "Unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
        return {
            "total_files": len(self.files),
            "total_duration_seconds": total_duration,
            "total_duration_hours": total_duration / 3600,
            "formats": formats,
            "unique_artists": len(set(f.metadata.get("artist", "") for f in self.files)),
            "unique_albums": len(set(f.metadata.get("album", "") for f in self.files)),
        }

    def __len__(self) -> int:
        return len(self.files)

    def __iter__(self):
        return iter(self.files)
