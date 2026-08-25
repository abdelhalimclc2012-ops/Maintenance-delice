"""
Gestion Maintenance - Département Technique (Délice) - V2
----------------------------------------------------
Application mobile en Kivy, optimisée pour Android + Pydroid 3 + APK Buildozer.

CORRECTIONS V2 :
- DB_PATH robuste (Pydroid + APK)
- Dossier export Android 13+ compatible
- Fix suppression historique (ne supprime plus les OT vides)
- fpdf/fpdf2 détection robuste
- Recherche avec debounce (performance)
- Vibration + Toast sécurisés
"""

import sqlite3
import os
import csv
import shutil
import threading
import traceback
import importlib.metadata
from datetime import datetime, timedelta
from collections import Counter

try:
    from fpdf import FPDF
    FPDF_DISPONIBLE = True
    ERREUR_IMPORT_FPDF = None
except Exception as e:
    # On capture le VRAI message d'erreur (pas seulement ImportError) :
    # un probleme dans une sous-dependance de fpdf2 (fonttools, Pillow...)
    # peut lever autre chose qu'un simple ImportError, et etait avale
    # silencieusement avant, masquant la cause reelle.
    FPDF_DISPONIBLE = False
    ERREUR_IMPORT_FPDF = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"

try:
    from plyer import vibrator
    VIBRATION_DISPONIBLE = True
except Exception:
    VIBRATION_DISPONIBLE = False

try:
    from plyer import filechooser
    FILECHOOSER_DISPONIBLE = True
except Exception:
    FILECHOOSER_DISPONIBLE = False


def vibrer(duree=0.15):
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
from kivy.uix.image import Image
from kivy.uix.filechooser import FileChooserIconView
from kivy.utils import platform
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp

Window.softinput_mode = "resize"

# ---------- Couleurs ----------
BLEU_NUIT = (10/255, 61/255, 98/255, 1)
BLEU_FONCE = (15/255, 94/255, 153/255, 1)
JAUNE = (255/255, 212/255, 0/255, 1)
BLANC = (1, 1, 1, 1)
GRIS_TEXTE = (0.2, 0.28, 0.34, 1)
VERT_RESOLU = (0.13, 0.55, 0.13, 1)
ORANGE_A_SUIVRE = (0.80, 0.42, 0.04, 1)

# ---------- Chemins robustes ----------
def obtenir_db_path():
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        test_path = os.path.join(base, ".write_test")
        with open(test_path, "w") as f:
            f.write("test")
        os.remove(test_path)
        return os.path.join(base, "donnee_utile.db")
    except Exception:
        # Dossier privé APK / Pydroid
        return os.path.join(os.path.expanduser("~"), "donnee_utile.db")

DB_PATH = obtenir_db_path()
STATUTS_INTERVENTION = ("Résolue", "À suivre")
NOM_REALISATEUR = "Hichri Abdelhalim"

def obtenir_dossier_export():
    """
    Dossier externe propre a l'application (scoped storage) : aucune
    permission requise, ET visible/accessible dans un gestionnaire de
    fichiers classique (contrairement au stockage interne pur, invisible
    sans root). Chemin resultant sur le telephone :
    Stockage interne / Android / data / org.delice.maintenancedelice / files / GestionMaintenanceDelice
    """
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        contexte = PythonActivity.mActivity
        chemin_externe = contexte.getExternalFilesDir(None).getAbsolutePath()
        dossier = os.path.join(chemin_externe, "GestionMaintenanceDelice")
        os.makedirs(dossier, exist_ok=True)
        return dossier
    except Exception:
        pass

    try:
        from android.storage import app_storage_path
        dossier = os.path.join(app_storage_path(), "GestionMaintenanceDelice")
        os.makedirs(dossier, exist_ok=True)
        return dossier
    except Exception:
        pass

    try:
        app = App.get_running_app()
        if app is not None:
            dossier = os.path.join(app.user_data_dir, "GestionMaintenanceDelice")
            os.makedirs(dossier, exist_ok=True)
            return dossier
    except Exception:
        pass

    # Repli local (Pydroid 3 / bureau)
    dossier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GestionMaintenanceDelice")
    os.makedirs(dossier, exist_ok=True)
    return dossier

# ========= CONFIGURATION ENTREPRISE (nom + logo personnalises) =========
def obtenir_config_entreprise():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT nom_entreprise, chemin_logo, service FROM config_entreprise WHERE id=1")
        ligne = c.fetchone()
    if ligne:
        return {"nom": ligne[0] or "", "logo": ligne[1] or "", "service": ligne[2] or ""}
    return {"nom": "", "logo": "", "service": ""}

def definir_config_entreprise(nom, chemin_logo, service=""):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM config_entreprise WHERE id=1")
        if c.fetchone():
            c.execute("UPDATE config_entreprise SET nom_entreprise=?, chemin_logo=?, service=? WHERE id=1", (nom, chemin_logo, service))
        else:
            c.execute("INSERT INTO config_entreprise (id, nom_entreprise, chemin_logo, service) VALUES (1,?,?,?)", (nom, chemin_logo, service))

def _lire_bytes_fichier_ou_uri(chemin):
    """Lit un fichier local classique, ou une URI content:// renvoyee par le
    selecteur natif Android (necessite alors de passer par le ContentResolver)."""
    try:
        with open(chemin, "rb") as f:
            return f.read()
    except Exception:
        pass
    from jnius import autoclass
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Uri = autoclass("android.net.Uri")
    ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
    activite = PythonActivity.mActivity
    resolveur = activite.getContentResolver()
    uri = Uri.parse(chemin)
    flux = resolveur.openInputStream(uri)
    sortie = ByteArrayOutputStream()
    tampon = bytearray(4096)
    while True:
        lu = flux.read(tampon)
        if lu == -1:
            break
        sortie.write(tampon, 0, lu)
    flux.close()
    return bytes(sortie.toByteArray())

def enregistrer_logo_entreprise(chemin_source):
    """Copie le logo choisi par l'utilisateur dans le stockage propre a
    l'app et renvoie le chemin local (stable, reutilisable ensuite)."""
    donnees = _lire_bytes_fichier_ou_uri(chemin_source)
    extension = os.path.splitext(chemin_source.split("?")[0])[1].lower()
    if extension not in (".png", ".jpg", ".jpeg"):
        extension = ".png"
    chemin_local = os.path.join(obtenir_dossier_export(), f"logo_entreprise{extension}")
    with open(chemin_local, "wb") as f:
        f.write(donnees)
    return chemin_local

def obtenir_poste_actuel():
    heure = datetime.now().hour
    if 6 <= heure < 14: return "Jour"
    elif 14 <= heure < 22: return "Après-midi"
    else: return "Nuit"

# ---------- Mode sombre ----------
_MODE_SOMBRE = {"actif": False}
FOND_FENETRE_SOMBRE = (0.07, 0.08, 0.10, 1)
FOND_CARTE_SOMBRE = (0.15, 0.16, 0.19, 1)
BORDURE_CARTE_SOMBRE = (0.28, 0.31, 0.35, 1)
TEXTE_PRINCIPAL_SOMBRE = (0.82, 0.85, 0.88, 1)
TEXTE_TITRE_SOMBRE = (0.55, 0.78, 0.98, 1)

def est_mode_sombre(): return _MODE_SOMBRE["actif"]
def basculer_mode_sombre(actif):
    _MODE_SOMBRE["actif"] = actif
    Window.clearcolor = FOND_FENETRE_SOMBRE if actif else (0.94, 0.96, 0.98, 1)
def couleur_fond_carte(): return FOND_CARTE_SOMBRE if est_mode_sombre() else BLANC
def couleur_bordure_carte(): return BORDURE_CARTE_SOMBRE if est_mode_sombre() else (0.82, 0.88, 0.93, 1)
def couleur_texte_principal(): return TEXTE_PRINCIPAL_SOMBRE if est_mode_sombre() else GRIS_TEXTE
def couleur_texte_titre(): return TEXTE_TITRE_SOMBRE if est_mode_sombre() else BLEU_NUIT

def calculer_plage_date(cle):
    aujourdhui = datetime.now().date()
    if cle == "aujourdhui": debut = fin = aujourdhui
    elif cle == "hier": debut = fin = aujourdhui - timedelta(days=1)
    elif cle == "semaine":
        debut = aujourdhui - timedelta(days=aujourdhui.weekday())
        fin = aujourdhui
    elif cle == "mois":
        debut = aujourdhui.replace(day=1)
        fin = aujourdhui
    else: debut = fin = aujourdhui
    return debut.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")

