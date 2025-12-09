# 1) API principale : LRCLIB
#👉 URL : https://lrclib.net/
#2) API secondaire (fallback) : Lyrics.ovh

import re
import requests
from urllib.parse import quote


class LyricsResolver:
    """
    Système de récupération de paroles 'intelligent' :

    1) Nettoie les titres (enlève : (Lyrics), (Official Video), (8D Audio), etc.)
    2) Essaie de deviner artiste / titre à partir du nom du fichier : "Artist - Title"
    3) Utilise Spotify (si dispo) pour corriger artiste / titre
    4) Interroge LRCLIB
    5) Fallback sur lyrics.ovh si LRCLIB ne trouve rien
    """

    def __init__(self, spotify_client=None):
        self.spotify = spotify_client

    # -------------------------------------------------------------
    # 1) Nettoyage intelligent du titre
    # -------------------------------------------------------------
    def clean_title(self, title: str) -> str:
        if not title:
            return ""

        t = title

        # Retirer les parties entre () ou [] qui contiennent des mots parasites
        remove_patterns = [
            r"\(.*lyrics.*\)",
            r"\[.*lyrics.*\]",
            r"\(.*official.*\)",
            r"\[.*official.*\]",
            r"\(.*video.*\)",
            r"\[.*video.*\]",
            r"\(.*audio.*\)",
            r"\[.*audio.*\]",
            r"\(.*8d.*\)",
            r"\[.*8d.*\]",
        ]

        for pat in remove_patterns:
            t = re.sub(pat, "", t, flags=re.IGNORECASE)

        # Retirer les (feat. XXX)
        t = re.sub(r"\(feat[^\)]*\)", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\(ft\.[^\)]*\)", "", t, flags=re.IGNORECASE)

        # Retirer certains mots inutiles hors parenthèses
        extra_noise = [
            r"8d audio",
            r"4k",
            r"hd",
        ]
        for pat in extra_noise:
            t = re.sub(pat, "", t, flags=re.IGNORECASE)

        # Guillemets, espaces en trop, tirets en bord
        t = t.replace("\"", "").replace("“", "").replace("”", "")
        t = t.strip(" -_")
        t = re.sub(r"\s+", " ", t)

        return t

    # -------------------------------------------------------------
    # 2) Deviner artiste/titre depuis le nom du fichier
    # -------------------------------------------------------------
    def guess_from_filename(self, filename: str):
        """
        Ex : 'The Neighbourhood - Softcore (Lyrics).mp3'
        -> ('The Neighbourhood', 'Softcore')
        """
        stem = filename.rsplit(".", 1)[0]
        stem = stem.replace("_", " ")

        if "-" in stem:
            # On ne split qu'une fois : Artiste - Titre - blabla
            left, right = stem.split("-", 1)
            artist = left.strip()
            title_raw = right.strip()
            title = self.clean_title(title_raw)
            return artist, title

        return None, None

    # -------------------------------------------------------------
    # 3) Correction artiste/titre via Spotify
    # -------------------------------------------------------------
    def spotify_fix(self, artist: str, title: str):
        """
        On utilise Spotify pour corriger artiste / titre s'il y a un écart
        (ex : "Softcore (Lyrics)" -> "Softcore")
        """
        if not self.spotify or not title:
            return artist, title

        try:
            query = title
            if artist:
                query = f"{title} {artist}"

            res = self.spotify.search(q=query, type="track", limit=1)
            items = res.get("tracks", {}).get("items", [])
            if not items:
                return artist, title

            track = items[0]
            new_artist = track["artists"][0]["name"]
            new_title = track["name"]

            return new_artist, new_title

        except Exception:
            # En cas de problème, on garde les valeurs d'origine
            return artist, title

    # -------------------------------------------------------------
    # 4) API LRCLIB
    # -------------------------------------------------------------
    def fetch_lrclib(self, artist: str, title: str):
        if not title:
            return None

        title_q = quote(title)
        artist_q = quote(artist or "")

        url = f"https://lrclib.net/api/get?track_name={title_q}&artist_name={artist_q}"
        print(f"[LRCLIB] → {url}")

        try:
            r = requests.get(url, timeout=8)
        except Exception as e:
            print("[LRCLIB] Erreur requête :", e)
            return None

        if r.status_code != 200:
            try:
                print("[LRCLIB] Status:", r.status_code, "| Réponse:", r.text[:200])
            except Exception:
                print("[LRCLIB] Status:", r.status_code)
            return None

        try:
            data = r.json()
        except Exception as e:
            print("[LRCLIB] Erreur JSON:", e)
            return None

        # plainLyrics direct
        lyrics = data.get("plainLyrics")
        if lyrics:
            return lyrics

        # syncedLyrics (liste de {time, line})
        synced = data.get("syncedLyrics")
        if synced and isinstance(synced, list):
            lines = [line.get("line") for line in synced if line.get("line")]
            if lines:
                return "\n".join(lines)

        return None

    # -------------------------------------------------------------
    # 5) API lyrics.ovh (fallback)
    # -------------------------------------------------------------
    def fetch_lyrics_ovh(self, artist: str, title: str):
        if not (artist and title):
            return None

        url = f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"
        print(f"[OVH] → {url}")

        try:
            r = requests.get(url, timeout=8)
        except Exception as e:
            print("[OVH] Erreur requête:", e)
            return None

        if r.status_code != 200:
            return None

        try:
            data = r.json()
        except Exception:
            return None

        return data.get("lyrics")

    # -------------------------------------------------------------
    # MÉTHODE PRINCIPALE : get_lyrics
    # -------------------------------------------------------------
    def get_lyrics(self, artist: str, title: str, filename: str):
        """
        1) Devine artiste/titre depuis le nom du fichier (prioritaire)
        2) Nettoie le titre
        3) Corrige via Spotify (si dispo)
        4) Interroge LRCLIB
        5) Fallback sur lyrics.ovh
        """

        # 1) Essayer de deviner depuis le nom du fichier
        guess_art, guess_title = self.guess_from_filename(filename)
        if guess_art and guess_title:
            artist = guess_art
            title = guess_title

        # 2) Nettoyer le titre
        title = self.clean_title(title)

        # 3) Correction via Spotify si possible
        artist, title = self.spotify_fix(artist, title)

        print(f"[LYRICS RESOLVER] Final → artist='{artist}' | title='{title}'")

        # 4) LRCLIB
        lyrics = self.fetch_lrclib(artist, title)
        if lyrics:
            return lyrics

        # 5) Fallback OVH
        lyrics2 = self.fetch_lyrics_ovh(artist, title)
        if lyrics2:
            return lyrics2

        return None
