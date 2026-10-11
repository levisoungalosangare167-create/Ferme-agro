# -*- coding: utf-8 -*-
"""Gestion Ferme - application Android (Kivy), hors ligne.

Navigation : Accueil · Parcelles · (+) Saisir · Caisse · Plus
Plus : Analyse · Calendrier du marché · Charges annuelles · Données
"""
import os
import re
from datetime import date

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexc

import core
from core import ValidationError, money

BG, CARD, INK = hexc("#EAF0EA"), (1, 1, 1, 1), hexc("#1B2A20")
MUTE, LEAF, TINT = hexc("#5A6D60"), hexc("#1F6B3A"), hexc("#DFF0E3")
LINE, GOLD, RED = hexc("#D3DFD4"), hexc("#B87D00"), hexc("#C0392B")
Window.clearcolor = BG
Window.softinput_mode = "below_target"      # le clavier ne cache pas le champ


# ------------------------------------------------------------------ widgets
def peindre(widget, rgba):
    with widget.canvas.before:
        Color(*rgba)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, v: setattr(rect, "pos", v),
                size=lambda w, v: setattr(rect, "size", v))


class WLabel(Label):
    """Texte qui retourne à la ligne et grandit avec son contenu."""

    def __init__(self, mute=False, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        kw.setdefault("color", MUTE if mute else INK)
        if mute:
            kw.setdefault("font_size", dp(13))
        super().__init__(**kw)
        self.bind(width=lambda *a: setattr(self, "text_size", (self.width, None)),
                  texture_size=lambda *a: setattr(
                      self, "height", max(dp(24), self.texture_size[1] + dp(4))))


class Card(BoxLayout):
    def __init__(self, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("padding", dp(14))
        kw.setdefault("spacing", dp(6))
        super().__init__(**kw)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*LINE)
            self._b = RoundedRectangle(radius=[dp(16)])
            Color(*CARD)
            self._f = RoundedRectangle(radius=[dp(15)])
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *_):
        self._b.pos, self._b.size = self.pos, self.size
        self._f.pos = (self.x + dp(1), self.y + dp(1))
        self._f.size = (max(self.width - dp(2), 0), max(self.height - dp(2), 0))


class CarteCliquable(ButtonBehavior, Card):
    pass


class Btn(Button):
    """Bouton aux coins arrondis."""

    def __init__(self, fond=LEAF, couleur=(1, 1, 1, 1), rayon=12, **kw):
        kw.update(background_normal="", background_down="", background_color=(0, 0, 0, 0))
        kw.setdefault("color", couleur)
        kw.setdefault("bold", True)
        super().__init__(**kw)
        with self.canvas.before:
            self._c = Color(*fond)
            self._r = RoundedRectangle(radius=[dp(rayon)])
        self.bind(pos=self._maj, size=self._maj,
                  state=lambda w, s: setattr(w, "opacity", 0.7 if s == "down" else 1))

    def _maj(self, *_):
        self._r.pos, self._r.size = self.pos, self.size

    def colorier(self, fond, couleur):
        self._c.rgba = fond
        self.color = couleur


STYLES = {"plein": (LEAF, (1, 1, 1, 1)), "clair": (TINT, LEAF), "rouge": (RED, (1, 1, 1, 1)),
          "gris": (hexc("#8A978E"), (1, 1, 1, 1))}


def bouton(texte, action, style="plein", hauteur=50):
    fond, couleur = STYLES[style]
    return Btn(text=texte, fond=fond, couleur=couleur, size_hint_y=None, height=dp(hauteur),
               on_release=lambda *_: action())


def puce(texte, actif, action):
    b = Btn(text=texte, fond=LEAF if actif else CARD, couleur=(1, 1, 1, 1) if actif else INK,
            size_hint=(None, None), height=dp(40), rayon=20, bold=actif,
            on_release=lambda *_: action())
    b.bind(texture_size=lambda w, ts: setattr(w, "width", ts[0] + dp(30)))
    return b


def puces(liste):
    """Rangée de puces qui défile horizontalement."""
    defil = ScrollView(size_hint_y=None, height=dp(46), do_scroll_y=False, bar_width=0)
    rang = BoxLayout(size_hint_x=None, spacing=dp(8))
    rang.bind(minimum_width=rang.setter("width"))
    for p in liste:
        rang.add_widget(p)
    defil.add_widget(rang)
    return defil


class Progress(Widget):
    def __init__(self, valeur=0, couleur=LEAF, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(10))
        super().__init__(**kw)
        self.valeur, self.couleur = valeur, couleur
        self.bind(pos=self.dessiner, size=self.dessiner)
        self.dessiner()

    def dessiner(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*TINT)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            Color(*self.couleur)
            RoundedRectangle(pos=self.pos, radius=[dp(5)],
                             size=(self.width * max(0, min(100, self.valeur)) / 100, self.height))