# ================= Base de données =================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS config_entreprise (id INTEGER PRIMARY KEY, nom_entreprise TEXT, chemin_logo TEXT, service TEXT)")
        c.execute("PRAGMA table_info(config_entreprise)")
        cols_config = [l[1] for l in c.fetchall()]
        if "service" not in cols_config:
            c.execute("ALTER TABLE config_entreprise ADD COLUMN service TEXT")
        c.execute("CREATE TABLE IF NOT EXISTS defauts (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS equipements (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS defauts_conditionnement (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS intervenants (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_ordre_travail TEXT,
                poste TEXT, equipement TEXT, type_maintenance TEXT,
                anomalie TEXT, action TEXT, duree TEXT,
                intervenant1 TEXT, intervenant2 TEXT, remarques TEXT, date_heure TEXT, statut TEXT)""")
        c.execute("PRAGMA table_info(interventions)")
        cols = [l[1] for l in c.fetchall()]
        if "numero_ordre_travail" not in cols: c.execute("ALTER TABLE interventions ADD COLUMN numero_ordre_travail TEXT")
        if "statut" not in cols:
            c.execute("ALTER TABLE interventions ADD COLUMN statut TEXT")
            c.execute("UPDATE interventions SET statut = 'Résolue' WHERE statut IS NULL OR statut = ''")
        # FIX V2 : Ne supprime les doublons que si OT est renseigné
        c.execute("""
            DELETE FROM interventions
            WHERE numero_ordre_travail IS NOT NULL AND numero_ordre_travail != ''
            AND id NOT IN (
                SELECT MIN(id) FROM interventions
                WHERE numero_ordre_travail IS NOT NULL AND numero_ordre_travail != ''
                GROUP BY numero_ordre_travail, poste, equipement, date_heure
            )
        """)
        c.execute("SELECT COUNT(*) FROM defauts")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT INTO defauts (description) VALUES (?)", [(d,) for d in ["Défaut variateur","Coupe film","Bourrage convoyeur","Défaut capteur photocellule","Perte de synchronisation"]])
        c.execute("SELECT COUNT(*) FROM equipements")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT INTO equipements (nom) VALUES (?)", [(e,) for e in ["Conditionneuse","Applicateur languette","Convoyeur","Encaisseuse","Palettiseur"]])
        c.execute("SELECT COUNT(*) FROM intervenants")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT INTO intervenants (nom) VALUES (?)", [(i,) for i in ["K. Trabelsi","M. Chaabane"]])
        c.execute("SELECT COUNT(*) FROM defauts_conditionnement")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT INTO defauts_conditionnement (description) VALUES (?)", [(d,) for d in ["Défaut de soudure","Bourrage carton","Défaut de collage","Alignement produit incorrect"]])
        # Fusion
        c.execute("SELECT description FROM defauts")
        exist = {r[0] for r in c.fetchall()}
        c.execute("SELECT description FROM defauts_conditionnement")
        for (d,) in c.fetchall():
            if d not in exist:
                c.execute("INSERT INTO defauts (description) VALUES (?)", (d,))

def get_defauts_conditionnement():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT id, description FROM defauts_conditionnement ORDER BY id").fetchall()
def ajouter_defaut_conditionnement(d):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("INSERT INTO defauts_conditionnement (description) VALUES (?)", (d,))
def supprimer_defaut_conditionnement(i):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM defauts_conditionnement WHERE id = ?", (i,))
def get_intervenants():
    with sqlite3.connect(DB_PATH) as conn: return conn.execute("SELECT id, nom FROM intervenants ORDER BY nom").fetchall()
def ajouter_intervenant(n):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("INSERT INTO intervenants (nom) VALUES (?)", (n,))
def supprimer_intervenant(i):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM intervenants WHERE id = ?", (i,))
def get_equipements():
    with sqlite3.connect(DB_PATH) as conn: return conn.execute("SELECT id, nom FROM equipements ORDER BY nom").fetchall()
def ajouter_equipement(n):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("INSERT INTO equipements (nom) VALUES (?)", (n,))
def supprimer_equipement(i):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM equipements WHERE id = ?", (i,))
def get_defauts():
    with sqlite3.connect(DB_PATH) as conn: return conn.execute("SELECT id, description FROM defauts ORDER BY description").fetchall()
def ajouter_defaut(d):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("INSERT INTO defauts (description) VALUES (?)", (d,))
def supprimer_defaut(i):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM defauts WHERE id = ?", (i,))

def _construire_clause_filtre(equipement=None, date_debut=None, date_fin=None, poste=None, recherche=None, statut=None):
    clause, params = "", []
    if equipement: clause += " AND equipement = ?"; params.append(equipement)
    if poste: clause += " AND poste = ?"; params.append(poste)
    if statut: clause += " AND statut = ?"; params.append(statut)
    if date_debut: clause += " AND date_heure >= ?"; params.append(date_debut + " 00:00")
    if date_fin: clause += " AND date_heure <= ?"; params.append(date_fin + " 23:59")
    if recherche:
        term = f"%{recherche}%"
        clause += " AND (numero_ordre_travail LIKE ? OR anomalie LIKE ? OR action LIKE ? OR remarques LIKE ? OR intervenant1 LIKE ? OR intervenant2 LIKE ?)"
        params.extend([term]*6)
    return clause, params

def get_interventions(equipement=None, date_debut=None, date_fin=None, poste=None, recherche=None, statut=None, limite=None, decalage=0):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        clause, params = _construire_clause_filtre(equipement, date_debut, date_fin, poste, recherche, statut)
        req = "SELECT id, numero_ordre_travail, date_heure, poste, equipement, type_maintenance, anomalie, action, duree, intervenant1, intervenant2, remarques, statut FROM interventions WHERE 1=1" + clause + " ORDER BY id DESC"
        if limite is not None:
            req += " LIMIT ? OFFSET ?"; params += [limite, decalage]
        c.execute(req, params); return c.fetchall()

def compter_interventions(**kwargs):
    with sqlite3.connect(DB_PATH) as conn:
        clause, params = _construire_clause_filtre(**kwargs)
        c = conn.cursor(); c.execute("SELECT COUNT(*) FROM interventions WHERE 1=1" + clause, params); return c.fetchone()[0]

def obtenir_intervention(i):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT id, numero_ordre_travail, poste, equipement, type_maintenance, anomalie, action, duree, intervenant1, intervenant2, remarques, statut, date_heure FROM interventions WHERE id = ?", (i,)).fetchone()

def modifier_intervention(i, data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE interventions SET numero_ordre_travail=?, poste=?, equipement=?, type_maintenance=?, anomalie=?, action=?, duree=?, intervenant1=?, intervenant2=?, remarques=?, statut=? WHERE id = ?",
                     (data["numero_ordre_travail"], data["poste"], data["equipement"], data["type_maintenance"], data["anomalie"], data["action"], data["duree"], data["intervenant1"], data["intervenant2"], data["remarques"], data["statut"], i))

def supprimer_intervention(i):
    with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM interventions WHERE id = ?", (i,))

def enregistrer_intervention(data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO interventions (numero_ordre_travail, poste, equipement, type_maintenance, anomalie, action, duree, intervenant1, intervenant2, remarques, statut, date_heure) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (data["numero_ordre_travail"], data["poste"], data["equipement"], data["type_maintenance"], data["anomalie"], data["action"], data["duree"], data["intervenant1"], data["intervenant2"], data["remarques"], data["statut"], datetime.now().strftime("%Y-%m-%d %H:%M")))

def _formater_ligne_export(d):
    d = list(d)
    try: d[1] = datetime.strptime(d[1], "%Y-%m-%d %H:%M").strftime("%d/%m/%Y")
    except: pass
    if d[7] not in (None,""): d[7] = f"{d[7]} min"
    return tuple(d)

# ================= Exports =================
def exporter_csv(titre, colonnes, lignes, nom_fichier):
    chemin = os.path.join(obtenir_dossier_export(), nom_fichier)
    with open(chemin, "w", newline="", encoding="utf-8-sig") as file:
        w = csv.writer(file, delimiter=";"); w.writerow([titre]); w.writerow(colonnes); w.writerows(lignes)
    return chemin

def _nettoyer_texte_pdf(t):
    t = str(t)
    for a,b in {"—":"-","–":"-","’":"'","‘":"'","“":'"',"”":'"',"…":"..."}.items(): t=t.replace(a,b)
    return t.encode("latin-1","replace").decode("latin-1")

def _tronquer_pour_pdf(pdf, texte, largeur_mm):
    texte = _nettoyer_texte_pdf(texte)
    if pdf.get_string_width(texte) <= largeur_mm: return texte
    while texte and pdf.get_string_width(texte+"...") > largeur_mm: texte=texte[:-1]
    return texte+"..." if texte else "..."

def _decouper_lignes(pdf, texte, largeur_mm):
    texte=_nettoyer_texte_pdf(texte); mots=texte.split(" "); lignes=[]; cur=""
    for mot in mots:
        essai=(cur+" "+mot).strip()
        if pdf.get_string_width(essai) <= largeur_mm: cur=essai
        else:
            if cur: lignes.append(cur)
            while pdf.get_string_width(mot) > largeur_mm and len(mot)>1:
                lim=len(mot)
                while lim>1 and pdf.get_string_width(mot[:lim])>largeur_mm: lim-=1
                lignes.append(mot[:lim]); mot=mot[lim:]
            cur=mot
    if cur: lignes.append(cur)
    return lignes if lignes else [""]

def exporter_pdf(titre, sous_titre, colonnes, lignes, nom_fichier):
    if not FPDF_DISPONIBLE: return None
    chemin=os.path.join(obtenir_dossier_export(), nom_fichier)
    pdf=FPDF(orientation="L", unit="mm", format="A4"); pdf.set_auto_page_break(auto=True, margin=10); pdf.add_page()
    pdf.set_font("Helvetica","B",14); pdf.set_text_color(10,61,98); pdf.cell(0,8,_nettoyer_texte_pdf(titre),ln=1)
    pdf.set_font("Helvetica","",9); pdf.set_text_color(92,119,136); pdf.multi_cell(0,5,_nettoyer_texte_pdf(sous_titre))
    pdf.set_font("Helvetica","I",8); pdf.set_text_color(140,150,160); pdf.cell(0,5,_nettoyer_texte_pdf(f"Application realisee par {NOM_REALISATEUR}"),ln=1); pdf.ln(2)
    largeur_page=pdf.w-2*pdf.l_margin; h=6
    poids=[7,8,6,8,6,12,12,7,7,7,10,8] if len(colonnes)==12 else [1]*len(colonnes)
    largeurs=[largeur_page*(p/sum(poids)) for p in poids]
    multi={5,6,10} if len(colonnes)==12 else set()
    def ligne_entete():
        pdf.set_font("Helvetica","B",8); pdf.set_fill_color(15,94,153); pdf.set_text_color(255,255,255)
        for i,col in enumerate(colonnes): pdf.cell(largeurs[i],h,_tronquer_pour_pdf(pdf,col,largeurs[i]-2),border=1,fill=True)
        pdf.ln(h)
    ligne_entete(); pdf.set_font("Helvetica","",7.5); pdf.set_text_color(20,40,55)
    if not lignes:
        pdf.cell(largeur_page,h,"Aucune donnee",border=1,ln=1,align="C")
    else:
        rempl=False
        for ligne in lignes:
            contenu=[]; nbmax=1
            for i,val in enumerate(ligne):
                txt=str(val) if val not in (None,"") else "-"; txt=_nettoyer_texte_pdf(txt)
                if i in multi:
                    sl=_decouper_lignes(pdf,txt,largeurs[i]-2); contenu.append(sl); nbmax=max(nbmax,len(sl))
                else: contenu.append(_tronquer_pour_pdf(pdf,txt,largeurs[i]-2))
            ht=nbmax*h
            if pdf.get_y()+ht>pdf.h-pdf.b_margin:
                pdf.add_page(); ligne_entete(); pdf.set_font("Helvetica","",7.5); pdf.set_text_color(20,40,55)
            colf=(242,245,248) if rempl else (255,255,255)
            xd=pdf.get_x(); yd=pdf.get_y(); xc=xd
            for i,cnt in enumerate(contenu):
                if i in multi:
                    pdf.set_fill_color(*colf); pdf.rect(xc,yd,largeurs[i],ht,style="DF")
                    for j,sl in enumerate(cnt): pdf.set_xy(xc+1,yd+j*h); pdf.cell(largeurs[i]-2,h,sl,border=0)
                else:
                    pdf.set_fill_color(*colf); pdf.set_xy(xc,yd); pdf.cell(largeurs[i],ht,cnt,border=1,fill=True)
                xc+=largeurs[i]
            pdf.set_xy(xd,yd+ht); rempl=not rempl
    pdf.output(chemin); return chemin

# ================= Widgets =================
class FondCouleur(BoxLayout):
    def __init__(self, couleur, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*couleur); self.rect=Rectangle(size=self.size,pos=self.pos)
        self.bind(size=self._maj_rect,pos=self._maj_rect)
    def _maj_rect(self,*a): self.rect.size=self.size; self.rect.pos=self.pos

def entete(titre):
    config = obtenir_config_entreprise()
    nom_affiche = config["nom"].strip() if config["nom"].strip() else "délice"
    titre_affiche = f"{config['service'].strip()} — {titre}" if config["service"].strip() else titre
    barre=FondCouleur(BLEU_FONCE, orientation="vertical", size_hint=(1,None), height=dp(84), padding=(dp(16),dp(8)))
    ligne_marque=BoxLayout(orientation="horizontal", size_hint=(1,None), height=dp(44), spacing=dp(8))
    lbl_marque=Label(text=f"[b]{nom_affiche}[/b]", markup=True, font_size=dp(20), color=BLANC, size_hint=(1,1), halign="left", valign="middle")
    lbl_marque.bind(size=lambda *a: setattr(lbl_marque,"text_size",lbl_marque.size))
    ligne_marque.add_widget(lbl_marque)
    if config["logo"] and os.path.exists(config["logo"]):
        ligne_marque.add_widget(Image(source=config["logo"], size_hint=(None,1), width=dp(44)))
    lbl_titre=Label(text=titre_affiche, font_size=dp(13), color=(0.85,0.92,1,1), size_hint=(1,None), height=dp(20), halign="left")
    lbl_titre.bind(size=lambda *a: setattr(lbl_titre,"text_size",lbl_titre.size))
    barre.add_widget(ligne_marque); barre.add_widget(lbl_titre)
    # References conservees pour permettre un rafraichissement sans tout reconstruire
    barre.lbl_marque=lbl_marque; barre.ligne_marque=ligne_marque; barre.lbl_titre=lbl_titre; barre.titre_base=titre
    return barre

def rafraichir_entete(barre):
    """Remet a jour le nom/service/logo d'un en-tete deja construit,
    sans recreer tout l'ecran. A appeler dans on_pre_enter de chaque
    ecran pour que les changements faits sur EcranEntreprise soient
    visibles immediatement, sans redemarrer l'app."""
    if barre is None:
        return
    config = obtenir_config_entreprise()
    nom_affiche = config["nom"].strip() if config["nom"].strip() else "délice"
    barre.lbl_marque.text = f"[b]{nom_affiche}[/b]"
    barre.lbl_titre.text = f"{config['service'].strip()} — {barre.titre_base}" if config["service"].strip() else barre.titre_base
    for w in list(barre.ligne_marque.children):
        if w is not barre.lbl_marque:
            barre.ligne_marque.remove_widget(w)
    if config["logo"] and os.path.exists(config["logo"]):
        barre.ligne_marque.add_widget(Image(source=config["logo"], size_hint=(None,1), width=dp(44)))

