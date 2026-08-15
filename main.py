"""
Gestion Maintenance - Département Technique (Délice)
----------------------------------------------------
Application mobile en Kivy, à exécuter avec Pydroid 3 sur Android.

INSTALLATION SUR VOTRE PHONE :
1. Installez "Pydroid 3" depuis le Play Store.
2. Ouvrez Pydroid 3 -> menu (☰) -> Pip -> recherchez "kivy" et "fpdf2" -> Installer.
   (Optionnel, pour la vibration de confirmation) recherchez aussi "plyer" -> Installer.
3. Copiez ce fichier sur votre téléphone, ouvrez-le avec Pydroid 3 et appuyez sur ▶ Play.
"""

import sqlite3
import os
import csv
import shutil
import webbrowser
import threading
import traceback
from datetime import datetime, timedelta
from collections import Counter

try:
    from fpdf import FPDF
    FPDF_DISPONIBLE = True
    ERREUR_IMPORT_FPDF = None
except Exception as e:
    import traceback
    FPDF_DISPONIBLE = False
    ERREUR_IMPORT_FPDF = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"

try:
    from plyer import vibrator
    VIBRATION_DISPONIBLE = True
except Exception:
    VIBRATION_DISPONIBLE = False


def vibrer(duree=0.15):
    """Déclenche une courte vibration si plyer/le matériel le permet. Ne fait rien sinon (silencieux)."""
    if not VIBRATION_DISPONIBLE:
        return
    try:
        vibrator.vibrate(duree)
    except Exception:
        pass


from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.carousel import Carousel
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp

Window.softinput_mode = "below_target"

# ---------- Couleurs (charte Délice) ----------
BLEU_NUIT = (10/255, 61/255, 98/255, 1)
BLEU_FONCE = (15/255, 94/255, 153/255, 1)
JAUNE = (255/255, 212/255, 0/255, 1)
BLANC = (1, 1, 1, 1)
GRIS_TEXTE = (0.2, 0.28, 0.34, 1)
VERT_RESOLU = (0.13, 0.55, 0.13, 1)
ORANGE_A_SUIVRE = (0.80, 0.42, 0.04, 1)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donnee_utile.db")

STATUTS_INTERVENTION = ("Résolue", "À suivre")

# Nom affiché comme réalisateur de l'application (écran de connexion + exports PDF)
NOM_REALISATEUR = "Hichri Abdelhalim"


def obtenir_dossier_export():
    """
    Cherche un dossier accessible en écriture pour les exports PDF/CSV,
    en testant une VRAIE écriture (pas seulement os.access, qui peut
    répondre "écrivable" à tort sur les dossiers publics comme Documents/
    Download depuis Android 10+, où une appli sans l'autorisation spéciale
    "Accès à tous les fichiers" ne peut en réalité pas y écrire — l'erreur
    ne survient alors qu'au moment de l'écriture réelle du fichier).
    """
    dossiers_candidats = [
        "/storage/emulated/0/GestionMaintenanceDelice",
        "/storage/emulated/0/Documents",
        "/storage/emulated/0/Download",
    ]
    for dossier in dossiers_candidats:
        try:
            os.makedirs(dossier, exist_ok=True)
            chemin_test = os.path.join(dossier, ".test_ecriture_delice")
            with open(chemin_test, "w") as f:
                f.write("test")
            os.remove(chemin_test)
            return dossier
        except Exception:
            continue

    # Aucun dossier public n'est réellement accessible en écriture (permission
    # "Accès à tous les fichiers" non accordée) : on se replie sur le dossier
    # propre à l'application, toujours accessible sans aucune permission,
    # sur toutes les versions d'Android.
    try:
        from android.storage import app_storage_path
        dossier = os.path.join(app_storage_path(), "GestionMaintenanceDelice")
        os.makedirs(dossier, exist_ok=True)
        return dossier
    except Exception:
        pass

    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            dossier = os.path.join(app.user_data_dir, "GestionMaintenanceDelice")
            os.makedirs(dossier, exist_ok=True)
            return dossier
    except Exception:
        pass

    return os.path.dirname(os.path.abspath(__file__))


def obtenir_poste_actuel():
    heure = datetime.now().hour
    if 6 <= heure < 14:
        return "Jour"
    elif 14 <= heure < 22:
        return "Après-midi"
    else:
        return "Nuit"


# ---------- Mode sombre ----------
# État global simple (l'app n'a qu'une seule fenêtre à la fois sur Android/Pydroid).
_MODE_SOMBRE = {"actif": False}

# Couleurs de la palette sombre (plus reposantes en zone peu éclairée / poste de nuit)
FOND_FENETRE_SOMBRE = (0.07, 0.08, 0.10, 1)
FOND_CARTE_SOMBRE = (0.15, 0.16, 0.19, 1)
BORDURE_CARTE_SOMBRE = (0.28, 0.31, 0.35, 1)
TEXTE_PRINCIPAL_SOMBRE = (0.82, 0.85, 0.88, 1)
TEXTE_TITRE_SOMBRE = (0.55, 0.78, 0.98, 1)


def est_mode_sombre():
    return _MODE_SOMBRE["actif"]


def basculer_mode_sombre(actif):
    """Active/désactive le mode sombre et met à jour immédiatement le fond de fenêtre.
    Les cartes déjà affichées à l'écran adopteront la nouvelle palette au prochain
    rafraîchissement (changement de filtre, de page, ou nouvelle entrée sur l'écran)."""
    _MODE_SOMBRE["actif"] = actif
    Window.clearcolor = FOND_FENETRE_SOMBRE if actif else (0.94, 0.96, 0.98, 1)


def couleur_fond_carte():
    return FOND_CARTE_SOMBRE if est_mode_sombre() else BLANC


def couleur_bordure_carte():
    return BORDURE_CARTE_SOMBRE if est_mode_sombre() else (0.82, 0.88, 0.93, 1)


def couleur_texte_principal():
    return TEXTE_PRINCIPAL_SOMBRE if est_mode_sombre() else GRIS_TEXTE


def couleur_texte_titre():
    return TEXTE_TITRE_SOMBRE if est_mode_sombre() else BLEU_NUIT


def calculer_plage_date(cle):
    """
    Retourne (date_debut, date_fin) au format AAAA-MM-JJ pour un raccourci donné :
    'aujourdhui', 'hier', 'semaine' (depuis lundi) ou 'mois' (depuis le 1er du mois).
    """
    aujourdhui = datetime.now().date()

    if cle == "aujourdhui":
        debut = fin = aujourdhui
    elif cle == "hier":
        debut = fin = aujourdhui - timedelta(days=1)
    elif cle == "semaine":
        debut = aujourdhui - timedelta(days=aujourdhui.weekday())
        fin = aujourdhui
    elif cle == "mois":
        debut = aujourdhui.replace(day=1)
        fin = aujourdhui
    else:
        debut = fin = aujourdhui

    return debut.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")


