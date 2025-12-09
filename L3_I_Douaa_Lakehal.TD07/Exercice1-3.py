"""
Ex 1.3 — Diff de deux fichiers texte (difflib)

Usage :
    py Exercice1-3.py A.txt B.txt
    py Exercice1-3.py A.txt B.txt -u
    py Exercice1-3.py A.txt B.txt -C
    py -X utf8 Exercice1-3.py A.txt B.txt -H > diff.html 
"""

import argparse
import difflib
import os
from datetime import datetime

def file2list(path):
    """Lit un fichier UTF-8 et renvoie la liste des lignes (avec \n)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines(True)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Produit le diff de deux fichiers")
    p.add_argument("filea", help="Fichier original")
    p.add_argument("fileb", help="Version modifiée")
    p.add_argument("-u", "--unified-diff", action="store_true", help="Diff unifié")
    p.add_argument("-C", "--context-diff", action="store_true", help="Diff contextuel")
    p.add_argument("-H", "--html-diff", action="store_true", help="Diff HTML")
    args = p.parse_args()

    a = file2list(args.filea)
    b = file2list(args.fileb)

    da = datetime.fromtimestamp(os.path.getmtime(args.filea)).isoformat()
    db = datetime.fromtimestamp(os.path.getmtime(args.fileb)).isoformat()

    if args.unified_diff:
        diff = difflib.unified_diff(a, b,
                                    fromfile=args.filea, tofile=args.fileb,
                                    fromfiledate=da, tofiledate=db)
        is_html = False
    elif args.context_diff:
        diff = difflib.context_diff(a, b,
                                    fromfile=args.filea, tofile=args.fileb,
                                    fromfiledate=da, tofiledate=db)
        is_html = False
    elif args.html_diff:
        diff = difflib.HtmlDiff().make_file(
            a, b,
            fromdesc=f"{args.filea} {da}",
            todesc=f"{args.fileb} {db}",
            context=True
        )
        is_html = True
    else:
        diff = difflib.ndiff(a, b)
        is_html = False

    if is_html:
        print(diff, end="")
    else:
        for line in diff:
            print(line, end="")