def afficher_toast(message, couleur_fond=VERT_RESOLU, duree=1.8):
    contenu=FondCouleur(couleur_fond, orientation="vertical", padding=dp(16))
    lbl=Label(text=message, color=BLANC, bold=True, font_size=dp(15), halign="center", valign="middle")
    lbl.bind(size=lambda *a: setattr(lbl,"text_size",lbl.size)); contenu.add_widget(lbl)
    popup=Popup(title="", separator_height=0, content=contenu, size_hint=(0.82,None), height=dp(90))
    popup.open(); Clock.schedule_once(lambda dt: popup.dismiss(), duree); return popup

def chemin_lisible(chemin):
    """Transforme un chemin technique Android en repere lisible,
    ex: 'Stockage interne > Android > data > ... > GestionMaintenanceDelice'."""
    dossier = os.path.dirname(chemin)
    dossier_affiche = dossier.replace("/storage/emulated/0", "Stockage interne")
    parties = [p for p in dossier_affiche.split(os.sep) if p]
    return " > ".join(parties) if parties else dossier_affiche

def afficher_popup_export_reussi(type_fichier, chemin):
    """Popup de confirmation apres export CSV/PDF, avec l'emplacement
    du fichier presente de facon lisible plutot que le chemin brut."""
    nom_fichier = os.path.basename(chemin)
    emplacement = chemin_lisible(chemin)
    message = f"{type_fichier} enregistre !\n\nFichier :\n{nom_fichier}\n\nEmplacement :\n{emplacement}"
    contenu = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
    lbl = Label(text=message, color=GRIS_TEXTE, font_size=dp(13.5), size_hint=(1, None), halign="center", valign="middle")
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1]))
    contenu.add_widget(lbl)
    popup = Popup(title="", separator_height=0, content=contenu, size_hint=(0.9, None), height=dp(300))
    contenu.add_widget(bouton("OK", lambda inst: popup.dismiss(), couleur_fond=VERT_RESOLU))
    popup.open()

def bouton(texte, callback, couleur_fond=BLEU_FONCE, couleur_texte=BLANC):
    b=Button(text=texte, size_hint=(1,None), height=dp(46), background_normal="", background_color=couleur_fond, color=couleur_texte, font_size=dp(14))
    b.bind(on_release=callback); return b

