"""
Ex 2.2.2 — Parcours d'un dossier, calcul d'un "poids" avec atime/mtime/ctime,
           détection d'incohérences, tri par (poids, ctime, mtime, atime).

Règles :
- incohérence ctime vs (atime/mtime) -> +8
- incohérence atime vs mtime        -> +4
- +1 par différence entre deux dates (chaque couple différent)

Usage :
    py Exercice2-2-2.py [DOSSIER]
"""

import os
import argparse

def weight_from_times(at, mt, ct):
    """Calcule le score/poids selon les règles de l'énoncé."""
    w = 0
    # 1) ctime incohérent par rapport à atime/mtime
    if mt < ct or at < ct:
        w += 8
    # 2) atime vs mtime incohérents (ici : s'ils sont différents)
    if at != mt:
        w += 4
    # 3) +1 pour chaque différence de dates (3 couples)
    if at != mt: w += 1
    if at != ct: w += 1
    if mt != ct: w += 1
    return w

def iter_paths(root):
    """
    Générateur qui émet :
      (chemin_dossier, True)  pour chaque dossier
      (chemin_fichier, False) pour chaque fichier

    On utilise 'yield' pour envoyer un élément à la fois .
    """
    for path, _dirs, files in os.walk(root):
        yield path, True            # d'abord le dossier courant
        for f in files:             # puis chaque fichier dedans
            yield os.path.join(path, f), False

if __name__ == "__main__":
    # Arguments
    p = argparse.ArgumentParser(description="Score basé sur atime/mtime/ctime (parcours récursif).")
    p.add_argument("folder", nargs="?", default=".", help="Dossier racine (défaut: .)")
    args = p.parse_args()

    # Petit garde-fou : la source doit être un dossier
    if not os.path.isdir(args.folder):
        print(f"[ERR] La source n'est pas un dossier : {args.folder}")
        raise SystemExit(2)

    rows = []
    for pth, is_dir in iter_paths(args.folder):
        try:
            # Récupération des 3 dates (en secondes epoch)
            at = os.path.getatime(pth)   # dernier accès
            mt = os.path.getmtime(pth)   # dernière modif contenu
            ct = os.path.getctime(pth)   # création (Windows) / changement métadonnées (Unix)
        except OSError:
            # Si on ne peut pas lire les métadonnées, on ignore
            continue

        w = weight_from_times(at, mt, ct)
        typ = "[DIR]" if is_dir else "FILE"
        rows.append((w, ct, mt, at, typ, pth))

    # Tri : (poids, ctime, mtime, atime, chemin)
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3], r[5]))

    # Affichage
    print(f"{'WEIGHT':>6}  {'CTIME':>14}  {'MTIME':>14}  {'ATIME':>14}  TYPE   PATH")
    for w, ct, mt, at, typ, pth in rows:
        print(f"{w:6d}  {ct:14.3f}  {mt:14.3f}  {at:14.3f}  {typ:4s}  {pth}")
