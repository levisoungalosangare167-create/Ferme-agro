# -*- coding: utf-8 -*-
"""Gestion Ferme - données et règles métier (SQLite, 100 % hors ligne).

Ce module ne dépend pas de Kivy : il peut être testé sur ordinateur.
Il reprend la logique du classeur Excel « Ferme_AGRO_.xlsm » :
  Parcelles, Activités, Récoltes (Rendement), Dépenses, Recettes, Caisse,
  Charges annuelles, Calendrier, Performance agricole, Analyse.
"""
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
        "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
CULTURES_CALENDRIER = ["TOMATE", "OIGNON", "POIVRON", "CELERI",
                       "AUBERGINE", "GOMBO", "PIMENT"]
TYPES_SAISIE = ["Activité culturale", "Récolte", "Dépense", "Recette"]

# Palette du calendrier (couleurs relevées dans le fichier Excel)
# Légende : vert foncé = produit rare sur le marché ; plus on s'éloigne du vert
# vers le rouge, plus il est abondant.
PALETTE = {"b": "#1B5E20", "v": "#8BC34A", "a": "#F08A24", "r": "#D62828",
           "n": "#FFFFFF"}
LEGENDE = [("b", "Rare sur le marché"), ("v", "Assez rare"),
           ("a", "Abondant"), ("r", "Très abondant"), ("n", "Pas de donnée")]
RARE = PALETTE["b"]
_CAL_DEFAUT = [  # une ligne par mois, une lettre par culture (ordre ci-dessus)
    "abaavbb", "aaarvbb", "ararbbb", "arbabbb", "brbabbb", "babbbbb",
    "babbbab", "babbbab", "bbbbbab", "bbbbbab", "abavvbb", "abavvbb"]

TABLES = ("parcelles", "activites", "recoltes", "depenses", "recettes",
          "caisse", "materiel", "charges")


class ValidationError(ValueError):
    """Erreur de saisie affichable telle quelle à l'utilisateur."""


# ----------------------------------------------------------------- masques
def parse_date(text):
    """'JJ/MM/AAAA' (ou 'Le JJ/MM/AAAA', ou ISO) -> 'AAAA-MM-JJ'."""
    text = (text or "").strip()
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        j, mo, a = map(int, m.groups())
    else:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not m:
            raise ValidationError("Date invalide : écrivez JJ/MM/AAAA")
        a, mo, j = map(int, m.groups())
    try:
        return date(a, mo, j).isoformat()
    except ValueError:
        raise ValidationError("Cette date n'existe pas : %s" % text)


def fmt_date(iso):
    if not iso:
        return ""
    a, m, j = iso.split("-")
    return "%s/%s/%s" % (j, m, a)


def today_fr():
    return fmt_date(date.today().isoformat())


def parse_number(text, label, strict_positive=True, integer=False):
    raw = str(text if text is not None else "").strip().replace(" ", "")
    raw = raw.replace(",", ".")
    if raw == "":
        raise ValidationError("%s : champ obligatoire" % label)
    try:
        val = float(raw)
    except ValueError:
        raise ValidationError("%s : nombre invalide" % label)
    if strict_positive and val <= 0:
        raise ValidationError("%s doit être supérieur à 0" % label)
    if val < 0:
        raise ValidationError("%s ne peut pas être négatif" % label)
    if integer:
        if val != int(val):
            raise ValidationError("%s doit être un nombre entier" % label)
        return int(val)
    return val


def norm_year(text):
    digits = re.sub(r"\D", "", str(text or ""))
    if len(digits) == 4:
        digits = digits[2:]
    if len(digits) != 2:
        raise ValidationError("Année : 2 chiffres (ex. 26) ou 4 chiffres")
    return int(digits)


def required(text, label):
    val = (text or "").strip()
    if not val:
        raise ValidationError("%s : champ obligatoire" % label)
    return val


def money(x):
    return ("{:,.0f}".format(x or 0)).replace(",", " ")


