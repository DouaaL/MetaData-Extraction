from pathlib import Path
from typing import List
import mimetypes


class FileExplorer:
    """
    Classe responsable du parcours récursif des dossiers.

    Principe : découverte et filtrage des fichiers audio.
    """

    SUPPORTED_EXTENSIONS = {".mp3", ".flac"}
    SUPPORTED_MIMETYPES = {
        "audio/mpeg",
        "audio/mp3",
        "audio/flac",
        "audio/x-flac",
    }

    def __init__(self):
        mimetypes.init()

    def explore_directory(self, directory: Path, recursive: bool = True) -> List[Path]:
        """
        Explore un répertoire et retourne tous les fichiers audio valides.
        """
        if not directory.exists():
            raise FileNotFoundError(f"Le répertoire {directory} n'existe pas")
        if not directory.is_dir():
            raise ValueError(f"{directory} n'est pas un répertoire")

        audio_files: List[Path] = []
        pattern = "**/*" if recursive else "*"

        for filepath in directory.glob(pattern):
            if self._is_valid_audio_file(filepath):
                audio_files.append(filepath)

        return sorted(audio_files)

    def _is_valid_audio_file(self, filepath: Path) -> bool:
        if not filepath.is_file():
            return False

        if filepath.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False

        mime_type, _ = mimetypes.guess_type(str(filepath))
        if mime_type not in self.SUPPORTED_MIMETYPES:
            return False

        return True
