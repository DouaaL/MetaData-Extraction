"""
Exercice1-2.py — Ex 1.2 : contrôle d'intégrité (taille + SHA-256).

- --save : parcourt le dossier et enregistre {fichier: [taille, hash]} dans un JSON.
- par défaut : compare l'état actuel aux empreintes du JSON.

Exemples :
    py Exercice1-2.py [DOSSIER] --save -H stored_hash.json
    py Exercice1-2.py [DOSSIER] -H stored_hash.json
"""

import os
import sys
import json
import argparse
import hashlib

HASH_FUN = "sha256"        # algorithme de hachage
CHUNK = 1024 * 1024        # lecture par blocs (1 Mo)


def hash_file(path):
    """
    Retourne (taille, empreinte_hex) pour 'path'.

    L'empreinte est la chaîne hexadécimale (hexdigest) du hash.
    """
    size = os.path.getsize(path)
    h = hashlib.new(HASH_FUN)
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return size, h.hexdigest()  # hexdigest = hash en lettres/chiffres (base 16)


def load_infos(json_path):
    """
    Charge le JSON des empreintes. Format attendu :
    { "chemin_absolu": [taille, empreinte_hex], ... }
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {os.path.abspath(k): (v[0], v[1]) for k, v in data.items()}


def save_infos(json_path, infos):
    """
    Sauvegarde { chemin_absolu: [taille, empreinte_hex] } dans un JSON.
    """
    out = {os.path.abspath(k): [v[0], v[1]] for k, v in infos.items()}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def main():
    p = argparse.ArgumentParser(
        description="Contrôle d'intégrité via taille + SHA-256 (save ou verify)."
    )
    p.add_argument("source", nargs="?", default=".", help="Dossier à parcourir (défaut: .)")
    p.add_argument("-s", "--save", action="store_true",
                   help="Sauvegarder les empreintes (au lieu de vérifier).")
    p.add_argument("-H", "--hash-file", default="./stored_hash.json",
                   help="Fichier JSON d'empreintes (lecture/écriture).")
    args = p.parse_args()

    if args.save:
        # mode enregistrement
        infos = {}
        for root, _, files in os.walk(args.source):
            for name in files:
                path = os.path.abspath(os.path.join(root, name))
                try:
                    size, hx = hash_file(path)
                    infos[path] = (size, hx)
                    print(f"[OK] {path}")
                except OSError:
                    print(f"[WARN] Lecture impossible: {path}")
        save_infos(args.hash_file, infos)
        print(f"[DONE] Empreintes écrites dans {args.hash_file}")
        sys.exit(0)

    # mode vérification
    if not os.path.exists(args.hash_file):
        print(f"[ERR] Fichier d'empreintes introuvable: {args.hash_file}")
        sys.exit(2)

    ref = load_infos(args.hash_file)
    vus = set()
    ok = 0
    err = 0

    for root, _, files in os.walk(args.source):
        for name in files:
            path = os.path.abspath(os.path.join(root, name))
            vus.add(path)
            try:
                size, hx = hash_file(path)
            except OSError:
                print(f"[ERR] Lecture impossible: {path}")
                err += 1
                continue

            if path not in ref:
                print(f"[NEW] Nouveau fichier: {path}")
                err += 1
                continue

            old_size, old_hx = ref[path]
            if size != old_size:
                print(f"[SIZE] {path} (ancien={old_size}, nouveau={size})")
                err += 1
            elif hx != old_hx:
                print(f"[HASH] {path} (différent)")
                err += 1
            else:
                ok += 1
                print(f"[OK] {path}")

    # fichiers attendus mais manquants
    for missing in set(ref.keys()) - vus:
        print(f"[MISS] Manquant: {missing}")
        err += 1

    if err:
        print(f"[RESULT] {ok} OK, {err} erreur(s).")
        sys.exit(2)
    else:
        print(f"[RESULT] {ok} OK, 0 erreur.")
        sys.exit(0)


if __name__ == "__main__":
    main()
