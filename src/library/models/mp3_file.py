from typing import Dict, Optional
from pathlib import Path
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
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

    def save_metadata(self):
        """Version avec validation stricte des données"""

        if not self.metadata:
            raise ValueError("Aucune métadonnée à sauvegarder")

        # Validation et nettoyage des données
        def clean_string(value):
            """Nettoie une valeur pour mutagen"""
            if value is None:
                return None
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            if value is None:
                return None
            s = str(value).strip()
            return s if s else None

        def clean_year(value):
            """Nettoie une année"""
            if value is None:
                return None
            s = clean_string(value)
            if not s:
                return None
            # Extraire les 4 premiers chiffres
            import re
            match = re.search(r'\d{4}', s)
            return match.group(0) if match else None

        # Nettoyer toutes les valeurs
        title = clean_string(self.metadata.get('title'))
        artist = clean_string(self.metadata.get('artist'))
        album = clean_string(self.metadata.get('album'))
        year = clean_year(self.metadata.get('year'))
        albumartist = clean_string(self.metadata.get('albumartist'))
        genre = clean_string(self.metadata.get('genre'))

        ext = self.filepath.suffix.lower()

        try:
            if ext == '.mp3':
                try:
                    audio = EasyID3(str(self.filepath))
                except ID3NoHeaderError:
                    audio = mutagen.File(str(self.filepath), easy=True)
                    audio.add_tags()
                
                # Écrire uniquement les valeurs valides
                if title:
                    audio['title'] = [title]
                if artist:
                    audio['artist'] = [artist]
                if album:
                    audio['album'] = [album]
                if year:
                    audio['date'] = [year]
                if albumartist:
                    audio['albumartist'] = [albumartist]
                if genre:
                    audio['genre'] = [genre]
                
                audio.save()
                print(f"✓ Tags MP3 sauvegardés : {self.filepath.name}")
            
            elif ext == '.flac':
                audio = FLAC(str(self.filepath))
                
                if title:
                    audio['title'] = title
                if artist:
                    audio['artist'] = artist
                if album:
                    audio['album'] = album
                if year:
                    audio['date'] = year
                if albumartist:
                    audio['albumartist'] = albumartist
                if genre:
                    audio['genre'] = genre
                
                audio.save()
                print(f"✓ Tags FLAC sauvegardés : {self.filepath.name}")
            
            elif ext in ['.m4a', '.mp4']:
                audio = MP4(str(self.filepath))
                
                if title:
                    audio['\xa9nam'] = [title]
                if artist:
                    audio['\xa9ART'] = [artist]
                if album:
                    audio['\xa9alb'] = [album]
                if year:
                    audio['\xa9day'] = [year]
                if genre:
                    audio['\xa9gen'] = [genre]
                
                audio.save()
                print(f"✓ Tags M4A sauvegardés : {self.filepath.name}")
            
            else:
                raise ValueError(f"Format {ext} non supporté")

        except Exception as e:
            raise Exception(f"Erreur sauvegarde : {e}")

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
    

    def reload(self) -> None:
        """
        Réinitialise l'objet audio pour forcer une relecture du fichier depuis le disque.
        Cela vidange le cache de mutagen et garantit que extract_metadata() lira les nouveaux tags.
        """
        try:
            ext = self.filepath.suffix.lower()
            if ext == '.mp3':
                self._audio_object = MP3(str(self.filepath))
            elif ext == '.flac':
                # Bien que nous utilisons MP3File, cela peut être appelé génériquement
                # Mais pour un vrai reload FLAC, on regarderait FLACFile
                self._audio_object = MP3(str(self.filepath))
            else:
                # Fallback pour M4A/MP4
                self._audio_object = MP3(str(self.filepath))
            print(f"Reload effectué pour : {self.filepath.name}")
        except Exception as e:
            print(f"Erreur lors du reload : {e}")