def afficher_popup_erreur_fpdf():
    """Affiche le vrai message d'erreur d'import de fpdf2, pour diagnostiquer
    si le probleme vient de fpdf2 lui-meme ou d'une sous-dependance
    (fonttools, Pillow, etc.) au lieu du message generique 'installez fpdf2'."""
    message = "Impossible de generer le PDF : fpdf2 n'a pas pu etre importe.\n"
    if ERREUR_IMPORT_FPDF:
        message += f"\nDetail technique :\n{ERREUR_IMPORT_FPDF}"
    else:
        message += "\nAucun detail disponible."
    contenu = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
    scroll = ScrollView(size_hint=(1, 1))
    lbl = Label(text=message, color=GRIS_TEXTE, font_size=dp(11.5), size_hint=(1, None), halign="left", valign="top")
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(10)))
    scroll.add_widget(lbl); contenu.add_widget(scroll)
    popup = Popup(title="Erreur PDF (fpdf2)", content=contenu, size_hint=(0.94, 0.82))
    contenu.add_widget(bouton("Fermer", lambda inst: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
    popup.open()

def ligne_raccourcis_dates(callback):
    ligne=BoxLayout(size_hint=(1,None), height=dp(40), spacing=dp(6))
    for texte,cle in (("Aujourd'hui","aujourdhui"),("Hier","hier"),("Cette semaine","semaine"),("Ce mois","mois")):
        btn=Button(text=texte, size_hint=(1,1), background_normal="", background_color=(0.85,0.92,1,1), color=BLEU_NUIT, font_size=dp(11), bold=True)
        btn.bind(on_release=lambda inst,c=cle: callback(c)); ligne.add_widget(btn)
    return ligne

def construire_ligne_top(rang, nom, count, count_max, couleur_barre=BLEU_FONCE):
    ligne=BoxLayout(size_hint=(1,None), height=dp(26), spacing=dp(6))
    lbl_nom=Label(text=f"{rang}. {nom}", font_size=dp(11), color=GRIS_TEXTE, size_hint=(0.44,1), halign="left", valign="middle", shorten=True, shorten_from="right")
    lbl_nom.bind(size=lambda *a: setattr(lbl_nom,"text_size",lbl_nom.size)); ligne.add_widget(lbl_nom)
    ratio=max(count/count_max,0.04) if count_max else 0.04
    cont=BoxLayout(size_hint=(0.40,1), padding=(0,dp(5))); barre=FondCouleur(couleur_barre, size_hint=(ratio,1)); cont.add_widget(barre)
    if ratio<1: cont.add_widget(BoxLayout(size_hint=(1-ratio,1)))
    ligne.add_widget(cont); ligne.add_widget(Label(text=str(count), font_size=dp(11.5), bold=True, color=BLEU_NUIT, size_hint=(0.16,1)))
    return ligne

def construire_bloc_top5(titre, paires, couleur_barre=BLEU_FONCE):
    bloc=BoxLayout(orientation="vertical", size_hint=(1,None), spacing=dp(3)); bloc.bind(minimum_height=bloc.setter("height"))
    lbl=Label(text=titre, font_size=dp(12.5), bold=True, color=BLEU_NUIT, size_hint=(1,None), height=dp(22), halign="left")
    lbl.bind(size=lambda *a: setattr(lbl,"text_size",lbl.size)); bloc.add_widget(lbl)
    if not paires:
        lv=Label(text="Aucune donnee pour cette periode", font_size=dp(11), color=GRIS_TEXTE, size_hint=(1,None), height=dp(24), halign="left")
        lv.bind(size=lambda *a: setattr(lv,"text_size",lv.size)); bloc.add_widget(lv)
    else:
        cm=paires[0][1]
        for rang,(nom,count) in enumerate(paires, start=1): bloc.add_widget(construire_ligne_top(rang,nom,count,cm,couleur_barre=couleur_barre))
    return bloc

def valider_duree(texte):
    texte=(texte or "").strip()
    if not texte: return True,""
    try: v=int(texte)
    except ValueError: return False,"La duree doit etre un nombre entier."
    if v<0: return False,"La duree ne peut pas etre negative."
    return True,""

def valider_numero_ot(texte):
    texte=(texte or "").strip()
    if not texte: return False,"Le N° OT est obligatoire (6 chiffres)."
    if not texte.isdigit() or len(texte)!=6: return False,"Le N° OT doit contenir exactement 6 chiffres."
    return True,""

def couleur_statut(v):
    if v=="Résolue": return VERT_RESOLU
    if v=="À suivre": return ORANGE_A_SUIVRE
    return None

def _label_champ_valeur(champ, valeur, largeur_disponible, couleur_valeur=None):
    lw=largeur_disponible*0.34; rw=largeur_disponible*0.66-dp(8)
    lbl_champ=Label(text=f"{champ}", font_size=dp(11.5), bold=True, color=couleur_texte_titre(), size_hint=(0.34,None), halign="left", valign="top", text_size=(lw,None))
    lbl_champ.texture_update(); hc=lbl_champ.texture_size[1]+dp(4)
    tv=str(valeur) if valeur not in (None,"") else "—"
    est_badge=champ=="Statut" and couleur_valeur is not None
    lbl_valeur=Label(text=tv, font_size=dp(12), color=(couleur_valeur or couleur_texte_principal()), bold=est_badge, size_hint=(0.66,None), halign="left", valign="top", text_size=(rw,None))
    lbl_valeur.texture_update(); hv=lbl_valeur.texture_size[1]+dp(4)
    hl=max(hc,hv,dp(20)); lbl_champ.height=hl; lbl_valeur.height=hl
    ligne=BoxLayout(orientation="horizontal", size_hint=(1,None), height=hl, spacing=dp(8))
    ligne.add_widget(lbl_champ); ligne.add_widget(lbl_valeur); return ligne

def construire_carte_intervention(colonnes, ligne_donnees, intervention_id=None, on_modifier=None, on_supprimer=None):
    padding_carte=dp(12); padding_conteneur=dp(10)
    largeur_disponible=max(Window.width-2*padding_conteneur-2*padding_carte, dp(150))
    carte=BoxLayout(orientation="vertical", size_hint=(1,None), padding=padding_carte, spacing=dp(6))
    lignes_widgets=[_label_champ_valeur(champ,valeur,largeur_disponible,couleur_valeur=couleur_statut(valeur) if champ=="Statut" else None) for champ,valeur in zip(colonnes,ligne_donnees)]
    hauteur_totale=2*padding_carte+sum(l.height for l in lignes_widgets)+dp(6)*max(len(lignes_widgets)-1,0)
    if intervention_id is not None and (on_modifier or on_supprimer):
        ligne_actions=BoxLayout(orientation="horizontal", size_hint=(1,None), height=dp(40), spacing=dp(8))
        if on_modifier:
            bm=Button(text="Modifier", size_hint=(1,1), background_normal="", background_color=(0.85,0.92,1,1), color=BLEU_NUIT, bold=True, font_size=dp(12.5))
            bm.bind(on_release=lambda inst,i=intervention_id: on_modifier(i)); ligne_actions.add_widget(bm)
        if on_supprimer:
            bs=Button(text="Supprimer", size_hint=(1,1), background_normal="", background_color=(0.96,0.82,0.8,1), color=(0.55,0.1,0.1,1), bold=True, font_size=dp(12.5))
            bs.bind(on_release=lambda inst,i=intervention_id: on_supprimer(i)); ligne_actions.add_widget(bs)
        lignes_widgets.append(ligne_actions); hauteur_totale+=dp(40)+dp(6)
    carte.height=hauteur_totale
    with carte.canvas.before:
        Color(*couleur_fond_carte()); rect=Rectangle(size=carte.size,pos=carte.pos)
        Color(*couleur_bordure_carte()); contour=Line(rectangle=(carte.x,carte.y,carte.width,carte.height),width=1)
    def _maj_fond(instance,*a):
        rect.size=instance.size; rect.pos=instance.pos; contour.rectangle=(instance.x,instance.y,instance.width,instance.height)
    carte.bind(size=_maj_fond,pos=_maj_fond)
    for w in lignes_widgets: carte.add_widget(w)
    return carte

def ouvrir_popup_edition_intervention(intervention_id, on_succes):
    ligne=obtenir_intervention(intervention_id)
    if not ligne: return
    (_id, numero_ot, poste, equipement, type_maintenance, anomalie, action_texte, duree, intervenant1, intervenant2, remarques, statut, date_heure)=ligne
    def champ_label(texte):
        l=Label(text=texte, font_size=dp(12), bold=True, color=BLEU_NUIT, size_hint=(1,None), height=dp(20), halign="left")
        l.bind(size=lambda *a: setattr(l,"text_size",l.size)); return l
    contenu=GridLayout(cols=1, padding=dp(14), spacing=dp(8), size_hint=(1,None)); contenu.bind(minimum_height=contenu.setter("height"))
    scroll=ScrollView(size_hint=(1,1)); scroll.add_widget(contenu)
    popup=Popup(title=f"Modifier OT: {numero_ot or '—'}", content=scroll, size_hint=(0.94,0.9))
    contenu.add_widget(champ_label("Numéro Ordre de Travail"))
    champ_numero_ot=TextInput(text=numero_ot or "", multiline=False, input_filter="int", size_hint=(1,None), height=dp(44)); contenu.add_widget(champ_numero_ot)
    contenu.add_widget(champ_label("Poste"))
    spinner_poste=Spinner(text=poste if poste in ("Jour","Après-midi","Nuit") else "Jour", values=("Jour","Après-midi","Nuit"), size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_poste)
    contenu.add_widget(champ_label("Équipement"))
    noms_equip=[nom for _,nom in get_equipements()]
    spinner_equipement=Spinner(text=equipement if equipement in noms_equip else (noms_equip[0] if noms_equip else "—"), values=noms_equip, size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_equipement)
    contenu.add_widget(champ_label("Type de maintenance"))
    spinner_type=Spinner(text=type_maintenance if type_maintenance in ("Corrective","Préventive","Prédictive") else "Corrective", values=("Corrective","Préventive","Prédictive"), size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_type)
    contenu.add_widget(champ_label("Anomalie"))
    champ_anomalie=TextInput(text=anomalie or "", multiline=False, size_hint=(1,None), height=dp(44)); contenu.add_widget(champ_anomalie)
    contenu.add_widget(champ_label("Action"))
    champ_action=TextInput(text=action_texte or "", multiline=True, size_hint=(1,None), height=dp(80)); contenu.add_widget(champ_action)
    contenu.add_widget(champ_label("Durée (min)"))
    champ_duree=TextInput(text=str(duree) if duree not in (None,"") else "", multiline=False, input_filter="int", size_hint=(1,None), height=dp(44)); contenu.add_widget(champ_duree)
    noms_interv=[nom for _,nom in get_intervenants()]; vals=["— aucun —"]+noms_interv
    contenu.add_widget(champ_label("Intervenant 1"))
    spinner_int1=Spinner(text=intervenant1 if intervenant1 in noms_interv else "— aucun —", values=vals, size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_int1)
    contenu.add_widget(champ_label("Intervenant 2"))
    spinner_int2=Spinner(text=intervenant2 if intervenant2 in noms_interv else "— aucun —", values=vals, size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_int2)
    contenu.add_widget(champ_label("Remarques"))
    champ_remarques=TextInput(text=remarques or "", multiline=True, size_hint=(1,None), height=dp(80)); contenu.add_widget(champ_remarques)
    contenu.add_widget(champ_label("Statut"))
    spinner_statut=Spinner(text=statut if statut in STATUTS_INTERVENTION else "Résolue", values=STATUTS_INTERVENTION, size_hint=(1,None), height=dp(44)); contenu.add_widget(spinner_statut)
    lbl_erreur=Label(text="", color=(0.75,0.15,0.1,1), font_size=dp(12), size_hint=(1,None), height=dp(24)); contenu.add_widget(lbl_erreur)
    def enregistrer(*a):
        if spinner_equipement.text in ("—","") or not champ_anomalie.text.strip():
            lbl_erreur.text="Renseignez au moins l'équipement et l'anomalie."; return
        ot_ok,msg_ot=valider_numero_ot(champ_numero_ot.text)
        if not ot_ok: lbl_erreur.text=msg_ot; return
        d_ok,msg_d=valider_duree(champ_duree.text)
        if not d_ok: lbl_erreur.text=msg_d; return
        modifier_intervention(intervention_id, {"numero_ordre_travail":champ_numero_ot.text.strip(),"poste":spinner_poste.text,"equipement":spinner_equipement.text,"type_maintenance":spinner_type.text,"anomalie":champ_anomalie.text.strip(),"action":champ_action.text.strip(),"duree":champ_duree.text.strip(),"intervenant1":"" if spinner_int1.text=="— aucun —" else spinner_int1.text,"intervenant2":"" if spinner_int2.text=="— aucun —" else spinner_int2.text,"remarques":champ_remarques.text.strip(),"statut":spinner_statut.text})
        popup.dismiss()
        if on_succes: on_succes()
    ligne_boutons=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8))
    ligne_boutons.add_widget(bouton("Enregistrer", enregistrer, couleur_fond=BLEU_FONCE))
    ligne_boutons.add_widget(bouton("Annuler", lambda inst: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
    contenu.add_widget(ligne_boutons); popup.open()

def ouvrir_popup_confirmation_suppression(intervention_id, on_succes):
    contenu=BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(16))
    contenu.add_widget(Label(text="Supprimer définitivement ?\nIrréversible.", color=GRIS_TEXTE, font_size=dp(13), halign="center"))
    popup=Popup(title="Confirmer", content=contenu, size_hint=(0.85,0.4))
    def confirmer(*a):
        supprimer_intervention(intervention_id); popup.dismiss()
        if on_succes: on_succes()
    lb=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8))
    lb.add_widget(bouton("Supprimer", confirmer, couleur_fond=(0.75,0.15,0.1,1), couleur_texte=BLANC))
    lb.add_widget(bouton("Annuler", lambda inst: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
    contenu.add_widget(lb); popup.open()

class SectionGeree(BoxLayout):
    def __init__(self, titre, get_func, add_func, delete_func, **kwargs):
        super().__init__(orientation="vertical", size_hint=(1,None), spacing=dp(6), **kwargs)
        self.get_func=get_func; self.add_func=add_func; self.delete_func=delete_func; self.selection_id=None; self.boutons={}
        self.bind(minimum_height=self.setter("height"))
        lt=Label(text=titre, font_size=dp(13), bold=True, color=BLEU_NUIT, size_hint=(1,None), height=dp(24), halign="left")
        lt.bind(size=lambda *a: setattr(lt,"text_size",lt.size)); self.add_widget(lt)
        self.zone_liste=GridLayout(cols=1, spacing=dp(4), size_hint=(1,None)); self.zone_liste.bind(minimum_height=self.zone_liste.setter("height"))
        scroll=ScrollView(size_hint=(1,None), height=dp(150)); scroll.add_widget(self.zone_liste); self.add_widget(scroll)
        lb=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8))
        lb.add_widget(bouton("Ajouter", self.ajouter, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        lb.add_widget(bouton("Supprimer", self.supprimer, couleur_fond=(0.93,0.75,0.75,1), couleur_texte=(0.55,0.1,0.1,1)))
        self.add_widget(lb); self.height=dp(24)+dp(150)+dp(46)+dp(12); self.recharger()
    def recharger(self):
        self.zone_liste.clear_widgets(); self.boutons={}; self.selection_id=None
        for iid,txt in self.get_func():
            btn=Button(text=txt, size_hint=(1,None), height=dp(36), background_normal="", background_color=(0.95,0.97,1,1), color=GRIS_TEXTE, font_size=dp(12))
            btn.bind(on_release=lambda inst,i=iid: self.selectionner(i)); self.boutons[iid]=btn; self.zone_liste.add_widget(btn)
    def selectionner(self,iid):
        for i,b in self.boutons.items(): b.background_color=(0.75,0.87,0.98,1) if i==iid else (0.95,0.97,1,1)
        self.selection_id=iid
    def ajouter(self,*a):
        c=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10)); ch=TextInput(hint_text="Nouvelle valeur", multiline=False, size_hint=(1,None), height=dp(44)); c.add_widget(ch)
        pop=Popup(title="Ajouter", content=c, size_hint=(0.85,0.35))
        def valider(*a):
            if ch.text.strip(): self.add_func(ch.text.strip()); self.recharger()
            pop.dismiss()
        c.add_widget(bouton("Ajouter", valider, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT)); pop.open()
    def supprimer(self,*a):
        if self.selection_id is not None: self.delete_func(self.selection_id); self.recharger()

