from pathlib import Path
from typing import List, Iterable
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
import os

from library.core.file_explorer import FileExplorer
from library.models.mp3_file import MP3File
from library.models.flac_file import FLACFile
from library.models.audio_file import AudioFile

XSPF_NS = "http://xspf.org/ns/0/"
ET.register_namespace("", XSPF_NS)


class PlaylistGenerator:
    """
    Gère la création de playlists XSPF.
    """

    def __init__(self, dossier: Path, fichier_sortie: str = "playlist.xspf"):
        self.dossier = Path(dossier)
        self.fichier_sortie = fichier_sortie

        self.explorer = FileExplorer()
        self.audio_files: List[AudioFile] = []
        self.tracks: List[ET.Element] = []

    def balise(self, nom: str) -> str:
        return f"{{{XSPF_NS}}}{nom}"

    def indenter_xml(self, elem: ET.Element, niveau: int = 0) -> None:
        i = "\n" + niveau * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for e in elem:
                self.indenter_xml(e, niveau + 1)
            if not e.tail or not e.tail.strip():
                e.tail = i
        else:
            if niveau and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def charger_audio_files(self):
        """
        Explore le dossier et charge les fichiers audio valides.
        """
        file_paths = self.explorer.explore_directory(self.dossier)
        self.audio_files.clear()

        for path in file_paths:
            if path.suffix.lower() == ".mp3":
                self.audio_files.append(MP3File(path))
            elif path.suffix.lower() == ".flac":
                self.audio_files.append(FLACFile(path))

    def set_audio_files(self, audio_files: Iterable[AudioFile]) -> None:
        """
        Permet d'injecter une liste d'AudioFile (utile pour la GUI).
        """
        self.audio_files = list(audio_files)

    def chemin_vers_uri_fichier(self, p: Path) -> str:
        return Path(p).resolve().as_uri()

    def construire_piste(self):
        """
        Construit les balises <track> pour chaque fichier audio, avec métadonnées.
        """
        self.tracks = []
        for audio in self.audio_files:
            metadata = audio.extract_metadata()

            t = ET.Element(self.balise("track"))
            ET.SubElement(t, self.balise("location")).text = self.chemin_vers_uri_fichier(
                audio.filepath
            )
            ET.SubElement(t, self.balise("title")).text = metadata.get(
                "title", audio.filepath.stem
            )
            ET.SubElement(t, self.balise("creator")).text = metadata.get("artist", "")
            ET.SubElement(t, self.balise("album")).text = metadata.get("album", "")
            ET.SubElement(t, self.balise("duration")).text = str(
                int(round(audio.get_duration() * 1000))
            )

            self.tracks.append(t)

    def ecrire_xspf(
        self,
        fichier_sortie: str | Path = None,
        titre: str = "Ma Playlist",
        createur: str = "Moi",
        info: str | None = None,
    ) -> Path:
        """
        Écrit la playlist XSPF sur disque.
        """
        if fichier_sortie is None:
            fichier_sortie = self.fichier_sortie
        fichier_sortie = Path(fichier_sortie)

        racine = ET.Element(self.balise("playlist"), {"version": "1"})
        ET.SubElement(racine, self.balise("title")).text = titre
        ET.SubElement(racine, self.balise("creator")).text = createur
        if info:
            ET.SubElement(racine, self.balise("info")).text = str(info)

        track_list = ET.SubElement(racine, self.balise("trackList"))
        for tr in self.tracks:
            track_list.append(tr)

        self.indenter_xml(racine)
        fichier_sortie.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(racine).write(
            fichier_sortie, encoding="utf-8", xml_declaration=True
        )
        print(f" Playlist générée : {fichier_sortie}")
        return fichier_sortie

    def generer_playlist(self, fichier_sortie: str | Path | None = None) -> Path:
        """
        1. Explore le dossier
        2. Construit les <track>
        3. Écrit le fichier XSPF
        """
        self.charger_audio_files()
        self.construire_piste()
        return self.ecrire_xspf(fichier_sortie)
