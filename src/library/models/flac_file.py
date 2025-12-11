from pathlib import Path
from typing import Dict, Optional
from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from src.library.models.audio_file import AudioFile

class FLACFile(AudioFile):
    """
    Classe specialisee pour les fichiers FLAC.

    Contient 2 methodes qui gerent les tags Vorbis:
    - extract_metadata: Extrait les metadata d'un fichier FLAC.
    - get_cover_art: Extrait la couverture du fichier (attached picture).
    """
    
    def __init__(self, filepath: Path):
        super().__init__(filepath)
        try:
            self._audio_object = FLAC(str(self.filepath))
        except Exception as e:
            raise ValueError(f"Erreur lors du chargement du FLAC: {e}")
    
    def save_metadata(self):
        """
        Sauvegarde les métadonnées (Vorbis Comment) modifiées pour le fichier FLAC.
        Les tags Vorbis sont des listes de chaînes.
        """
        if not self._audio_object.tags:
            # Créer les tags si le fichier n'en a pas (nécessaire avec FLAC)
            self._audio_object.add_tags()
        
        tags = self._audio_object.tags
        
        # Les tags FLAC (Vorbis) sont sensibles à la casse et stockés comme des listes
        if "title" in self.metadata and self.metadata['title']:
            tags["TITLE"] = [self.metadata['title']]
        if "artist" in self.metadata and self.metadata['artist']:
            tags["ARTIST"] = [self.metadata['artist']]
        if "album" in self.metadata and self.metadata['album']:
            tags["ALBUM"] = [self.metadata['album']]
        if "year" in self.metadata and self.metadata['year']:
            tags["DATE"] = [self.metadata['year']] # Vorbis utilise DATE ou YEAR
        if "genre" in self.metadata and self.metadata['genre']:
            tags["GENRE"] = [self.metadata['genre']]
        if "track_number" in self.metadata and self.metadata['track_number']:
            tags["TRACKNUMBER"] = [self.metadata['track_number']]

        self._audio_object.save(str(self.filepath))
    
    def extract_metadata(self) -> Dict[str, any]:
        """
        Extrait les métadonnées Vorbis Comment du fichier FLAC.
        
        Tags Vorbis courants :
        - TITLE: Titre
        - ARTIST: Artiste
        - ALBUM: Album
        - DATE: Date/Année
        - GENRE: Genre
        - TRACKNUMBER: Numéro de piste
        
        Returns:
            Dictionnaire avec les métadonnées normalisées
        """
        self.metadata = {
            'filepath': str(self.filepath),
            'filename': self.filepath.name,
            'format': 'FLAC',
            'duration': self.get_duration(),
            'title': '',
            'artist': '',
            'album': '',
            'year': '',
            'genre': '',
            'track_number': '',
        }
        
        # Les tags FLAC sont des listes, on prend le premier élément
        if self._audio_object.tags:
            tags = self._audio_object.tags
            
            self.metadata['title'] = tags.get('title', [''])[0]
            self.metadata['artist'] = tags.get('artist', [''])[0]
            self.metadata['album'] = tags.get('album', [''])[0]
            # Vorbis utilise souvent DATE
            self.metadata['year'] = tags.get('date', [''])[0]
            self.metadata['genre'] = tags.get('genre', [''])[0]
            self.metadata['track_number'] = tags.get('tracknumber', [''])[0]
        
        return self.metadata
    
    def get_cover_art(self) -> Optional[bytes]:
        """
        Extrait l'image de couverture des pictures FLAC.
        
        Returns:
            Données binaires de l'image
        """
        if self._audio_object.pictures:
            # Prendre la première image
            return self._audio_object.pictures[0].data
        return None
    
    def reload(self) -> None:
        """
        Réinitialise l'objet audio pour forcer une relecture du fichier depuis le disque.
        Cela vidange le cache de mutagen et garantit que extract_metadata() lira les nouveaux tags.
        """
        try:
            self._audio_object = FLAC(str(self.filepath))
            print(f"Reload effectué pour : {self.filepath.name}")
        except Exception as e:
            print(f"Erreur lors du reload : {e}")