class Barres(Widget):
    """Histogramme : recettes (vert) et dépenses (rouge) pour chaque période."""

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(130))
        super().__init__(**kw)
        self.donnees = []
        self.bind(pos=self.dessiner, size=self.dessiner)

    def maj(self, donnees):          # [(recette, dépense)]
        self.donnees = donnees
        self.dessiner()

    def dessiner(self, *_):
        self.canvas.clear()
        if not self.donnees:
            return
        vmax = max(max(r, d) for r, d in self.donnees) or 1
        pas = self.width / len(self.donnees)
        with self.canvas:
            for i, (r, d) in enumerate(self.donnees):
                x = self.x + pas * i + pas * 0.1
                Color(*LEAF)
                Rectangle(pos=(x, self.y), size=(pas * 0.38, max(self.height * r / vmax, dp(2))))
                Color(*RED)
                Rectangle(pos=(x + pas * 0.4, self.y),
                          size=(pas * 0.38, max(self.height * d / vmax, dp(2))))


class Champ(TextInput):
    def __init__(self, **kw):
        kw.setdefault("multiline", False)
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(46))
        kw.setdefault("padding", [dp(12), dp(12), dp(12), dp(8)])
        kw.setdefault("write_tab", False)
        kw.setdefault("foreground_color", INK)
        super().__init__(**kw)


class DateInput(Champ):
    """Masque JJ/MM/AAAA : les « / » se placent tout seuls."""

    def __init__(self, **kw):
        kw.setdefault("hint_text", "JJ/MM/AAAA")
        kw.setdefault("input_type", "number")
        super().__init__(**kw)
        self.bind(text=self._formater)

    def _formater(self, _w, valeur):
        d = re.sub(r"\D", "", valeur)[:8]
        out = d[:2] + ("/" + d[2:4] if len(d) > 2 else "") + ("/" + d[4:] if len(d) > 4 else "")
        if out != valeur:
            self.text = out
            Clock.schedule_once(lambda dt: self.do_cursor_movement("cursor_end"), 0)


class NumInput(Champ):
    """Chiffres uniquement ; la virgule du clavier devient un point."""
    decimal = True

    def __init__(self, decimal=True, **kw):
        kw.setdefault("input_type", "number")
        super().__init__(**kw)
        self.decimal = decimal

    def insert_text(self, substring, from_undo=False):
        s = re.sub(r"[^0-9.]" if self.decimal else r"[^0-9]", "",
                   substring.replace(",", "."))
        if self.decimal and "." in self.text:
            s = s.replace(".", "")
        return super().insert_text(s, from_undo=from_undo)


def liste_deroulante(valeurs, texte="Choisir…"):
    return Spinner(text=texte, values=valeurs, size_hint_y=None, height=dp(46),
                   background_normal="", background_color=TINT, color=INK)


def ligne(gauche, droite, couleur=INK, gras=False):
    l = BoxLayout(size_hint_y=None, spacing=dp(8))
    l.bind(minimum_height=l.setter("height"))
    l.add_widget(WLabel(text=gauche))
    l.add_widget(WLabel(text=droite, halign="right", color=couleur, bold=gras,
                        size_hint_x=None, width=dp(130)))
    return l


def message(titre, texte, erreur=False):
    contenu = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    contenu.add_widget(WLabel(text=texte, color=RED if erreur else INK))
    contenu.add_widget(bouton("OK", lambda: pop.dismiss(), hauteur=44))
    pop = Popup(title=titre, content=contenu, size_hint=(0.9, None), height=dp(270))
    pop.open()


def toast(texte):
    pop = Popup(title="", separator_height=0, size_hint=(0.8, None), height=dp(80),
                content=WLabel(text=texte, halign="center", bold=True, color=LEAF))
    pop.open()
    Clock.schedule_once(lambda dt: pop.dismiss(), 1.6)


def confirmer(texte, action, bouton_texte="Supprimer"):
    contenu = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    contenu.add_widget(WLabel(text=texte))
    rang = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(46))
    rang.add_widget(bouton("Annuler", lambda: pop.dismiss(), "gris", 44))
    rang.add_widget(bouton(bouton_texte, lambda: (pop.dismiss(), action()), "rouge", 44))
    contenu.add_widget(rang)
    pop = Popup(title="Confirmation", content=contenu, size_hint=(0.9, None), height=dp(250))
    pop.open()


# ------------------------------------------------------------------ écrans
RETOUR = {"pform": "parcelles", "detail": "parcelles", "analyse": "plus",
          "calendrier": "plus", "charges": "plus", "donnees": "plus", "saisie": "accueil"}
ONGLET = {"pform": "parcelles", "detail": "parcelles", "analyse": "plus",
          "calendrier": "plus", "charges": "plus", "donnees": "plus"}


