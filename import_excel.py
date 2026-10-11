# -*- coding: utf-8 -*-
"""Importe les données d'un classeur « Ferme_AGRO_.xlsm / .xlsx » dans la base.

Usage sur ordinateur :  python import_excel.py Ferme_AGRO_.xlsm [ferme.db]
Dans l'application   :  bouton « Importer depuis Excel » (menu Données).
"""
import sys
from datetime import date, datetime

import core
from core import ValidationError

FEUILLES = {  # nom Excel -> (clé, colonnes utiles)
    "Parcelles": "parcelles", "Activites": "activites", "Rendement": "recoltes",
    "Depenses": "depenses", "Recette": "recettes", "Caisse": "caisse",
    "Les charge annuel": "charges",
}


def _num(v):
    if v is None or isinstance(v, str) and v.strip().startswith("="):
        return None
    try:
        x = float(str(v).replace(" ", "").replace(",", "."))
        return x
    except ValueError:
        return None


def _date(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    try:
        return core.parse_date(str(v))
    except ValidationError:
        return None


def _txt(v):
    if v is None or (isinstance(v, str) and v.strip().startswith("=")):
        return ""
    return str(v).strip()


def _lignes(wb, nom):
    if nom not in wb.sheetnames:
        return []
    return [r for r in wb[nom].iter_rows(min_row=2, values_only=True)]


def import_classeur(db, chemin, remplacer=False):
    """Retourne {table: nombre de lignes importées}. Refuse si la base contient déjà des données."""
    from openpyxl import load_workbook
    if not remplacer and any(db.count(t) for t in core.TABLES):
        raise ValidationError("La base contient déjà des données : importez dans une "
                              "installation vide (ou réinitialisez d'abord).")
    wb = load_workbook(chemin, read_only=True, data_only=False)
    if remplacer:
        for t in core.TABLES:
            db.con.execute("DELETE FROM %s" % t)
    n = dict.fromkeys(core.TABLES, 0)
    ins = db.con.execute

    for r in _lignes(wb, "Parcelles"):
        r = tuple(r) + (None,) * 9
        num, sup, cult, semis, rec, cyc, an, code, fin = r[:9]
        if not _txt(num) or _num(sup) is None or not _txt(cult):
            continue
        cyc, an = _num(cyc), _num(an)
        code = _txt(code) or "%s-%s%s" % (int(an or 0), _txt(num), int(cyc or 0))
        ins("INSERT OR IGNORE INTO parcelles(numero,superficie,culture,date_semis,"
            "date_recolte,cycle,annee,code,date_fin_recolte) VALUES(?,?,?,?,?,?,?,?,?)",
            (_txt(num), _num(sup), _txt(cult).upper(), _date(semis), _date(rec),
             int(cyc) if cyc else None, int(an) if an else None, code, _date(fin)))
        n["parcelles"] += 1

    for r in _lignes(wb, "Activites"):
        d, typ, code, intr = (tuple(r) + (None,) * 4)[:4]
        if _date(d) and _txt(typ) and _txt(code):
            ins("INSERT INTO activites(date,type_activite,code,intrant) VALUES(?,?,?,?)",
                (_date(d), _txt(typ), _txt(code), _txt(intr)))
            n["activites"] += 1

    for r in _lignes(wb, "Rendement"):
        d, code, sacs = (tuple(r) + (None,) * 3)[:3]
        if _date(d) and _txt(code) and _num(sacs):
            ins("INSERT INTO recoltes(date,code,sacs) VALUES(?,?,?)",
                (_date(d), _txt(code), _num(sacs)))
            n["recoltes"] += 1

    for r in _lignes(wb, "Depenses"):
        d, cat, mt, code = (tuple(r) + (None,) * 4)[:4]
        if _date(d) and _txt(cat) and _num(mt) and _txt(code):
            ins("INSERT INTO depenses(date,categorie,montant,code) VALUES(?,?,?,?)",
                (_date(d), _txt(cat), _num(mt), _txt(code)))
            n["depenses"] += 1

    for r in _lignes(wb, "Recette"):
        d, prod, q, p, _m, code = (tuple(r) + (None,) * 6)[:6]
        if _date(d) and _txt(prod) and _num(q) and _num(p) and _txt(code):
            ins("INSERT INTO recettes(date,produit,quantite,prix_unitaire,montant,code)"
                " VALUES(?,?,?,?,?,?)",
                (_date(d), _txt(prod), _num(q), _num(p), _num(q) * _num(p), _txt(code)))
            n["recettes"] += 1

    for r in _lignes(wb, "Caisse"):
        d, motif, ent, sor = (tuple(r) + (None,) * 4)[:4]
        if _date(d) and _txt(motif) and (_num(ent) or _num(sor)):
            ins("INSERT INTO caisse(date,motif,entree,sortie) VALUES(?,?,?,?)",
                (_date(d), _txt(motif), _num(ent) or 0, _num(sor) or 0))
            n["caisse"] += 1

    for r in _lignes(wb, "Les charge annuel"):
        r = tuple(r) + (None,) * 7
        mat, mt, duree = r[0], r[1], r[2]
        if _txt(mat) and _num(mt) and _num(duree):
            ins("INSERT INTO materiel(nom,montant,duree) VALUES(?,?,?)",
                (_txt(mat), _num(mt), _num(duree)))
            n["materiel"] += 1
        if _txt(r[5]) and _num(r[6]):
            ins("INSERT INTO charges(nom,montant) VALUES(?,?)", (_txt(r[5]), _num(r[6])))
            n["charges"] += 1
    db.con.commit()
    wb.close()
    return n


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    base = core.Db(sys.argv[2] if len(sys.argv) > 2 else "ferme.db")
    print(import_classeur(base, sys.argv[1]))
