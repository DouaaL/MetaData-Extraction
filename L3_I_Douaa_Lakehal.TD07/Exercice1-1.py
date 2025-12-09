"""
Le module ici est : Exercice1-1.py

Exercice 1.1 — Afficher les caractéristiques des fichiers d'une arborescence.

Ce script utilise la bibliothèque `python-magic` (libmagic) si elle est disponible,
sinon il bascule vers le module standard `mimetypes` (moins précis).

Il parcourt récursivement un dossier (par défaut le dossier courant '.') et affiche pour chaque fichier :
    - le chemin complet
    - le type MIME
    - l'encodage
    - le type lisible détecté

"""

import os
import sys
import argparse


def try_import_magic():
    """
    Tente d'importer le module `magic` (python-magic).

    Returns
    -------
    module | None
        Le module importé s'il est disponible, sinon None.

    """
    try:
        import magic  
        return magic
    except Exception:
        return None

def detect_with_magic(magic_mod, path, only_mime=False):
    """
    Détecte le type de fichier à l'aide du module `magic`.

    Paramètres
    ----------
    magic_mod : module
        Module `magic` importé dynamiquement.
    path : str
        Chemin complet du fichier à analyser.
    only_mime : bool, optional
        Si True, renvoie uniquement le type MIME.

    Returns
    -------
    tuple[str, str, str]
        (mime_type, encoding, type_name)
    """

# On vérifie d'abord si le module "magic" possède la méthode
    # "detect_from_filename" 
    if hasattr(magic_mod, "detect_from_filename"):
        # On appelle cette méthode pour obtenir les informations sur le fichier.
        # Elle renvoie un objet avec 3 attributs : name, mime_type, encoding.
        info = magic_mod.detect_from_filename(path)

        # On renvoie ces informations sous forme de tuple.
        # Si une des valeurs est absente, on met "unknown" à la place.
        return (
            info.mime_type or "unknown",
            info.encoding or "unknown",
            info.name or "unknown",
        )

    # Sinon, si l'objet "magic_mod" possède la méthode "from_file"
    # (c’est le cas de la version utilisée sur Windows comme dans mon cas).
    elif hasattr(magic_mod, "from_file"):
        # Si l’utilisateur veut uniquement le type MIME (--mime activé)
        if only_mime:
            # On appelle "from_file" avec mime=True pour ne renvoyer que le type MIME.
            mime = magic_mod.from_file(path, mime=True)

            # On retourne un tuple (MIME, encodage inconnu, type inconnu)
            return (mime or "unknown", "unknown", "unknown")
        else:
            # Sinon, on récupère le nom de type complet du fichier
            name = magic_mod.from_file(path)

            # On retourne "unknown" pour MIME et encodage (non fournis par cette API).
            return ("unknown", "unknown", name or "unknown")

    # Si le module ne possède aucune des deux méthodes (cas très rare),
    # on retourne des valeurs par défaut "unknown".
    else:
        return ("unknown", "unknown", "unknown")


def detect_fallback(path, only_mime=False):
    """
    Fallback : détection du type de fichier avec `mimetypes`.

    Paramètres
    ----------
    path : str
        Chemin du fichier.
    only_mime : bool, optional
        Si True, renvoie uniquement le type MIME.

    Returns
    -------
    tuple[str, str, str]
        (mime_type, encoding, "fallback (mimetypes)")
    """
    import mimetypes

    mime, enc = mimetypes.guess_type(path)
    return (mime or "unknown", enc or "unknown", "fallback (mimetypes)")


def main():
    """
    Point d'entrée principal du script.

    Analyse les arguments de ligne de commande puis affiche, pour chaque
    fichier de l'arborescence, les informations de type MIME/encodage/type.

    Options
    -------
    --mime : n'affiche que le type MIME
    """
    parser = argparse.ArgumentParser(
        description=(
            "Lister type MIME / encodage / nom de type pour tous les fichiers "
            "d'un dossier (récursif)."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Dossier à parcourir (défaut: .)",
    )
    parser.add_argument(
        "--mime",
        action="store_true",
        help="N'afficher que le type MIME",
    )
    args = parser.parse_args()

    magic_mod = try_import_magic()

    for root, _, files in os.walk(args.folder):
        for fname in files:
            fpath = os.path.join(root, fname)
            if magic_mod:
                mime, enc, name = detect_with_magic(
                    magic_mod, fpath, only_mime=args.mime
                )
            else:
                mime, enc, name = detect_fallback(fpath, only_mime=args.mime)

            if args.mime:
                print(f"{fpath}\tMIME={mime}")
            else:
                print(f"{fpath}\tMIME={mime}\tENC={enc}\tTYPE={name}")


if __name__ == "__main__":
    main()
