#!/usr/bin/env python3
"""Deuxième source : les arrêtés CatNat lus directement dans le Journal officiel.

Source : open data de la DILA (https://echanges.dila.gouv.fr/OPENDATA/JORF/),
publié chaque jour, gratuit et sans clé.

- Chaque jour : traite les nouvelles archives JORF_AAAAMMJJ-HHMMSS.tar.gz.
- Une seule fois (--backfill) : parcourt l'archive complète « Freemium_jorf_global »
  pour récupérer les arrêtés depuis le 1er janvier 2024.

Résultat : data/jo_catnat.json
  {"traites": [...archives déjà lues...],
   "lignes": [[insee, deb, fin, date_jo, statut, nor], ...]}   statut : R = reconnue, X = rejetée
"""
import html, io, json, os, re, sys, tarfile, unicodedata, urllib.request

BASE = "https://echanges.dila.gouv.fr/OPENDATA/JORF/"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "jo_catnat.json")
DEPUIS = "2024-01-01"
UA = {"User-Agent": "lezarde-bot/1.0 (+https://github.com)"}

MOIS = {m: i + 1 for i, m in enumerate(
    ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
     "septembre", "octobre", "novembre", "decembre"])}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\bst\b", "saint", s)
    s = re.sub(r"\bste\b", "sainte", s)
    return s


def get(url, timeout=600):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


# ---------- référentiel des communes (geo.api.gouv.fr) ----------
def referentiel():
    deps = json.load(get("https://geo.api.gouv.fr/departements"))
    coms = json.load(get("https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement&format=json"))
    dep_by_name = {norm(d["nom"]): d["code"] for d in deps}
    idx = {}
    for c in coms:
        idx.setdefault((c["codeDepartement"], norm(c["nom"])), c["code"])
    return dep_by_name, idx, coms


# ---------- lecture des dates ----------
def date_iso(t):
    t = norm(t).replace("1er", "1")
    m = re.search(r"(\d{1,2}) (\d{1,2}) (\d{4})", t)  # 01/07/2025 normalisé en "01 07 2025"
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"(\d{1,2}) ([a-z]+) (\d{4})", t)
    if m and m.group(2) in MOIS:
        d, mo, y = m.groups()
        return f"{y}-{MOIS[mo]:02d}-{int(d):02d}"
    return None


def txt(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").strip()


# ---------- extraction d'un fichier XML du JO ----------
RE_TABLE = re.compile(r"<table.*?</table>", re.S | re.I)
RE_ROW = re.compile(r"<tr.*?</tr>", re.S | re.I)
RE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
RE_REJET = re.compile(r"annexe\s*(ii|2)\b|rejet|non\s+reconnu", re.I)


def parse_xml(raw, dep_by_name, idx, out):
    if b"catastrophe naturelle" not in raw or b"<table" not in raw.lower():
        return 0
    x = raw.decode("utf-8", errors="replace")
    titre = re.search(r"<TITRE_TXT[^>]*>(.*?)</TITRE_TXT>", x, re.S) or re.search(r"<TITREFULL>(.*?)</TITREFULL>", x, re.S)
    if not titre or "reconnaissance de l etat de catastrophe naturelle" not in norm(txt(titre.group(1))):
        return 0
    jo = re.search(r'date_publi="(\d{4}-\d{2}-\d{2})"', x) or re.search(r"<DATE_PUBLI>(\d{4}-\d{2}-\d{2})</DATE_PUBLI>", x)
    if not jo or jo.group(1) < DEPUIS:
        return 0
    jo = jo.group(1)
    nor = (re.search(r'nor="([A-Z0-9]+)"', x) or re.search(r"<NOR>([A-Z0-9]+)</NOR>", x))
    nor = nor.group(1) if nor else ""
    num = re.search(r"<NUM>(.*?)</NUM>", x, re.S)
    statut = "X" if num and RE_REJET.search(txt(num.group(1))) else "R"

    n, pos, dep = 0, 0, None
    for tm in RE_TABLE.finditer(x):
        avant = txt(x[pos:tm.start()])
        if avant:
            statut = "X" if RE_REJET.search(avant[-400:]) else ("R" if re.search(r"annexe\s*(i|1)\b|reconnue", avant[-400:], re.I) else statut)
        pos = tm.end()
        for row in RE_ROW.findall(tm.group(0)):
            cells = [txt(c) for c in RE_CELL.findall(row)]
            p = next((i for i, c in enumerate(cells) if "secheresse" in norm(c)), None)
            if p is None or p < 1:
                continue
            dates = [d for d in (date_iso(c) for c in cells[p + 1:]) if d]
            if len(dates) < 2:
                continue
            commune = cells[p - 1]
            if p >= 2 and norm(cells[p - 2]) in dep_by_name:
                dep = dep_by_name[norm(cells[p - 2])]
            if not dep:
                continue
            code = idx.get((dep, norm(commune)))
            if not code:
                print(f"  ? commune non trouvée : {commune} ({dep}) – {nor}")
                continue
            out.add((code, dates[0], dates[1], jo, statut, nor))
            n += 1
    return n


def lire_archive(url, dep_by_name, idx, out):
    n = 0
    with get(url, timeout=3600) as r, tarfile.open(fileobj=r, mode="r|gz") as tf:
        for m in tf:
            if not m.isfile() or not m.name.endswith(".xml"):
                continue
            f = tf.extractfile(m)
            if f:
                n += parse_xml(f.read(), dep_by_name, idx, out)
    return n


def main():
    backfill = "--backfill" in sys.argv
    etat = {"traites": [], "lignes": []}
    if os.path.exists(OUT):
        etat = json.load(open(OUT, encoding="utf-8"))
    out = set(tuple(l) for l in etat["lignes"])
    dep_by_name, idx, _ = referentiel()

    liste = get(BASE).read().decode("utf-8", errors="replace")
    archives = sorted(set(re.findall(r'href="((?:Freemium_jorf_global|JORF)_[\d-]+\.tar\.gz)"', liste)))
    a_lire = [a for a in archives if a.startswith("JORF_") and a not in etat["traites"]]
    if backfill:
        a_lire = [a for a in archives if a.startswith("Freemium")][-1:] + a_lire

    for a in a_lire:
        print(f"Lecture {a} …")
        n = lire_archive(BASE + a, dep_by_name, idx, out)
        print(f"  {n} lignes sécheresse")
        etat["traites"].append(a)

    etat["traites"] = sorted(set(etat["traites"]))[-400:]
    etat["lignes"] = sorted(out)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(etat, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(out)} lignes sécheresse issues du JO -> {OUT}")


if __name__ == "__main__":
    main()
