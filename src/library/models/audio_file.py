from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional
import hashlib


class AudioFile(ABC):
    """
    Classe abstraite qui sert de modèle à MP3File et FLACFile.

    Interface commune à tous les types de fichiers audio traités.
    """

    def __init__(self, filepath: Path):
        """
        Initialise un fichier audio.

        Args:
            filepath: Chemin vers le fichier audio
        """
        self.filepath = Path(filepath)
        self.metadata: Dict[str, any] = {}
        self._audio_object = None

        # Vérifie qu'il existe et qu'il est un fichier
        if not self.filepath.exists():
            raise FileNotFoundError(f"Le fichier {filepath} n'existe pas")
        if not self.filepath.is_file():
            raise ValueError(f"{filepath} n'est pas un fichier")

    @abstractmethod
    def extract_metadata(self) -> Dict[str, any]:
        """
        Méthode abstraite, une méthode est définie pour chaque format
        dans la classe correspondante.

        Returns:
            Dictionnaire contenant les métadonnées du fichier
        """
        raise NotImplementedError

    @abstractmethod
    def save_metadata(self) -> None:
        """
        Sauvegarde les métadonnées (tags) dans le fichier audio.
        """
        raise NotImplementedError

    @abstractmethod
    def get_cover_art(self) -> Optional[bytes]:
        """
        Retourne les données binaires de l’image de couverture (embedded),
        ou None si aucune cover n’est trouvée.
        """
        raise NotImplementedError
    
    @abstractmethod
    def reload(self) -> None:
        """
        Réinitialise l'objet audio pour forcer une relecture du fichier depuis le disque.
        Utile après une sauvegarde pour éviter le cache de mutagen.
        """
        raise NotImplementedError

    def get_duration(self) -> float:
        """
        Retourne la durée du fichier en secondes.

        Returns:
            Durée en secondes
        """
        if self._audio_object and hasattr(self._audio_object.info, "length"):
            return self._audio_object.info.length
        return 0.0

    def get_file_hash(self) -> str:
        """
        Calcule un hash MD5 du fichier pour détecter les doublons.

        Returns:
            Hash MD5 du fichier
        """
        hash_md5 = hashlib.md5()
        with open(self.filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: {self.filepath.name}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.filepath}')"