class Base(Screen):
    titre = ""
    arg = None

    def __init__(self, **kw):
        super().__init__(**kw)
        racine = BoxLayout(orientation="vertical")
        barre = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(16), dp(8)], spacing=dp(8))
        titre = Label(text=self.titre, bold=True, font_size=dp(20), color=INK,
                      halign="left", valign="middle")
        titre.bind(size=lambda w, s: setattr(w, "text_size", s))
        barre.add_widget(titre)
        if self.name in RETOUR:
            barre.add_widget(Btn(text="<", fond=TINT, couleur=LEAF, size_hint=(None, None),
                                 size=(dp(44), dp(40)),
                                 on_release=lambda *_: self.aller(RETOUR[self.name])))
        defil = ScrollView()
        self.corps = BoxLayout(orientation="vertical", size_hint_y=None,
                               padding=[dp(14), dp(4), dp(14), dp(20)], spacing=dp(12))
        self.corps.bind(minimum_height=self.corps.setter("height"))
        defil.add_widget(self.corps)
        racine.add_widget(barre)
        racine.add_widget(defil)
        self.add_widget(racine)
        self.construire()

    @property
    def db(self):
        return App.get_running_app().db

    def aller(self, nom, arg=None):
        App.get_running_app().aller(nom, arg)

    def champ(self, libelle, widget):
        self.corps.add_widget(WLabel(text=libelle, bold=True))
        self.corps.add_widget(widget)
        return widget

    def construire(self):
        pass

    def actualiser(self):
        self.corps.clear_widgets()
        self.rendre()

    def rendre(self):
        pass

    def on_pre_enter(self, *a):
        self.actualiser()

    def tenter(self, fonction):
        """Exécute une saisie ; affiche l'erreur de validation le cas échéant."""
        try:
            return fonction()
        except ValidationError as e:
            message("À corriger", str(e), erreur=True)
        except Exception as e:  # filet de sécurité : jamais de fermeture brutale
            message("Erreur", "Une erreur est survenue : %s" % e, erreur=True)
        return None

    def carte_parcelle(self, p):
        c = CarteCliquable()
        c.bind(on_release=lambda *_: self.aller("detail", p["code"]))
        c.add_widget(ligne("%s · %s" % (p["culture"], p["code"]), p["statut"],
                           GOLD if p["statut_cle"] == "recolte" else LEAF, True))
        c.add_widget(Progress(p["progression"]))
        c.add_widget(ligne("%g m² · semis %s" % (p["superficie"], core.fmt_date(p["date_semis"])),
                           "Marge %s" % money(p["marge"]),
                           LEAF if p["marge"] >= 0 else RED, True))
        return c


class AccueilScreen(Base):
    titre = "Gestion Ferme"

    def rendre(self):
        tb = self.db.tableau_de_bord()
        c = Card()
        c.add_widget(WLabel(text="Solde de la caisse", mute=True))
        c.add_widget(WLabel(text=money(tb["solde"]), font_size=dp(34), bold=True,
                            color=INK if tb["solde"] >= 0 else RED))
        c.add_widget(ligne("Entrées +%s" % money(tb["entrees"]), "Sorties −%s" % money(tb["sorties"])))
        self.corps.add_widget(c)
        if not self.db.count("parcelles"):
            b = Card()
            b.add_widget(WLabel(text="Bienvenue", bold=True, font_size=dp(18)))
            b.add_widget(WLabel(text="Commencez par ajouter votre première culture : l'application "
                                     "suivra ensuite vos récoltes, dépenses et recettes."))
            b.add_widget(bouton("Ajouter ma première culture", lambda: self.aller("pform")))
            self.corps.add_widget(b)
        for niveau, texte in tb["alertes"]:
            a = BoxLayout(size_hint_y=None, spacing=dp(8))
            a.bind(minimum_height=a.setter("height"))
            barre = Widget(size_hint_x=None, width=dp(5))
            peindre(barre, RED if niveau == "alerte" else GOLD)
            a.add_widget(barre)
            a.add_widget(WLabel(text=texte))
            peindre(a, CARD)
            self.corps.add_widget(a)
        m = Card()
        m.add_widget(WLabel(text="Le marché en %s" % core.MOIS[date.today().month - 1].lower(),
                            bold=True))
        grille = GridLayout(cols=2, size_hint_y=None, row_default_height=dp(26),
                            row_force_default=True)
        grille.bind(minimum_height=grille.setter("height"))
        for cult, couleur in tb["marche"]:
            r = BoxLayout(spacing=dp(8))
            pastille = Widget(size_hint=(None, None), size=(dp(14), dp(14)))
            peindre(pastille, hexc(couleur))
            r.add_widget(pastille)
            r.add_widget(WLabel(text=cult))
            grille.add_widget(r)
        m.add_widget(grille)
        m.add_widget(WLabel(text="Vert foncé : rare, donc bien payé. Rouge : abondant.", mute=True))
        for k in tb["conseils"][:2]:
            m.add_widget(WLabel(text="%s : semez avant le %s pour récolter en %s, quand il est "
                                     "rare sur le marché." % (
                                         k["culture"], k["limite"].strftime("%d/%m/%Y"),
                                         core.MOIS[k["mois"] - 1].lower())))
        self.corps.add_widget(m)
        if tb["en_cours"]:
            self.corps.add_widget(WLabel(text="Parcelles en cours", bold=True))
            for p in tb["en_cours"]:
                self.corps.add_widget(self.carte_parcelle(p))
        self.corps.add_widget(bouton("Voir l'analyse", lambda: self.aller("analyse"), "clair"))