# ================= Base de données =================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS defauts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS equipements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS defauts_conditionnement (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS intervenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_ordre_travail TEXT,
                poste TEXT,
                equipement TEXT,
                type_maintenance TEXT,
                anomalie TEXT,
                action TEXT,
                duree TEXT,
                intervenant1 TEXT,
                intervenant2 TEXT,
                remarques TEXT,
                date_heure TEXT
            )
        """)

        c.execute("PRAGMA table_info(interventions)")
        colonnes_existantes = [ligne[1] for ligne in c.fetchall()]
        if "numero_ordre_travail" not in colonnes_existantes:
            c.execute("ALTER TABLE interventions ADD COLUMN numero_ordre_travail TEXT")
        if "statut" not in colonnes_existantes:
            c.execute("ALTER TABLE interventions ADD COLUMN statut TEXT")
            # Les interventions déjà enregistrées avant l'ajout de ce champ
            # sont considérées comme résolues par défaut.
            c.execute("UPDATE interventions SET statut = 'Résolue' WHERE statut IS NULL OR statut = ''")

        c.execute("""
            DELETE FROM interventions
            WHERE id NOT IN (
                SELECT MIN(id) FROM interventions
                GROUP BY numero_ordre_travail, poste, equipement, type_maintenance, anomalie,
                         action, duree, intervenant1, intervenant2, remarques, date_heure
            )
        """)

        c.execute("SELECT COUNT(*) FROM defauts")
        if c.fetchone()[0] == 0:
            defauts_defaut = [
                "Défaut variateur", "Coupe film", "Bourrage convoyeur",
                "Défaut capteur photocellule", "Perte de synchronisation"
            ]
            c.executemany("INSERT INTO defauts (description) VALUES (?)", [(d,) for d in defauts_defaut])

        c.execute("SELECT COUNT(*) FROM equipements")
        if c.fetchone()[0] == 0:
            equipements_defaut = [
                "Conditionneuse", "Applicateur languette", "Convoyeur", "Encaisseuse", "Palettiseur"
            ]
            c.executemany("INSERT INTO equipements (nom) VALUES (?)", [(e,) for e in equipements_defaut])

        c.execute("SELECT COUNT(*) FROM intervenants")
        if c.fetchone()[0] == 0:
            intervenants_defaut = ["K. Trabelsi", "M. Chaabane"]
            c.executemany("INSERT INTO intervenants (nom) VALUES (?)", [(i,) for i in intervenants_defaut])

        c.execute("SELECT COUNT(*) FROM defauts_conditionnement")
        if c.fetchone()[0] == 0:
            defauts_conditionnement_defaut = [
                "Défaut de soudure", "Bourrage carton", "Défaut de collage", "Alignement produit incorrect"
            ]
            c.executemany("INSERT INTO defauts_conditionnement (description) VALUES (?)", [(d,) for d in defauts_conditionnement_defaut])

        # Fusion : les défauts "conditionnement" sont désormais regroupés avec les défauts
        # généraux dans une seule liste. On migre une fois les entrées non déjà présentes.
        c.execute("SELECT description FROM defauts")
        descriptions_existantes = {ligne[0] for ligne in c.fetchall()}
        c.execute("SELECT description FROM defauts_conditionnement")
        for (description,) in c.fetchall():
            if description not in descriptions_existantes:
                c.execute("INSERT INTO defauts (description) VALUES (?)", (description,))
                descriptions_existantes.add(description)


def get_defauts_conditionnement():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, description FROM defauts_conditionnement ORDER BY id")
        return c.fetchall()


def ajouter_defaut_conditionnement(description):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO defauts_conditionnement (description) VALUES (?)", (description,))


def supprimer_defaut_conditionnement(defaut_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM defauts_conditionnement WHERE id = ?", (defaut_id,))


def get_intervenants():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nom FROM intervenants ORDER BY nom")
        return c.fetchall()


def ajouter_intervenant(nom):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO intervenants (nom) VALUES (?)", (nom,))


def supprimer_intervenant(intervenant_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM intervenants WHERE id = ?", (intervenant_id,))


def get_equipements():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nom FROM equipements ORDER BY nom")
        return c.fetchall()


def ajouter_equipement(nom):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO equipements (nom) VALUES (?)", (nom,))


def supprimer_equipement(equipement_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM equipements WHERE id = ?", (equipement_id,))


def get_defauts():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, description FROM defauts ORDER BY id")
        return c.fetchall()


def ajouter_defaut(description):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO defauts (description) VALUES (?)", (description,))


def supprimer_defaut(defaut_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM defauts WHERE id = ?", (defaut_id,))


def _construire_clause_filtre(equipement=None, date_debut=None, date_fin=None, poste=None, recherche=None, statut=None):
    """Construit la clause SQL (WHERE ...) et la liste de paramètres partagées par
    get_interventions() et compter_interventions(), pour éviter la duplication."""
    clause = ""
    parametres = []

    if equipement:
        clause += " AND equipement = ?"
        parametres.append(equipement)

    if poste:
        clause += " AND poste = ?"
        parametres.append(poste)

    if statut:
        clause += " AND statut = ?"
        parametres.append(statut)

    if date_debut:
        clause += " AND date_heure >= ?"
        parametres.append(date_debut + " 00:00")

    if date_fin:
        clause += " AND date_heure <= ?"
        parametres.append(date_fin + " 23:59")

    if recherche:
        term = f"%{recherche}%"
        clause += """ AND (numero_ordre_travail LIKE ? OR anomalie LIKE ? 
                       OR action LIKE ? OR remarques LIKE ? OR intervenant1 LIKE ? OR intervenant2 LIKE ?)"""
        parametres.extend([term] * 6)

    return clause, parametres


def get_interventions(equipement=None, date_debut=None, date_fin=None, poste=None, recherche=None, statut=None,
                       limite=None, decalage=0):
    """
    Récupère les interventions filtrées. Si `limite` est fourni, applique une
    pagination SQL (LIMIT/OFFSET) — utile pour ne charger qu'une page de résultats
    à la fois (performance sur smartphones d'entrée de gamme avec un gros historique).
    """
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        clause, parametres = _construire_clause_filtre(equipement, date_debut, date_fin, poste, recherche, statut)
        requete = """
            SELECT id, numero_ordre_travail, date_heure, poste, equipement, type_maintenance,
                   anomalie, action, duree, intervenant1, intervenant2, remarques, statut
            FROM interventions
            WHERE 1=1
        """ + clause + " ORDER BY id DESC"

        if limite is not None:
            requete += " LIMIT ? OFFSET ?"
            parametres = parametres + [limite, decalage]

        c.execute(requete, parametres)
        return c.fetchall()


def compter_interventions(equipement=None, date_debut=None, date_fin=None, poste=None, recherche=None, statut=None):
    """Compte le nombre total d'interventions correspondant aux filtres (pour la pagination)."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        clause, parametres = _construire_clause_filtre(equipement, date_debut, date_fin, poste, recherche, statut)
        requete = "SELECT COUNT(*) FROM interventions WHERE 1=1" + clause
        c.execute(requete, parametres)
        return c.fetchone()[0]


def obtenir_intervention(intervention_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, numero_ordre_travail, poste, equipement, type_maintenance, anomalie,
                   action, duree, intervenant1, intervenant2, remarques, statut, date_heure
            FROM interventions WHERE id = ?
        """, (intervention_id,))
        return c.fetchone()


def modifier_intervention(intervention_id, data):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE interventions
            SET numero_ordre_travail = ?, poste = ?, equipement = ?, type_maintenance = ?,
                anomalie = ?, action = ?, duree = ?, intervenant1 = ?, intervenant2 = ?, remarques = ?,
                statut = ?
            WHERE id = ?
        """, (
            data["numero_ordre_travail"], data["poste"], data["equipement"], data["type_maintenance"],
            data["anomalie"], data["action"], data["duree"],
            data["intervenant1"], data["intervenant2"], data["remarques"], data["statut"],
            intervention_id
        ))


def supprimer_intervention(intervention_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM interventions WHERE id = ?", (intervention_id,))


def enregistrer_intervention(data):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO interventions
            (numero_ordre_travail, poste, equipement, type_maintenance, anomalie, action, duree,
             intervenant1, intervenant2, remarques, statut, date_heure)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["numero_ordre_travail"], data["poste"], data["equipement"], data["type_maintenance"],
            data["anomalie"], data["action"], data["duree"],
            data["intervenant1"], data["intervenant2"], data["remarques"], data["statut"],
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))


def _formater_ligne_export(donnees):
    """
    Met en forme une ligne d'intervention pour les exports (PDF/CSV) :
    - Colonne Date (index 1) : "2026-07-26 20:15" -> "26/07/2026" (évite la
      troncature "2026-07-26 20:..." dans le PDF, colonne trop étroite pour
      la date+heure complète).
    - Colonne Durée (index 7) : ajoute le suffixe " min" (ex: "15" -> "15 min").
    """
    donnees = list(donnees)

    date_heure = donnees[1]
    if date_heure:
        try:
            donnees[1] = datetime.strptime(date_heure, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            pass

    duree = donnees[7]
    if duree not in (None, ""):
        donnees[7] = f"{duree} min"

    return tuple(donnees)


# ================= Exports (PDF & Excel/CSV) =================
def exporter_csv(titre, colonnes, lignes, nom_fichier):
    chemin = os.path.join(obtenir_dossier_export(), nom_fichier)
    with open(chemin, mode="w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow([titre])
        writer.writerow(colonnes)
        for ligne in lignes:
            writer.writerow(ligne)
    return chemin


def _nettoyer_texte_pdf(texte):
    texte = str(texte)
    remplacements = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}
    for original, remplacement in remplacements.items():
        texte = texte.replace(original, remplacement)
    return texte.encode("latin-1", "replace").decode("latin-1")


def _tronquer_pour_pdf(pdf, texte, largeur_mm):
    texte = _nettoyer_texte_pdf(texte)
    if pdf.get_string_width(texte) <= largeur_mm:
        return texte
    while texte and pdf.get_string_width(texte + "...") > largeur_mm:
        texte = texte[:-1]
    return texte + "..." if texte else "..."


def _decouper_lignes(pdf, texte, largeur_mm):
    texte = _nettoyer_texte_pdf(texte)
    mots = texte.split(" ")
    lignes = []
    ligne_actuelle = ""
    for mot in mots:
        essai = (ligne_actuelle + " " + mot).strip()
        if pdf.get_string_width(essai) <= largeur_mm:
            ligne_actuelle = essai
        else:
            if ligne_actuelle:
                lignes.append(ligne_actuelle)
            while pdf.get_string_width(mot) > largeur_mm and len(mot) > 1:
                limite = len(mot)
                while limite > 1 and pdf.get_string_width(mot[:limite]) > largeur_mm:
                    limite -= 1
                lignes.append(mot[:limite])
                mot = mot[limite:]
            ligne_actuelle = mot
    if ligne_actuelle:
        lignes.append(ligne_actuelle)
    return lignes if lignes else [""]


def exporter_pdf(titre, sous_titre, colonnes, lignes, nom_fichier):
    if not FPDF_DISPONIBLE:
        return None

    chemin = os.path.join(obtenir_dossier_export(), nom_fichier)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(10, 61, 98)
    pdf.cell(0, 8, _nettoyer_texte_pdf(titre), ln=1)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(92, 119, 136)
    pdf.multi_cell(0, 5, _nettoyer_texte_pdf(sous_titre))

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(140, 150, 160)
    pdf.cell(0, 5, _nettoyer_texte_pdf(f"Application réalisée par {NOM_REALISATEUR}"), ln=1)
    pdf.ln(2)

    largeur_page = pdf.w - 2 * pdf.l_margin
    hauteur_ligne = 6

    poids_par_defaut = [7, 8, 6, 8, 6, 12, 12, 7, 7, 7, 10, 8]
    poids = poids_par_defaut if len(colonnes) == len(poids_par_defaut) else [1] * len(colonnes)
    total_poids = sum(poids)
    largeurs = [largeur_page * (p / total_poids) for p in poids]
    colonnes_multilignes = {5, 6, 10} if len(colonnes) == len(poids_par_defaut) else set()

    def ligne_entete():
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(15, 94, 153)
        pdf.set_text_color(255, 255, 255)
        for i, col in enumerate(colonnes):
            pdf.cell(largeurs[i], hauteur_ligne, _tronquer_pour_pdf(pdf, col, largeurs[i] - 2), border=1, fill=True)
        pdf.ln(hauteur_ligne)

    ligne_entete()
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(20, 40, 55)

    if not lignes:
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(largeur_page, hauteur_ligne, "Aucune donnée à afficher", border=1, ln=1, align="C")
    else:
        remplissage = False
        for ligne in lignes:
            contenu_colonnes = []
            nb_lignes_max = 1
            for i, valeur in enumerate(ligne):
                texte = str(valeur) if valeur not in (None, "") else "—"
                texte = _nettoyer_texte_pdf(texte)
                if i in colonnes_multilignes:
                    sous_lignes = _decouper_lignes(pdf, texte, largeurs[i] - 2)
                    contenu_colonnes.append(sous_lignes)
                    nb_lignes_max = max(nb_lignes_max, len(sous_lignes))
                else:
                    contenu_colonnes.append(_tronquer_pour_pdf(pdf, texte, largeurs[i] - 2))

            hauteur_totale = nb_lignes_max * hauteur_ligne

            if pdf.get_y() + hauteur_totale > pdf.h - pdf.b_margin:
                pdf.add_page()
                ligne_entete()
                pdf.set_font("Helvetica", "", 7.5)
                pdf.set_text_color(20, 40, 55)

            couleur_fond = (242, 245, 248) if remplissage else (255, 255, 255)
            x_debut = pdf.get_x()
            y_debut = pdf.get_y()
            x_courant = x_debut

            for i, contenu in enumerate(contenu_colonnes):
                if i in colonnes_multilignes:
                    pdf.set_fill_color(*couleur_fond)
                    pdf.rect(x_courant, y_debut, largeurs[i], hauteur_totale, style="DF")
                    for indice_ligne, sous_ligne in enumerate(contenu):
                        pdf.set_xy(x_courant + 1, y_debut + indice_ligne * hauteur_ligne)
                        pdf.cell(largeurs[i] - 2, hauteur_ligne, sous_ligne, border=0, align="L")
                else:
                    pdf.set_fill_color(*couleur_fond)
                    pdf.set_xy(x_courant, y_debut)
                    pdf.cell(largeurs[i], hauteur_totale, contenu, border=1, fill=True)
                x_courant += largeurs[i]

            pdf.set_xy(x_debut, y_debut + hauteur_totale)
            remplissage = not remplissage

    pdf.output(chemin)
    return chemin


# ================= Widgets utilitaires =================
class FondCouleur(BoxLayout):
    def __init__(self, couleur, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*couleur)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._maj_rect, pos=self._maj_rect)

    def _maj_rect(self, *args):
        self.rect.size = self.size
        self.rect.pos = self.pos


