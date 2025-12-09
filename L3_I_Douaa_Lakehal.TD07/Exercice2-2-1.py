"""
Ex 2.2.1 — Trier tous les fichiers trouvés (os.walk) par taille décroissante.
Usage:
    py Exercice2-2-1.py [DOSSIER]
"""
import os
import sys
import argparse

def collect_sizes(root):
    out = []
    for path, _, files in os.walk(root):
        for fname in files:
            fpath = os.path.join(path, fname)
            try:
                size = os.path.getsize(fpath)
            except Exception:
                continue
            out.append((size, fpath))
    return out

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Lister les fichiers d'un dossier (récursif) triés par taille.")
    p.add_argument("folder", nargs="?", default=".", help="Dossier à parcourir (défaut: .)")
    args = p.parse_args()
    items = collect_sizes(args.folder)
    for size, fpath in sorted(items, key=lambda t: (-t[0], t[1])):
        print(f"{size:>12}  {fpath}")