class EcranEntreprise(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chemin_logo_en_attente = None
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Parametres entreprise"); racine.add_widget(self._barre_entete)
        corps=BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        corps.add_widget(Label(text="Nom de l'entreprise", font_size=dp(13), color=GRIS_TEXTE, size_hint=(1,None), height=dp(22), halign="left"))
        self.champ_nom=TextInput(hint_text="Ex: Delice", multiline=False, size_hint=(1,None), height=dp(44))
        corps.add_widget(self.champ_nom)
        corps.add_widget(Label(text="Service / Departement", font_size=dp(13), color=GRIS_TEXTE, size_hint=(1,None), height=dp(22), halign="left"))
        self.champ_service=TextInput(hint_text="Ex: Service Mecanique, Service Electrique...", multiline=False, size_hint=(1,None), height=dp(44))
        corps.add_widget(self.champ_service)
        corps.add_widget(Label(text="Logo (optionnel)", font_size=dp(13), color=GRIS_TEXTE, size_hint=(1,None), height=dp(22), halign="left"))
        self.apercu_logo=Image(size_hint=(1,None), height=dp(110))
        corps.add_widget(self.apercu_logo)
        corps.add_widget(bouton("Choisir un logo", self.choisir_logo, couleur_fond=(0.90,0.93,0.97,1), couleur_texte=BLEU_NUIT))
        self.lbl_message=Label(text="", font_size=dp(12), color=(0.13,0.55,0.13,1), size_hint=(1,None), height=dp(22))
        corps.add_widget(self.lbl_message)
        corps.add_widget(bouton("Enregistrer", self.enregistrer, couleur_fond=BLEU_FONCE))
        corps.add_widget(bouton("Retour", self.retour, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        corps.add_widget(BoxLayout())
        racine.add_widget(corps); self.add_widget(racine)

    def on_pre_enter(self):
        rafraichir_entete(self._barre_entete)
        config=obtenir_config_entreprise()
        self.champ_nom.text=config["nom"]
        self.champ_service.text=config["service"]
        self._chemin_logo_en_attente=None
        if config["logo"] and os.path.exists(config["logo"]):
            self.apercu_logo.source=config["logo"]; self.apercu_logo.reload()

    def choisir_logo(self, *a):
        if platform == "android" and FILECHOOSER_DISPONIBLE:
            try:
                filechooser.open_file(on_selection=self._logo_selectionne, filters=[["Images","*.png","*.jpg","*.jpeg"]])
                return
            except Exception as e:
                self.lbl_message.color=(0.75,0.15,0.1,1); self.lbl_message.text=f"Selecteur natif indisponible ({e}), mode alternatif."
        self._popup_selecteur_fichiers()

    def _popup_selecteur_fichiers(self):
        """Repli : navigateur de fichiers integre a Kivy, utile sur Pydroid/PC
        ou quand le selecteur natif Android n'est pas disponible."""
        dossier_depart = obtenir_dossier_export()
        for candidat in ("/storage/emulated/0/Pictures", "/storage/emulated/0/DCIM", "/storage/emulated/0/Download", "/storage/emulated/0"):
            if os.path.isdir(candidat):
                dossier_depart = candidat
                break
        contenu = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        chooser = FileChooserIconView(path=dossier_depart, filters=["*.png","*.jpg","*.jpeg","*.PNG","*.JPG","*.JPEG"])
        contenu.add_widget(chooser)
        popup = Popup(title="Choisir un logo", content=contenu, size_hint=(0.95, 0.9))
        btns = BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8))
        def choisir(*a):
            if chooser.selection:
                popup.dismiss(); self._logo_selectionne([chooser.selection[0]])
            else:
                self.lbl_message.color=(0.75,0.15,0.1,1); self.lbl_message.text="Aucun fichier selectionne."
        btns.add_widget(bouton("Annuler", lambda i: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        btns.add_widget(bouton("Choisir", choisir, couleur_fond=BLEU_FONCE))
        contenu.add_widget(btns)
        popup.open()

    def _logo_selectionne(self, selection):
        if not selection:
            return
        chemin_choisi=selection[0]
        def travail():
            try:
                chemin_local=enregistrer_logo_entreprise(chemin_choisi)
                Clock.schedule_once(lambda dt: self._logo_pret(chemin_local), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt, err=str(e): self._logo_erreur(err), 0)
        threading.Thread(target=travail, daemon=True).start()

    def _logo_pret(self, chemin_local):
        self._chemin_logo_en_attente=chemin_local
        self.apercu_logo.source=chemin_local; self.apercu_logo.reload()
        self.lbl_message.color=(0.13,0.55,0.13,1); self.lbl_message.text="Logo pret. N'oubliez pas d'Enregistrer."

    def _logo_erreur(self, message):
        self.lbl_message.color=(0.75,0.15,0.1,1); self.lbl_message.text=f"Erreur logo: {message}"

    def enregistrer(self, *a):
        nom=self.champ_nom.text.strip()
        service=self.champ_service.text.strip()
        if not nom:
            self.lbl_message.color=(0.75,0.15,0.1,1); self.lbl_message.text="Veuillez saisir un nom d'entreprise."; return
        config_actuelle=obtenir_config_entreprise()
        chemin_logo=self._chemin_logo_en_attente or config_actuelle["logo"]
        definir_config_entreprise(nom, chemin_logo, service)
        self.lbl_message.color=(0.13,0.55,0.13,1); self.lbl_message.text="Enregistre !"
        vibrer()
        Clock.schedule_once(lambda dt: self.retour(), 1.1)

    def retour(self, *a):
        self.manager.transition=SlideTransition(direction="right")
        self.manager.current="login"

class EcranLogin(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Gestion Maintenance — Département Technique"); racine.add_widget(self._barre_entete)
        corps=BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        corps.add_widget(Label(text="Bienvenue\nGestion Maintenance", font_size=dp(16), color=BLEU_NUIT, bold=True, size_hint=(1,None), height=dp(60), halign="center"))
        corps.add_widget(Label(text="Saisissez votre nom et mot de passe", font_size=dp(12), color=GRIS_TEXTE, size_hint=(1,None), height=dp(24)))
        self.champ_login=TextInput(hint_text="Login", multiline=False, size_hint=(1,None), height=dp(44))
        self.champ_pass=TextInput(hint_text="Mot de passe", multiline=False, password=True, size_hint=(1,None), height=dp(44))
        self.lbl_erreur=Label(text="", color=(0.75,0.15,0.1,1), font_size=dp(12), size_hint=(1,None), height=dp(24))
        corps.add_widget(self.champ_login); corps.add_widget(self.champ_pass); corps.add_widget(self.lbl_erreur)
        lb=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(10))
        lb.add_widget(bouton("OK", self.connecter)); lb.add_widget(bouton("Annuler", self.effacer, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        corps.add_widget(lb); corps.add_widget(BoxLayout())
        corps.add_widget(bouton("Entreprise (nom / logo)", self.ouvrir_entreprise, couleur_fond=(0.90,0.93,0.97,1), couleur_texte=BLEU_NUIT))
        lr=Label(text=f"Réalisé par {NOM_REALISATEUR} - V2", font_size=dp(11), color=(0.6,0.66,0.72,1), size_hint=(1,None), height=dp(22), halign="center")
        lr.bind(size=lambda *a: setattr(lr,"text_size",lr.size)); corps.add_widget(lr)
        racine.add_widget(corps); self.add_widget(racine)
    def on_pre_enter(self):
        rafraichir_entete(self._barre_entete)
    def ouvrir_entreprise(self,*a):
        self.manager.transition=SlideTransition(direction="left"); self.manager.current="entreprise"
    def connecter(self,*a):
        if not self.champ_login.text.strip() or not self.champ_pass.text.strip():
            self.lbl_erreur.text="Veuillez saisir login et mot de passe."; return
        self.lbl_erreur.text=""; self.manager.transition=SlideTransition(direction="left"); self.manager.current="objectifs"
    def effacer(self,*a): self.champ_login.text=""; self.champ_pass.text=""; self.lbl_erreur.text=""

class EcranObjectifs(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Menu principal"); racine.add_widget(self._barre_entete)
        corps=BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))
        corps.add_widget(Label(text="Choisir votre objectif", font_size=dp(14), bold=True, color=BLEU_FONCE, size_hint=(1,None), height=dp(30)))
        self.carrousel=Carousel(direction="right", loop=True, size_hint=(1,1))
        for texte,cible in [("Données Utiles","donnees_utiles"),("Historique","historique"),("Rapport","rapport"),("Fiche Intervention","fiche")]:
            case=FondCouleur(JAUNE, orientation="vertical", padding=dp(16))
            case.add_widget(Button(text=texte, background_normal="", background_color=(0,0,0,0), color=BLEU_NUIT, bold=True, font_size=dp(17), on_release=lambda inst,c=cible: self.aller_vers(c)))
            self.carrousel.add_widget(case)
        corps.add_widget(self.carrousel)
        self.btn_mode_sombre=bouton(self._libelle_mode_sombre(), self.basculer_theme, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE)
        corps.add_widget(self.btn_mode_sombre)
        corps.add_widget(bouton("Se déconnecter", self.deconnecter, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        racine.add_widget(corps); self.add_widget(racine); self._evt=None
    def _libelle_mode_sombre(self): return "Mode clair" if est_mode_sombre() else "Mode sombre"
    def basculer_theme(self,*a): basculer_mode_sombre(not est_mode_sombre()); self.btn_mode_sombre.text=self._libelle_mode_sombre()
    def on_enter(self):
        rafraichir_entete(self._barre_entete)
        self.btn_mode_sombre.text=self._libelle_mode_sombre()
        self._evt=Clock.schedule_interval(lambda dt: self.carrousel.load_next(mode="loop"), 3.5)
    def on_leave(self):
        if self._evt: self._evt.cancel(); self._evt=None
    def aller_vers(self,nom): self.manager.transition=SlideTransition(direction="left"); self.manager.current=nom
    def deconnecter(self,*a): self.manager.transition=SlideTransition(direction="right"); self.manager.current="login"

class EcranDonneesUtiles(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Données Utiles"); racine.add_widget(self._barre_entete)
        scroll=ScrollView(); corps=GridLayout(cols=1, padding=dp(16), spacing=dp(20), size_hint=(1,None)); corps.bind(minimum_height=corps.setter("height"))
        corps.add_widget(SectionGeree("Liste Équipement", get_equipements, ajouter_equipement, supprimer_equipement))
        corps.add_widget(SectionGeree("Liste Intervenant", get_intervenants, ajouter_intervenant, supprimer_intervenant))
        corps.add_widget(SectionGeree("Défauts Généraux", get_defauts, ajouter_defaut, supprimer_defaut))
        corps.add_widget(bouton("Sauvegarder la base", self.sauvegarder_db, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        corps.add_widget(bouton("Menu principal", self.retour, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        scroll.add_widget(corps); racine.add_widget(scroll); self.add_widget(racine)
    def on_pre_enter(self):
        rafraichir_entete(self._barre_entete)
        for e in self.walk():
            if isinstance(e, SectionGeree): e.recharger()
    def sauvegarder_db(self,*a):
        try:
            dossier=obtenir_dossier_export(); dest=os.path.join(dossier, f"donnee_utile_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy(DB_PATH, dest); Popup(title="Backup OK", content=Label(text=f"Sauvé:\n{dest}"), size_hint=(0.88,0.4)).open()
        except Exception as e: Popup(title="Erreur", content=Label(text=str(e)), size_hint=(0.88,0.4)).open()
    def retour(self,*a): self.manager.transition=SlideTransition(direction="right"); self.manager.current="objectifs"

class EcranHistorique(Screen):
    COLONNES=["N° OT","Date","Poste","Équipement","Type","Anomalie","Action","Durée","Interv. 1","Interv. 2","Remarques","Statut"]
    TAILLE_PAGE=20
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.page_courante=0; self.total_lignes=0; self._filtres_actuels={}; self._debounce=None
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Historique Intervention"); racine.add_widget(self._barre_entete)
        barre_haute=BoxLayout(size_hint=(1,None), height=dp(46), padding=(dp(10),0), spacing=dp(8))
        barre_haute.add_widget(bouton("Menu", self.retour, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        barre_haute.add_widget(bouton("Excel", self.exporter_excel, couleur_fond=(0.1,0.5,0.2,1), couleur_texte=BLANC))
        barre_haute.add_widget(bouton("PDF", self.imprimer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        racine.add_widget(barre_haute)
        barre_filtres=BoxLayout(size_hint=(1,None), padding=(dp(10),dp(8)), spacing=dp(8), orientation="vertical"); barre_filtres.bind(minimum_height=barre_filtres.setter("height"))
        self.champ_recherche=TextInput(hint_text="Recherche OT, anomalie...", multiline=False, size_hint=(1,None), height=dp(44))
        self.champ_recherche.bind(text=self._on_recherche_text)
        barre_filtres.add_widget(self.champ_recherche)
        ligne_filtre_1=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.spinner_filtre_equipement=Spinner(text="Tous les équipements", values=(), size_hint=(1,1))
        self.spinner_filtre_equipement.bind(text=lambda inst,val: self._filtre_change())
        ligne_filtre_1.add_widget(self.spinner_filtre_equipement); barre_filtres.add_widget(ligne_filtre_1)
        ligne_filtre_statut=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.spinner_filtre_statut=Spinner(text="Tous les statuts", values=("Tous les statuts",)+STATUTS_INTERVENTION, size_hint=(1,1))
        self.spinner_filtre_statut.bind(text=lambda inst,val: self._filtre_change())
        ligne_filtre_statut.add_widget(self.spinner_filtre_statut); barre_filtres.add_widget(ligne_filtre_statut)
        barre_filtres.add_widget(ligne_raccourcis_dates(self.appliquer_raccourci_date))
        ligne_filtre_2=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.champ_date_debut=TextInput(hint_text="Début AAAA-MM-JJ", multiline=False, size_hint=(0.35,1))
        self.champ_date_fin=TextInput(hint_text="Fin AAAA-MM-JJ", multiline=False, size_hint=(0.35,1))
        bf=Button(text="Filtrer", size_hint=(0.15,1), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True, font_size=dp(12))
        bf.bind(on_release=lambda inst: self._filtre_change())
        br=Button(text="X", size_hint=(0.15,1), background_normal="", background_color=(0.85,0.88,0.9,1), color=GRIS_TEXTE, font_size=dp(12))
        br.bind(on_release=lambda inst: self.reinitialiser_filtres())
        ligne_filtre_2.add_widget(self.champ_date_debut); ligne_filtre_2.add_widget(self.champ_date_fin); ligne_filtre_2.add_widget(bf); ligne_filtre_2.add_widget(br)
        barre_filtres.add_widget(ligne_filtre_2); racine.add_widget(barre_filtres)
        self.scroll_v=ScrollView(size_hint=(1,1))
        self.conteneur_cartes=GridLayout(cols=1, spacing=dp(10), padding=dp(10), size_hint=(1,None))
        self.conteneur_cartes.bind(minimum_height=self.conteneur_cartes.setter("height"))
        self.scroll_v.add_widget(self.conteneur_cartes); racine.add_widget(self.scroll_v)
        barre_pag=BoxLayout(size_hint=(1,None), height=dp(48), padding=(dp(10),dp(4)), spacing=dp(8))
        self.btn_page_precedente=Button(text="Precedent", size_hint=(0.28,1), background_normal="", background_color=(0.85,0.88,0.9,1), color=GRIS_TEXTE, font_size=dp(12), bold=True)
        self.btn_page_precedente.bind(on_release=lambda inst: self.changer_page(-1))
        self.lbl_pagination=Label(text="", size_hint=(0.44,1), color=BLEU_NUIT, font_size=dp(11.5), bold=True)
        self.btn_page_suivante=Button(text="Suivant", size_hint=(0.28,1), background_normal="", background_color=(0.85,0.88,0.9,1), color=GRIS_TEXTE, font_size=dp(12), bold=True)
        self.btn_page_suivante.bind(on_release=lambda inst: self.changer_page(1))
        barre_pag.add_widget(self.btn_page_precedente); barre_pag.add_widget(self.lbl_pagination); barre_pag.add_widget(self.btn_page_suivante)
        racine.add_widget(barre_pag); self.add_widget(racine)
    def on_pre_enter(self):
        rafraichir_entete(self._barre_entete)
        noms=[n for _,n in get_equipements()]; self.spinner_filtre_equipement.values=["Tous les équipements"]+noms
        if self.spinner_filtre_equipement.text not in self.spinner_filtre_equipement.values: self.spinner_filtre_equipement.text="Tous les équipements"
        self.page_courante=0; self.remplir_tableau()
    def _on_recherche_text(self, inst, val):
        if self._debounce: self._debounce.cancel()
        self._debounce=Clock.schedule_once(lambda dt: self._filtre_change(), 0.35)
    def _filtre_change(self): self.page_courante=0; self.remplir_tableau()
    def appliquer_raccourci_date(self, cle):
        debut,fin=calculer_plage_date(cle); self.champ_date_debut.text=debut; self.champ_date_fin.text=fin; self._filtre_change()
    def reinitialiser_filtres(self):
        self.champ_recherche.text=""; self.spinner_filtre_equipement.text="Tous les équipements"; self.spinner_filtre_statut.text="Tous les statuts"
        self.champ_date_debut.text=""; self.champ_date_fin.text=""; self.page_courante=0; self.remplir_tableau()
    def changer_page(self, delta):
        max_page=max((self.total_lignes-1)//self.TAILLE_PAGE,0) if self.total_lignes else 0
        np=self.page_courante+delta
        if np<0 or np>max_page: return
        self.page_courante=np; self.remplir_tableau(); self.scroll_v.scroll_y=1
    def remplir_tableau(self):
        self.conteneur_cartes.clear_widgets()
        equip=self.spinner_filtre_equipement.text
        if equip=="Tous les équipements": equip=None
        statut=self.spinner_filtre_statut.text
        if statut=="Tous les statuts": statut=None
        self._filtres_actuels=dict(equipement=equip, date_debut=self.champ_date_debut.text.strip() or None, date_fin=self.champ_date_fin.text.strip() or None, recherche=self.champ_recherche.text.strip() or None, statut=statut)
        self.total_lignes=compter_interventions(**self._filtres_actuels)
        max_page=max((self.total_lignes-1)//self.TAILLE_PAGE,0) if self.total_lignes else 0
        if self.page_courante>max_page: self.page_courante=max_page
        lignes=get_interventions(**self._filtres_actuels, limite=self.TAILLE_PAGE, decalage=self.page_courante*self.TAILLE_PAGE)
        if not lignes:
            self.conteneur_cartes.add_widget(Label(text="Aucune intervention", size_hint=(1,None), height=dp(40), color=GRIS_TEXTE, font_size=dp(13)))
        else:
            for ligne in lignes:
                iid=ligne[0]; donnees=ligne[1:]
                self.conteneur_cartes.add_widget(construire_carte_intervention(self.COLONNES, donnees, intervention_id=iid, on_modifier=self.modifier_intervention_ui, on_supprimer=self.supprimer_intervention_ui))
        self.dernieres_lignes=[ligne[1:] for ligne in lignes]
        if self.total_lignes:
            debut_affiche=self.page_courante*self.TAILLE_PAGE+1; fin_affiche=min((self.page_courante+1)*self.TAILLE_PAGE, self.total_lignes); nb_pages=max_page+1
            self.lbl_pagination.text=f"{debut_affiche}-{fin_affiche} sur {self.total_lignes} (p{self.page_courante+1}/{nb_pages})"
        else: self.lbl_pagination.text="0 resultat"
        self.btn_page_precedente.disabled=self.page_courante<=0; self.btn_page_suivante.disabled=self.page_courante>=max_page
    def modifier_intervention_ui(self,iid): ouvrir_popup_edition_intervention(iid, on_succes=self.remplir_tableau)
    def supprimer_intervention_ui(self,iid): ouvrir_popup_confirmation_suppression(iid, on_succes=self.remplir_tableau)
    def _lignes_completes_filtrees(self):
        lignes=get_interventions(**self._filtres_actuels); return [_formater_ligne_export(ligne[1:]) for ligne in lignes]
    def exporter_excel(self,*a):
        lignes=self._lignes_completes_filtrees(); chemin=exporter_csv("Historique Maintenance", self.COLONNES, lignes, "historique_maintenance.csv")
        afficher_popup_export_reussi("CSV", chemin)
    def imprimer(self,*a):
        sous_titre=f"Historique - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        if not FPDF_DISPONIBLE: afficher_popup_erreur_fpdf(); return
        lignes=self._lignes_completes_filtrees(); _cfg=obtenir_config_entreprise(); nom_ent=_cfg["nom"].strip() or "Delice"; _svc=f" ({_cfg['service'].strip()})" if _cfg["service"].strip() else ""; chemin=exporter_pdf(f"Historique Intervention - {nom_ent}{_svc}", sous_titre, self.COLONNES, lignes, "historique_intervention.pdf")
        afficher_popup_export_reussi("PDF", chemin)
    def retour(self,*a): self.manager.transition=SlideTransition(direction="right"); self.manager.current="objectifs"

class EcranRapport(Screen):
    COLONNES=["N° OT","Date","Poste","Équipement","Type","Anomalie","Action","Durée","Interv. 1","Interv. 2","Remarques","Statut"]
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Rapport Intervention"); racine.add_widget(self._barre_entete)
        barre_haute=BoxLayout(size_hint=(1,None), height=dp(46), padding=(dp(10),0), spacing=dp(8))
        barre_haute.add_widget(bouton("Menu", self.retour, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        barre_haute.add_widget(bouton("Excel", self.exporter_excel, couleur_fond=(0.1,0.5,0.2,1), couleur_texte=BLANC))
        barre_haute.add_widget(bouton("PDF", self.imprimer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        racine.add_widget(barre_haute)
        barre_filtres=BoxLayout(size_hint=(1,None), padding=(dp(10),dp(8)), spacing=dp(8), orientation="vertical"); barre_filtres.bind(minimum_height=barre_filtres.setter("height"))
        barre_filtres.add_widget(ligne_raccourcis_dates(self.appliquer_raccourci_date))
        lp=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        lp.add_widget(Label(text="Du", size_hint=(0.15,1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.champ_date_debut=TextInput(hint_text="AAAA-MM-JJ", multiline=False, size_hint=(0.35,1)); lp.add_widget(self.champ_date_debut)
        lp.add_widget(Label(text="Au", size_hint=(0.15,1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.champ_date_fin=TextInput(hint_text="AAAA-MM-JJ", multiline=False, size_hint=(0.35,1)); lp.add_widget(self.champ_date_fin)
        barre_filtres.add_widget(lp)
        lposte=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        lposte.add_widget(Label(text="Poste", size_hint=(0.3,1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.spinner_poste=Spinner(text="Tous les postes", values=("Tous les postes","Jour","Après-midi","Nuit"), size_hint=(0.7,1)); lposte.add_widget(self.spinner_poste); barre_filtres.add_widget(lposte)
        ls=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        ls.add_widget(Label(text="Statut", size_hint=(0.3,1), color=BLEU_NUIT, bold=True, font_size=dp(12)))
        self.spinner_statut=Spinner(text="Tous les statuts", values=("Tous les statuts",)+STATUTS_INTERVENTION, size_hint=(0.7,1)); ls.add_widget(self.spinner_statut); barre_filtres.add_widget(ls)
        la=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8))
        la.add_widget(bouton("Generer", self.generer, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        la.add_widget(bouton("Reinit", self.reinitialiser, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        barre_filtres.add_widget(la); racine.add_widget(barre_filtres)
        self.lbl_kpi=Label(text="", font_size=dp(12), bold=True, color=BLEU_FONCE, size_hint=(1,None), halign="left", valign="middle")
        self.lbl_kpi.bind(width=lambda inst,w: setattr(inst,"text_size",(w,None))); self.lbl_kpi.bind(texture_size=lambda inst,ts: setattr(inst,"height",ts[1]+dp(10)))
        ck=BoxLayout(size_hint=(1,None), padding=(dp(12),dp(4))); ck.bind(minimum_height=ck.setter("height")); ck.add_widget(self.lbl_kpi); racine.add_widget(ck)
        racine.add_widget(bouton("Voir Top 5", self.ouvrir_popup_top5, couleur_fond=(0.90,0.93,0.97,1), couleur_texte=BLEU_NUIT))
        self.top5_equipements=[]; self.top5_anomalies=[]
        self.scroll_v=ScrollView(size_hint=(1,1))
        self.conteneur_cartes=GridLayout(cols=1, spacing=dp(10), padding=dp(10), size_hint=(1,None)); self.conteneur_cartes.bind(minimum_height=self.conteneur_cartes.setter("height"))
        self.scroll_v.add_widget(self.conteneur_cartes); racine.add_widget(self.scroll_v); self.add_widget(racine)
    def on_pre_enter(self): rafraichir_entete(self._barre_entete); self.generer()
    def ouvrir_popup_top5(self,*a):
        contenu=FondCouleur(BLANC, orientation="vertical", padding=dp(14), spacing=dp(10))
        scroll=ScrollView(size_hint=(1,1)); corps=BoxLayout(orientation="vertical", size_hint=(1,None), spacing=dp(16), padding=(0,dp(4))); corps.bind(minimum_height=corps.setter("height"))
        corps.add_widget(construire_bloc_top5("Top 5 Equipements", self.top5_equipements, couleur_barre=BLEU_FONCE))
        corps.add_widget(construire_bloc_top5("Top 5 Anomalies", self.top5_anomalies, couleur_barre=ORANGE_A_SUIVRE))
        scroll.add_widget(corps); contenu.add_widget(scroll)
        popup=Popup(title="Top 5", content=contenu, size_hint=(0.94,0.85), background_color=(1,1,1,1), title_color=BLEU_NUIT)
        contenu.add_widget(bouton("Fermer", lambda inst: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE)); popup.open()
    def appliquer_raccourci_date(self,cle): debut,fin=calculer_plage_date(cle); self.champ_date_debut.text=debut; self.champ_date_fin.text=fin; self.generer()
    def reinitialiser(self,*a): self.champ_date_debut.text=""; self.champ_date_fin.text=""; self.spinner_poste.text="Tous les postes"; self.spinner_statut.text="Tous les statuts"; self.generer()
    def generer(self,*a):
        self.conteneur_cartes.clear_widgets()
        poste=self.spinner_poste.text; 
        if poste=="Tous les postes": poste=None
        statut=self.spinner_statut.text;
        if statut=="Tous les statuts": statut=None
        lignes=get_interventions(date_debut=self.champ_date_debut.text.strip() or None, date_fin=self.champ_date_fin.text.strip() or None, poste=poste, statut=statut)
        ce=Counter(); ca=Counter()
        if not lignes:
            self.conteneur_cartes.add_widget(Label(text="Aucune intervention", size_hint=(1,None), height=dp(40), color=GRIS_TEXTE, font_size=dp(13))); self.lbl_kpi.text="0 intervention"
        else:
            duree=0; nb_suivi=0
            for ligne in lignes:
                iid=ligne[0]; d=ligne[1:]
                if d[-1]=="À suivre": nb_suivi+=1
                self.conteneur_cartes.add_widget(construire_carte_intervention(self.COLONNES, d, intervention_id=iid, on_modifier=self.modifier_intervention_ui, on_supprimer=self.supprimer_intervention_ui))
                try: duree+=int(d[7])
                except: pass
                ce[d[3] or "—"]+=1; ca[d[5] or "—"]+=1
            mttr=round(duree/len(lignes),1) if lignes else 0
            self.lbl_kpi.text=f"Total: {len(lignes)} | Duree: {duree} min | MTTR: {mttr} min | A suivre: {nb_suivi}"
        self.top5_equipements=ce.most_common(5); self.top5_anomalies=ca.most_common(5)
        self.dernieres_lignes=[_formater_ligne_export(l[1:]) for l in lignes]
    def modifier_intervention_ui(self,iid): ouvrir_popup_edition_intervention(iid, on_succes=self.generer)
    def supprimer_intervention_ui(self,iid): ouvrir_popup_confirmation_suppression(iid, on_succes=self.generer)
    def exporter_excel(self,*a): chemin=exporter_csv("Rapport", self.COLONNES, getattr(self,"dernieres_lignes",[]), "rapport_maintenance.csv"); afficher_popup_export_reussi("CSV", chemin)
    def imprimer(self,*a):
        sous=f"Rapport - {self.lbl_kpi.text}"
        if not FPDF_DISPONIBLE: afficher_popup_erreur_fpdf(); return
        _cfg=obtenir_config_entreprise(); nom_ent=_cfg["nom"].strip() or "Delice"; _svc=f" ({_cfg['service'].strip()})" if _cfg["service"].strip() else ""; chemin=exporter_pdf(f"Rapport - {nom_ent}{_svc}", sous, self.COLONNES, getattr(self,"dernieres_lignes",[]), "rapport_intervention.pdf")
        afficher_popup_export_reussi("PDF", chemin)
    def retour(self,*a): self.manager.transition=SlideTransition(direction="right"); self.manager.current="objectifs"

class EcranFiche(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        racine=BoxLayout(orientation="vertical"); self._barre_entete=entete("Fiche Intervention"); racine.add_widget(self._barre_entete)
        scroll=ScrollView(); corps=GridLayout(cols=1, padding=dp(16), spacing=dp(16), size_hint=(1,None)); corps.bind(minimum_height=corps.setter("height"))
        def label(t):
            l=Label(text=t, font_size=dp(12), bold=True, color=BLEU_NUIT, size_hint=(1,None), height=dp(20), halign="left")
            l.bind(size=lambda *a: setattr(l,"text_size",l.size)); return l
        corps.add_widget(label("Numéro OT (6 chiffres) *"))
        self.champ_numero_ot=TextInput(hint_text="ex: 504567", multiline=False, input_filter="int", size_hint=(1,None), height=dp(44)); corps.add_widget(self.champ_numero_ot)
        corps.add_widget(label("Poste"))
        self.spinner_poste=Spinner(text=obtenir_poste_actuel(), values=("Jour","Après-midi","Nuit"), size_hint=(1,None), height=dp(44)); corps.add_widget(self.spinner_poste)
        corps.add_widget(label("Équipement *"))
        le=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.spinner_equipement=Spinner(text="— sélectionner —", values=(), size_hint=(1,1))
        be=Button(text="+", size_hint=(None,1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        be.bind(on_release=self.ajouter_equipement_popup); le.add_widget(self.spinner_equipement); le.add_widget(be); corps.add_widget(le)
        corps.add_widget(label("Type maintenance"))
        self.spinner_type=Spinner(text="Corrective", values=("Corrective","Préventive","Prédictive"), size_hint=(1,None), height=dp(44)); corps.add_widget(self.spinner_type)
        corps.add_widget(label("Anomalie *"))
        self.champ_anomalie=TextInput(multiline=False, size_hint=(1,None), height=dp(44)); corps.add_widget(self.champ_anomalie)
        corps.add_widget(bouton("Choisir defaut", self.ouvrir_liste_defauts, couleur_fond=(0.90,0.93,0.97,1), couleur_texte=BLEU_NUIT))
        corps.add_widget(label("Action"))
        self.champ_action=TextInput(multiline=True, size_hint=(1,None), height=dp(80)); corps.add_widget(self.champ_action)
        corps.add_widget(label("Durée (min)"))
        self.champ_duree=TextInput(multiline=False, input_filter="int", size_hint=(1,None), height=dp(44)); corps.add_widget(self.champ_duree)
        corps.add_widget(label("Intervenant 1"))
        li1=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.spinner_intervenant1=Spinner(text="— aucun —", values=(), size_hint=(1,1))
        bi1=Button(text="+", size_hint=(None,1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        bi1.bind(on_release=lambda inst: self.ajouter_intervenant_popup(self.spinner_intervenant1))
        li1.add_widget(self.spinner_intervenant1); li1.add_widget(bi1); corps.add_widget(li1)
        corps.add_widget(label("Intervenant 2"))
        li2=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.spinner_intervenant2=Spinner(text="— aucun —", values=(), size_hint=(1,1))
        bi2=Button(text="+", size_hint=(None,1), width=dp(44), background_normal="", background_color=JAUNE, color=BLEU_NUIT, bold=True)
        bi2.bind(on_release=lambda inst: self.ajouter_intervenant_popup(self.spinner_intervenant2))
        li2.add_widget(self.spinner_intervenant2); li2.add_widget(bi2); corps.add_widget(li2)
        corps.add_widget(label("Remarques"))
        self.champ_remarques=TextInput(multiline=True, size_hint=(1,None), height=dp(80)); corps.add_widget(self.champ_remarques)
        corps.add_widget(label("Statut"))
        ls=BoxLayout(size_hint=(1,None), height=dp(44), spacing=dp(6))
        self.btn_statut_resolue=Button(text="Resolue", size_hint=(0.5,1), background_normal="", background_color=VERT_RESOLU, color=BLANC, bold=True, font_size=dp(13))
        self.btn_statut_a_suivre=Button(text="A suivre", size_hint=(0.5,1), background_normal="", background_color=(0.85,0.88,0.9,1), color=GRIS_TEXTE, bold=True, font_size=dp(13))
        self.btn_statut_resolue.bind(on_release=lambda inst: self._choisir_statut("Résolue"))
        self.btn_statut_a_suivre.bind(on_release=lambda inst: self._choisir_statut("À suivre"))
        ls.add_widget(self.btn_statut_resolue); ls.add_widget(self.btn_statut_a_suivre); corps.add_widget(ls)
        self.statut_selectionne="Résolue"
        self.lbl_confirmation=Label(text="", font_size=dp(12), color=(0.1,0.5,0.2,1), size_hint=(1,None), height=dp(24)); corps.add_widget(self.lbl_confirmation)
        corps.add_widget(bouton("Enregistrer", self.enregistrer, couleur_fond=BLEU_FONCE))
        corps.add_widget(bouton("Retour", self.retour, couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        scroll.add_widget(corps); racine.add_widget(scroll); self.add_widget(racine)
    def _choisir_statut(self,s):
        self.statut_selectionne=s
        if s=="Résolue":
            self.btn_statut_resolue.background_color=VERT_RESOLU; self.btn_statut_resolue.color=BLANC
            self.btn_statut_a_suivre.background_color=(0.85,0.88,0.9,1); self.btn_statut_a_suivre.color=GRIS_TEXTE
        else:
            self.btn_statut_a_suivre.background_color=ORANGE_A_SUIVRE; self.btn_statut_a_suivre.color=BLANC
            self.btn_statut_resolue.background_color=(0.85,0.88,0.9,1); self.btn_statut_resolue.color=GRIS_TEXTE
    def on_pre_enter(self): rafraichir_entete(self._barre_entete); self.spinner_poste.text=obtenir_poste_actuel(); self.recharger_equipements(); self.recharger_intervenants()
    def ouvrir_liste_defauts(self,*a):
        c=BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        c.add_widget(Label(text="Choisir un defaut", font_size=dp(15), bold=True, color=BLEU_NUIT, size_hint=(1,None), height=dp(28)))
        scroll=ScrollView(size_hint=(1,1)); grille=GridLayout(cols=1, spacing=dp(8), size_hint=(1,None), padding=(0,dp(4))); grille.bind(minimum_height=grille.setter("height")); scroll.add_widget(grille); c.add_widget(scroll)
        lb=BoxLayout(size_hint=(1,None), height=dp(46), spacing=dp(8)); c.add_widget(lb)
        popup=Popup(title="", separator_height=0, content=c, size_hint=(0.94,0.82))
        def sel(d,*a): self.champ_anomalie.text=d; popup.dismiss()
        defauts=get_defauts()
        if not defauts: grille.add_widget(Label(text="Aucun defaut", size_hint=(1,None), height=dp(44), color=GRIS_TEXTE, font_size=dp(13)))
        else:
            largeur=Window.width*0.94-dp(48)
            for _,desc in defauts:
                btn=Button(text=desc, size_hint=(1,None), background_normal="", background_color=(0.95,0.97,1,1), color=GRIS_TEXTE, font_size=dp(13.5), halign="left", valign="middle", padding=(dp(12),dp(10)))
                btn.text_size=(largeur,None)
                def _aj(inst,ts): inst.height=max(dp(46), ts[1]+dp(20))
                btn.bind(texture_size=_aj); btn.bind(on_release=lambda inst,d=desc: sel(d)); grille.add_widget(btn)
        lb.add_widget(bouton("+ Nouveau", lambda inst: self.ajouter_defaut_popup(popup_liste=popup), couleur_fond=JAUNE, couleur_texte=BLEU_NUIT))
        lb.add_widget(bouton("Fermer", lambda inst: popup.dismiss(), couleur_fond=(0.85,0.88,0.9,1), couleur_texte=GRIS_TEXTE))
        popup.open()
    def ajouter_defaut_popup(self,*a,popup_liste=None):
        c=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10)); ch=TextInput(hint_text="Nouveau defaut", multiline=False, size_hint=(1,None), height=dp(44)); c.add_widget(ch)
        pop=Popup(title="Nouveau defaut", content=c, size_hint=(0.85,0.35))
        def val(*a):
            d=ch.text.strip()
            if d: ajouter_defaut(d); self.champ_anomalie.text=d
            pop.dismiss()
            if popup_liste: popup_liste.dismiss()
        c.add_widget(bouton("Ajouter", val, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT)); pop.open()
    def recharger_intervenants(self):
        noms=[n for _,n in get_intervenants()]; self.spinner_intervenant1.values=noms; self.spinner_intervenant2.values=["— aucun —"]+noms
        if self.spinner_intervenant1.text not in noms and self.spinner_intervenant1.text!="— aucun —": self.spinner_intervenant1.text="— aucun —" if not noms else noms[0]
        if self.spinner_intervenant2.text not in self.spinner_intervenant2.values: self.spinner_intervenant2.text="— aucun —"
    def ajouter_intervenant_popup(self,spinner_cible):
        c=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10)); ch=TextInput(hint_text="Nom intervenant", multiline=False, size_hint=(1,None), height=dp(44)); c.add_widget(ch)
        pop=Popup(title="Nouvel intervenant", content=c, size_hint=(0.85,0.35))
        def val(*a):
            n=ch.text.strip()
            if n: ajouter_intervenant(n); self.recharger_intervenants(); spinner_cible.text=n
            pop.dismiss()
        c.add_widget(bouton("Ajouter", val, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT)); pop.open()
    def recharger_equipements(self,selectionner=None):
        noms=[n for _,n in get_equipements()]; self.spinner_equipement.values=noms
        if selectionner and selectionner in noms: self.spinner_equipement.text=selectionner
        elif self.spinner_equipement.text not in noms: self.spinner_equipement.text="— sélectionner —"
    def ajouter_equipement_popup(self,*a):
        c=BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10)); ch=TextInput(hint_text="Nouvel equipement", multiline=False, size_hint=(1,None), height=dp(44)); c.add_widget(ch)
        pop=Popup(title="Nouvel equipement", content=c, size_hint=(0.85,0.35))
        def val(*a):
            n=ch.text.strip()
            if n: ajouter_equipement(n); self.recharger_equipements(selectionner=n)
            pop.dismiss()
        c.add_widget(bouton("Ajouter", val, couleur_fond=JAUNE, couleur_texte=BLEU_NUIT)); pop.open()
    def enregistrer(self,*a):
        if getattr(self,"_en_cours",False): return
        if self.spinner_equipement.text=="— sélectionner —" or not self.champ_anomalie.text.strip():
            self.lbl_confirmation.color=(0.75,0.15,0.1,1); self.lbl_confirmation.text="Equipement et anomalie obligatoires."; return
        ok,msg=valider_numero_ot(self.champ_numero_ot.text)
        if not ok: self.lbl_confirmation.color=(0.75,0.15,0.1,1); self.lbl_confirmation.text=msg; return
        ok2,msg2=valider_duree(self.champ_duree.text)
        if not ok2: self.lbl_confirmation.color=(0.75,0.15,0.1,1); self.lbl_confirmation.text=msg2; return
        self._en_cours=True
        i1="" if self.spinner_intervenant1.text=="— aucun —" else self.spinner_intervenant1.text
        i2="" if self.spinner_intervenant2.text=="— aucun —" else self.spinner_intervenant2.text
        try:
            enregistrer_intervention({"numero_ordre_travail":self.champ_numero_ot.text.strip(),"poste":self.spinner_poste.text,"equipement":self.spinner_equipement.text,"type_maintenance":self.spinner_type.text,"anomalie":self.champ_anomalie.text.strip(),"action":self.champ_action.text.strip(),"duree":self.champ_duree.text.strip(),"intervenant1":i1,"intervenant2":i2,"remarques":self.champ_remarques.text.strip(),"statut":self.statut_selectionne})
        except sqlite3.Error as e:
            self.lbl_confirmation.color=(0.75,0.15,0.1,1); self.lbl_confirmation.text=f"Erreur: {e}"; self._en_cours=False; return
        self.lbl_confirmation.color=(0.1,0.5,0.2,1); self.lbl_confirmation.text="Fiche enregistrée."; vibrer(0.15); afficher_toast("Fiche enregistrée", couleur_fond=VERT_RESOLU)
        self.champ_numero_ot.text=""; self.champ_anomalie.text=""; self.champ_action.text=""; self.champ_duree.text=""
        self.spinner_intervenant1.text="— aucun —" if not self.spinner_intervenant1.values else self.spinner_intervenant1.values[0]
        self.spinner_intervenant2.text="— aucun —"; self.champ_remarques.text=""; self._choisir_statut("Résolue")
        Clock.schedule_once(lambda dt: setattr(self,"_en_cours",False), 1.0)
    def retour(self,*a): self.manager.transition=SlideTransition(direction="right"); self.manager.current="objectifs"

class GestionMaintenanceApp(App):
    def build(self):
        basculer_mode_sombre(obtenir_poste_actuel()=="Nuit"); init_db()
        self.sm=ScreenManager(); self.sm.add_widget(EcranEntreprise(name="entreprise")); self.sm.add_widget(EcranLogin(name="login")); self.sm.add_widget(EcranObjectifs(name="objectifs"))
        self.sm.add_widget(EcranDonneesUtiles(name="donnees_utiles")); self.sm.add_widget(EcranHistorique(name="historique"))
        self.sm.add_widget(EcranRapport(name="rapport")); self.sm.add_widget(EcranFiche(name="fiche"))
        self.sm.current = "login" if obtenir_config_entreprise()["nom"].strip() else "entreprise"
        Window.bind(on_keyboard=self.gerer_bouton_retour); return self.sm
    def gerer_bouton_retour(self,window,key,*a):
        if key==27:
            cur=self.sm.current
            if cur in ("login","entreprise"): return False
            if cur=="objectifs": self.sm.transition=SlideTransition(direction="right"); self.sm.current="login"; return True
            self.sm.transition=SlideTransition(direction="right"); self.sm.current="objectifs"; return True
        return False

if __name__=="__main__":
    GestionMaintenanceApp().run()