def entete(titre):
    barre = FondCouleur(BLEU_FONCE, orientation="vertical", size_hint=(1, None),
                         height=dp(64), padding=(dp(16), dp(8)))
    lbl_marque = Label(text="[b]délice[/b]", markup=True, font_size=dp(20), color=BLANC,
                        size_hint=(1, None), height=dp(26), halign="left")
    lbl_marque.bind(size=lambda *a: setattr(lbl_marque, "text_size", lbl_marque.size))
    lbl_titre = Label(text=titre, font_size=dp(13), color=(0.85, 0.92, 1, 1),
                       size_hint=(1, None), height=dp(20), halign="left")
    lbl_titre.bind(size=lambda *a: setattr(lbl_titre, "text_size", lbl_titre.size))
    barre.add_widget(lbl_marque)
    barre.add_widget(lbl_titre)
    return barre


def afficher_popup_erreur_generique(titre, message_erreur):
    """
    Affiche une erreur inattendue dans un popup lisible (au lieu de laisser
    l'application planter intégralement), et sauvegarde la trace complète
    dans un fichier texte lisible depuis un gestionnaire de fichiers Android.
    `message_erreur` doit déjà être une chaîne complète (trace incluse) :
    ne pas dépendre de traceback.format_exc() en dehors du bloc except
    d'origine, car le contexte de l'exception serait alors perdu.
    """
    chemin_log = None
    try:
        chemin_log = os.path.join(obtenir_dossier_export(), "erreur_pdf.txt")
        with open(chemin_log, "w", encoding="utf-8") as f:
            f.write(message_erreur)
    except Exception:
        chemin_log = None

    message = message_erreur
    if chemin_log:
        message += f"\n\nCe message a aussi été enregistré dans :\n{chemin_log}"

    contenu = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    scroll = ScrollView(size_hint=(1, 1))
    lbl = Label(text=message, color=GRIS_TEXTE, font_size=dp(11.5),
                size_hint=(1, None), halign="left", valign="top")
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(10)))
    scroll.add_widget(lbl)
    contenu.add_widget(scroll)

    popup = Popup(title=titre, content=contenu, size_hint=(0.94, 0.8))
    contenu.add_widget(bouton("Fermer", lambda inst: popup.dismiss(),
                               couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
    popup.open()


def lancer_generation_pdf_en_arriere_plan(titre, sous_titre, colonnes, obtenir_lignes, nom_fichier):
    """
    Génère le PDF (récupération des données + écriture du fichier) dans un
    thread séparé, avec un popup de progression pendant ce temps.

    C'est essentiel sur Android : si la génération s'exécute directement sur
    le thread principal (celui de l'interface) et prend plus de quelques
    secondes (gros historique, téléphone lent), le système considère l'appli
    comme bloquée ("ANR") et la ferme brutalement — un crash qu'aucun
    try/except ne peut intercepter, car ce n'est pas une erreur Python mais
    une décision du système d'exploitation. En déplaçant le travail dans un
    thread, l'interface reste réactive et ce risque disparaît, quel que soit
    le nombre de lignes à exporter.

    `obtenir_lignes` est une fonction sans argument qui retourne la liste de
    lignes à exporter (appelée dans le thread, pas sur l'écran).
    """
    popup_attente = Popup(title="Génération du PDF…",
                           content=Label(text="Veuillez patienter,\ngénération du PDF en cours..."),
                           size_hint=(0.8, 0.32), auto_dismiss=False)
    popup_attente.open()

    resultat = {}

    def travail_arriere_plan():
        try:
            lignes = obtenir_lignes()
            chemin = exporter_pdf(titre, sous_titre, colonnes, lignes, nom_fichier)
            resultat["chemin"] = chemin
        except Exception as e:
            resultat["erreur"] = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"

    def terminer(dt):
        popup_attente.dismiss()
        if "erreur" in resultat:
            afficher_popup_erreur_generique("Erreur génération PDF", resultat["erreur"])
            return
        chemin = resultat.get("chemin")
        if not chemin:
            afficher_popup_erreur_generique("Erreur génération PDF", "Le fichier PDF n'a pas pu être créé (raison inconnue).")
            return
        try:
            webbrowser.open("file://" + chemin)
        except Exception:
            pass
        popup = Popup(title="PDF Généré", content=Label(text=f"Fichier PDF créé :\n{chemin}"), size_hint=(0.88, 0.4))
        popup.open()

    def travail_et_notifier():
        travail_arriere_plan()
        Clock.schedule_once(terminer, 0)

    threading.Thread(target=travail_et_notifier, daemon=True).start()


def afficher_popup_erreur_fpdf():
    """
    Affiche le détail complet de l'échec d'import de fpdf2/fontTools dans un
    popup qui s'enroule correctement (au lieu de couper le texte à droite),
    et sauvegarde aussi le message complet dans un fichier texte lisible
    depuis un gestionnaire de fichiers Android, pour diagnostic hors-écran.
    """
    message = "Impossible de générer le PDF (fpdf2/fontTools indisponible).\n"
    if ERREUR_IMPORT_FPDF:
        message += f"\nDétail technique :\n{ERREUR_IMPORT_FPDF}"
    else:
        message += "\n(Aucun détail disponible.)"

    chemin_log = None
    try:
        chemin_log = os.path.join(obtenir_dossier_export(), "erreur_pdf.txt")
        with open(chemin_log, "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        chemin_log = None

    if chemin_log:
        message += f"\n\nCe message a aussi été enregistré dans :\n{chemin_log}"

    contenu = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    scroll = ScrollView(size_hint=(1, 1))
    lbl = Label(text=message, color=GRIS_TEXTE, font_size=dp(12.5),
                size_hint=(1, None), halign="left", valign="top")
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(10)))
    scroll.add_widget(lbl)
    contenu.add_widget(scroll)

    popup = Popup(title="Erreur PDF (fpdf2)", content=contenu, size_hint=(0.92, 0.75))
    contenu.add_widget(bouton("Fermer", lambda inst: popup.dismiss(),
                               couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
    popup.open()


def afficher_toast(message, couleur_fond=VERT_RESOLU, duree=1.8):
    """
    Affiche une confirmation visuelle marquée (type 'Toast') qui se ferme
    automatiquement après `duree` secondes, sans action requise de l'utilisateur.
    """
    contenu = FondCouleur(couleur_fond, orientation="vertical", padding=dp(16))
    lbl = Label(text=message, color=BLANC, bold=True, font_size=dp(15),
                halign="center", valign="middle")
    lbl.bind(size=lambda *a: setattr(lbl, "text_size", lbl.size))
    contenu.add_widget(lbl)

    popup = Popup(title="", separator_height=0, content=contenu,
                   size_hint=(0.82, None), height=dp(90))
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), duree)
    return popup


def bouton(texte, callback, couleur_fond=BLEU_FONCE, couleur_texte=BLANC):
    b = Button(text=texte, size_hint=(1, None), height=dp(46),
               background_normal="", background_color=couleur_fond,
               color=couleur_texte, font_size=dp(14))
    b.bind(on_release=callback)
    return b


def ligne_raccourcis_dates(callback):
    """
    Crée une rangée de 4 boutons raccourcis de date : Aujourd'hui, Hier,
    Cette semaine, Ce mois. `callback(cle)` est appelé au clic avec la clé
    correspondante ('aujourdhui', 'hier', 'semaine', 'mois').
    """
    ligne = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
    boutons = (
        ("Aujourd'hui", "aujourdhui"),
        ("Hier", "hier"),
        ("Cette semaine", "semaine"),
        ("Ce mois", "mois"),
    )
    for texte, cle in boutons:
        btn = Button(text=texte, size_hint=(1, 1), background_normal="",
                     background_color=(0.85, 0.92, 1, 1), color=BLEU_NUIT,
                     font_size=dp(11), bold=True)
        btn.bind(on_release=lambda inst, c=cle: callback(c))
        ligne.add_widget(btn)
    return ligne


def construire_ligne_top(rang, nom, count, count_max, couleur_barre=BLEU_FONCE):
    """Une ligne du graphique Top 5 : rang + nom, barre proportionnelle, valeur."""
    ligne = BoxLayout(size_hint=(1, None), height=dp(26), spacing=dp(6))

    lbl_nom = Label(text=f"{rang}. {nom}", font_size=dp(11), color=GRIS_TEXTE,
                     size_hint=(0.44, 1), halign="left", valign="middle",
                     shorten=True, shorten_from="right")
    lbl_nom.bind(size=lambda *a: setattr(lbl_nom, "text_size", lbl_nom.size))
    ligne.add_widget(lbl_nom)

    ratio = max(count / count_max, 0.04) if count_max else 0.04
    conteneur_barre = BoxLayout(size_hint=(0.40, 1), padding=(0, dp(5)))
    barre = FondCouleur(couleur_barre, size_hint=(ratio, 1))
    conteneur_barre.add_widget(barre)
    if ratio < 1:
        conteneur_barre.add_widget(BoxLayout(size_hint=(1 - ratio, 1)))
    ligne.add_widget(conteneur_barre)

    lbl_count = Label(text=str(count), font_size=dp(11.5), bold=True, color=BLEU_NUIT, size_hint=(0.16, 1))
    ligne.add_widget(lbl_count)

    return ligne


def construire_bloc_top5(titre, paires, couleur_barre=BLEU_FONCE):
    """
    Construit un bloc 'Top 5' à partir d'une liste de tuples (nom, nombre)
    déjà triée par ordre décroissant (ex: Counter.most_common(5)).
    """
    bloc = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(3))
    bloc.bind(minimum_height=bloc.setter("height"))

    lbl_titre = Label(text=titre, font_size=dp(12.5), bold=True, color=BLEU_NUIT,
                       size_hint=(1, None), height=dp(22), halign="left")
    lbl_titre.bind(size=lambda *a: setattr(lbl_titre, "text_size", lbl_titre.size))
    bloc.add_widget(lbl_titre)

    if not paires:
        lbl_vide = Label(text="Aucune donnée pour cette période", font_size=dp(11),
                          color=GRIS_TEXTE, size_hint=(1, None), height=dp(24), halign="left")
        lbl_vide.bind(size=lambda *a: setattr(lbl_vide, "text_size", lbl_vide.size))
        bloc.add_widget(lbl_vide)
    else:
        count_max = paires[0][1]
        for rang, (nom, count) in enumerate(paires, start=1):
            bloc.add_widget(construire_ligne_top(rang, nom, count, count_max, couleur_barre=couleur_barre))

    return bloc


def valider_duree(texte):
    """
    Valide le champ Durée (minutes). Retourne (valide, message_erreur).
    Le champ est optionnel (texte vide autorisé), mais s'il est renseigné,
    il doit être un entier positif ou nul — jamais négatif.
    """
    texte = (texte or "").strip()
    if not texte:
        return True, ""
    try:
        valeur = int(texte)
    except ValueError:
        return False, "La durée doit être un nombre entier."
    if valeur < 0:
        return False, "La durée ne peut pas être négative."
    return True, ""


def valider_numero_ot(texte):
    """
    Valide le champ N° Ordre de Travail. Obligatoire, doit contenir
    exactement 6 chiffres (ex: 504567). Retourne (valide, message_erreur).
    """
    texte = (texte or "").strip()
    if not texte:
        return False, "Le N° OT est obligatoire (6 chiffres)."
    if not texte.isdigit() or len(texte) != 6:
        return False, "Le N° OT doit contenir exactement 6 chiffres."
    return True, ""


