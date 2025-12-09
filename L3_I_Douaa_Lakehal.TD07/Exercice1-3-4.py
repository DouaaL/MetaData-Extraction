"""
Ex 1.3.4 — Générer des diffs de fichiers binaires
- Convertit les fichiers en séquences hexadécimales.
- Aligne les "mots" (groupes d'octets) sur les changements (SequenceMatcher).
- Peut afficher une colonne ASCII (-a).
- Paramètres: offset (-O), length (-l), wordsize (-w).
"""
import argparse
import difflib
from difflib import SequenceMatcher
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")  # forcer UTF-8 sur Windows
except Exception:
    pass


def chr_repr(c, default='.'):
    """Représentation ASCII sûre d'un octet (0..255)."""
    if 32 <= c <= 126:  # caractères imprimables standards
        return chr(c)
    return default

def seq2res(seq, count, txt):
    """
    Transforme une séquence 'seq' (bytes) en ligne:
    - hex groupé par 'count' octets (2 chars par octet)
    - éventuellement une zone ASCII à droite si txt=True
    """
    # hex
    hx = seq.hex()
    # découper tous les 2 chars -> octets, puis regrouper par 'count'
    bytes_hex = [hx[i:i+2] for i in range(0, len(hx), 2)]
    words = []
    for i in range(0, len(bytes_hex), count):
        words.append(" ".join(bytes_hex[i:i+count]))
    left = " | ".join(words) if words else ""
    if not txt:
        return left + "\n"
    # ascii
    ascii_part = "".join(chr_repr(b) for b in seq)
    return f"{left:<60}  ||  {ascii_part}\n"

def file2hex(fname, offset=0, length=-1):
    """
    Lit 'fname' en binaire, applique offset/length, renvoie liste d'octets (chaînes hex 'hh').
    """
    with open(fname, "rb") as f:
        f.seek(max(0, offset), 0)
        data = f.read(None if length is None or length < 0 else length)
    # rendre chaque octet sous forme 'hh'
    return [f"{b:02x}" for b in data]

def hex2seqs(seqa, seqb, count=1, txt=False):
    """
    Transforme deux listes d'octets hex ['hh', ...] en listes de "mots" alignés
    selon les opcodes du SequenceMatcher.
    Retourne (listA, listB) où chaque élément est une ligne (str) prête pour diffs.
    """
    # Rejoindre par octet -> bytes à la fin pour regrouper
    # On garde d'abord en octets numériques
    A = bytes(int(x, 16) for x in seqa)
    B = bytes(int(x, 16) for x in seqb)

    sm = SequenceMatcher(None, A, B, autojunk=False)
    listA, listB = [], []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal' or tag == 'replace':
            # parcourir par blocs 'count' pour garder alignement
            a_chunk = A[i1:i2]
            b_chunk = B[j1:j2]
            # avancer en pas de 'count' mais ne pas perdre le reste
            maxlen = max(len(a_chunk), len(b_chunk))
            pos = 0
            while pos < maxlen:
                a_part = a_chunk[pos:pos+count]
                b_part = b_chunk[pos:pos+count]
                listA.append(seq2res(a_part, count, txt))
                listB.append(seq2res(b_part, count, txt))
                pos += count
        elif tag == 'delete':
            a_chunk = A[i1:i2]
            pos = 0
            while pos < len(a_chunk):
                a_part = a_chunk[pos:pos+count]
                listA.append(seq2res(a_part, count, txt))
                listB.append(seq2res(b"", count, txt))
                pos += count
        elif tag == 'insert':
            b_chunk = B[j1:j2]
            pos = 0
            while pos < len(b_chunk):
                b_part = b_chunk[pos:pos+count]
                listA.append(seq2res(b"", count, txt))
                listB.append(seq2res(b_part, count, txt))
                pos += count
        else:
            # shouldn't occur
            pass
    return listA, listB

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diff binaire/hex (aligne des mots, option ASCII).")
    parser.add_argument("filea", help="Fichier original")
    parser.add_argument("fileb", help="Fichier modifié")
    parser.add_argument("-a", "--ascii", action="store_true", help="Affiche une colonne ASCII")
    parser.add_argument("-O", "--offset", type=int, default=0, help="Offset de départ en octets")
    parser.add_argument("-l", "--length", type=int, default=-1, help="Nombre max d'octets à lire")
    parser.add_argument("-w", "--wordsize", type=int, default=8, help="Taille des mots (en octets)")
    parser.add_argument("-u", "--unified-diff", action="store_true", help="Produit un diff unifié")
    parser.add_argument("-C", "--context-diff", action="store_true", help="Produit un diff contextuel")
    parser.add_argument("-H", "--html-diff", action="store_true", help="Produit un diff HTML")
    args = parser.parse_args()

    # Préparer les séquences hex limitées
    Ahex = file2hex(args.filea, offset=args.offset, length=args.length)
    Bhex = file2hex(args.fileb, offset=args.offset, length=args.length)

    la, lb = hex2seqs(Ahex, Bhex, count=max(1, args.wordsize), txt=args.ascii)

    # Choix du rendu difflib
    if args.unified_diff:
        diff_fun = difflib.unified_diff
        kwargs = {"fromfile": args.filea, "tofile": args.fileb}
    elif args.context_diff:
        diff_fun = difflib.context_diff
        kwargs = {"fromfile": args.filea, "tofile": args.fileb}
    elif args.html_diff:
        html_diff = difflib.HtmlDiff()
        diff_fun = html_diff.make_file
        kwargs = {"fromdesc": args.filea, "todesc": args.fileb, "context": True}
    else:
        diff_fun = difflib.ndiff
        kwargs = {}

    rdiff = diff_fun(la, lb, **kwargs)
    if args.html_diff:
        sys.stdout.write(rdiff)
    else:
        for line in rdiff:
            sys.stdout.write(line)
