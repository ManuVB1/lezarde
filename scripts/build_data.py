#!/usr/bin/env python3
"""Télécharge la base GASPAR (Géorisques) et produit data/secheresse.json.

Lancé chaque jour par GitHub Actions (.github/workflows/maj-georisques.yml).
Aucun serveur : le fichier JSON est publié avec le site sur GitHub Pages.
"""
import csv, io, json, sys, unicodedata, urllib.request, zipfile, datetime, os

URL = "https://files.georisques.fr/GASPAR/gaspar.zip"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "secheresse.json")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum() or ch == "_")


def pick(headers, *cands):
    """Retrouve une colonne même si son nom change un peu d'une version à l'autre."""
    h = {norm(x): x for x in headers}
    for c in cands:
        for k, orig in h.items():
            if c in k:
                return orig
    raise KeyError(f"Colonne introuvable parmi {cands} dans {headers}")


def iso(d):
    d = (d or "").strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(d, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "lezarde-bot/1.0"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if "catnat" in n.lower() and n.lower().endswith(".csv"))
    text = z.read(name).decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t")
    rows = csv.DictReader(io.StringIO(text), dialect=dialect)

    c_insee = pick(rows.fieldnames, "code_commune", "cod_commune", "code_insee", "insee")
    c_nom = pick(rows.fieldnames, "lib_commune", "libelle_commune", "commune")
    c_risk = pick(rows.fieldnames, "lib_risque", "libelle_risque")
    c_deb = pick(rows.fieldnames, "dat_deb", "date_debut")
    c_fin = pick(rows.fieldnames, "dat_fin", "date_fin")
    c_jo = pick(rows.fieldnames, "dat_pub_jo", "publication_jo")

    communes, n = {}, 0
    for r in rows:
        if "secheresse" not in norm(r[c_risk]):
            continue
        jo = iso(r[c_jo])
        if not jo:
            continue
        code = r[c_insee].strip().zfill(5)
        entry = communes.setdefault(code, [r[c_nom].strip(), []])
        item = [iso(r[c_deb]), iso(r[c_fin]), jo]
        if item not in entry[1]:
            entry[1].append(item)
            n += 1

    if n < 1000:  # garde-fou : on n'écrase pas les données si le fichier source est cassé
        sys.exit(f"Seulement {n} arrêtés trouvés : fichier source suspect, mise à jour annulée.")

    # ----- 2e source : Journal officiel (scripts/jo_catnat.py) + toutes les communes -----
    for v in communes.values():
        v.append([])  # [nom, arrêtés reconnus, demandes rejetées]
    n_jo = 0
    try:
        req = urllib.request.Request("https://geo.api.gouv.fr/communes?fields=nom,code&format=json",
                                     headers={"User-Agent": "lezarde-bot/1.0"})
        for c in json.load(urllib.request.urlopen(req, timeout=120)):
            communes.setdefault(c["code"], [c["nom"], [], []])
    except Exception as e:
        print("Liste des communes indisponible :", e)
    jo_path = os.path.join(os.path.dirname(OUT), "jo_catnat.json")
    if os.path.exists(jo_path):
        def d(s):
            return datetime.date.fromisoformat(s)
        for code, deb, fin, jo, statut, nor in json.load(open(jo_path, encoding="utf-8"))["lignes"]:
            if code not in communes:
                continue
            liste = communes[code][1] if statut == "R" else communes[code][2]
            doublon = any(x[0][:7] == deb[:7] and x[1][:7] == fin[:7] and abs((d(x[2]) - d(jo)).days) <= 15 for x in liste)
            if not doublon:
                liste.append([deb, fin, jo])
                n_jo += 1

    for v in communes.values():
        v[1].sort(key=lambda x: x[2], reverse=True)
        v[2].sort(key=lambda x: x[2], reverse=True)
        if not v[2]:
            v.pop()

    out = {
        "maj": datetime.date.today().isoformat(),
        "source": "Géorisques (GASPAR) + Journal officiel (DILA)",
        "communes": dict(sorted(communes.items())),
    }
    print(f"{n_jo} arrêtés ajoutés depuis le Journal officiel")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(communes)} communes, {n} arrêtés sécheresse -> {OUT}")


if __name__ == "__main__":
    main()