class ParcellesScreen(Base):
    titre = "Parcelles"

    def rendre(self):
        self.corps.add_widget(bouton("+ Nouvelle culture", lambda: self.aller("pform")))
        liste = self.db.parcelles_detail()
        if not liste:
            self.corps.add_widget(WLabel(text="Aucune parcelle pour l'instant."))
        for p in liste:
            self.corps.add_widget(self.carte_parcelle(p))


class DetailScreen(Base):
    titre = "Détail parcelle"

    def rendre(self):
        p = next((x for x in self.db.parcelles_detail() if x["code"] == self.arg), None)
        if not p:
            self.corps.add_widget(WLabel(text="Parcelle introuvable."))
            return
        c = Card()
        c.add_widget(ligne(p["culture"], p["statut"], LEAF, True))
        c.add_widget(WLabel(text="Code %s · %g m² · cycle %s" % (p["code"], p["superficie"], p["cycle"]),
                            mute=True))
        c.add_widget(Progress(p["progression"]))
        c.add_widget(WLabel(text="Semis %s · récolte prévue %s" % (
            core.fmt_date(p["date_semis"]), core.fmt_date(p["date_recolte"]) or "—"), mute=True))
        self.corps.add_widget(c)
        f = Card()
        f.add_widget(ligne("Recettes", money(p["recettes"])))
        f.add_widget(ligne("Dépenses", money(p["depenses"])))
        f.add_widget(ligne("Marge", money(p["marge"]), LEAF if p["marge"] >= 0 else RED, True))
        self.corps.add_widget(f)
        r = Card()
        r.add_widget(ligne("Sacs récoltés", "%g" % p["sacs"]))
        r.add_widget(ligne("Rendement", "%.1f sacs/100 m²" % p["rendement"]))
        r.add_widget(ligne("Coût", "%s / m²" % money(p["cout_m2"])))
        self.corps.add_widget(r)
        self.corps.add_widget(bouton("Saisir pour cette parcelle",
                                     lambda: self.aller("saisie", p["code"])))


class ParcelleFormScreen(Base):
    titre = "Nouvelle culture"

    def construire(self):
        self.numero = self.champ("Numéro de la parcelle *", Champ(hint_text="ex. P1"))
        self.superficie = self.champ("Superficie (m²) *", NumInput())
        self.culture_liste = liste_deroulante([], "Choisir la culture")
        self.champ("Culture *", self.culture_liste)
        self.culture_libre = Champ(hint_text="ou écrire une nouvelle culture")
        self.corps.add_widget(self.culture_libre)
        self.semis = self.champ("Date de semis *", DateInput())
        self.recolte = self.champ("Date de récolte prévue", DateInput())
        self.fin = self.champ("Date de fin des récoltes", DateInput())
        self.cycle = self.champ("Cycle *", NumInput(decimal=False, hint_text="1, 2, 3…"))
        self.annee = self.champ("Année * (2 chiffres)", NumInput(decimal=False))
        self.apercu = WLabel(text="", bold=True, color=LEAF)
        self.corps.add_widget(self.apercu)
        for w in (self.numero, self.cycle, self.annee):
            w.bind(text=lambda *a: self.maj_code())
        self.corps.add_widget(bouton("Enregistrer la parcelle", self.enregistrer))

    def maj_code(self):
        try:
            self.apercu.text = "Code de suivi : %s-%s%s" % (
                core.norm_year(self.annee.text), self.numero.text.strip(), self.cycle.text.strip())
        except ValidationError:
            self.apercu.text = ""

    def actualiser(self):
        self.culture_liste.values = self.db.cultures_connues()
        if not self.annee.text:
            self.annee.text = core.today_fr()[-2:]

    def enregistrer(self):
        culture = self.culture_libre.text.strip() or (
            self.culture_liste.text if self.culture_liste.text in self.culture_liste.values else "")

        def action():
            code = self.db.add_parcelle(self.numero.text, self.superficie.text, culture,
                                        self.semis.text, self.recolte.text,
                                        self.cycle.text, self.annee.text, self.fin.text)
            for w in (self.numero, self.superficie, self.culture_libre, self.semis,
                      self.recolte, self.fin, self.cycle):
                w.text = ""
            self.culture_liste.text = "Choisir la culture"
            toast("Parcelle %s enregistrée" % code)
            self.aller("parcelles")
        self.tenter(action)