# ------------------------------------------------------------------ schéma
SCHEMA = """
CREATE TABLE IF NOT EXISTS parcelles(
  id INTEGER PRIMARY KEY, numero TEXT NOT NULL, superficie REAL NOT NULL,
  culture TEXT NOT NULL, date_semis TEXT, date_recolte TEXT, cycle INTEGER,
  annee INTEGER, code TEXT NOT NULL UNIQUE, date_fin_recolte TEXT);
CREATE TABLE IF NOT EXISTS activites(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, type_activite TEXT NOT NULL,
  code TEXT NOT NULL, intrant TEXT);
CREATE TABLE IF NOT EXISTS recoltes(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, code TEXT NOT NULL,
  sacs REAL NOT NULL);
CREATE TABLE IF NOT EXISTS depenses(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, categorie TEXT NOT NULL,
  montant REAL NOT NULL, code TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recettes(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, produit TEXT NOT NULL,
  quantite REAL NOT NULL, prix_unitaire REAL NOT NULL, montant REAL NOT NULL,
  code TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS caisse(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, motif TEXT NOT NULL,
  entree REAL NOT NULL DEFAULT 0, sortie REAL NOT NULL DEFAULT 0,
  source TEXT, ref INTEGER);
CREATE TABLE IF NOT EXISTS materiel(
  id INTEGER PRIMARY KEY, nom TEXT NOT NULL, montant REAL NOT NULL,
  duree REAL NOT NULL);
CREATE TABLE IF NOT EXISTS charges(
  id INTEGER PRIMARY KEY, nom TEXT NOT NULL, montant REAL NOT NULL);
CREATE TABLE IF NOT EXISTS calendrier(
  mois INTEGER NOT NULL, culture TEXT NOT NULL, couleur TEXT NOT NULL,
  PRIMARY KEY(mois, culture));
"""


