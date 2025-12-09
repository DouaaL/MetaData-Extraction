from typing import Dict, Optional, List
from pathlib import Path
from urllib.parse import quote
import os
import requests

from library.models.audio_file import AudioFile
from library.core.lyricsresolver import LyricsResolver

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
    Gère :
    - Métadonnées enrichies via Spotify
    - Paroles via LyricsResolver
    - Récupération / téléchargement / sauvegarde de la cover d'album (par fichier)
    """

    def __init__(self):

        # --- DEBUG LYRICS (désactivé par défaut) ---
        self.debug_force_lyrics = False
        self.debug_artist = "Coldplay"
        self.debug_title = "Yellow"

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
            except Exception as e:
                print(f"Erreur de connexion Spotify : {e}")
                self.sp = None
        else:
            print("'spotipy' non installé : Spotify désactivé.")

        # Toujours créer le LyricsResolver
        self.lyrics_resolver = LyricsResolver(spotify_client=self.sp)

    # ----------------------------------------------------------
    # COVER – par fichier via MusicBrainz + Cover Art Archive
    # ----------------------------------------------------------
    def ensure_cover_image(self, audio_file: AudioFile) -> Optional[Path]:
        """
        S'assure qu'une cover spécifique existe pour CE fichier :
        - cherche <stem>_cover.jpg dans le dossier du fichier
        - sinon la télécharge via MusicBrainz + Cover Art Archive
        - NE PAS réutiliser la cover d'un autre morceau
        """
        audio_path = Path(audio_file.filepath)
        album_dir = audio_path.parent
        stem = audio_path.stem

        # 1) Chercher une cover spécifique à ce fichier
        specific_cover = album_dir / f"{stem}_cover.jpg"
        if specific_cover.exists():
            print("[ensure_cover_image] Cover spécifique déjà présente :", specific_cover)
            return specific_cover

        # 2) Récupérer les métadonnées existantes
        try:
            md = getattr(audio_file, "metadata", None) or audio_file.extract_metadata() or {}
        except Exception:
            md = {}

        artist = (md.get("artist") or "").strip()
        title = (md.get("title") or "").strip()
        album = (md.get("album") or "").strip()

        import re

        def clean_text(s: str) -> str:
            s = s.replace("_", " ")
            s = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", s)      # enlève extension
            s = re.sub(r"\([^)]*\)", "", s)               # enlève (....)
            s = re.sub(r"\s+", " ", s)
            return s.strip()

        # Si tags vides, deviner depuis le nom de fichier
        if not artist or not title:
            stem_name = clean_text(audio_path.stem)
            parts = [p.strip() for p in stem_name.split("-") if p.strip()]
            if len(parts) >= 2:
                if not artist:
                    artist = parts[0]
                if not title:
                    title = parts[1]
            else:
                if not title:
                    title = stem_name

        artist = clean_text(artist)
        title = clean_text(title)
        album = clean_text(album) if album else ""

        print("[ensure_cover_image] Artist deviné  :", repr(artist))
        print("[ensure_cover_image] Title deviné   :", repr(title))
        print("[ensure_cover_image] Album deviné   :", repr(album))

        if not artist or not title:
            print("[ensure_cover_image] Impossible de deviner artist/title → abandon.")
            return None

        # 3) Tenter MusicBrainz pour CE fichier uniquement
        try:
            cover_path = self._search_musicbrainz_and_download_cover(
                artist=artist,
                title=title,
                album=album,
                dest_dir=album_dir,
                filename_stem=stem,
            )
            if cover_path:
                print("[ensure_cover_image] Cover téléchargée pour ce fichier :", cover_path)
            else:
                print("[ensure_cover_image] Aucune cover trouvée via MusicBrainz pour ce fichier.")
            return cover_path
        except Exception as e:
            print("[ensure_cover_image] Erreur MusicBrainz cover:", e)
            return None

    def _search_musicbrainz_and_download_cover(
        self,
        artist: str,
        title: str,
        album: str,
        dest_dir: Path,
        filename_stem: str,
    ) -> Optional[Path]:
        """
        Utilise MusicBrainz + Cover Art Archive pour récupérer une pochette
        et l'enregistre sous dest_dir / '<stem>_cover.jpg'.
        """
        headers = {
            "User-Agent": "PyMetaPlay/1.0 (contact@example.com)"
        }

        # 1) Requête recording artist + title
        query = f'recording:"{title}" AND artist:"{artist}"'
        url = (
            "https://musicbrainz.org/ws/2/recording/"
            f"?query={quote(query)}&fmt=json&limit=1&inc=releases"
        )
        print("[MB] Requête 1 :", url)

        try:
            resp = requests.get(url, headers=headers, timeout=8)
        except Exception as e:
            print("[MB] Erreur requête :", e)
            return None

        if resp.status_code != 200:
            print("[MB] Erreur HTTP :", resp.status_code)
            return None

        data = resp.json()
        recordings = data.get("recordings") or []
        if not recordings:
            print("[MB] Aucun recording trouvé pour", artist, "/", title)
            return None

        rec = recordings[0]
        releases = rec.get("releases") or []
        if not releases:
            print("[MB] Recording trouvé mais pas de release.")
            return None

        release_id = releases[0].get("id")
        print("[MB] Release choisie :", release_id)
        if not release_id:
            return None

        # 2) Cover Art Archive
        caa_url = f"https://coverartarchive.org/release/{release_id}/front"
        print("[CAA] URL cover :", caa_url)
        try:
            caa_resp = requests.get(caa_url, headers=headers, timeout=8)
        except Exception as e:
            print("[CAA] Erreur requête cover:", e)
            return None

        if caa_resp.status_code != 200:
            print("[CAA] Pas de cover pour release", release_id, "status=", caa_resp.status_code)
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{filename_stem}_cover.jpg"
        try:
            with open(dest_path, "wb") as f:
                f.write(caa_resp.content)
        except Exception as e:
            print("[CAA] Erreur écriture fichier cover :", e)
            return None

        print("[CAA] Cover enregistrée dans :", dest_path)
        return dest_path

    # ----------------------------------------------------------
    # SPOTIFY – Recherche metadata
    # ----------------------------------------------------------
    def search_metadata(self, artist: str, title: str) -> Optional[Dict[str, str]]:
        if not self.sp:
            return None
        if not title:
            return None

        artist = artist or ""
        query = f"track:{title}"
        if artist:
            query += f" artist:{artist}"

        print(f"🔍 Spotify search : {query}")

        try:
            results = self.sp.search(q=query, limit=1, type="track")
            items = results.get("tracks", {}).get("items", [])

            if not items:
                print("Spotify : aucun résultat.")
                return None

            track = items[0]
            album = track.get("album", {})
            release_date = album.get("release_date", "")
            year = release_date.split("-")[0] if release_date else ""
            images = album.get("images", [])
            cover_url = images[0]["url"] if images else ""

            metadata = {
                "title": track.get("name", title),
                "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                "album": album.get("name", ""),
                "year": year if len(year) == 4 else "",
                "genre": "",
                "track_number": str(track.get("track_number", "")),
                "cover_url": cover_url,
            }

            print("Spotify → OK :", metadata["title"])
            return metadata

        except Exception as e:
            print("Erreur Spotify :", e)
            return None

    # ----------------------------------------------------------
    # SPOTIFY – Update file metadata
    # ----------------------------------------------------------
    def update_audio_file_metadata(self, audio_file: AudioFile) -> bool:
        if not self.sp:
            print("Spotify désactivé → update_metadata False.")
            return False

        try:
            current = audio_file.extract_metadata() or {}
        except Exception:
            current = {}

        title = current.get("title") or audio_file.filepath.stem
        artist = current.get("artist") or ""

        enriched = self.search_metadata(artist, title)
        if not enriched:
            return False

        new_md = dict(current)
        for k, v in enriched.items():
            if v:
                new_md[k] = v

        keys = ["title", "artist", "album", "year", "genre", "track_number", "cover_url"]
        changed = any(new_md.get(k) != current.get(k) for k in keys)

        if not changed:
            print("Spotify : rien à mettre à jour.")
            return False

        if not hasattr(audio_file, "metadata") or audio_file.metadata is None:
            audio_file.metadata = dict(current)

        audio_file.metadata.update(new_md)

        try:
            audio_file.save_metadata()
            print("Tags mis à jour ✔️")
        except Exception as e:
            print("Erreur sauvegarde tags :", e)

        return True

    # ----------------------------------------------------------
    # SPOTIFY – Search tracks (GUI)
    # ----------------------------------------------------------
    def search_tracks(self, query: str, limit: int = 10) -> List[Dict[str, object]]:
        if not self.sp:
            return []
        if not query.strip():
            return []

        try:
            results = self.sp.search(q=query, type="track", limit=limit)
        except Exception as e:
            print("Erreur search_tracks :", e)
            return []

        items = results.get("tracks", {}).get("items", [])
        tracks = []

        for t in items:
            album = t.get("album", {})
            year = (album.get("release_date", "") or "").split("-")[0]
            images = album.get("images", [])
            cover = images[0]["url"] if images else ""

            tracks.append({
                "spotify_id": t.get("id"),
                "title": t.get("name", ""),
                "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                "album": album.get("name", ""),
                "year": year,
                "duration": (t.get("duration_ms") or 0) / 1000,
                "preview_url": t.get("preview_url") or "",
                "cover_url": cover,
            })

        return tracks

    # ----------------------------------------------------------
    # LYRICS – via LyricsResolver
    # ----------------------------------------------------------
    def fetch_lyrics_for_audio(self, audio_file: AudioFile) -> Optional[str]:
        md = getattr(audio_file, "metadata", {}) or {}

        artist = md.get("artist") or ""
        title = md.get("title") or ""
        filename = audio_file.filepath.name

        return self.lyrics_resolver.get_lyrics(
            artist=artist,
            title=title,
            filename=filename
        )