def couleur_statut(valeur):
    if valeur == "Résolue":
        return VERT_RESOLU
    if valeur == "À suivre":
        return ORANGE_A_SUIVRE
    return None


def _label_champ_valeur(champ, valeur, largeur_disponible, couleur_valeur=None):
    largeur_champ = largeur_disponible * 0.34
    largeur_valeur = largeur_disponible * 0.66 - dp(8)

    lbl_champ = Label(text=f"{champ}", font_size=dp(11.5), bold=True, color=couleur_texte_titre(),
                       size_hint=(0.34, None), halign="left", valign="top", text_size=(largeur_champ, None))
    lbl_champ.texture_update()
    hauteur_champ = lbl_champ.texture_size[1] + dp(4)

    texte_valeur = str(valeur) if valeur not in (None, "") else "—"
    est_badge = champ == "Statut" and couleur_valeur is not None
    lbl_valeur = Label(text=texte_valeur,
                        font_size=dp(12), color=(couleur_valeur or couleur_texte_principal()),
                        bold=est_badge,
                        size_hint=(0.66, None), halign="left", valign="top", text_size=(largeur_valeur, None))
    lbl_valeur.texture_update()
    hauteur_valeur = lbl_valeur.texture_size[1] + dp(4)

    hauteur_ligne = max(hauteur_champ, hauteur_valeur, dp(20))
    lbl_champ.height = hauteur_ligne
    lbl_valeur.height = hauteur_ligne

    ligne = BoxLayout(orientation="horizontal", size_hint=(1, None), height=hauteur_ligne, spacing=dp(8))
    ligne.add_widget(lbl_champ)
    ligne.add_widget(lbl_valeur)
    return ligne


def construire_carte_intervention(colonnes, ligne_donnees, intervention_id=None, on_modifier=None, on_supprimer=None):
    padding_carte = dp(12)
    padding_conteneur = dp(10)
    largeur_disponible = max(Window.width - 2 * padding_conteneur - 2 * padding_carte, dp(150))

    carte = BoxLayout(orientation="vertical", size_hint=(1, None), padding=padding_carte, spacing=dp(6))
    lignes_widgets = [
        _label_champ_valeur(champ, valeur, largeur_disponible, couleur_valeur=couleur_statut(valeur) if champ == "Statut" else None)
        for champ, valeur in zip(colonnes, ligne_donnees)
    ]

    hauteur_totale = 2 * padding_carte + sum(l.height for l in lignes_widgets) + dp(6) * max(len(lignes_widgets) - 1, 0)

    if intervention_id is not None and (on_modifier or on_supprimer):
        ligne_actions = BoxLayout(orientation="horizontal", size_hint=(1, None), height=dp(40), spacing=dp(8))
        if on_modifier:
            btn_modifier = Button(text="✏️ Modifier", size_hint=(1, 1), background_normal="",
                                   background_color=(0.85, 0.92, 1, 1), color=BLEU_NUIT, bold=True, font_size=dp(12.5))
            btn_modifier.bind(on_release=lambda inst, i=intervention_id: on_modifier(i))
            ligne_actions.add_widget(btn_modifier)
        if on_supprimer:
            btn_supprimer = Button(text="🗑 Supprimer", size_hint=(1, 1), background_normal="",
                                    background_color=(0.96, 0.82, 0.8, 1), color=(0.55, 0.1, 0.1, 1), bold=True, font_size=dp(12.5))
            btn_supprimer.bind(on_release=lambda inst, i=intervention_id: on_supprimer(i))
            ligne_actions.add_widget(btn_supprimer)
        lignes_widgets.append(ligne_actions)
        hauteur_totale += dp(40) + dp(6)

    carte.height = hauteur_totale

    with carte.canvas.before:
        Color(*couleur_fond_carte())
        rect = Rectangle(size=carte.size, pos=carte.pos)
        Color(*couleur_bordure_carte())
        contour = Line(rectangle=(carte.x, carte.y, carte.width, carte.height), width=1)

    def _maj_fond(instance, *a):
        rect.size = instance.size
        rect.pos = instance.pos
        contour.rectangle = (instance.x, instance.y, instance.width, instance.height)

    carte.bind(size=_maj_fond, pos=_maj_fond)
    for ligne_widget in lignes_widgets:
        carte.add_widget(ligne_widget)

    return carte