class Db:
    def __init__(self, path=":memory:"):
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrer()
        self._seed_calendrier()

    # ---------------------------------------------------------- utilitaires
    def _q(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def _migrer(self):
        """Ajoute les colonnes apparues après la première version."""
        cols = [r[1] for r in self._q("PRAGMA table_info(caisse)")]
        for nom, typ in (("source", "TEXT"), ("ref", "INTEGER")):
            if nom not in cols:
                self.con.execute("ALTER TABLE caisse ADD COLUMN %s %s" % (nom, typ))
        self.con.commit()

    def reset(self):
        """Remet l'application à zéro (le calendrier du marché est conservé)."""
        for t in TABLES:
            self.con.execute("DELETE FROM %s" % t)
        self.con.commit()

    def _seed_calendrier(self):
        if self._q("SELECT 1 FROM calendrier LIMIT 1"):
            return
        for m, ligne in enumerate(_CAL_DEFAUT, start=1):
            for cult, lettre in zip(CULTURES_CALENDRIER, ligne):
                self.con.execute("INSERT INTO calendrier VALUES(?,?,?)",
                                 (m, cult, PALETTE[lettre]))
        self.con.commit()

    def _code_exists(self, code):
        if not self._q("SELECT 1 FROM parcelles WHERE code=?", (code,)):
            raise ValidationError(
                "Choisissez un code de parcelle existant (créez d'abord la culture)")

    def count(self, table):
        assert table in TABLES
        return self._q("SELECT COUNT(*) FROM %s" % table)[0][0]

    # ------------------------------------------------------------ parcelles
    def add_parcelle(self, numero, superficie, culture, date_semis,
                     date_recolte, cycle, annee, date_fin=""):
        numero = required(numero, "Numéro de parcelle")
        sup = parse_number(superficie, "Superficie (m²)")
        cult = required(culture, "Culture").upper()
        cyc = parse_number(cycle, "Cycle", integer=True)
        an = norm_year(annee)
        semis = parse_date(date_semis)
        rec = parse_date(date_recolte) if (date_recolte or "").strip() else None
        fin = parse_date(date_fin) if (date_fin or "").strip() else None
        if rec and rec < semis:
            raise ValidationError(
                "La date de récolte prévue est avant la date de semis")
        if fin and fin < (rec or semis):
            raise ValidationError(
                "La date de fin des récoltes est trop tôt")
        code = "%s-%s%s" % (an, numero, cyc)
        if self._q("SELECT 1 FROM parcelles WHERE code=?", (code,)):
            raise ValidationError("Le code %s existe déjà" % code)
        self.con.execute(
            "INSERT INTO parcelles(numero,superficie,culture,date_semis,"
            "date_recolte,cycle,annee,code,date_fin_recolte) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (numero, sup, cult, semis, rec, cyc, an, code, fin))
        self.con.commit()
        return code

    def parcelle_codes(self):
        return [r[0] for r in self._q("SELECT code FROM parcelles ORDER BY code")]

    def cultures_utilisees(self):
        """Cultures qui ont au moins une parcelle enregistrée."""
        return [r[0] for r in self._q(
            "SELECT DISTINCT culture FROM parcelles ORDER BY culture")]

    def cultures_connues(self):
        vues = [r[0] for r in self._q(
            "SELECT DISTINCT culture FROM parcelles ORDER BY culture")]
        return vues + [c for c in CULTURES_CALENDRIER if c not in vues]

    def annees(self):
        return [r[0] for r in self._q(
            "SELECT DISTINCT annee FROM parcelles WHERE annee IS NOT NULL "
            "ORDER BY annee DESC")]

    def parcelle_info(self, code):
        r = self._q("SELECT * FROM parcelles WHERE code=?", (code,))
        return dict(r[0]) if r else None

    # ------------------------------------------------------ saisies liées
    def add_activite(self, date_txt, code, type_activite, intrant=""):
        self._code_exists(code)
        self.con.execute(
            "INSERT INTO activites(date,type_activite,code,intrant) VALUES(?,?,?,?)",
            (parse_date(date_txt), required(type_activite, "Type d'activité"),
             code, (intrant or "").strip()))
        self.con.commit()

    def add_recolte(self, date_txt, code, sacs):
        self._code_exists(code)
        self.con.execute(
            "INSERT INTO recoltes(date,code,sacs) VALUES(?,?,?)",
            (parse_date(date_txt), code, parse_number(sacs, "Nombre de sacs")))
        self.con.commit()

    def add_depense(self, date_txt, code, categorie, montant, en_caisse=False):
        self._code_exists(code)
        d = parse_date(date_txt)
        cat = required(categorie, "Catégorie")
        m = parse_number(montant, "Montant total")
        cur = self.con.execute(
            "INSERT INTO depenses(date,categorie,montant,code) VALUES(?,?,?,?)",
            (d, cat, m, code))
        if en_caisse:
            self.con.execute(
                "INSERT INTO caisse(date,motif,entree,sortie,source,ref) "
                "VALUES(?,?,0,?,'depense',?)", (d, "%s (%s)" % (cat, code), m, cur.lastrowid))
        self.con.commit()

    def add_recette(self, date_txt, code, produit, quantite, prix, en_caisse=False):
        self._code_exists(code)
        d = parse_date(date_txt)
        prod = required(produit, "Produit vendu")
        q = parse_number(quantite, "Quantité")
        p = parse_number(prix, "Prix unitaire")
        cur = self.con.execute(
            "INSERT INTO recettes(date,produit,quantite,prix_unitaire,montant,code)"
            " VALUES(?,?,?,?,?,?)", (d, prod, q, p, q * p, code))
        if en_caisse:
            self.con.execute(
                "INSERT INTO caisse(date,motif,entree,sortie,source,ref) "
                "VALUES(?,?,?,0,'recette',?)",
                (d, "Vente %s (%s)" % (prod, code), q * p, cur.lastrowid))
        self.con.commit()
        return q * p

    # --------------------------------------------------------------- caisse
    def add_caisse(self, sens, date_txt, motif, montant):
        if sens not in ("entree", "sortie"):
            raise ValidationError("Choisissez Entrée ou Sortie")
        m = parse_number(montant, "Montant")
        self.con.execute(
            "INSERT INTO caisse(date,motif,entree,sortie) VALUES(?,?,?,?)",
            (parse_date(date_txt), required(motif, "Motif"),
             m if sens == "entree" else 0, m if sens == "sortie" else 0))
        self.con.commit()

    def caisse_recente(self, limite=20):
        """[(id, date JJ/MM/AAAA, motif, entrée, sortie)] des dernières opérations."""
        return [(r["id"], fmt_date(r["date"]), r["motif"], r["entree"], r["sortie"])
                for r in self._q("SELECT * FROM caisse ORDER BY date DESC, id DESC LIMIT ?",
                                 (limite,))]

    def caisse_totaux(self):
        e, s = self._q("SELECT COALESCE(SUM(entree),0), COALESCE(SUM(sortie),0)"
                       " FROM caisse")[0]
        return e, s, e - s

    # -------------------------------------------------------------- charges
    def add_materiel(self, nom, montant, duree):
        self.con.execute(
            "INSERT INTO materiel(nom,montant,duree) VALUES(?,?,?)",
            (required(nom, "Matériel"), parse_number(montant, "Montant"),
             parse_number(duree, "Durée (années)")))
        self.con.commit()

    def add_charge(self, nom, montant):
        self.con.execute("INSERT INTO charges(nom,montant) VALUES(?,?)",
                         (required(nom, "Charge"), parse_number(montant, "Montant")))
        self.con.commit()

    def materiel_liste(self):
        """[(id, nom, montant, duree, amortissement)] ; amortissement = montant/durée."""
        return [(r["id"], r["nom"], r["montant"], r["duree"],
                 r["montant"] / r["duree"])
                for r in self._q("SELECT * FROM materiel ORDER BY id")]

    def charges_totaux(self):
        amort = sum(x[4] for x in self.materiel_liste())
        autres = self._q("SELECT COALESCE(SUM(montant),0) FROM charges")[0][0]
        return amort, autres, amort + autres

    # ------------------------------------------------------ rapports Excel
    def performance(self, culture, annee):
        """Tableau croisé « Performance AGRICOLE » : sacs par date."""
        rows = self._q(
            "SELECT r.date, SUM(r.sacs) FROM recoltes r JOIN parcelles p "
            "ON p.code=r.code WHERE UPPER(p.culture)=UPPER(?) AND p.annee=? "
            "GROUP BY r.date ORDER BY r.date", (culture, annee))
        lignes = [(fmt_date(d), s) for d, s in rows]
        return lignes, sum(s for _, s in lignes)

    def _par_annee(self, table, champ):
        rows = self._q(
            "SELECT p.annee, SUM(t.%s) FROM %s t LEFT JOIN parcelles p "
            "ON p.code=t.code GROUP BY p.annee ORDER BY p.annee" % (champ, table))
        return [("vide" if a is None else str(a), v) for a, v in rows]

    def recettes_par_annee(self):
        return self._par_annee("recettes", "montant")

    def depenses_par_annee(self):
        return self._par_annee("depenses", "montant")

    def _par_culture(self, table, annee):
        sql = ("SELECT p.culture, SUM(t.montant) FROM %s t LEFT JOIN parcelles p "
               "ON p.code=t.code " % table)
        args = ()
        if annee is not None:
            sql += "WHERE p.annee=? "
            args = (annee,)
        sql += "GROUP BY p.culture ORDER BY p.culture"
        return [("vide" if c is None else c, v) for c, v in self._q(sql, args)]

    def recettes_par_culture(self, annee=None):
        return self._par_culture("recettes", annee)

    def depenses_par_culture(self, annee=None):
        return self._par_culture("depenses", annee)

    def bilan(self, annee=None):
        """Recettes - dépenses - charges annuelles (amortissement + autres)."""
        def somme(table):
            if annee is None:
                return self._q("SELECT COALESCE(SUM(montant),0) FROM %s" % table)[0][0]
            return self._q(
                "SELECT COALESCE(SUM(t.montant),0) FROM %s t JOIN parcelles p "
                "ON p.code=t.code WHERE p.annee=?" % table, (annee,))[0][0]
        rec, dep = somme("recettes"), somme("depenses")
        amort, autres, ch = self.charges_totaux()
        return {"recettes": rec, "depenses": dep, "amortissement": amort,
                "autres_charges": autres, "resultat": rec - dep - ch,
                "solde_caisse": self.caisse_totaux()[2]}

    # ------------------------------------------------------------ calendrier
    def calendrier(self):
        """{(mois 1..12, culture): '#RRGGBB'}"""
        return {(r["mois"], r["culture"]): r["couleur"]
                for r in self._q("SELECT * FROM calendrier")}

    def calendrier_suivant(self, mois, culture):
        ordre = [PALETTE[k] for k in ("b", "v", "a", "r", "n")]
        actuel = self.calendrier().get((mois, culture), ordre[0])
        nouveau = ordre[(ordre.index(actuel) + 1) % len(ordre)] \
            if actuel in ordre else ordre[0]
        self.con.execute("UPDATE calendrier SET couleur=? WHERE mois=? AND culture=?",
                         (nouveau, mois, culture))
        self.con.commit()
        return nouveau

    # ------------------------------------------------- tableau de bord (v2)
    @staticmethod
    def _d(iso):
        return date.fromisoformat(iso) if iso else None

    def statut(self, p, today=None):
        """(libellé, clé) : À semer / En croissance / En récolte / Terminée."""
        today = today or date.today()
        semis, rec, fin = self._d(p["date_semis"]), self._d(p["date_recolte"]), \
            self._d(p["date_fin_recolte"])
        if fin and today > fin:
            return "Terminée", "fin"
        if rec and today >= rec:
            return "En récolte", "recolte"
        if semis and today >= semis:
            return "En croissance", "croissance"
        return "À semer", "semer"

    def progression(self, p, today=None):
        """Avancement semis -> récolte prévue, de 0 à 100."""
        today = today or date.today()
        semis, rec = self._d(p["date_semis"]), self._d(p["date_recolte"])
        if not semis:
            return 0.0
        fin = rec or semis + timedelta(days=90)
        total = max((fin - semis).days, 1)
        return max(0.0, min(100.0, (today - semis).days / total * 100))

    def stats_parcelle(self, code, sup):
        r = self._q("SELECT COALESCE(SUM(montant),0) FROM recettes WHERE code=?", (code,))[0][0]
        d = self._q("SELECT COALESCE(SUM(montant),0) FROM depenses WHERE code=?", (code,))[0][0]
        s = self._q("SELECT COALESCE(SUM(sacs),0) FROM recoltes WHERE code=?", (code,))[0][0]
        return {"recettes": r, "depenses": d, "sacs": s, "marge": r - d,
                "rendement": s / (sup / 100.0), "cout_m2": d / sup}

    def parcelles_detail(self, today=None):
        out = []
        for row in self._q("SELECT * FROM parcelles ORDER BY id"):
            p = dict(row)
            p.update(self.stats_parcelle(p["code"], p["superficie"]))
            p["statut"], p["statut_cle"] = self.statut(p, today)
            p["progression"] = self.progression(p, today)
            out.append(p)
        return out

    def alertes(self, today=None):
        """[(niveau, texte)] niveau = 'info' ou 'alerte'."""
        today = today or date.today()
        res = []
        for p in self.parcelles_detail(today):
            rec = self._d(p["date_recolte"])
            if rec and 0 <= (rec - today).days <= 7:
                j = (rec - today).days
                res.append(("info", "Récolte de %s (%s) %s." % (
                    p["culture"], p["code"], "aujourd'hui" if j == 0 else "dans %d jours" % j)))
            if p["statut_cle"] == "recolte" and p["sacs"] == 0:
                res.append(("alerte", "%s est en récolte : aucun sac enregistré." % p["code"]))
        if self.caisse_totaux()[2] < 0:
            res.append(("alerte", "La caisse est négative."))
        return res

    def annees_saisies(self):
        ans = {date.today().year}
        for t in ("recettes", "depenses"):
            ans.update(int(r[0]) for r in self._q(
                "SELECT DISTINCT strftime('%%Y', date) FROM %s" % t))
        return sorted(ans, reverse=True)

    def flux_mensuels(self, annee):
        """([recettes x12], [dépenses x12]) pour une année civile."""
        out = []
        for t in ("recettes", "depenses"):
            vals = [0.0] * 12
            for m, s in self._q(
                    "SELECT CAST(strftime('%%m', date) AS INTEGER), SUM(montant) FROM %s "
                    "WHERE strftime('%%Y', date)=? GROUP BY 1" % t, (str(annee),)):
                vals[m - 1] = s
            out.append(vals)
        return out[0], out[1]

    def marge_par_culture(self):
        o = {}
        for p in self.parcelles_detail():
            o[p["culture"]] = o.get(p["culture"], 0) + p["marge"]
        return o

    def marche_du_mois(self, mois=None):
        mois = mois or date.today().month
        cal = self.calendrier()
        return [(c, cal.get((mois, c), PALETTE["n"])) for c in CULTURES_CALENDRIER]

    def conseils_semis(self, today=None):
        """Pour chaque culture suivie : date limite de semis pour récolter au prochain
        mois « rare » du calendrier, d'après la durée moyenne semis -> récolte."""
        today = today or date.today()
        cal = self.calendrier()
        out = []
        for cult in CULTURES_CALENDRIER:
            durees = [(self._d(r["date_recolte"]) - self._d(r["date_semis"])).days
                      for r in self._q(
                          "SELECT date_semis, date_recolte FROM parcelles "
                          "WHERE UPPER(culture)=? AND date_recolte IS NOT NULL", (cult,))]
            durees = [d for d in durees if d > 0]
            if not durees:
                continue
            duree = sum(durees) / len(durees)
            for k in range(13):
                idx = today.month - 1 + k
                mois, annee = idx % 12 + 1, today.year + idx // 12
                if cal.get((mois, cult)) != RARE:
                    continue
                limite = date(annee, mois, 1) - timedelta(days=int(duree))
                if limite >= today:
                    out.append({"culture": cult, "mois": mois, "limite": limite,
                                "duree": int(duree)})
                    break
        return out

    def tableau_de_bord(self, today=None):
        e, s, solde = self.caisse_totaux()
        return {"solde": solde, "entrees": e, "sorties": s,
                "alertes": self.alertes(today),
                "en_cours": [p for p in self.parcelles_detail(today)
                             if p["statut_cle"] != "fin"],
                "marche": self.marche_du_mois(),
                "conseils": self.conseils_semis(today)}

    # ------------------------------------------------------------ historique
    def history(self, table, limit=200):
        """[(id, texte)] des dernières lignes d'une table."""
        assert table in TABLES
        out = []
        for r in self._q("SELECT * FROM %s ORDER BY id DESC LIMIT ?" % table, (limit,)):
            if table == "parcelles":
                t = "%s · %s · %g m² · semis %s" % (
                    r["code"], r["culture"], r["superficie"], fmt_date(r["date_semis"]))
            elif table == "activites":
                t = "%s · %s · %s %s" % (fmt_date(r["date"]), r["code"],
                                         r["type_activite"], r["intrant"] or "")
            elif table == "recoltes":
                t = "%s · %s · %g sacs" % (fmt_date(r["date"]), r["code"], r["sacs"])
            elif table == "depenses":
                t = "%s · %s · %s · %s" % (fmt_date(r["date"]), r["code"],
                                           r["categorie"], money(r["montant"]))
            elif table == "recettes":
                t = "%s · %s · %s · %g × %s = %s" % (
                    fmt_date(r["date"]), r["code"], r["produit"], r["quantite"],
                    money(r["prix_unitaire"]), money(r["montant"]))
            elif table == "caisse":
                sens = "Entrée +" + money(r["entree"]) if r["entree"] else \
                    "Sortie -" + money(r["sortie"])
                t = "%s · %s · %s" % (fmt_date(r["date"]), r["motif"], sens)
            elif table == "materiel":
                t = "%s · %s sur %g an(s)" % (r["nom"], money(r["montant"]), r["duree"])
            else:
                t = "%s · %s" % (r["nom"], money(r["montant"]))
            out.append((r["id"], t))
        return out

    def delete(self, table, row_id):
        assert table in TABLES
        if table == "parcelles":
            code = self._q("SELECT code FROM parcelles WHERE id=?", (row_id,))
            if code:
                code = code[0][0]
                for t in ("activites", "recoltes", "depenses", "recettes"):
                    if self._q("SELECT 1 FROM %s WHERE code=? LIMIT 1" % t, (code,)):
                        raise ValidationError(
                            "Suppression impossible : des saisies utilisent %s" % code)
        if table in ("depenses", "recettes"):   # supprime aussi l'écriture de caisse liée
            self.con.execute("DELETE FROM caisse WHERE source=? AND ref=?",
                             (table[:-1], row_id))
        self.con.execute("DELETE FROM %s WHERE id=?" % table, (row_id,))
        self.con.commit()

    # --------------------------------------------------------------- export
    def export_xlsx(self, path):
        """Un classeur Excel avec une feuille par table (colonnes calculées incluses)."""
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)

        def feuille(nom, entetes, lignes):
            ws = wb.create_sheet(nom)
            ws.append(entetes)
            for ligne in lignes:
                ws.append(list(ligne))
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(
                    12, min(40, max(len(str(c.value or "")) for c in col) + 2))

        feuille("Parcelles",
                ["Numéro", "Superficie (m2)", "Culture", "Date semis",
                 "Date récolte prévue", "Cycle", "Année", "Code de suivi",
                 "Date fin des récoltes"],
                [(r["numero"], r["superficie"], r["culture"], fmt_date(r["date_semis"]),
                  fmt_date(r["date_recolte"]), r["cycle"], r["annee"], r["code"],
                  fmt_date(r["date_fin_recolte"]))
                 for r in self._q("SELECT * FROM parcelles ORDER BY id")])
        lien = ("LEFT JOIN parcelles p ON p.code=t.code ")
        feuille("Activites", ["Date", "Type d'activité", "Code", "Intrant utilisé"],
                [(fmt_date(r["date"]), r["type_activite"], r["code"], r["intrant"])
                 for r in self._q("SELECT * FROM activites ORDER BY date,id")])
        feuille("Rendement", ["Date", "Code", "Nbrs de sac", "Année", "Cycle", "Culture"],
                [(fmt_date(r["date"]), r["code"], r["sacs"], r["annee"], r["cycle"],
                  r["culture"]) for r in self._q(
                      "SELECT t.*, p.annee, p.cycle, p.culture FROM recoltes t "
                      + lien + "ORDER BY t.date,t.id")])
        feuille("Depenses", ["Date", "Catégorie", "Montant total", "Code", "Année",
                             "Cycle", "Culture"],
                [(fmt_date(r["date"]), r["categorie"], r["montant"], r["code"],
                  r["annee"], r["cycle"], r["culture"]) for r in self._q(
                      "SELECT t.*, p.annee, p.cycle, p.culture FROM depenses t "
                      + lien + "ORDER BY t.date,t.id")])
        feuille("Recette", ["Date", "Produit vendu", "Quantité", "Prix unitaire",
                            "Montant total", "Code", "Année", "Cycle", "Culture"],
                [(fmt_date(r["date"]), r["produit"], r["quantite"], r["prix_unitaire"],
                  r["montant"], r["code"], r["annee"], r["cycle"], r["culture"])
                 for r in self._q(
                     "SELECT t.*, p.annee, p.cycle, p.culture FROM recettes t "
                     + lien + "ORDER BY t.date,t.id")])
        feuille("Caisse", ["Date", "Motif", "Montant entré", "Montant sorti"],
                [(fmt_date(r["date"]), r["motif"], r["entree"] or None,
                  r["sortie"] or None)
                 for r in self._q("SELECT * FROM caisse ORDER BY date,id")])
        feuille("Charges annuelles", ["Matériel", "Montant", "Durée (ans)",
                                      "Amortissement"],
                [(n, m, d, a) for _, n, m, d, a in self.materiel_liste()]
                + [("Autre charge : " + r["nom"], r["montant"], "", r["montant"])
                   for r in self._q("SELECT * FROM charges ORDER BY id")])
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        wb.save(path)
        return path

    def backup(self, dest_dir):
        """Copie du fichier de base de données (sauvegarde complète)."""
        self.con.commit()
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, "ferme_%s.db" % datetime.now().strftime("%Y%m%d_%H%M"))
        dst = sqlite3.connect(dest)
        with dst:
            self.con.backup(dst)
        dst.close()
        return dest