class SaisieScreen(Base):
    titre = "Saisir une donnée"
    TABS = ["Récolte", "Dépense", "Recette", "Activité culturale"]
    tab = "Récolte"
    pick = ""

    def rendre(self):
        if self.arg:
            self.pick, self.arg = self.arg, None
        self.champs, self.caisse_cb, self.chips = {}, None, {}
        self.corps.add_widget(puces([puce(t, t == self.tab, lambda t=t: self.choisir_tab(t))
                                     for t in self.TABS]))
        self.corps.add_widget(WLabel(text="Parcelle *", bold=True))
        codes = self.db.parcelle_codes()
        if not codes:
            self.corps.add_widget(WLabel(text="Créez d'abord une culture."))
            self.corps.add_widget(bouton("+ Nouvelle culture", lambda: self.aller("pform"), "clair"))
            return
        for c in codes:
            cult = self.db.parcelle_info(c)["culture"]
            self.chips[c] = puce("%s · %s" % (c, cult), c == self.pick,
                                 lambda c=c: self.choisir_code(c))
        self.corps.add_widget(puces(list(self.chips.values())))
        self.ajouter("date", "Date *", DateInput(text=core.today_fr()))
        t = self.tab
        if t == "Récolte":
            self.ajouter("sacs", "Nombre de sacs *", NumInput())
        elif t == "Dépense":
            self.ajouter("categorie", "Catégorie *", Champ(hint_text="ex. Engrais, Main-d'œuvre"))
            self.ajouter("montant", "Montant *", NumInput())
        elif t == "Recette":
            self.ajouter("produit", "Produit vendu *", Champ())
            self.ajouter("quantite", "Quantité *", NumInput())
            self.ajouter("prix", "Prix unitaire *", NumInput())
            self.total = WLabel(text="Montant total : 0", bold=True, color=LEAF)
            self.corps.add_widget(self.total)
            for k in ("quantite", "prix"):
                self.champs[k].bind(text=lambda *a: self.maj_total())
        else:
            self.ajouter("type", "Type d'activité *", Champ(hint_text="ex. Désherbage"))
            self.ajouter("intrant", "Intrant utilisé", Champ())
        if t in ("Dépense", "Recette"):
            r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            self.caisse_cb = CheckBox(active=True, size_hint_x=None, width=dp(44))
            r.add_widget(self.caisse_cb)
            r.add_widget(WLabel(text="Enregistrer aussi dans la caisse"))
            self.corps.add_widget(r)
        self.corps.add_widget(bouton("Enregistrer", self.enregistrer))

    def ajouter(self, cle, libelle, widget):
        self.champs[cle] = self.champ(libelle, widget)

    def choisir_tab(self, tab):
        self.tab = tab
        self.actualiser()

    def choisir_code(self, code):
        self.pick = code
        for c, b in self.chips.items():
            actif = c == code
            b.colorier(LEAF if actif else CARD, (1, 1, 1, 1) if actif else INK)

    def maj_total(self):
        try:
            q = float(self.champs["quantite"].text or 0)
            p = float(self.champs["prix"].text or 0)
        except ValueError:
            return
        self.total.text = "Montant total : %s" % money(q * p)

    def enregistrer(self):
        code, c = self.pick, {k: w.text for k, w in self.champs.items()}
        if not code:
            message("À corriger", "Choisissez la parcelle.", True)
            return
        en_caisse = bool(self.caisse_cb and self.caisse_cb.active)

        def action():
            if self.tab == "Récolte":
                self.db.add_recolte(c["date"], code, c["sacs"])
            elif self.tab == "Dépense":
                self.db.add_depense(c["date"], code, c["categorie"], c["montant"], en_caisse)
            elif self.tab == "Recette":
                self.db.add_recette(c["date"], code, c["produit"], c["quantite"], c["prix"], en_caisse)
            else:
                self.db.add_activite(c["date"], code, c["type"], c["intrant"])
            toast("Enregistré avec succès")
            self.actualiser()
        self.tenter(action)


class CaisseScreen(Base):
    titre = "Caisse"
    sens = "entree"

    def rendre(self):
        e, s, solde = self.db.caisse_totaux()
        c = Card()
        c.add_widget(WLabel(text="Solde", mute=True))
        c.add_widget(WLabel(text=money(solde), font_size=dp(34), bold=True,
                            color=INK if solde >= 0 else RED))
        c.add_widget(WLabel(text="Entrées %s · Sorties %s" % (money(e), money(s)), mute=True))
        self.corps.add_widget(c)
        self.puces = {}
        for cle, txt in (("entree", "Entrée"), ("sortie", "Sortie")):
            self.puces[cle] = puce(txt, cle == self.sens, lambda k=cle: self.choisir(k))
        self.corps.add_widget(puces(list(self.puces.values())))
        self.date = self.champ("Date *", DateInput(text=core.today_fr()))
        self.motif = self.champ("Motif *", Champ(hint_text="ex. Achat de semences"))
        self.montant = self.champ("Montant *", NumInput())
        self.corps.add_widget(bouton("Enregistrer", self.enregistrer))
        self.corps.add_widget(WLabel(text="Dernières opérations", bold=True))
        for _, d, motif, ent, sor in self.db.caisse_recente(20):
            self.corps.add_widget(ligne("%s · %s" % (d, motif),
                                        ("+%s" % money(ent)) if ent else ("−%s" % money(sor)),
                                        LEAF if ent else RED, True))

    def choisir(self, sens):
        self.sens = sens
        for k, b in self.puces.items():
            b.colorier(LEAF if k == sens else CARD, (1, 1, 1, 1) if k == sens else INK)

    def enregistrer(self):
        def action():
            self.db.add_caisse(self.sens, self.date.text, self.motif.text, self.montant.text)
            toast("Enregistré avec succès")
            self.actualiser()
        self.tenter(action)


