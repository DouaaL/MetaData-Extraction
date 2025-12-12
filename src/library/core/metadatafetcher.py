from typing import Dict, Optional
from pathlib import Path
from urllib.parse import quote
import os
import requests
import re
import time

from library.models.audio_file import AudioFile
from library.core.lyricsresolver import LyricsResolver

# Désactiver les warnings HTTPS non vérifiés
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Spotify (Spotipy)
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False
    spotipy = None


class MetadataFetcher:
    """
    - Métadonnées enrichies via Spotify (optionnel)
    - Paroles via LyricsResolver
    - Cover via Deezer API (par fichier)
    """

    def __init__(self):

        # Spotify Credentials
        CLIENT_ID = "446cb6cddd38445fb33fa44babbab96f"
        CLIENT_SECRET = "375898f045794e4f845283e9b8d4da9a"

        env_id = os.environ.get("SPOTIFY_CLIENT_ID")
        env_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        if env_id and env_secret:
            CLIENT_ID = env_id
            CLIENT_SECRET = env_secret

        # Connexion Spotify
        self.sp = None
        if HAS_SPOTIPY:
            try:
                mgr = SpotifyClientCredentials(
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                )
                self.sp = spotipy.Spotify(client_credentials_manager=mgr)
                print("Connexion à l’API Spotify OK.")
            except Exception:
                self.sp = None
                print("Spotify désactivé (erreur connexion).")
        else:
            print("Spotify non installé.")

        self.lyrics_resolver = LyricsResolver(spotify_client=self.sp)

    # ----------------------------------------------------------
    # 🔧 1. Split intelligent artiste/titre si tags manquants
    # ----------------------------------------------------------
    def smart_split_filename(self, stem: str):
        parts = stem.split(" - ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "", stem.strip()

    # ----------------------------------------------------------
    # 🔧 helper : détecter les artistes “génériques”
    # ----------------------------------------------------------
    def _is_generic_artist(self, name: str) -> bool:
        if not name:
            return True
        n = name.strip().lower()
        generics = [
            "unknown",
            "unknown artist",
            "artiste inconnu",
            "inconnu",
            "various artists",
            "artist",
        ]
        return n in generics

    def clean_text(self, s: str) -> str:
        s = s.replace("_", " ")
        s = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", s)  # enlève extension
        s = re.sub(r"\([^)]*\)", "", s)            # enlève (....)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    # ----------------------------------------------------------
    # 🎨 2. Cover par fichier (Logique Principale)
    # ----------------------------------------------------------
    def ensure_cover_image(self, audio_file: AudioFile) -> Optional[Path]:
        """
        S'assure qu'une cover spécifique existe pour CE fichier :
        - cherche <stem>_cover.jpg dans le dossier du fichier
        - sinon la télécharge via DEEZER API
        """
        audio_path = Path(audio_file.filepath)
        album_dir = audio_path.parent
        stem = audio_path.stem

        # 1) Chercher une cover locale existante
        specific_cover = album_dir / f"{stem}_cover.jpg"
        if specific_cover.exists():
            # print("[ensure_cover_image] Cover spécifique déjà présente.")
            return specific_cover

        # 2) Récupérer les métadonnées pour la recherche
        try:
            # On privilégie les métadonnées en mémoire (fraîchement éditées par l'utilisateur)
            md = getattr(audio_file, "metadata", None) or audio_file.extract_metadata() or {}
        except Exception:
            md = {}

        raw_artist = (md.get("artist") or "").strip()
        raw_title = (md.get("title") or "").strip()

        # Deviner à partir du nom de fichier si les tags sont vides
        filename_artist, filename_title = self.smart_split_filename(
            self.clean_text(audio_path.stem)
        )

        # Choix de l'artiste
        if self._is_generic_artist(raw_artist):
            artist = filename_artist
        else:
            artist = raw_artist or filename_artist

        # Choix du titre
        if raw_title and " - " not in raw_title:
            title = raw_title
        else:
            title = filename_title or raw_title

        artist = self.clean_text(artist)
        title = self.clean_text(title)

        if not artist or not title:
            print("[ensure_cover_image] Impossible de deviner artist/title → abandon.")
            return None

        # 3) Tenter DEEZER pour CE fichier uniquement
        try:
            print(f"[Cover] Recherche Deezer pour : {artist} - {title}")
            cover_path = self._search_deezer_and_download_cover(
                artist=artist,
                title=title,
                dest_dir=album_dir,
                filename_stem=stem,
            )
            return cover_path
        except Exception as e:
            print("[ensure_cover_image] Erreur Deezer cover:", e)
            return None

    # ----------------------------------------------------------
    # 🎨 3. Appel DEEZER API (Remplace MusicBrainz)
    # ----------------------------------------------------------
    def _search_deezer_and_download_cover(
        self, artist: str, title: str, dest_dir: Path, filename_stem: str
    ) -> Optional[Path]:
        
        headers = {
            "User-Agent": "PyMetaPlay/1.0 (Python Audio Project)"
        }
        
        # URL de l'API publique Deezer
        base_url = "https://api.deezer.com/search"
        
        # Requête précise : artist:"..." track:"..."
        # On utilise des guillemets pour forcer la correspondance exacte si possible
        query = f'artist:"{artist}" track:"{title}"'
        params = {
            "q": query,
            "limit": 1  # On veut juste le premier résultat
        }

        try:
            # Appel API (verify=False conservé pour compatibilité avec votre config)
            resp = requests.get(base_url, params=params, headers=headers, timeout=5, verify=False)
            
            if resp.status_code != 200:
                print(f"[Deezer] Erreur API: {resp.status_code}")
                return None
            
            data = resp.json()
            
            # Vérification des résultats
            if "data" not in data or not data["data"]:
                print("[Deezer] Aucun résultat trouvé.")
                return None
            
            track_info = data["data"][0]
            album_info = track_info.get("album", {})
            
            # Deezer propose plusieurs tailles : cover_xl (1000px), cover_big (500px), cover_medium
            cover_url = album_info.get("cover_xl") or album_info.get("cover_big") or album_info.get("cover_medium")
            
            if not cover_url:
                print("[Deezer] Pas d'URL de cover dans le résultat.")
                return None
                
            print(f"[Deezer] Image trouvée : {cover_url}")

            # Téléchargement de l'image
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f"{filename_stem}_cover.jpg"

            img_resp = requests.get(cover_url, headers=headers, timeout=8, verify=False)
            if img_resp.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(img_resp.content)
                print(f"[Deezer] Cover sauvegardée : {dest_path}")
                return dest_path
            else:
                print("[Deezer] Erreur lors du téléchargement de l'image.")
                return None

        except Exception as e:
            print(f"[Deezer] Exception : {e}")
            return None

    # ----------------------------------------------------------
    # 🎧 4. Spotify → récupération metadata
    # ----------------------------------------------------------
    def search_metadata(self, artist: str, title: str) -> Optional[Dict[str, str]]:
        if not self.sp:
            return None

        query = f"track:{title}"
        if artist:
            query += f" artist:{artist}"

        try:
            results = self.sp.search(q=query, limit=1, type="track")
            items = results.get("tracks", {}).get("items", [])

            if not items:
                return None

            track = items[0]
            album = track.get("album", {})
            release_date = album.get("release_date", "")
            year = release_date.split("-")[0] if release_date else ""
            img = album.get("images", [])
            cover_url = img[0]["url"] if img else ""

            return {
                "title": track.get("name", title),
                "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                "album": album.get("name", ""),
                "year": year if len(year) == 4 else "",
                "genre": "",
                "track_number": str(track.get("track_number", "")),
                "cover_url": cover_url,
            }

        except Exception:
            return None

    # ----------------------------------------------------------
    # 🎧 5. Mise à jour metadata audio_file
    # ----------------------------------------------------------
    def update_audio_file_metadata(self, audio_file: AudioFile) -> bool:
        if not self.sp:
            return False

        try:
            current = audio_file.metadata if audio_file.metadata else (audio_file.extract_metadata() or {})
        except Exception:
            current = {}

        # Recherche API (Spotify pour les textes)
        enriched = self.search_metadata(
            current.get("artist") or "",
            current.get("title") or audio_file.filepath.stem,
        )

        if not enriched:
            return False

        if not audio_file.metadata:
            audio_file.metadata = dict(current)
        
        audio_file.metadata.update(enriched)

        # Sauvegarde physique
        try:
            audio_file.save_metadata()
            # On tente aussi de télécharger la cover Deezer immédiatement
            self.ensure_cover_image(audio_file)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde : {e}")
            return False

        return True

    # ----------------------------------------------------------
    # 🎤 6. Paroles
    # ----------------------------------------------------------
    def fetch_lyrics_for_audio(self, audio_file: AudioFile) -> Optional[str]:
        md = audio_file.metadata or {}
        return self.lyrics_resolver.get_lyrics(
            artist=md.get("artist") or "",
            title=md.get("title") or "",
            filename=audio_file.filepath.name,
        )