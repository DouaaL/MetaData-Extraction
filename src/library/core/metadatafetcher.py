from typing import Dict, Optional
from pathlib import Path
from urllib.parse import quote
import os
import requests
import re
import time

from library.models.audio_file import AudioFile
from library.core.lyricsresolver import LyricsResolver

# Désactiver les warnings HTTPS non vérifiés (MB / CAA)
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
    - Cover via MusicBrainz / Cover Art Archive (par fichier)
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

        # Pour respecter le rate-limit MusicBrainz (1 req/s)
        self._last_mb_request_ts: float = 0.0

    # ----------------------------------------------------------
    # 🔧 Rate limit MusicBrainz
    # ----------------------------------------------------------
    def _rate_limit(self, min_interval: float = 1.1):
        """
        MusicBrainz demande ~1 requête/s max par client.
        On ajoute un petit sleep si on enchaîne trop vite.
        """
        now = time.time()
        elapsed = now - self._last_mb_request_ts
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_mb_request_ts = time.time()

    # ----------------------------------------------------------
    # 🔧 1. Split intelligent artiste/titre si tags manquants
    # ----------------------------------------------------------
    def smart_split_filename(self, stem: str):
        """
        Exemples :
        - "Artist - Title" → ("Artist", "Title")
        - "Kevin MacLeod - Movement Proposition" → ("Kevin MacLeod", "Movement Proposition")
        - "UnknownTrack" → ("", "UnknownTrack")
        """
        parts = stem.split(" - ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "", stem.strip()

    # ----------------------------------------------------------
    # 🎨 2. Cover par fichier
    # ----------------------------------------------------------
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

    # ----------------------------------------------------------
    # 🎨 2. Cover par fichier
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

        raw_artist = (md.get("artist") or "").strip()
        raw_title = (md.get("title") or "").strip()
        raw_album = (md.get("album") or "").strip()

        print(f"[cover] raw_artist={raw_artist!r}, raw_title={raw_title!r}")

        # Deviner à partir du nom de fichier
        filename_artist, filename_title = self.smart_split_filename(
            self.clean_text(audio_path.stem)
        )
        print(f"[cover] filename_artist={filename_artist!r}, filename_title={filename_title!r}")

        # --- Choix de l'artiste ---
        # Si le tag est "Artiste inconnu" ou autre générique -> on prend le filename
        if self._is_generic_artist(raw_artist):
            artist = filename_artist
        else:
            artist = raw_artist or filename_artist

        # --- Choix du titre ---
        # Si le tag titre est vide ou ressemble trop à "Artist - Title", on prend filename_title
        if raw_title and " - " not in raw_title:
            title = raw_title
        else:
            # soit vide, soit "Artist - Title" -> on préfère le title extrait du filename
            title = filename_title or raw_title

        album = raw_album

        artist = self.clean_text(artist)
        title = self.clean_text(title)
        album = self.clean_text(album) if album else ""

        print(f"[cover] final artist={artist!r}, title={title!r}, album={album!r}")

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


    def clean_text(self, s: str) -> str:
        s = s.replace("_", " ")
        s = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", s)  # enlève extension
        s = re.sub(r"\([^)]*\)", "", s)            # enlève (....)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    # ----------------------------------------------------------
    # 🎨 3. Appel MusicBrainz + CoverArt
    # ----------------------------------------------------------
    def _search_musicbrainz_and_download_cover(
        self, artist: str, title: str, album: str, dest_dir: Path, filename_stem: str
    ) -> Optional[Path]:

        headers = {
            "User-Agent": "PyMetaPlay/1.0 (https://example.com; contact@example.com)"
        }

        try:
            # → Requête recording
            if artist and title:
                query = f'recording:"{title}" AND artist:"{artist}"'
            elif title:
                query = f'recording:"{title}"'
            else:
                query = title or artist

            url = (
                "https://musicbrainz.org/ws/2/recording/"
                f"?query={quote(query)}&fmt=json&limit=1&inc=releases"
            )

            print("[MB] URL:", url)

            # Respect rate-limit MusicBrainz
            self._rate_limit()
            # ⚠ MB : verify=False à cause de ton environnement SSL
            resp = requests.get(url, headers=headers, timeout=8, verify=False)
            print("[MB] status:", resp.status_code)

            if resp.status_code != 200:
                print("[MB] body (début):", resp.text[:400])
                return None

            data = resp.json()
            recordings = data.get("recordings") or []
            if not recordings:
                print("[MB] Aucun recording trouvé")
                return None

            releases = recordings[0].get("releases") or []
            if not releases:
                print("[MB] Aucun release avec cette recording")
                return None

            release_id = releases[0]["id"]
            print("[MB] release choisi:", release_id)

            # → Cover Art Archive
            caa_url = f"https://coverartarchive.org/release/{release_id}/front"
            print("[CAA] URL:", caa_url)

            # ⚠ CAA : verify=False aussi (même problème SSL que MB)
            self._rate_limit()
            img = requests.get(caa_url, headers=headers, timeout=8, verify=False)
            print("[CAA] status:", img.status_code)

            if img.status_code != 200:
                print("[CAA] Pas de cover pour ce release")
                return None

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f"{filename_stem}_cover.jpg"

            with open(dest_path, "wb") as f:
                f.write(img.content)

            print("[cover] Cover téléchargée:", dest_path)
            return dest_path

        except Exception as e:
            print("[MB] Exception:", e)
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
    # 🎧 5. Mise à jour metadata audio_file (mémoire ONLY)
    # ----------------------------------------------------------
    def update_audio_file_metadata(self, audio_file: AudioFile) -> bool:
        if not self.sp:
            return False

        try:
            current = audio_file.extract_metadata() or {}
        except Exception:
            current = {}

        enriched = self.search_metadata(
            current.get("artist") or "",
            current.get("title") or audio_file.filepath.stem,
        )

        if not enriched:
            return False

        if not audio_file.metadata:
            audio_file.metadata = dict(current)

        audio_file.metadata.update(enriched)

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