class PlusScreen(Base):
    titre = "Plus"

    def rendre(self):
        for texte, ecran in [("Analyse recettes et dépenses", "analyse"),
                             ("Calendrier du marché", "calendrier"),
                             ("Charges annuelles", "charges"),
                             ("Données, export, sauvegarde", "donnees")]:
            self.corps.add_widget(bouton(texte, lambda e=ecran: self.aller(e), "clair", 56))


class AnalyseScreen(Base):
    titre = "Analyse"
    annee = None

    def rendre(self):
        annees = self.db.annees_saisies()
        if self.annee not in annees:
            self.annee = annees[0]
        sp = liste_deroulante([str(a) for a in annees], str(self.annee))
        sp.bind(text=lambda w, t: self.changer(t))
        self.corps.add_widget(sp)
        b = self.db.bilan()
        c = Card()
        c.add_widget(WLabel(text="Résultat (recettes − dépenses − charges annuelles)", mute=True))
        c.add_widget(WLabel(text=money(b["resultat"]), font_size=dp(30), bold=True,
                            color=LEAF if b["resultat"] >= 0 else RED))
        c.add_widget(WLabel(text="Recettes %s · dépenses %s · charges %s" % (
            money(b["recettes"]), money(b["depenses"]),
            money(b["amortissement"] + b["autres_charges"])), mute=True))
        self.corps.add_widget(c)
        rec, dep = self.db.flux_mensuels(self.annee)
        m = Card()
        m.add_widget(WLabel(text="Mois par mois (%s)" % self.annee, bold=True))
        graphe = Barres()
        graphe.maj(list(zip(rec, dep)))
        m.add_widget(graphe)
        etiq = GridLayout(cols=12, size_hint_y=None, height=dp(18))
        for nom in core.MOIS:
            etiq.add_widget(Label(text=nom[0], font_size=dp(11), color=MUTE))
        m.add_widget(etiq)
        m.add_widget(WLabel(text="Vert : recettes · Rouge : dépenses", mute=True))
        self.corps.add_widget(m)
        marges = self.db.marge_par_culture()
        k = Card()
        k.add_widget(WLabel(text="Marge par culture", bold=True))
        if not marges:
            k.add_widget(WLabel(text="Aucune donnée pour l'instant.", mute=True))
        vmax = max([abs(v) for v in marges.values()] + [1])
        for cult, v in marges.items():
            k.add_widget(ligne(cult, money(v), LEAF if v >= 0 else RED, True))
            k.add_widget(Progress(abs(v) / vmax * 100, LEAF if v >= 0 else RED))
        self.corps.add_widget(k)
        cl = Card()
        cl.add_widget(WLabel(text="Classement des parcelles", bold=True))
        for p in sorted(self.db.parcelles_detail(), key=lambda x: -x["marge"]):
            cl.add_widget(ligne("%s %s · %.1f sacs/100 m²" % (p["code"], p["culture"], p["rendement"]),
                                money(p["marge"]), LEAF if p["marge"] >= 0 else RED, True))
        self.corps.add_widget(cl)

    def changer(self, texte):
        if texte.isdigit() and int(texte) != self.annee:
            self.annee = int(texte)
            self.actualiser()