def ouvrir_popup_edition_intervention(intervention_id, on_succes):
    ligne = obtenir_intervention(intervention_id)
    if not ligne:
        return
    (_id, numero_ot, poste, equipement, type_maintenance, anomalie,
     action_texte, duree, intervenant1, intervenant2, remarques, statut, date_heure) = ligne

    def champ_label(texte):
        l = Label(text=texte, font_size=dp(12), bold=True, color=BLEU_NUIT,
                   size_hint=(1, None), height=dp(20), halign="left")
        l.bind(size=lambda *a: setattr(l, "text_size", l.size))
        return l

    contenu = GridLayout(cols=1, padding=dp(14), spacing=dp(8), size_hint=(1, None))
    contenu.bind(minimum_height=contenu.setter("height"))
    scroll = ScrollView(size_hint=(1, 1))
    scroll.add_widget(contenu)

    popup = Popup(title=f"Modifier l'intervention (OT: {numero_ot or '—'})", content=scroll, size_hint=(0.94, 0.9))

    contenu.add_widget(champ_label("Numéro Ordre de Travail"))
    champ_numero_ot = TextInput(text=numero_ot or "", multiline=False, input_filter="int",
                                 size_hint=(1, None), height=dp(44))
    contenu.add_widget(champ_numero_ot)

    contenu.add_widget(champ_label("Poste"))
    spinner_poste = Spinner(text=poste if poste in ("Jour", "Après-midi", "Nuit") else "Jour",
                             values=("Jour", "Après-midi", "Nuit"), size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_poste)

    contenu.add_widget(champ_label("Équipement"))
    noms_equip = [nom for _, nom in get_equipements()]
    spinner_equipement = Spinner(text=equipement if equipement in noms_equip else (noms_equip[0] if noms_equip else "—"),
                                  values=noms_equip, size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_equipement)

    contenu.add_widget(champ_label("Type de maintenance"))
    spinner_type = Spinner(text=type_maintenance if type_maintenance in ("Corrective", "Préventive", "Prédictive") else "Corrective",
                            values=("Corrective", "Préventive", "Prédictive"), size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_type)

    contenu.add_widget(champ_label("Anomalie"))
    champ_anomalie = TextInput(text=anomalie or "", multiline=False, size_hint=(1, None), height=dp(44))
    contenu.add_widget(champ_anomalie)

    contenu.add_widget(champ_label("Action"))
    champ_action = TextInput(text=action_texte or "", multiline=True, size_hint=(1, None), height=dp(80))
    contenu.add_widget(champ_action)

    contenu.add_widget(champ_label("Durée (min)"))
    champ_duree = TextInput(text=str(duree) if duree not in (None, "") else "", multiline=False,
                             input_filter="int", size_hint=(1, None), height=dp(44))
    contenu.add_widget(champ_duree)

    noms_intervenants = [nom for _, nom in get_intervenants()]
    valeurs_intervenants = ["— aucun —"] + noms_intervenants

    contenu.add_widget(champ_label("Intervenant 1"))
    spinner_int1 = Spinner(text=intervenant1 if intervenant1 in noms_intervenants else "— aucun —",
                            values=valeurs_intervenants, size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_int1)

    contenu.add_widget(champ_label("Intervenant 2"))
    spinner_int2 = Spinner(text=intervenant2 if intervenant2 in noms_intervenants else "— aucun —",
                            values=valeurs_intervenants, size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_int2)

    contenu.add_widget(champ_label("Remarques"))
    champ_remarques = TextInput(text=remarques or "", multiline=True, size_hint=(1, None), height=dp(80))
    contenu.add_widget(champ_remarques)

    contenu.add_widget(champ_label("Statut de la panne"))
    spinner_statut = Spinner(text=statut if statut in STATUTS_INTERVENTION else "Résolue",
                              values=STATUTS_INTERVENTION, size_hint=(1, None), height=dp(44))
    contenu.add_widget(spinner_statut)

    lbl_erreur = Label(text="", color=(0.75, 0.15, 0.1, 1), font_size=dp(12), size_hint=(1, None), height=dp(24))
    contenu.add_widget(lbl_erreur)

    def enregistrer(*a):
        if spinner_equipement.text in ("—", "") or not champ_anomalie.text.strip():
            lbl_erreur.text = "Renseignez au moins l'équipement et l'anomalie."
            return
        ot_valide, message_erreur_ot = valider_numero_ot(champ_numero_ot.text)
        if not ot_valide:
            lbl_erreur.text = message_erreur_ot
            return
        duree_valide, message_erreur_duree = valider_duree(champ_duree.text)
        if not duree_valide:
            lbl_erreur.text = message_erreur_duree
            return
        modifier_intervention(intervention_id, {
            "numero_ordre_travail": champ_numero_ot.text.strip(),
            "poste": spinner_poste.text,
            "equipement": spinner_equipement.text,
            "type_maintenance": spinner_type.text,
            "anomalie": champ_anomalie.text.strip(),
            "action": champ_action.text.strip(),
            "duree": champ_duree.text.strip(),
            "intervenant1": "" if spinner_int1.text == "— aucun —" else spinner_int1.text,
            "intervenant2": "" if spinner_int2.text == "— aucun —" else spinner_int2.text,
            "remarques": champ_remarques.text.strip(),
            "statut": spinner_statut.text,
        })
        popup.dismiss()
        if on_succes:
            on_succes()

    ligne_boutons = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
    ligne_boutons.add_widget(bouton("Enregistrer", enregistrer, couleur_fond=BLEU_FONCE))
    ligne_boutons.add_widget(bouton("Annuler", lambda inst: popup.dismiss(),
                                     couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
    contenu.add_widget(ligne_boutons)

    popup.open()


def ouvrir_popup_confirmation_suppression(intervention_id, on_succes):
    contenu = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(16))
    contenu.add_widget(Label(text="Supprimer définitivement cette intervention ?\nCette action est irréversible.",
                              color=GRIS_TEXTE, font_size=dp(13), halign="center"))

    popup = Popup(title="Confirmer la suppression", content=contenu, size_hint=(0.85, 0.4))

    def confirmer(*a):
        supprimer_intervention(intervention_id)
        popup.dismiss()
        if on_succes:
            on_succes()

    ligne_boutons = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
    ligne_boutons.add_widget(bouton("Supprimer", confirmer, couleur_fond=(0.75, 0.15, 0.1, 1), couleur_texte=BLANC))
    ligne_boutons.add_widget(bouton("Annuler", lambda inst: popup.dismiss(),
                                     couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
    contenu.add_widget(ligne_boutons)

    popup.open()


class SectionGeree(BoxLayout):
    def __init__(self, titre, get_func, add_func, delete_func, **kwargs):
        super().__init__(orientation="vertical", size_hint=(1, None), spacing=dp(6), **kwargs)
        self.get_func = get_func
        self.add_func = add_func
        self.delete_func = delete_func
        self.selection_id = None
        self.boutons = {}
        self.bind(minimum_height=self.setter("height"))

        lbl_titre = Label(text=titre, font_size=dp(13), bold=True, color=BLEU_NUIT,
                           size_hint=(1, None), height=dp(24), halign="left")
        lbl_titre.bind(size=lambda *a: setattr(lbl_titre, "text_size", lbl_titre.size))
        self.add_widget(lbl_titre)

        self.zone_liste = GridLayout(cols=1, spacing=dp(4), size_hint=(1, None))
        self.zone_liste.bind(minimum_height=self.zone_liste.setter("height"))
        scroll = ScrollView(size_hint=(1, None), height=dp(150))
        scroll.add_widget(self.zone_liste)
        self.add_widget(scroll)

        ligne_boutons = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
        ligne_boutons.add_widget(bouton("Ajouter", self.ajouter, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        ligne_boutons.add_widget(bouton("Supprimer", self.supprimer, couleur_fond=(0.93, 0.75, 0.75, 1), couleur_texte=(0.55, 0.1, 0.1, 1)))
        self.add_widget(ligne_boutons)
        self.height = dp(24) + dp(150) + dp(46) + dp(12)
        self.recharger()

    def recharger(self):
        self.zone_liste.clear_widgets()
        self.boutons = {}
        self.selection_id = None
        for item_id, texte in self.get_func():
            btn = Button(text=texte, size_hint=(1, None), height=dp(36),
                         background_normal="", background_color=(0.95, 0.97, 1, 1),
                         color=GRIS_TEXTE, font_size=dp(12))
            btn.bind(on_release=lambda inst, i=item_id: self.selectionner(i))
            self.boutons[item_id] = btn
            self.zone_liste.add_widget(btn)

    def selectionner(self, item_id):
        for i, b in self.boutons.items():
            b.background_color = (0.75, 0.87, 0.98, 1) if i == item_id else (0.95, 0.97, 1, 1)
        self.selection_id = item_id

    def ajouter(self, *args):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        champ = TextInput(hint_text="Nouvelle valeur", multiline=False, size_hint=(1, None), height=dp(44))
        contenu.add_widget(champ)
        popup = Popup(title="Ajouter", content=contenu, size_hint=(0.85, 0.35))

        def valider(*a):
            if champ.text.strip():
                self.add_func(champ.text.strip())
                self.recharger()
            popup.dismiss()

        contenu.add_widget(bouton("Ajouter", valider, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        popup.open()

    def supprimer(self, *args):
        if self.selection_id is not None:
            self.delete_func(self.selection_id)
            self.recharger()


# ================= Écran 1 : Connexion =================
class EcranLogin(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Gestion Maintenance — Département Technique"))

        corps = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        corps.add_widget(Label(text="Bienvenue dans l'application\nGestion Maintenance",
                                font_size=dp(16), color=BLEU_NUIT, bold=True,
                                size_hint=(1, None), height=dp(60), halign="center"))
        corps.add_widget(Label(text="Saisissez votre nom et votre mot de passe",
                                font_size=dp(12), color=GRIS_TEXTE, size_hint=(1, None), height=dp(24)))

        self.champ_login = TextInput(hint_text="Login", multiline=False, size_hint=(1, None), height=dp(44))
        self.champ_pass = TextInput(hint_text="Mot de passe", multiline=False, password=True, size_hint=(1, None), height=dp(44))
        self.lbl_erreur = Label(text="", color=(0.75, 0.15, 0.1, 1), font_size=dp(12), size_hint=(1, None), height=dp(24))

        corps.add_widget(self.champ_login)
        corps.add_widget(self.champ_pass)
        corps.add_widget(self.lbl_erreur)

        ligne_boutons = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(10))
        ligne_boutons.add_widget(bouton("OK", self.connecter))
        ligne_boutons.add_widget(bouton("Annuler", self.effacer, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        corps.add_widget(ligne_boutons)
        corps.add_widget(BoxLayout())

        lbl_realisateur = Label(text=f"Réalisé par {NOM_REALISATEUR}",
                                 font_size=dp(11), color=(0.6, 0.66, 0.72, 1),
                                 size_hint=(1, None), height=dp(22), halign="center")
        lbl_realisateur.bind(size=lambda *a: setattr(lbl_realisateur, "text_size", lbl_realisateur.size))
        corps.add_widget(lbl_realisateur)

        racine.add_widget(corps)
        self.add_widget(racine)

    def connecter(self, *args):
        if not self.champ_login.text.strip() or not self.champ_pass.text.strip():
            self.lbl_erreur.text = "Veuillez saisir votre login et votre mot de passe."
            return
        self.lbl_erreur.text = ""
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "objectifs"

    def effacer(self, *args):
        self.champ_login.text = ""
        self.champ_pass.text = ""
        self.lbl_erreur.text = ""


# ================= Écran 2 : Choix de l'objectif =================
class EcranObjectifs(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Menu principal"))

        corps = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))
        corps.add_widget(Label(text="Choisir votre objectif SVP", font_size=dp(14), bold=True, color=BLEU_FONCE, size_hint=(1, None), height=dp(30)))

        self.carrousel = Carousel(direction="right", loop=True, size_hint=(1, 1))
        tuiles = [
            ("Données Utiles", "donnees_utiles"),
            ("Historique Intervention", "historique"),
            ("Rapport Intervention", "rapport"),
            ("Fiche Intervention", "fiche"),
        ]
        for texte, cible in tuiles:
            case = FondCouleur(JAUNE, orientation="vertical", padding=dp(16))
            case.add_widget(Button(
                text=texte, background_normal="", background_color=(0, 0, 0, 0),
                color=BLEU_NUIT, bold=True, font_size=dp(17),
                on_release=lambda inst, c=cible: self.aller_vers(c)
            ))
            self.carrousel.add_widget(case)

        corps.add_widget(self.carrousel)
        self.btn_mode_sombre = bouton(self._libelle_mode_sombre(), self.basculer_theme,
                                       couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE)
        corps.add_widget(self.btn_mode_sombre)
        corps.add_widget(bouton("Se déconnecter", self.deconnecter, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        racine.add_widget(corps)
        self.add_widget(racine)
        self._evenement_rotation = None

    def _libelle_mode_sombre(self):
        return "☀️ Passer en mode clair" if est_mode_sombre() else "🌙 Passer en mode sombre"

    def basculer_theme(self, *args):
        basculer_mode_sombre(not est_mode_sombre())
        self.btn_mode_sombre.text = self._libelle_mode_sombre()

    def on_enter(self):
        self.btn_mode_sombre.text = self._libelle_mode_sombre()
        self._evenement_rotation = Clock.schedule_interval(self._tourner, 3.5)

    def on_leave(self):
        if self._evenement_rotation is not None:
            self._evenement_rotation.cancel()
            self._evenement_rotation = None

    def _tourner(self, dt):
        self.carrousel.load_next(mode="loop")

    def aller_vers(self, nom_ecran):
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = nom_ecran

    def deconnecter(self, *args):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "login"


# ================= Écran : Données Utiles =================
class EcranDonneesUtiles(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Données Utiles"))

        scroll = ScrollView()
        corps = GridLayout(cols=1, padding=dp(16), spacing=dp(20), size_hint=(1, None))
        corps.bind(minimum_height=corps.setter("height"))

        corps.add_widget(SectionGeree("Liste Équipement", get_equipements, ajouter_equipement, supprimer_equipement))
        corps.add_widget(SectionGeree("Liste Intervenant", get_intervenants, ajouter_intervenant, supprimer_intervenant))
        corps.add_widget(SectionGeree("Défauts Généraux", get_defauts, ajouter_defaut, supprimer_defaut))

        corps.add_widget(bouton("Sauvegarder la base (Backup DB)", self.sauvegarder_db, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        corps.add_widget(bouton("← Menu principal", self.retour, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))

        scroll.add_widget(corps)
        racine.add_widget(scroll)
        self.add_widget(racine)

    def on_pre_enter(self):
        for enfant in self.walk():
            if isinstance(enfant, SectionGeree):
                enfant.recharger()

    def sauvegarder_db(self, *args):
        try:
            dossier = obtenir_dossier_export()
            nom_backup = f"donnee_utile_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            destination = os.path.join(dossier, nom_backup)
            shutil.copy(DB_PATH, destination)

            popup = Popup(title="Backup réussi",
                          content=Label(text=f"Base sauvegardée dans :\n{destination}"),
                          size_hint=(0.88, 0.4))
            popup.open()
        except Exception as e:
            popup = Popup(title="Erreur Backup",
                          content=Label(text=f"Impossible de sauvegarder :\n{e}"),
                          size_hint=(0.88, 0.4))
            popup.open()

    def retour(self, *args):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "objectifs"


# ================= Écran : Historique Intervention =================
class EcranHistorique(Screen):
    COLONNES = ["N° OT", "Date", "Poste", "Équipement", "Type", "Anomalie", "Action", "Durée", "Interv. 1", "Interv. 2", "Remarques", "Statut"]
    TAILLE_PAGE = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.page_courante = 0
        self.total_lignes = 0
        self._filtres_actuels = {}

        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Historique Intervention"))

        barre_haute = BoxLayout(size_hint=(1, None), height=dp(46), padding=(dp(10), 0), spacing=dp(8))
        barre_haute.add_widget(bouton("← Menu", self.retour, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        barre_haute.add_widget(bouton("Excel / CSV", self.exporter_excel, couleur_fond=(0.1, 0.5, 0.2, 1), couleur_texte=BLANC))
        barre_haute.add_widget(bouton("PDF", self.imprimer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        racine.add_widget(barre_haute)

        # ----- Filtres + Recherche -----
        barre_filtres = BoxLayout(size_hint=(1, None), padding=(dp(10), dp(8)), spacing=dp(8), orientation="vertical")
        barre_filtres.bind(minimum_height=barre_filtres.setter("height"))

        self.champ_recherche = TextInput(hint_text="🔍 Recherche libre (OT, anomalie, action...)", multiline=False, size_hint=(1, None), height=dp(44))
        self.champ_recherche.bind(text=lambda inst, val: self._filtre_change())
        barre_filtres.add_widget(self.champ_recherche)

        ligne_filtre_1 = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.spinner_filtre_equipement = Spinner(text="Tous les équipements", values=(), size_hint=(1, 1))
        ligne_filtre_1.add_widget(self.spinner_filtre_equipement)
        barre_filtres.add_widget(ligne_filtre_1)

        ligne_filtre_statut = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.spinner_filtre_statut = Spinner(text="Tous les statuts",
                                              values=("Tous les statuts",) + STATUTS_INTERVENTION,
                                              size_hint=(1, 1))
        self.spinner_filtre_statut.bind(text=lambda inst, val: self._filtre_change())
        ligne_filtre_statut.add_widget(self.spinner_filtre_statut)
        barre_filtres.add_widget(ligne_filtre_statut)

        # ----- Raccourcis de date -----
        barre_filtres.add_widget(ligne_raccourcis_dates(self.appliquer_raccourci_date))

        ligne_filtre_2 = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.champ_date_debut = TextInput(hint_text="Début AAAA-MM-JJ", multiline=False, size_hint=(0.35, 1))
        self.champ_date_fin = TextInput(hint_text="Fin AAAA-MM-JJ", multiline=False, size_hint=(0.35, 1))
        btn_filtrer = Button(text="Filtrer", size_hint=(0.15, 1), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True, font_size=dp(12))
        btn_filtrer.bind(on_release=lambda inst: self._filtre_change())
        btn_reinit = Button(text="✕", size_hint=(0.15, 1), background_normal="", background_color=(0.85, 0.88, 0.9, 1), color=GRIS_TEXTE, font_size=dp(12))
        btn_reinit.bind(on_release=lambda inst: self.reinitialiser_filtres())
        ligne_filtre_2.add_widget(self.champ_date_debut)
        ligne_filtre_2.add_widget(self.champ_date_fin)
        ligne_filtre_2.add_widget(btn_filtrer)
        ligne_filtre_2.add_widget(btn_reinit)
        barre_filtres.add_widget(ligne_filtre_2)

        racine.add_widget(barre_filtres)

        self.scroll_v = ScrollView(size_hint=(1, 1))
        self.conteneur_cartes = GridLayout(cols=1, spacing=dp(10), padding=dp(10), size_hint=(1, None))
        self.conteneur_cartes.bind(minimum_height=self.conteneur_cartes.setter("height"))
        self.scroll_v.add_widget(self.conteneur_cartes)
        racine.add_widget(self.scroll_v)

        # ----- Barre de pagination (Précédent / Suivant) -----
        barre_pagination = BoxLayout(size_hint=(1, None), height=dp(48), padding=(dp(10), dp(4)), spacing=dp(8))
        self.btn_page_precedente = Button(text="◀ Précédent", size_hint=(0.28, 1), background_normal="",
                                           background_color=(0.85, 0.88, 0.9, 1), color=GRIS_TEXTE,
                                           font_size=dp(12), bold=True)
        self.btn_page_precedente.bind(on_release=lambda inst: self.changer_page(-1))
        self.lbl_pagination = Label(text="", size_hint=(0.44, 1), color=BLEU_NUIT, font_size=dp(11.5), bold=True)
        self.btn_page_suivante = Button(text="Suivant ▶", size_hint=(0.28, 1), background_normal="",
                                         background_color=(0.85, 0.88, 0.9, 1), color=GRIS_TEXTE,
                                         font_size=dp(12), bold=True)
        self.btn_page_suivante.bind(on_release=lambda inst: self.changer_page(1))
        barre_pagination.add_widget(self.btn_page_precedente)
        barre_pagination.add_widget(self.lbl_pagination)
        barre_pagination.add_widget(self.btn_page_suivante)
        racine.add_widget(barre_pagination)

        self.add_widget(racine)

    def on_pre_enter(self):
        noms_equipements = [nom for _, nom in get_equipements()]
        self.spinner_filtre_equipement.values = ["Tous les équipements"] + noms_equipements
        if self.spinner_filtre_equipement.text not in self.spinner_filtre_equipement.values:
            self.spinner_filtre_equipement.text = "Tous les équipements"
        self.page_courante = 0
        self.remplir_tableau()

    def _filtre_change(self):
        """Un filtre (recherche, statut, date...) a changé : on revient à la première page."""
        self.page_courante = 0
        self.remplir_tableau()

    def appliquer_raccourci_date(self, cle):
        debut, fin = calculer_plage_date(cle)
        self.champ_date_debut.text = debut
        self.champ_date_fin.text = fin
        self._filtre_change()

    def reinitialiser_filtres(self):
        self.champ_recherche.text = ""
        self.spinner_filtre_equipement.text = "Tous les équipements"
        self.spinner_filtre_statut.text = "Tous les statuts"
        self.champ_date_debut.text = ""
        self.champ_date_fin.text = ""
        self.page_courante = 0
        self.remplir_tableau()

    def changer_page(self, delta):
        max_page = max((self.total_lignes - 1) // self.TAILLE_PAGE, 0) if self.total_lignes else 0
        nouvelle_page = self.page_courante + delta
        if nouvelle_page < 0 or nouvelle_page > max_page:
            return
        self.page_courante = nouvelle_page
        self.remplir_tableau()
        self.scroll_v.scroll_y = 1  # remonte en haut de la liste de cartes

    def remplir_tableau(self):
        self.conteneur_cartes.clear_widgets()
        equipement = self.spinner_filtre_equipement.text
        if equipement == "Tous les équipements":
            equipement = None

        statut = self.spinner_filtre_statut.text
        if statut == "Tous les statuts":
            statut = None

        self._filtres_actuels = dict(
            equipement=equipement,
            date_debut=self.champ_date_debut.text.strip() or None,
            date_fin=self.champ_date_fin.text.strip() or None,
            recherche=self.champ_recherche.text.strip() or None,
            statut=statut
        )

        # Nombre total de résultats pour cette recherche (sans tout charger)
        self.total_lignes = compter_interventions(**self._filtres_actuels)
        max_page = max((self.total_lignes - 1) // self.TAILLE_PAGE, 0) if self.total_lignes else 0
        if self.page_courante > max_page:
            self.page_courante = max_page

        # Ne charge qu'une page (20 par défaut) de cartes à la fois : évite de
        # ralentir l'app quand l'historique contient des milliers d'interventions.
        lignes = get_interventions(
            **self._filtres_actuels,
            limite=self.TAILLE_PAGE,
            decalage=self.page_courante * self.TAILLE_PAGE
        )

        if not lignes:
            vide = Label(text="Aucune intervention trouvée", size_hint=(1, None), height=dp(40), color=GRIS_TEXTE, font_size=dp(13))
            self.conteneur_cartes.add_widget(vide)
        else:
            for ligne in lignes:
                intervention_id = ligne[0]
                donnees = ligne[1:]
                self.conteneur_cartes.add_widget(construire_carte_intervention(
                    self.COLONNES, donnees, intervention_id=intervention_id,
                    on_modifier=self.modifier_intervention_ui, on_supprimer=self.supprimer_intervention_ui
                ))

        self.dernieres_lignes = [ligne[1:] for ligne in lignes]

        # ----- Mise à jour de la barre de pagination -----
        if self.total_lignes:
            debut_affiche = self.page_courante * self.TAILLE_PAGE + 1
            fin_affiche = min((self.page_courante + 1) * self.TAILLE_PAGE, self.total_lignes)
            nb_pages = max_page + 1
            self.lbl_pagination.text = f"{debut_affiche}-{fin_affiche} sur {self.total_lignes} (page {self.page_courante + 1}/{nb_pages})"
        else:
            self.lbl_pagination.text = "0 résultat"
        self.btn_page_precedente.disabled = self.page_courante <= 0
        self.btn_page_suivante.disabled = self.page_courante >= max_page

    def modifier_intervention_ui(self, intervention_id):
        ouvrir_popup_edition_intervention(intervention_id, on_succes=self.remplir_tableau)

    def supprimer_intervention_ui(self, intervention_id):
        ouvrir_popup_confirmation_suppression(intervention_id, on_succes=self.remplir_tableau)

    def _lignes_completes_filtrees(self):
        """Récupère TOUTES les lignes correspondant aux filtres actuels (sans pagination),
        pour que les exports Excel/PDF couvrent bien l'ensemble du résultat filtré,
        même si l'écran n'en affiche qu'une page à la fois."""
        lignes = get_interventions(**self._filtres_actuels)
        return [_formater_ligne_export(ligne[1:]) for ligne in lignes]

    def exporter_excel(self, *args):
        try:
            lignes_completes = self._lignes_completes_filtrees()
            chemin = exporter_csv("Historique Maintenance", self.COLONNES, lignes_completes, "historique_maintenance.csv")
            popup = Popup(title="Export CSV réussi", content=Label(text=f"Fichier créé :\n{chemin}"), size_hint=(0.88, 0.4))
            popup.open()
        except Exception as e:
            afficher_popup_erreur_generique("Erreur export CSV", f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

    def imprimer(self, *args):
        sous_titre = f"Historique - Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        if not FPDF_DISPONIBLE:
            afficher_popup_erreur_fpdf()
            return

        lancer_generation_pdf_en_arriere_plan(
            "Historique Intervention - Delice", sous_titre, self.COLONNES,
            self._lignes_completes_filtrees, "historique_intervention.pdf"
        )

    def retour(self, *args):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "objectifs"


# ================= Écran : Rapport Intervention =================
class EcranRapport(Screen):
    COLONNES = ["N° OT", "Date", "Poste", "Équipement", "Type", "Anomalie", "Action", "Durée", "Interv. 1", "Interv. 2", "Remarques", "Statut"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Rapport Intervention"))

        barre_haute = BoxLayout(size_hint=(1, None), height=dp(46), padding=(dp(10), 0), spacing=dp(8))
        barre_haute.add_widget(bouton("← Menu", self.retour, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        barre_haute.add_widget(bouton("Excel / CSV", self.exporter_excel, couleur_fond=(0.1, 0.5, 0.2, 1), couleur_texte=BLANC))
        barre_haute.add_widget(bouton("PDF", self.imprimer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        racine.add_widget(barre_haute)

        # ----- Barre de filtres + KPIs -----
        barre_filtres = BoxLayout(size_hint=(1, None), padding=(dp(10), dp(8)), spacing=dp(8), orientation="vertical")
        barre_filtres.bind(minimum_height=barre_filtres.setter("height"))

        # ----- Raccourcis de date -----
        barre_filtres.add_widget(ligne_raccourcis_dates(self.appliquer_raccourci_date))

        ligne_periode = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        ligne_periode.add_widget(Label(text="Du", size_hint=(0.15, 1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.champ_date_debut = TextInput(hint_text="AAAA-MM-JJ", multiline=False, size_hint=(0.35, 1))
        ligne_periode.add_widget(self.champ_date_debut)
        ligne_periode.add_widget(Label(text="Au", size_hint=(0.15, 1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.champ_date_fin = TextInput(hint_text="AAAA-MM-JJ", multiline=False, size_hint=(0.35, 1))
        ligne_periode.add_widget(self.champ_date_fin)
        barre_filtres.add_widget(ligne_periode)

        ligne_poste = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        ligne_poste.add_widget(Label(text="Poste", size_hint=(0.3, 1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.spinner_poste = Spinner(text="Tous les postes", values=("Tous les postes", "Jour", "Après-midi", "Nuit"), size_hint=(0.7, 1))
        ligne_poste.add_widget(self.spinner_poste)
        barre_filtres.add_widget(ligne_poste)

        ligne_statut = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        ligne_statut.add_widget(Label(text="Statut", size_hint=(0.3, 1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.spinner_statut = Spinner(text="Tous les statuts", values=("Tous les statuts",) + STATUTS_INTERVENTION, size_hint=(0.7, 1))
        ligne_statut.add_widget(self.spinner_statut)
        barre_filtres.add_widget(ligne_statut)

        ligne_actions = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
        ligne_actions.add_widget(bouton("Générer le rapport", self.generer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        ligne_actions.add_widget(bouton("Réinitialiser", self.reinitialiser, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        barre_filtres.add_widget(ligne_actions)

        racine.add_widget(barre_filtres)

        self.lbl_kpi = Label(text="", font_size=dp(12), bold=True, color=BLEU_FONCE,
                              size_hint=(1, None), halign="left", valign="middle")
        self.lbl_kpi.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.lbl_kpi.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(10)))
        conteneur_kpi = BoxLayout(size_hint=(1, None), padding=(dp(12), dp(4)))
        conteneur_kpi.bind(minimum_height=conteneur_kpi.setter("height"))
        conteneur_kpi.add_widget(self.lbl_kpi)
        racine.add_widget(conteneur_kpi)

        racine.add_widget(bouton("Voir le Top 5 des pannes", self.ouvrir_popup_top5,
                                  couleur_fond=(0.90, 0.93, 0.97, 1), couleur_texte=BLEU_NUIT))

        self.top5_equipements = []
        self.top5_anomalies = []

        self.scroll_v = ScrollView(size_hint=(1, 1))
        self.conteneur_cartes = GridLayout(cols=1, spacing=dp(10), padding=dp(10), size_hint=(1, None))
        self.conteneur_cartes.bind(minimum_height=self.conteneur_cartes.setter("height"))
        self.scroll_v.add_widget(self.conteneur_cartes)
        racine.add_widget(self.scroll_v)

        self.add_widget(racine)

    def on_pre_enter(self):
        self.generer()

    def ouvrir_popup_top5(self, *args):
        contenu = FondCouleur(BLANC, orientation="vertical", padding=dp(14), spacing=dp(10))

        scroll = ScrollView(size_hint=(1, 1))
        corps = BoxLayout(orientation="vertical", size_hint=(1, None), spacing=dp(16), padding=(0, dp(4)))
        corps.bind(minimum_height=corps.setter("height"))
        corps.add_widget(construire_bloc_top5(
            "Top 5 Équipements les plus en panne",
            self.top5_equipements, couleur_barre=BLEU_FONCE
        ))
        corps.add_widget(construire_bloc_top5(
            "Top 5 Anomalies les plus fréquentes",
            self.top5_anomalies, couleur_barre=ORANGE_A_SUIVRE
        ))
        scroll.add_widget(corps)
        contenu.add_widget(scroll)

        popup = Popup(title="Top 5 des pannes", content=contenu, size_hint=(0.94, 0.85),
                       background_color=(1, 1, 1, 1), title_color=BLEU_NUIT)
        contenu.add_widget(bouton("Fermer", lambda inst: popup.dismiss(),
                                   couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))
        popup.open()

    def appliquer_raccourci_date(self, cle):
        debut, fin = calculer_plage_date(cle)
        self.champ_date_debut.text = debut
        self.champ_date_fin.text = fin
        self.generer()

    def reinitialiser(self, *args):
        self.champ_date_debut.text = ""
        self.champ_date_fin.text = ""
        self.spinner_poste.text = "Tous les postes"
        self.spinner_statut.text = "Tous les statuts"
        self.generer()

    def generer(self, *args):
        self.conteneur_cartes.clear_widgets()
        poste = self.spinner_poste.text
        if poste == "Tous les postes":
            poste = None

        statut = self.spinner_statut.text
        if statut == "Tous les statuts":
            statut = None

        lignes = get_interventions(
            date_debut=self.champ_date_debut.text.strip() or None,
            date_fin=self.champ_date_fin.text.strip() or None,
            poste=poste,
            statut=statut
        )

        compteur_equipements = Counter()
        compteur_anomalies = Counter()

        if not lignes:
            vide = Label(text="Aucune intervention trouvée", size_hint=(1, None), height=dp(40), color=GRIS_TEXTE, font_size=dp(13))
            self.conteneur_cartes.add_widget(vide)
            self.lbl_kpi.text = "0 intervention"
        else:
            duree_totale = 0
            nb_a_suivre = 0
            for ligne in lignes:
                intervention_id = ligne[0]
                donnees = ligne[1:]
                if donnees[-1] == "À suivre":
                    nb_a_suivre += 1
                self.conteneur_cartes.add_widget(construire_carte_intervention(
                    self.COLONNES, donnees, intervention_id=intervention_id,
                    on_modifier=self.modifier_intervention_ui, on_supprimer=self.supprimer_intervention_ui
                ))
                try:
                    duree_totale += int(donnees[7])
                except (ValueError, TypeError):
                    pass

                nom_equipement = donnees[3] or "—"
                nom_anomalie = donnees[5] or "—"
                compteur_equipements[nom_equipement] += 1
                compteur_anomalies[nom_anomalie] += 1

            mttr = round(duree_totale / len(lignes), 1) if len(lignes) > 0 else 0
            self.lbl_kpi.text = (
                f"Total: {len(lignes)} inter. | Durée: {duree_totale} min | "
                f"MTTR (moyenne): {mttr} min | À suivre: {nb_a_suivre}"
            )

        self.top5_equipements = compteur_equipements.most_common(5)
        self.top5_anomalies = compteur_anomalies.most_common(5)

        self.dernieres_lignes = [_formater_ligne_export(ligne[1:]) for ligne in lignes]

    def modifier_intervention_ui(self, intervention_id):
        ouvrir_popup_edition_intervention(intervention_id, on_succes=self.generer)

    def supprimer_intervention_ui(self, intervention_id):
        ouvrir_popup_confirmation_suppression(intervention_id, on_succes=self.generer)

    def exporter_excel(self, *args):
        try:
            chemin = exporter_csv("Rapport Maintenance", self.COLONNES, getattr(self, "dernieres_lignes", []), "rapport_maintenance.csv")
            popup = Popup(title="Export CSV réussi", content=Label(text=f"Fichier créé :\n{chemin}"), size_hint=(0.88, 0.4))
            popup.open()
        except Exception as e:
            afficher_popup_erreur_generique("Erreur export CSV", f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")

    def imprimer(self, *args):
        sous_titre = f"Rapport - {self.lbl_kpi.text}"
        if not FPDF_DISPONIBLE:
            afficher_popup_erreur_fpdf()
            return

        donnees = getattr(self, "dernieres_lignes", [])
        lancer_generation_pdf_en_arriere_plan(
            "Rapport Intervention - Delice", sous_titre, self.COLONNES,
            lambda: donnees, "rapport_intervention.pdf"
        )

    def retour(self, *args):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "objectifs"


# ================= Écran 4 : Fiche Intervention =================
class EcranFiche(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        racine = BoxLayout(orientation="vertical")
        racine.add_widget(entete("Fiche Intervention"))

        scroll = ScrollView()
        corps = GridLayout(cols=1, padding=dp(16), spacing=dp(16), size_hint=(1, None))
        corps.bind(minimum_height=corps.setter("height"))

        def label(texte):
            l = Label(text=texte, font_size=dp(12), bold=True, color=BLEU_NUIT, size_hint=(1, None), height=dp(20), halign="left")
            l.bind(size=lambda *a: setattr(l, "text_size", l.size))
            return l

        corps.add_widget(label("Numéro Ordre de Travail"))
        self.champ_numero_ot = TextInput(hint_text="ex: 504567 (6 chiffres)", multiline=False,
                                          input_filter="int", size_hint=(1, None), height=dp(44))
        corps.add_widget(self.champ_numero_ot)

        corps.add_widget(label("Poste (Auto-détecté)"))
        self.spinner_poste = Spinner(text=obtenir_poste_actuel(), values=("Jour", "Après-midi", "Nuit"), size_hint=(1, None), height=dp(44))
        corps.add_widget(self.spinner_poste)

        corps.add_widget(label("Équipement"))
        ligne_equipement = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.spinner_equipement = Spinner(text="— sélectionner —", values=(), size_hint=(1, 1))
        btn_ajout_equip = Button(text="+", size_hint=(None, 1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        btn_ajout_equip.bind(on_release=self.ajouter_equipement_popup)
        ligne_equipement.add_widget(self.spinner_equipement)
        ligne_equipement.add_widget(btn_ajout_equip)
        corps.add_widget(ligne_equipement)

        corps.add_widget(label("Type de maintenance"))
        self.spinner_type = Spinner(text="Corrective", values=("Corrective", "Préventive", "Prédictive"), size_hint=(1, None), height=dp(44))
        corps.add_widget(self.spinner_type)

        corps.add_widget(label("Anomalie"))
        self.champ_anomalie = TextInput(multiline=False, size_hint=(1, None), height=dp(44))
        corps.add_widget(self.champ_anomalie)
        corps.add_widget(bouton("📋 Choisir un défaut dans la liste", self.ouvrir_liste_defauts,
                                 couleur_fond=(0.90, 0.93, 0.97, 1), couleur_texte=BLEU_NUIT))

        corps.add_widget(label("Action"))
        self.champ_action = TextInput(multiline=True, size_hint=(1, None), height=dp(80))
        corps.add_widget(self.champ_action)

        corps.add_widget(label("Durée (min)"))
        self.champ_duree = TextInput(multiline=False, input_filter="int", size_hint=(1, None), height=dp(44))
        corps.add_widget(self.champ_duree)

        corps.add_widget(label("Intervenant 1"))
        ligne_int1 = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.spinner_intervenant1 = Spinner(text="— aucun —", values=(), size_hint=(1, 1))
        btn_ajout_int1 = Button(text="+", size_hint=(None, 1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        btn_ajout_int1.bind(on_release=lambda inst: self.ajouter_intervenant_popup(self.spinner_intervenant1))
        ligne_int1.add_widget(self.spinner_intervenant1)
        ligne_int1.add_widget(btn_ajout_int1)
        corps.add_widget(ligne_int1)

        corps.add_widget(label("Intervenant 2"))
        ligne_int2 = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.spinner_intervenant2 = Spinner(text="— aucun —", values=(), size_hint=(1, 1))
        btn_ajout_int2 = Button(text="+", size_hint=(None, 1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        btn_ajout_int2.bind(on_release=lambda inst: self.ajouter_intervenant_popup(self.spinner_intervenant2))
        ligne_int2.add_widget(self.spinner_intervenant2)
        ligne_int2.add_widget(btn_ajout_int2)
        corps.add_widget(ligne_int2)

        corps.add_widget(label("Remarques"))
        self.champ_remarques = TextInput(multiline=True, size_hint=(1, None), height=dp(80))
        corps.add_widget(self.champ_remarques)

        corps.add_widget(label("Statut de la panne"))
        ligne_statut = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(6))
        self.btn_statut_resolue = Button(text="✔ Résolue", size_hint=(0.5, 1), background_normal="",
                                          background_color=VERT_RESOLU, color=BLANC, bold=True, font_size=dp(13))
        self.btn_statut_a_suivre = Button(text="⏱ À suivre", size_hint=(0.5, 1), background_normal="",
                                           background_color=(0.85, 0.88, 0.9, 1), color=GRIS_TEXTE, bold=True, font_size=dp(13))
        self.btn_statut_resolue.bind(on_release=lambda inst: self._choisir_statut("Résolue"))
        self.btn_statut_a_suivre.bind(on_release=lambda inst: self._choisir_statut("À suivre"))
        ligne_statut.add_widget(self.btn_statut_resolue)
        ligne_statut.add_widget(self.btn_statut_a_suivre)
        corps.add_widget(ligne_statut)
        self.statut_selectionne = "Résolue"

        self.lbl_confirmation = Label(text="", font_size=dp(12), color=(0.1, 0.5, 0.2, 1), size_hint=(1, None), height=dp(24))
        corps.add_widget(self.lbl_confirmation)

        corps.add_widget(bouton("Enregistrer", self.enregistrer, couleur_fond=BLEU_FONCE))
        corps.add_widget(bouton("← Retour", self.retour, couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))

        scroll.add_widget(corps)
        racine.add_widget(scroll)
        self.add_widget(racine)

    def _choisir_statut(self, statut):
        self.statut_selectionne = statut
        if statut == "Résolue":
            self.btn_statut_resolue.background_color = VERT_RESOLU
            self.btn_statut_resolue.color = BLANC
            self.btn_statut_a_suivre.background_color = (0.85, 0.88, 0.9, 1)
            self.btn_statut_a_suivre.color = GRIS_TEXTE
        else:
            self.btn_statut_a_suivre.background_color = ORANGE_A_SUIVRE
            self.btn_statut_a_suivre.color = BLANC
            self.btn_statut_resolue.background_color = (0.85, 0.88, 0.9, 1)
            self.btn_statut_resolue.color = GRIS_TEXTE

    def on_pre_enter(self):
        self.spinner_poste.text = obtenir_poste_actuel()
        self.recharger_equipements()
        self.recharger_intervenants()

    def ouvrir_liste_defauts(self, *args):
        contenu = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))

        lbl_titre_popup = Label(text="Sélectionner un défaut", font_size=dp(15), bold=True, color=BLEU_NUIT,
                                 size_hint=(1, None), height=dp(28))
        contenu.add_widget(lbl_titre_popup)

        scroll = ScrollView(size_hint=(1, 1))
        grille = GridLayout(cols=1, spacing=dp(8), size_hint=(1, None), padding=(0, dp(4)))
        grille.bind(minimum_height=grille.setter("height"))
        scroll.add_widget(grille)
        contenu.add_widget(scroll)

        ligne_bas = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(8))
        contenu.add_widget(ligne_bas)

        popup = Popup(title="", separator_height=0, content=contenu, size_hint=(0.94, 0.82))

        def selectionner(description, *a):
            self.champ_anomalie.text = description
            popup.dismiss()

        defauts = get_defauts()
        if not defauts:
            grille.add_widget(Label(text="Aucun défaut enregistré pour l'instant.", size_hint=(1, None),
                                     height=dp(44), color=GRIS_TEXTE, font_size=dp(13)))
        else:
            largeur_bouton = Window.width * 0.94 - dp(24) - dp(24)
            for _, description in defauts:
                btn = Button(text=description, size_hint=(1, None), background_normal="",
                             background_color=(0.95, 0.97, 1, 1), color=GRIS_TEXTE, font_size=dp(13.5),
                             halign="left", valign="middle", padding=(dp(12), dp(10)))
                btn.text_size = (largeur_bouton, None)

                def _ajuster_hauteur(instance, taille_texture):
                    instance.height = max(dp(46), taille_texture[1] + dp(20))

                btn.bind(texture_size=_ajuster_hauteur)
                btn.bind(on_release=lambda inst, d=description: selectionner(d))
                grille.add_widget(btn)

        ligne_bas.add_widget(bouton("+ Nouveau défaut", lambda inst: self.ajouter_defaut_popup(popup_liste=popup),
                                     couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        ligne_bas.add_widget(bouton("Fermer", lambda inst: popup.dismiss(),
                                     couleur_fond=(0.85, 0.88, 0.9, 1), couleur_texte=GRIS_TEXTE))

        popup.open()

    def ajouter_defaut_popup(self, *args, popup_liste=None):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        champ = TextInput(hint_text="Nouveau défaut", multiline=False, size_hint=(1, None), height=dp(44))
        contenu.add_widget(champ)
        popup = Popup(title="Nouveau défaut", content=contenu, size_hint=(0.85, 0.35))

        def valider(*a):
            description = champ.text.strip()
            if description:
                ajouter_defaut(description)
                self.champ_anomalie.text = description
            popup.dismiss()
            if popup_liste is not None:
                popup_liste.dismiss()

        contenu.add_widget(bouton("Ajouter", valider, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        popup.open()

    def recharger_intervenants(self):
        intervenants = get_intervenants()
        noms = [nom for _, nom in intervenants]
        self.spinner_intervenant1.values = noms
        self.spinner_intervenant2.values = ["— aucun —"] + noms
        if self.spinner_intervenant1.text not in noms and self.spinner_intervenant1.text != "— aucun —":
            self.spinner_intervenant1.text = "— aucun —" if not noms else noms[0]
        if self.spinner_intervenant2.text not in self.spinner_intervenant2.values:
            self.spinner_intervenant2.text = "— aucun —"

    def ajouter_intervenant_popup(self, spinner_cible):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        champ = TextInput(hint_text="Nom de l'intervenant", multiline=False, size_hint=(1, None), height=dp(44))
        contenu.add_widget(champ)
        popup = Popup(title="Nouvel intervenant", content=contenu, size_hint=(0.85, 0.35))

        def valider(*a):
            nom = champ.text.strip()
            if nom:
                ajouter_intervenant(nom)
                self.recharger_intervenants()
                spinner_cible.text = nom
            popup.dismiss()

        contenu.add_widget(bouton("Ajouter", valider, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        popup.open()

    def recharger_equipements(self, selectionner=None):
        equipements = get_equipements()
        noms = [nom for _, nom in equipements]
        self.spinner_equipement.values = noms
        if selectionner and selectionner in noms:
            self.spinner_equipement.text = selectionner
        elif self.spinner_equipement.text not in noms:
            self.spinner_equipement.text = "— sélectionner —"

    def ajouter_equipement_popup(self, *args):
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        champ = TextInput(hint_text="Nom du nouvel équipement", multiline=False, size_hint=(1, None), height=dp(44))
        contenu.add_widget(champ)
        popup = Popup(title="Nouvel équipement", content=contenu, size_hint=(0.85, 0.35))

        def valider(*a):
            nom = champ.text.strip()
            if nom:
                ajouter_equipement(nom)
                self.recharger_equipements(selectionner=nom)
            popup.dismiss()

        contenu.add_widget(bouton("Ajouter", valider, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        popup.open()

    def enregistrer(self, *args):
        if getattr(self, "_enregistrement_en_cours", False):
            return

        if self.spinner_equipement.text == "— sélectionner —" or not self.champ_anomalie.text.strip():
            self.lbl_confirmation.color = (0.75, 0.15, 0.1, 1)
            self.lbl_confirmation.text = "Renseignez au moins l'équipement et l'anomalie."
            return

        ot_valide, message_erreur_ot = valider_numero_ot(self.champ_numero_ot.text)
        if not ot_valide:
            self.lbl_confirmation.color = (0.75, 0.15, 0.1, 1)
            self.lbl_confirmation.text = message_erreur_ot
            return

        duree_valide, message_erreur_duree = valider_duree(self.champ_duree.text)
        if not duree_valide:
            self.lbl_confirmation.color = (0.75, 0.15, 0.1, 1)
            self.lbl_confirmation.text = message_erreur_duree
            return

        self._enregistrement_en_cours = True

        intervenant1 = "" if self.spinner_intervenant1.text == "— aucun —" else self.spinner_intervenant1.text
        intervenant2 = "" if self.spinner_intervenant2.text == "— aucun —" else self.spinner_intervenant2.text

        try:
            enregistrer_intervention({
                "numero_ordre_travail": self.champ_numero_ot.text.strip(),
                "poste": self.spinner_poste.text,
                "equipement": self.spinner_equipement.text,
                "type_maintenance": self.spinner_type.text,
                "anomalie": self.champ_anomalie.text.strip(),
                "action": self.champ_action.text.strip(),
                "duree": self.champ_duree.text.strip(),
                "intervenant1": intervenant1,
                "intervenant2": intervenant2,
                "remarques": self.champ_remarques.text.strip(),
                "statut": self.statut_selectionne,
            })
        except sqlite3.Error as erreur:
            self.lbl_confirmation.color = (0.75, 0.15, 0.1, 1)
            self.lbl_confirmation.text = f"Erreur d'enregistrement : {erreur}"
            self._enregistrement_en_cours = False
            return

        self.lbl_confirmation.color = (0.1, 0.5, 0.2, 1)
        self.lbl_confirmation.text = "Fiche enregistrée avec succès."
        vibrer(0.15)
        afficher_toast("✔ Fiche enregistrée avec succès", couleur_fond=VERT_RESOLU)

        self.champ_numero_ot.text = ""
        self.champ_anomalie.text = ""
        self.champ_action.text = ""
        self.champ_duree.text = ""
        self.spinner_intervenant1.text = "— aucun —" if not self.spinner_intervenant1.values else self.spinner_intervenant1.values[0]
        self.spinner_intervenant2.text = "— aucun —"
        self.champ_remarques.text = ""
        self._choisir_statut("Résolue")

        Clock.schedule_once(lambda dt: setattr(self, "_enregistrement_en_cours", False), 1.0)

    def retour(self, *args):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "objectifs"


# ================= Application =================
class GestionMaintenanceApp(App):
    def build(self):
        # Détection automatique : poste de nuit -> mode sombre par défaut
        # (l'utilisateur garde la main via l'interrupteur du menu principal).
        basculer_mode_sombre(obtenir_poste_actuel() == "Nuit")
        init_db()

        self.sm = ScreenManager()
        self.sm.add_widget(EcranLogin(name="login"))
        self.sm.add_widget(EcranObjectifs(name="objectifs"))
        self.sm.add_widget(EcranDonneesUtiles(name="donnees_utiles"))
        self.sm.add_widget(EcranHistorique(name="historique"))
        self.sm.add_widget(EcranRapport(name="rapport"))
        self.sm.add_widget(EcranFiche(name="fiche"))

        Window.bind(on_keyboard=self.gerer_bouton_retour)
        return self.sm

    def gerer_bouton_retour(self, window, key, *args):
        if key == 27:
            ecran_actuel = self.sm.current
            if ecran_actuel == "login":
                return False
            if ecran_actuel == "objectifs":
                self.sm.transition = SlideTransition(direction="right")
                self.sm.current = "login"
                return True

            self.sm.transition = SlideTransition(direction="right")
            self.sm.current = "objectifs"
            return True
        return False


if __name__ == "__main__":
    GestionMaintenanceApp().run()
