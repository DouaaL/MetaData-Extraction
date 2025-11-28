from typing import Dict, Optional
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, ID3NoHeaderError

from .audio_file import AudioFile


class MP3File(AudioFile):
    """
    Classe spécialisée pour les fichiers MP3.

    - extract_metadata : lit les tags ID3
    - save_metadata    : écrit / met à jour les tags ID3
    - get_cover_art    : récupère la cover (APIC)
    """

    def __init__(self, filepath: Path | str):
        super().__init__(filepath)
        try:
            self._audio_object = MP3(str(self.filepath))
        except Exception as e:
            raise ValueError(f"Erreur lors du chargement du MP3: {e}")

    def save_metadata(self) -> None:
        """
        Sauvegarde les métadonnées dans les tags ID3.
        """
        try:
            audio = ID3(str(self.filepath))
        except ID3NoHeaderError:
            audio = ID3()

        # On nettoie les frames existantes pour éviter les doublons
        for frame_id in ("TIT2", "TPE1", "TALB", "TDRC", "TCON", "TRCK"):
            if frame_id in audio:
                del audio[frame_id]

        title = self.metadata.get("title", "")
        artist = self.metadata.get("artist", "")
        album = self.metadata.get("album", "")
        year = self.metadata.get("year", "")
        genre = self.metadata.get("genre", "")
        track_number = self.metadata.get("track_number", "")

        if title:
            audio.add(TIT2(encoding=3, text=title))
        if artist:
            audio.add(TPE1(encoding=3, text=artist))
        if album:
            audio.add(TALB(encoding=3, text=album))
        if year:
            audio.add(TDRC(encoding=3, text=year))
        if genre:
            audio.add(TCON(encoding=3, text=genre))
        if track_number:
            audio.add(TRCK(encoding=3, text=track_number))

        audio.save(str(self.filepath))
        # Recharger l'objet mutagen MP3
        self._audio_object = MP3(str(self.filepath))

    def extract_metadata(self) -> Dict[str, any]:
        """
        Extrait les métadonnées ID3 du fichier MP3.

        Tags ID3 courants :
        - TIT2: Titre
        - TPE1: Artiste
        - TALB: Album
        - TDRC: Année
        - TCON: Genre
        - TRCK: Numéro de piste
        """
        self.metadata = {
            "filepath": str(self.filepath),
            "filename": self.filepath.name,
            "format": "MP3",
            "duration": self.get_duration(),
            "title": "",
            "artist": "",
            "album": "",
            "year": "",
            "genre": "",
            "track_number": "",
        }

        tags = getattr(self._audio_object, "tags", None)
        if tags:
            self.metadata["title"] = str(tags.get("TIT2", [""])[0])
            self.metadata["artist"] = str(tags.get("TPE1", [""])[0])
            self.metadata["album"] = str(tags.get("TALB", [""])[0])
            self.metadata["year"] = str(tags.get("TDRC", [""])[0])
            self.metadata["genre"] = str(tags.get("TCON", [""])[0])
            self.metadata["track_number"] = str(tags.get("TRCK", [""])[0])

        return self.metadata

    def get_cover_art(self) -> Optional[bytes]:
        """
        Retourne les données binaires de la cover (APIC) si présente.
        """
        tags = getattr(self._audio_object, "tags", None)
        if not tags:
            return None

        for tag in tags.values():
            if getattr(tag, "FrameID", "") == "APIC":
                return tag.data
        return None