class CalendrierScreen(Base):
    titre = "Calendrier du marché"

    def rendre(self):
        lg = Card()
        lg.add_widget(WLabel(text="Quand le produit est-il rare ?", bold=True))
        for lettre, texte in core.LEGENDE:
            r = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(8))
            p = Widget(size_hint=(None, None), size=(dp(18), dp(18)))
            peindre(p, hexc(core.PALETTE[lettre]))
            r.add_widget(p)
            r.add_widget(WLabel(text=texte))
            lg.add_widget(r)
        lg.add_widget(WLabel(text="Touchez une case pour la modifier. Le mois en cours est en gras.",
                             mute=True))
        self.corps.add_widget(lg)
        cal = self.db.calendrier()
        grille = GridLayout(cols=len(core.CULTURES_CALENDRIER) + 1, size_hint_y=None,
                            row_default_height=dp(38), row_force_default=True, spacing=dp(2))
        grille.bind(minimum_height=grille.setter("height"))
        grille.add_widget(Label(text=""))
        for c in core.CULTURES_CALENDRIER:
            grille.add_widget(Label(text=c[:4], bold=True, font_size=dp(11), color=INK))
        mois_now = date.today().month
        for m in range(1, 13):
            grille.add_widget(Label(text=core.MOIS[m - 1][:4], font_size=dp(11), color=INK,
                                    bold=(m == mois_now)))
            for c in core.CULTURES_CALENDRIER:
                b = Button(text="", background_normal="", background_down="",
                           background_color=hexc(cal[(m, c)]))
                b.bind(on_release=lambda w, m=m, c=c: self.changer(w, m, c))
                grille.add_widget(b)
        self.corps.add_widget(grille)
        cs = Card()
        cs.add_widget(WLabel(text="Conseils de semis", bold=True))
        cs.add_widget(WLabel(text="Calculés avec la durée de vos cycles (semis → récolte).", mute=True))
        conseils = self.db.conseils_semis()
        for k in conseils:
            cs.add_widget(WLabel(text="%s : semez avant le %s pour récolter en %s." % (
                k["culture"], k["limite"].strftime("%d/%m/%Y"), core.MOIS[k["mois"] - 1].lower())))
        if not conseils:
            cs.add_widget(WLabel(text="Enregistrez une parcelle avec ses dates de semis et de récolte."))
        self.corps.add_widget(cs)

    def changer(self, bouton_, mois, culture):
        bouton_.background_color = hexc(self.db.calendrier_suivant(mois, culture))


class ChargesScreen(Base):
    titre = "Charges annuelles"

    def construire(self):
        pass

    def rendre(self):
        self.corps.add_widget(WLabel(text="Matériel (amortissement = montant ÷ durée)", bold=True))
        self.nom = self.champ("Matériel", Champ(hint_text="ex. Matériel d'irrigation"))
        self.montant = self.champ("Montant", NumInput())
        self.duree = self.champ("Durée (années)", NumInput())
        self.corps.add_widget(bouton("Ajouter le matériel", self.ajouter_materiel))
        self.nom2 = self.champ("Autre charge annuelle", Champ(hint_text="ex. Assurance, location"))
        self.montant2 = self.champ("Montant", NumInput())
        self.corps.add_widget(bouton("Ajouter la charge", self.ajouter_charge, "clair"))
        c = Card()
        for _, n, m, d, a in self.db.materiel_liste():
            c.add_widget(ligne("%s (%s sur %g an)" % (n, money(m), d), "%s/an" % money(a)))
        for _, t in self.db.history("charges"):
            c.add_widget(WLabel(text=t))
        c.add_widget(WLabel(text="Total : %s / an" % money(self.db.charges_totaux()[2]), bold=True))
        self.corps.add_widget(c)

    def ajouter_materiel(self):
        def action():
            self.db.add_materiel(self.nom.text, self.montant.text, self.duree.text)
            self.actualiser()
        self.tenter(action)

    def ajouter_charge(self):
        def action():
            self.db.add_charge(self.nom2.text, self.montant2.text)
            self.actualiser()
        self.tenter(action)


class DonneesScreen(Base):
    titre = "Données"
    NOMS = {"Parcelles": "parcelles", "Activités": "activites", "Récoltes": "recoltes",
            "Dépenses": "depenses", "Recettes": "recettes", "Caisse": "caisse",
            "Matériel": "materiel", "Autres charges": "charges"}

    def construire(self):
        self.corps.add_widget(bouton("Exporter vers Excel (.xlsx)", self.exporter))
        self.corps.add_widget(bouton("Sauvegarder la base", self.sauvegarder, "clair"))
        self.corps.add_widget(bouton("Importer depuis Excel", self.importer, "clair"))
        self.corps.add_widget(bouton("Remettre l'application à zéro", self.remise_a_zero, "rouge"))
        self.table = self.champ("Historique — choisir une table",
                                liste_deroulante(list(self.NOMS), "Table"))
        self.table.bind(text=lambda *a: self.afficher())
        self.liste = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.liste.bind(minimum_height=self.liste.setter("height"))
        self.corps.add_widget(self.liste)

    def actualiser(self):
        self.afficher()

    def afficher(self):
        self.liste.clear_widgets()
        nom = self.NOMS.get(self.table.text)
        if not nom:
            return
        for rid, texte in self.db.history(nom):
            rang = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(6))
            rang.add_widget(WLabel(text=texte, size_hint_y=1))
            rang.add_widget(Btn(text="X", fond=RED, size_hint=(None, None), size=(dp(44), dp(44)),
                                on_release=lambda *_, n=nom, i=rid, t=texte: confirmer(
                                    "Supprimer :\n%s ?" % t, lambda: self.supprimer(n, i))))
            self.liste.add_widget(rang)
        if not self.liste.children:
            self.liste.add_widget(WLabel(text="Aucune ligne."))

    def supprimer(self, nom, rid):
        self.tenter(lambda: (self.db.delete(nom, rid), self.afficher()))

    def exporter(self):
        def action():
            f = self.db.export_xlsx(os.path.join(App.get_running_app().dossier_export(),
                                                 "Ferme_export.xlsx"))
            message("Export terminé", "Fichier créé :\n%s" % f)
        self.tenter(action)

    def sauvegarder(self):
        def action():
            f = self.db.backup(App.get_running_app().dossier_export())
            message("Sauvegarde terminée", "Copie de la base :\n%s" % f)
        self.tenter(action)

    def remise_a_zero(self):
        def action():
            self.db.reset()
            toast("Application remise à zéro")
            self.afficher()
        confirmer("Effacer TOUTES les données (parcelles, caisse, recettes…) ?\n"
                  "Pensez à exporter avant.", action, "Tout effacer")

    def importer(self):
        def action():
            import import_excel
            dossier = App.get_running_app().dossier_export()
            for nom in ("Ferme_AGRO_.xlsm", "Ferme_AGRO_.xlsx", "import.xlsx", "import.xlsm"):
                chemin = os.path.join(dossier, nom)
                if os.path.exists(chemin):
                    n = import_excel.import_classeur(self.db, chemin)
                    message("Import terminé", ", ".join("%s : %d" % kv for kv in n.items() if kv[1])
                            or "Aucune ligne trouvée.")
                    return
            message("Fichier introuvable",
                    "Copiez votre fichier Ferme_AGRO_.xlsm dans ce dossier puis réessayez :\n%s" % dossier, True)
        self.tenter(action)


