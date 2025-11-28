from typing import Dict, Optional, List
from pathlib import Path
import os
import tempfile

import requests

from library.models.audio_file import AudioFile

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
    Gère la récupération de métadonnées via des API Web :

    - Spotify Web API :
        * search_metadata(artist, title) : métadonnées pour un fichier local
        * search_tracks(query) : recherche de morceaux en ligne (pour la GUI)
    - API lyrics (ex: lyrics.ovh) : paroles d’un morceau
    """

    def __init__(self):
        # Tes propres clés Spotify (tu peux aussi les lire depuis des variables d'environnement)
        CLIENT_ID = "446cb6cddd38445fb33fa44babbab96f"
        CLIENT_SECRET = "375898f045794e4f845283e9b8d4da9a"

        env_id = os.environ.get("SPOTIFY_CLIENT_ID")
        env_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        if env_id and env_secret:
            CLIENT_ID = env_id
            CLIENT_SECRET = env_secret

        self.sp = None
        if HAS_SPOTIPY:
            try:
                mgr = SpotifyClientCredentials(
                    client_id=CLIENT_ID, client_secret=CLIENT_SECRET
                )
                self.sp = spotipy.Spotify(client_credentials_manager=mgr)
                print("Connexion à l’API Spotify OK.")
            except Exception as e:
                print(f" Erreur de connexion Spotify : {e}")
                self.sp = None
        else:
            print(" 'spotipy' non installé : l’API Spotify sera désactivée.")

    # ------------------------------------------------------------------
    #  SPOTIFY – pour les fichiers locaux (comme avant)
    # ------------------------------------------------------------------
    def search_metadata(self, artist: str, title: str) -> Optional[Dict[str, str]]:
        """
        Recherche des métadonnées enrichies via l'API Spotify pour un couple
        artiste / titre. Retourne un dict normalisé ou None.
        """
        if not self.sp:
            return None

        query = f"track:{title} artist:{artist}"
        print(f"🔍 Spotify (fichier local): {query}")
        try:
            results = self.sp.search(q=query, limit=1, type="track")
            items = results.get("tracks", {}).get("items", [])
            if not items:
                print("Aucun résultat Spotify.")
                return None

            track = items[0]
            album = track.get("album", {})
            release_date = album.get("release_date", "")  # YYYY-MM-DD
            year = release_date.split("-")[0] if release_date else ""

            # cover_url = première image d’album si dispo
            cover_url = ""
            images = album.get("images", [])
            if images:
                cover_url = images[0].get("url", "")

            metadata = {
                "title": track.get("name", title),
                "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                "album": album.get("name", ""),
                "year": year if len(year) == 4 else "",
                "genre": "",  # Spotify ne donne pas un genre direct ici
                "track_number": str(track.get("track_number", "")),
                "cover_url": cover_url,
            }
            print(f" Métadonnées Spotify trouvées : {metadata['title']}")
            return metadata
        except Exception as e:
            print(f" Erreur Spotify (search_metadata) : {e}")
            return None

    def update_audio_file_metadata(self, audio_file: AudioFile) -> Optional[Dict[str, str]]:
        """
        Met à jour les métadonnées d’un AudioFile via Spotify
        et les sauvegarde dans le fichier.
        Retourne le dict enrichi ou None.
        """
        current = audio_file.extract_metadata()
        artist = current.get("artist") or audio_file.filepath.stem
        title = current.get("title") or audio_file.filepath.stem

        enriched = self.search_metadata(artist, title)
        if not enriched:
            return None

        # S'assurer qu'on a un dict metadata sur l'objet
        if not hasattr(audio_file, "metadata") or audio_file.metadata is None:
            audio_file.metadata = dict(current)

        # On met à jour seulement les champs non vides
        for key, value in enriched.items():
            if value:
                audio_file.metadata[key] = value

        try:
            audio_file.save_metadata()
            print(" Métadonnées audio mises à jour et sauvegardées.")
        except Exception as e:
            print(f" Erreur lors de la sauvegarde des tags : {e}")

        return enriched

    # ------------------------------------------------------------------
    #  SPOTIFY – recherche de morceaux en ligne (pour la GUI)
    # ------------------------------------------------------------------
    def search_tracks(self, query: str, limit: int = 10) -> List[Dict[str, object]]:
        """
        Recherche des morceaux sur Spotify à partir d'une requête libre.
        Retourne une liste de dicts :

        [
            {
                "spotify_id": "...",
                "title": "...",
                "artist": "...",
                "album": "...",
                "year": "YYYY",
                "duration": 187.3,           # secondes
                "preview_url": "https://...", # extrait 30s (peut être vide)
                "cover_url": "https://..."
            },
            ...
        ]
        """
        if not self.sp:
            print(" Spotify désactivé : search_tracks() retourne [].")
            return []

        if not query.strip():
            return []

        print(f" Spotify (search_tracks) : {query}")
        try:
            results = self.sp.search(q=query, type="track", limit=limit)
            items = results.get("tracks", {}).get("items", [])
            tracks: List[Dict[str, object]] = []

            for track in items:
                album = track.get("album", {})
                release_date = album.get("release_date", "")
                year = release_date.split("-")[0] if release_date else ""
                images = album.get("images", [])
                cover_url = images[0].get("url", "") if images else ""

                duration_ms = track.get("duration_ms") or 0
                duration_sec = float(duration_ms) / 1000.0

                track_dict = {
                    "spotify_id": track.get("id"),
                    "title": track.get("name", ""),
                    "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                    "album": album.get("name", ""),
                    "year": year if len(year) == 4 else "",
                    "duration": duration_sec,
                    "preview_url": track.get("preview_url") or "",
                    "cover_url": cover_url,
                }
                tracks.append(track_dict)

            print(f" {len(tracks)} pistes trouvées via Spotify.")
            return tracks
        except Exception as e:
            print(f" Erreur Spotify (search_tracks) : {e}")
            return []

    def download_preview(self, preview_url: str) -> Optional[Path]:
        """
        Télécharge le MP3 d’aperçu (preview_url) dans un fichier temporaire
        et retourne le Path vers ce fichier, ou None en cas d’erreur.

        À utiliser avec pygame côté GUI, par ex :
            tmp = fetcher.download_preview(track["preview_url"])
            pygame.mixer.music.load(str(tmp))
        """
        if not preview_url:
            return None

        try:
            resp = requests.get(preview_url, stream=True, timeout=10)
            if resp.status_code != 200:
                print(f" HTTP {resp.status_code} sur preview_url.")
                return None

            fd, tmp_path = tempfile.mkstemp(
                prefix="pymetaplay_preview_", suffix=".mp3"
            )
            tmp_file = Path(tmp_path)
            with os.fdopen(fd, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            print(f"Aperçu téléchargé : {tmp_file}")
            return tmp_file
        except Exception as e:
            print(f" Erreur téléchargement preview : {e}")
            return None

    # ------------------------------------------------------------------
    #  LYRICS
    # ------------------------------------------------------------------
    def fetch_lyrics(self, artist: str, title: str) -> Optional[str]:
        """
        Exemple d’appel à une API de lyrics (simple).
        Ici, on utilise l’API lyrics.ovh (ou similaire).
        Si ça ne marche pas, on renvoie None.
        """
        if not artist or not title:
            return None

        try:
            url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
            print(f" Lyrics API : {url}")
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f" Lyrics API HTTP {resp.status_code}")
                return None
            data = resp.json()
            lyrics = data.get("lyrics")
            if not lyrics:
                return None
            return lyrics
        except Exception as e:
            print(f" Erreur API lyrics : {e}")
            return None

    def fetch_lyrics_for_audio(self, audio_file: AudioFile) -> Optional[str]:
        """
        Récupère les paroles pour un AudioFile donné.
        """
        md = audio_file.extract_metadata()
        artist = md.get("artist") or audio_file.filepath.stem
        title = md.get("title") or audio_file.filepath.stem
        return self.fetch_lyrics(artist, title)