# --------------------------------------------------------------- application
NAV = [("accueil", "Accueil"), ("parcelles", "Parcelles"), ("saisie", "+"),
       ("caisse", "Caisse"), ("plus", "Plus")]


class FermeApp(App):
    title = "Gestion Ferme"

    def build(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        self.db = core.Db(os.path.join(self.user_data_dir, "ferme.db"))
        self.sm = ScreenManager(transition=NoTransition())
        for nom, classe in [("accueil", AccueilScreen), ("parcelles", ParcellesScreen),
                            ("detail", DetailScreen), ("pform", ParcelleFormScreen),
                            ("saisie", SaisieScreen), ("caisse", CaisseScreen),
                            ("plus", PlusScreen), ("analyse", AnalyseScreen),
                            ("calendrier", CalendrierScreen), ("charges", ChargesScreen),
                            ("donnees", DonneesScreen)]:
            self.sm.add_widget(classe(name=nom))
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(self.sm)
        barre = BoxLayout(size_hint_y=None, height=dp(64), padding=[dp(4), dp(4)])
        peindre(barre, CARD)
        self.onglets = {}
        for cle, texte in NAV:
            if cle == "saisie":
                b = Btn(text="+", fond=LEAF, rayon=26, font_size=dp(30), size_hint=(None, None),
                        size=(dp(52), dp(52)), pos_hint={"center_y": 0.5},
                        on_release=lambda *_: self.aller("saisie"))
                conteneur = BoxLayout(size_hint_x=None, width=dp(72), padding=[dp(10), 0])
                conteneur.add_widget(b)
                barre.add_widget(conteneur)
            else:
                b = Button(text=texte, background_normal="", background_down="",
                           background_color=(0, 0, 0, 0), color=MUTE, font_size=dp(13),
                           on_release=lambda w, c=cle: self.aller(c))
                self.onglets[cle] = b
                barre.add_widget(b)
        racine.add_widget(barre)
        self.sm.bind(current=lambda w, v: self.marquer(v))
        self.marquer("accueil")
        Window.bind(on_keyboard=self.touche)
        return racine

    def aller(self, nom, arg=None):
        ecran = self.sm.get_screen(nom)
        ecran.arg = arg
        if self.sm.current == nom:
            ecran.actualiser()
        else:
            self.sm.current = nom

    def marquer(self, courant):
        actif = ONGLET.get(courant, courant)
        for cle, b in self.onglets.items():
            b.color = LEAF if cle == actif else MUTE
            b.bold = cle == actif

    def touche(self, _w, cle, *args):
        if cle == 27 and self.sm.current != "accueil":   # bouton Retour d'Android
            self.aller(RETOUR.get(self.sm.current, "accueil"))
            return True
        return False

    def dossier_export(self):
        """Dossier visible depuis le gestionnaire de fichiers (Android/data/<app>/files)."""
        try:
            from jnius import autoclass
            activite = autoclass("org.kivy.android.PythonActivity").mActivity
            d = activite.getExternalFilesDir(None)
            if d is not None:
                return d.getAbsolutePath()
        except Exception:
            pass
        return self.user_data_dir

    def on_pause(self):
        self.db.con.commit()
        return True

    def on_start(self):
        self.sm.current = "accueil"


if __name__ == "__main__":
    FermeApp().run()
