"""Unternehmer-Cockpit – Schritt 1–4 (intern: eine Firma; extern: Berater mit Mandanten; Zugänge mit Rollen).

Start:  python -m streamlit run app.py
"""
import io
import json
import os
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import importlib
import aufbau as A
import bereinigung as BR
import logik as L
import sql_abfragen as SQL
import diagramme as D
import ki
import massnahmen as M
import quelle as Q
import sprache as S
import zugang as Z
from sprache import T
for _m in (S, Q, L, A, BR, D, ki, M, Z):   # Code-Änderungen ohne Neustart übernehmen
    importlib.reload(_m)

st.set_page_config(page_title="Unternehmer-Cockpit", page_icon="🧭", layout="wide")

# Diagnose: ?versionen=1 zeigt die installierten Paketversionen (für requirements.txt und Fehlersuche)
if st.query_params.get("versionen"):
    import platform
    from importlib.metadata import PackageNotFoundError, version as _v
    def _ver(n):
        try:
            return _v(n)
        except PackageNotFoundError:
            return "–"
    st.code(f"python=={platform.python_version()}\n" + "\n".join(
        f"{n}=={_ver(n)}" for n in ["streamlit", "pandas", "numpy", "matplotlib", "openpyxl", "xlsxwriter", "altair", "pythonnet"]))
    st.stop()

# Online-Demo (z. B. Streamlit Community Cloud): COCKPIT_DEMO=1 als Umgebungsvariable oder Secret.
# Dann speichert niemand etwas für andere: Maßnahmen gelten nur in der eigenen Sitzung, Schwellen sind fest.
def _demo() -> bool:
    if str(os.environ.get("COCKPIT_DEMO", "")).strip() == "1":
        return True
    try:
        return str(st.secrets.get("COCKPIT_DEMO", "")).strip() == "1"
    except Exception:  # noqa: BLE001 – keine secrets.toml vorhanden
        return False


DEMO = _demo()
UPLOAD_MAX_MB = 20                                   # Grenze für Uploads; gleich wie server.maxUploadSize in .streamlit/config.toml
POWERBI_MOEGLICH = os.name == "nt" and not DEMO      # Power BI Desktop gibt es nur lokal unter Windows

# Farben aus der Unicorn-Präsentation (Corporate Identity)
NAVY, BLAU, HELLBLAU, ORANGE, GRAU = "#0A2342", "#1A63B7", "#7DB9FF", "#F28C28", "#3D5470"
AMPEL_RAND = {"grün": "#2E9E5B", "gelb": "#F28C28", "rot": "#D0435E"}
AMPEL_TEXT = {"grün": "#2E7348", "gelb": "#A84F0F", "rot": "#9A3550"}
# Ampel mit Form UND Farbe, damit sie auch bei Rot-Grün-Schwäche lesbar ist
AMPEL_PUNKT = {"grün": "✅", "gelb": "⚠️", "rot": "⛔"}


def datenfehler(e: Exception):
    """Verständliche Meldung statt Traceback, wenn die Daten nicht geladen werden können."""
    st.error(T("**Die Daten konnten nicht geladen werden.**  \n"
               "Die App braucht die Datei `unicorn_cockpit.sqlite` – im Ordner `daten/` der App, "
               "im Nachbarordner `10_cockpit_daten/` oder unter dem Pfad in `COCKPIT_DB`.",
               "**The data could not be loaded.**  \n"
               "The app needs the file `unicorn_cockpit.sqlite` – in the app's `daten/` folder, "
               "in the sibling folder `10_cockpit_daten/` or at the path in `COCKPIT_DB`."))
    with st.expander(T("Technische Details", "Technical details")):
        st.code(f"{type(e).__name__}: {e}")
    st.stop()


def seitenfehler(e: Exception):
    """Fehler auf einer Seite: kurze Meldung, Details aufklappbar, Rest der App bleibt bedienbar."""
    st.warning(T("Diese Ansicht konnte gerade nicht berechnet werden. Bitte einen anderen Stichtag "
                 "oder eine andere Seite wählen.",
                 "This view could not be calculated. Please pick another reporting date or another page."))
    with st.expander(T("Technische Details", "Technical details")):
        st.code(f"{type(e).__name__}: {e}")



st.markdown(f"""
<style>
html, body, [class*="css"] {{font-family: "Inter", "Segoe UI", Arial, sans-serif;}}
[data-testid="stSidebar"] {{background: {NAVY};}}
[data-testid="stSidebar"] * {{color: #F2F6FB !important;}}
[data-testid="stSidebar"] h1 {{color: #FFFFFF !important;}}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{color: {ORANGE} !important; font-weight: 700;}}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"], [data-testid="stSidebar"] [data-baseweb="select"] > div {{background: #1B3A63 !important; border: 1px solid #3E5E88 !important; border-radius: 8px;}}
[data-testid="stSidebar"] [data-testid="stSelectbox"] input, [data-testid="stSidebar"] [data-testid="stSelectbox"] svg, [data-testid="stSidebar"] [data-baseweb="select"] * {{color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important; opacity: 1 !important; background: transparent;}}
[data-testid="stSidebar"] [data-testid="stAlertContainer"] {{background: rgba(255,255,255,0.08) !important; border: 1px solid #3E5E88 !important;}}
[data-testid="stSidebar"] [data-testid="stAlertContainer"] * {{color: #F2F6FB !important; -webkit-text-fill-color: #F2F6FB !important; opacity: 1 !important;}}
h1, h2, h3 {{color: {NAVY} !important; font-weight: 800 !important;}}
[data-testid="stApp"], [data-testid="stHeader"] {{background: #E2E8F1 !important;}}
[data-testid="stMain"] p, [data-testid="stMain"] li {{color: {NAVY};}}
[data-testid="stMain"] [data-testid^="stBaseButton-primary"] p {{color: #FFFFFF !important; font-weight: 700;}}
[data-testid="stSidebar"] button:not([data-testid="stBaseButton-headerNoPadding"]) {{background: #1B3A63 !important; border: 1px solid #3E5E88 !important;}}
[data-testid="stSidebar"] button[kind*="Active"], [data-testid="stSidebar"] button[aria-checked="true"],
[data-testid="stSidebar"] button[aria-pressed="true"] {{background: {ORANGE} !important; border-color: {ORANGE} !important;}}
[data-testid="stMain"] [data-testid="stCaptionContainer"], [data-testid="stMain"] [data-testid="stCaptionContainer"] * {{color: #3D5470 !important; opacity: 1 !important;}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"], [data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {{color: #C9D6E8 !important; opacity: 1 !important;}}
[data-testid="stMetric"] {{background: #FFFFFF; border-radius: 10px; border: 1px solid #C3CEDC; border-top: 4px solid {BLAU}; padding: 0.6rem 0.8rem; box-shadow: 0 6px 18px rgba(10,35,66,0.24);}}
[data-testid="stMetricLabel"] * {{color: {GRAU} !important; font-weight: 600 !important; font-size: 0.85rem !important;}}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{font-size: clamp(1.05rem, 1.6vw, 1.6rem) !important; font-weight: 700 !important; color: {BLAU} !important; overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important;}}
.eyebrow {{color: {BLAU}; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em;
           text-transform: uppercase; margin-bottom: -0.6rem;}}
.lage {{background: #FFFFFF; border: 1px solid #C3CEDC; box-shadow: 0 6px 18px rgba(10,35,66,0.24); border-radius: 12px; padding: 14px 18px; margin-bottom: 14px; color: #0E2949;}}
.badge-modus {{display: inline-block; background: #FDE6D2; color: #8A4A12; border: 1px solid #F6A25E; border-radius: 999px; padding: 3px 12px; font-size: 0.9rem; font-weight: 600; margin-bottom: 10px;}}
.kachel {{background: #FFFFFF; border: 1px solid #C3CEDC; box-shadow: 0 6px 18px rgba(10,35,66,0.24); border-radius: 12px; padding: 14px 16px; border-top: 6px solid; margin-bottom: 8px;}}
.kachel .name {{font-size: 0.85rem; font-weight: 600; color: {GRAU};}}
.kachel .wert {{font-size: clamp(1.05rem, 1.7vw, 1.7rem); font-weight: 700; color: {BLAU}; line-height: 1.3; white-space: nowrap;}}
.kachel .sub {{font-size: 0.82rem; font-weight: 600; color: {NAVY};}}
.signal {{background: #FFFFFF; border: 1px solid #C3CEDC; box-shadow: 0 4px 12px rgba(10,35,66,0.22); border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; border-left: 6px solid;}}
.signal b {{color: #0E2949;}}
.aussage {{font-size: 0.95rem; color: {NAVY}; background: #FFFFFF; border: 1px solid #C3CEDC; border-left: 5px solid #E07F2E;
          border-radius: 8px; padding: 8px 12px; margin: -4px 0 18px 0;}}
[data-testid="stImage"] img, [data-testid="stPyplot"] img {{border-radius: 12px; border: 1px solid #C3CEDC; box-shadow: 0 6px 18px rgba(10,35,66,0.24);}}
</style>""", unsafe_allow_html=True)


def kopf(eyebrow: str, titel: str):
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(titel)


@st.cache_data(show_spinner="Lade Daten aus der SQLite-Datei …")
def daten():
    return L.lade_daten()


@st.cache_data(show_spinner="Lade Daten aus Power BI Desktop …", max_entries=4)
def daten_powerbi(port: int, gestartet: float, neu: int):   # gestartet/neu: nur Cache-Schlüssel
    return L.lade_daten(quelle="powerbi", port=port)


@st.cache_data(show_spinner=False, max_entries=4)
def abgleich_powerbi(port: int, gestartet: float, neu: int):
    tab = lambda d: {n: getattr(d, Q.FELD[n]) for n in Q.TABELLEN}
    return Q.abgleich(tab(daten_powerbi(port, gestartet, neu)), tab(daten()))


# einstellbare Schwellen der Frühwarnung (gespeichert neben der App)
EINST = Path(__file__).resolve().parent / "einstellungen.json"


def lade_schwellen() -> dict:
    werte = dict(L.SCHWELLEN_STANDARD)
    try:
        werte.update(json.loads(EINST.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        pass
    return werte


L.setze_schwellen(lade_schwellen())

# ------------------------------------------------------------------ Sprache
ss = st.session_state
if "sprache_s" not in ss:                                   # ?lang=en im Link öffnet die App auf Englisch
    ss.sprache_s = "en" if str(st.query_params.get("lang", "")).lower().startswith("en") else "de"
S.setze(ss.sprache_s)


def uebersetzung_sperren(sprache: str) -> None:
    """Browser-Übersetzung abschalten und die Seitensprache richtig setzen.

    Streamlit liefert die Seite immer mit lang="en" aus. Ein deutscher Chrome bietet dann an,
    sie zu übersetzen; die Übersetzung ändert die Seite hinter dem Rücken von React und führt
    zu Fehlern wie „NotFoundError: removeChild“. Die App ist selbst zweisprachig, also aus.
    """
    js = f"""<script>
    const doc = window.parent.document, h = doc.documentElement;
    h.setAttribute("lang", "{sprache}"); h.setAttribute("translate", "no"); h.classList.add("notranslate");
    if (!doc.querySelector('meta[name="google"]')) {{
        const m = doc.createElement("meta"); m.name = "google"; m.content = "notranslate"; doc.head.appendChild(m);
    }}
    </script>"""
    try:
        import streamlit.components.v1 as components
        with st.sidebar:
            components.html(js, height=0)
    except Exception:                                       # nur Komfort, darf die App nie stoppen
        pass


uebersetzung_sperren(ss.sprache_s)


def sprachwahl(ort):
    neu = ort.segmented_control("🌐", list(S.SPRACHEN), format_func=S.SPRACHEN.get, default=ss.sprache_s,
                                key=f"sprache_{id(ort)}", label_visibility="collapsed")
    if neu and neu != ss.sprache_s:
        ss.sprache_s = neu
        st.query_params["lang"] = neu
        st.rerun()


@st.cache_data(show_spinner=False)
def befunde(sprache: str) -> dict:
    """Kernaussagen für die Startseite, live aus den Daten (Stichtag = letzter Monat)."""
    S.setze(sprache)
    d = daten()
    s = L.stichtage(d)[-1]
    k = L.kennzahlen(d, s)
    rp = L.rabatt_profil(d, s)
    h = rp[(rp.rabattstufe == "> 20 %") & (rp.zeitraum == "Ist")].iloc[0]
    pf = L.portfolio(d, s).set_index("mandant")
    schwach = pf.umsatz_abw.idxmin()
    bm = L.benchmark(d, s).set_index("kz")
    return {"s": s, "k": k, "h": h, "pf": pf, "schwach": schwach, "dso": bm.loc["dso"]}


def startseite(zug: dict):
    st.markdown('<style>[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], '
                '[data-testid="stExpandSidebarButton"] {display: none !important;}</style>',
                unsafe_allow_html=True)      # leere Seitenleiste würde die Startseite verdecken
    _, sp = st.columns([5, 1.3])
    sprachwahl(sp)
    kopf(T("Portfolio-Projekt · Data Analytics", "Portfolio project · Data analytics"),
         T("Unternehmer-Cockpit", "Business Cockpit"))
    st.markdown(T(
        "Ein Controlling-Cockpit für kleine Händler und ihre Berater: **Wo stehe ich gegen Plan, warum, "
        "reicht das Geld, und was tue ich jetzt?** Gebaut mit Python, pandas, SQL und Streamlit auf einem "
        "fiktiven Händler-Datensatz, mit optionaler Anbindung an Power BI.",
        "A controlling cockpit for small retailers and their advisors: **Where do I stand against plan, why, "
        "will the cash last, and what do I do now?** Built with Python, pandas, SQL and Streamlit on a "
        "fictional retail dataset, with an optional Power BI connection."))

    b = befunde(S.aktiv())
    k, h, pf, sw, dso = b["k"], b["h"], b["pf"], b["schwach"], b["dso"]
    st.subheader(T(f"Drei Erkenntnisse (Stand {L.datum(b['s'])})", f"Three findings (as of {L.datum(b['s'])})"))
    c = st.columns(3)
    karten = [
        (T("Rabatte fressen die Marge", "Discounts eat the margin"),
         T(f"Der Umsatz liegt {L.proz(abs(k['umsatz_abw']), False)} {'über' if k['umsatz_abw'] >= 0 else 'unter'} Plan, "
           f"der DB I {L.proz(abs(k['db1_abw']), False)} {'darunter' if k['db1_abw'] < 0 else 'darüber'}. "
           f"Aufträge mit über 20 % Rabatt bringen {L.proz(h.anteil, False)} des Umsatzes und {L.geld(h.db1)} DB I.",
           f"Revenue is {L.proz(k['umsatz_abw'])} vs. plan, but contribution margin is {L.proz(k['db1_abw'])}. "
           f"Orders with more than 20% discount bring {L.proz(h.anteil, False)} of revenue and {L.geld(h.db1)} of margin.")),
        (T(f"{sw} rutscht ins Minus", f"{sw} slides into the red"),
         T(f"Region {sw} verfehlt den Plan um {L.proz(abs(pf.loc[sw, 'umsatz_abw']), False)}. Als eigener Mandant betrachtet: "
           f"EBIT {L.geld(pf.loc[sw, 'ebit'])}, Konto {L.geld(pf.loc[sw, 'kontostand'])}, in 13 Wochen bis "
           f"{L.geld(pf.loc[sw, 'liq_min'])}.",
           f"Region {sw} misses plan by {L.proz(abs(pf.loc[sw, 'umsatz_abw']), False)}. Viewed as a separate client: "
           f"EBIT {L.geld(pf.loc[sw, 'ebit'])}, cash {L.geld(pf.loc[sw, 'kontostand'])}, down to "
           f"{L.geld(pf.loc[sw, 'liq_min'])} within 13 weeks.")),
        (T("Kunden zahlen langsam", "Customers pay slowly"),
         T(f"Die Forderungslaufzeit liegt bei {L.zahl(dso.gesamt, 1)} Tagen, der Einzelhandel schafft "
           f"{L.zahl(dso.branche, 1)} Tage (Bundesbank). Einzelne Geschäftskunden zahlen zuletzt 30–60 Tage später.",
           f"Days sales outstanding are {L.zahl(dso.gesamt, 1)} days vs. {L.zahl(dso.branche, 1)} days for "
           f"German retail (Bundesbank). Some business customers recently pay 30–60 days later.")),
    ]
    for spalte, (titel, text) in zip(c, karten):
        spalte.markdown(f'<div class="kachel" style="border-color:{ORANGE}"><div class="wert" style="white-space:normal;'
                        f'font-size:1.05rem">{titel}</div><div class="sub" style="font-weight:500">{text}</div></div>',
                        unsafe_allow_html=True)

    st.subheader(T("Ausprobieren", "Try it"))
    if zug.get("demo"):
        st.caption(T("Ein Klick meldet dich mit einem Demo-Zugang an. Jede Rolle sieht etwas anderes.",
                     "One click logs you in with a demo account. Each role sees something different."))
        rollen = [("berater", T("👔 Als Berater", "👔 As advisor"),
                   T("alle Mandanten, Mandanten-Übersicht, Benchmark", "all clients, client overview, benchmark")),
                  ("inhaber", T("🏢 Als Inhaberin", "🏢 As owner"),
                   T("die eigene Firma: Plan-Ist, Liquidität, Was-wäre-wenn", "own company: plan vs. actual, cash, what-if")),
                  ("central", T("🧾 Als Mandant Central", "🧾 As client Central"),
                   T("nur die eigenen Zahlen, andere anonym", "only own numbers, others anonymised"))]
        for spalte, (name, knopf, was) in zip(st.columns(3), rollen):
            if spalte.button(knopf, type="primary", use_container_width=True, key=f"demo_{name}"):
                n = zug["nutzer"][name]
                sprache = ss.sprache_s
                ss.clear()
                ss.sprache_s = sprache
                ss.nutzer = {"name": name, "rolle": n["rolle"], "mandant": n.get("mandant")}
                st.rerun()
            spalte.caption(was)
        st.markdown(T(
            "**In 60 Sekunden durch:** ① *Als Inhaberin* → **Überblick**: Ampeln und Signale · "
            "② **Plan-Ist**: die DB-I-Brücke zeigt den Rabatt-Effekt, darunter „SQL hinter diesen Zahlen“ · "
            "③ **Was wäre wenn?** Rabatt bei 20 % deckeln und die EBIT-Wirkung sehen · "
            "④ *Als Berater* → **Mandanten-Übersicht**: Central steht im Minus.",
            "**60-second tour:** ① *As owner* → **Overview**: traffic lights and signals · "
            "② **Plan vs. actual**: the margin bridge shows the discount effect, below it “SQL behind these figures” · "
            "③ **What if?** Cap discounts at 20% and see the EBIT impact · "
            "④ *As advisor* → **Client overview**: Central is in the red."))
    with st.expander(T("Mit Benutzername anmelden", "Log in with username"), expanded=not zug.get("demo")):
        with st.form("anmeldung"):
            n = st.text_input(T("Benutzername", "Username"))
            p = st.text_input(T("Passwort", "Password"), type="password")
            ok = st.form_submit_button(T("Anmelden", "Log in"), type="primary", use_container_width=True)
        if ok:
            nutzer = Z.pruefen(zug, n, p)
            if nutzer:
                sprache = ss.sprache_s
                ss.clear()
                ss.sprache_s = sprache
                ss.nutzer = nutzer
                st.rerun()
            st.error(T("Benutzername oder Passwort stimmt nicht.", "Username or password is incorrect."))
        if zug.get("demo"):
            st.caption(T("Demo: berater / demo-berater · inhaber / demo-inhaber · central / demo-central "
                         "(ebenso east, south, west)",
                         "Demo: berater / demo-berater · inhaber / demo-inhaber · central / demo-central "
                         "(also east, south, west)"))

    st.subheader(T("Was dahintersteckt", "What's behind it"))
    a_, b_ = st.columns(2)
    a_.markdown(T(
        "- **Plan-Ist-Analyse** mit Zerlegung der Margenabweichung in Menge, Mix und Preis/Rabatt\n"
        "- **13-Wochen-Liquiditätsprognose** aus offenen Rechnungen und dem Zahlungsverhalten jedes Kunden\n"
        "- **Frühwarnung** mit einstellbaren Schwellen, daraus **Maßnahmen** mit Verantwortlichen und Fälligkeit\n"
        "- **Was-wäre-wenn**: Rabattdeckel, Menge, Fixkosten, Zahlungsziele; EBIT-Brücke und Break-even\n"
        "- **Mandanten-Modus** für Berater mit Kostenumlage, Rollen und anonymem **Branchenvergleich**",
        "- **Plan vs. actual** with a breakdown of the margin gap into volume, mix and price/discount\n"
        "- **13-week cash forecast** from open invoices and each customer's payment behaviour\n"
        "- **Early warning** with adjustable thresholds, turned into **actions** with owners and due dates\n"
        "- **What-if**: discount cap, volume, fixed costs, payment terms; EBIT bridge and break-even\n"
        "- **Client mode** for advisors with cost allocation, roles and an anonymised **industry benchmark**"))
    b_.markdown(T(
        "- **Daten:** fiktiver Übungsdatensatz (Tableau Sample Superstore, im Masterschool-Kurs als SQL-Datenbank "
        "„Unicorn“), 9.997 Auftragspositionen 2015–2018. Plan, Fixkosten und Zahlungen sind dazu simuliert.\n"
        "- **Werkzeuge:** SQL, Python, pandas, matplotlib, Streamlit; Power BI Desktop per DAX (lokal); automatische Tests mit pytest\n"
        "- **Branchenwerte:** Deutsche Bundesbank, Jahresabschlussstatistik Einzelhandel\n"
        "- **Datenschutz:** Rollen mit Passwort-Hash, Pseudonymisierung der Kundennamen, in der Demo wird nichts gespeichert",
        "- **Data:** fictional training dataset (Tableau Sample Superstore, used as the SQL database “Unicorn” in the "
        "Masterschool course), 9,997 order lines 2015–2018. Plan, fixed costs and payments are simulated on top.\n"
        "- **Tools:** SQL, Python, pandas, matplotlib, Streamlit; Power BI Desktop via DAX (local); automated tests with pytest\n"
        "- **Industry values:** Deutsche Bundesbank, financial statements statistics for retail\n"
        "- **Privacy:** roles with password hashing, customer-name pseudonymisation, nothing is stored in the demo"))
    st.caption(T("Projekt von Denise Tirrel · Alle Unternehmens- und Kundendaten sind fiktiv.",
                 "Project by Denise Tirrel · All company and customer data are fictional."))


ROLLEN_TEXT = {"berater": ("Berater", "Advisor"), "inhaber": ("Inhaber", "Owner"), "mandant": ("Mandant", "Client")}
_zug = Z.laden()
if not _zug["nutzer"]:
    NUTZER = {"name": "ohne Anmeldung", "rolle": "berater", "mandant": None}   # keine zugaenge.json: offen wie bisher
elif ss.get("nutzer"):
    NUTZER = ss.nutzer
else:
    # eigene, versteckte Navigation: sonst bleibt das Seitenmenü der letzten Sitzung stehen
    st.navigation([st.Page(lambda: startseite(_zug), title=T("Start", "Start"), icon="🧭", url_path="start")],
                  position="hidden").run()
    st.stop()
ROLLE = NUTZER["rolle"]

# ------------------------------------------------------------------ Datenquelle
st.sidebar.title(T("🧭 Unternehmer-Cockpit", "🧭 Business Cockpit"))
sprachwahl(st.sidebar)
a_, b_ = st.sidebar.columns([2, 1])
a_.caption(f"👤 {NUTZER['name']} · {T(*ROLLEN_TEXT[ROLLE])}" + (f" Unicorn {NUTZER['mandant']}" if NUTZER["mandant"] else ""))
if _zug["nutzer"] and b_.button(T("Abmelden", "Log out"), use_container_width=True):
    sprache = ss.sprache_s
    ss.clear()
    ss.sprache_s = sprache
    st.rerun()
QUELLEN = {"sqlite": T("SQLite-Datei", "SQLite file")}
if POWERBI_MOEGLICH:
    QUELLEN["powerbi"] = "Power BI Desktop"
if ss.get("upload_daten") is not None and ROLLE != "mandant":
    QUELLEN["upload"] = T("Aufbereitete Datei", "Prepared file")
ss.setdefault("quelle_s", "sqlite")
ss.setdefault("pbi_neu", 0)
ss.setdefault("upload_neu", 0)
if ss.quelle_s not in QUELLEN:
    ss.quelle_s = "sqlite"
if ROLLE == "mandant" or len(QUELLEN) == 1:
    quelle = "sqlite"          # Mandanten wählen keine Datenquelle
else:
    quelle = st.sidebar.radio(T("Datenquelle", "Data source"), list(QUELLEN), index=list(QUELLEN).index(ss.quelle_s),
                              format_func=QUELLEN.get, horizontal=len(QUELLEN) == 2)
ss.quelle_s = quelle
QUELLE_TEXT, PBI_ABGLEICH, D_GESAMT = QUELLEN["sqlite"], None, None
if quelle == "upload":
    D_GESAMT = ss.upload_daten
    QUELLE_TEXT = T("aufbereitete Datei ", "prepared file ") + ss.upload_name
if quelle == "powerbi":
    instanzen = Q.pbi_instanzen()
    if not instanzen:
        st.sidebar.warning(T("Kein geöffnetes Power-BI-Desktop-Modell gefunden. Öffne deine .pbix in "
                             "Power BI Desktop und klicke dann auf „Neu verbinden“. Bis dahin zeigt die "
                             "App die SQLite-Datei.",
                             "No open Power BI Desktop model found. Open your .pbix in Power BI Desktop, then "
                             "click “Reconnect”. Until then the app shows the SQLite file."))
    else:
        inst = instanzen[0] if len(instanzen) == 1 else st.sidebar.selectbox(
            T("Geöffnetes Modell", "Open model"), instanzen, format_func=lambda i: i.text)
        try:
            D_GESAMT = daten_powerbi(inst.port, inst.gestartet, ss.pbi_neu)
            QUELLE_TEXT = f"Power BI Desktop ({inst.text})"
            PBI_ABGLEICH = abgleich_powerbi(inst.port, inst.gestartet, ss.pbi_neu)
        except Q.PaketFehlt:
            st.sidebar.error(T("Für Power BI fehlt das Python-Paket pythonnet. Die App zeigt solange die SQLite-Datei.",
                               "Power BI needs the Python package pythonnet. Until then the app shows the SQLite file."))
            if st.sidebar.button(T("pythonnet jetzt installieren", "Install pythonnet now"), type="primary",
                                 use_container_width=True):
                with st.sidebar.status(T("Installiere pythonnet …", "Installing pythonnet …")):
                    ok, log = Q.installiere_pythonnet()
                    st.code(log)
                if ok:
                    ss.pbi_neu += 1
                    st.rerun()
                st.sidebar.error(T("Installation fehlgeschlagen, siehe Meldung oben.", "Installation failed, see the message above."))
        except Q.QuellenFehler as e:
            st.sidebar.error(f"{e}\n\n" + T("Die App zeigt solange die SQLite-Datei.", "Until then the app shows the SQLite file."))
        if ss.get("pbi_modell_zeigen"):
            try:
                for t in Q.pbi_modell(inst.port):
                    st.sidebar.markdown(f"**{t['tabelle']}** · {t['zeilen']} {T('Zeilen', 'rows')}  \n" + ", ".join(t["spalten"]))
                    st.sidebar.dataframe(t["probe"], hide_index=True)
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(T("Modell nicht lesbar: ", "Model not readable: ") + str(e))
        st.sidebar.toggle(T("Inhalt des Power-BI-Modells zeigen", "Show Power BI model contents"), key="pbi_modell_zeigen")
    if st.sidebar.button(T("↻ Neu verbinden / Daten neu laden", "↻ Reconnect / reload data"), use_container_width=True):
        ss.pbi_neu += 1
        st.rerun()
try:
    if D_GESAMT is None:
        D_GESAMT = daten()
except Exception as e:  # noqa: BLE001 – Datei fehlt, Tabelle fehlt, Datei beschädigt
    datenfehler(e)

# Quelle und Pseudonymisierung gehören zu jedem Cache-Schlüssel: so bekommt keine Sitzung
# Ergebnisse einer anderen Quelle oder Klarnamen, wenn sie pseudonymisiert arbeitet.
ss.setdefault("pseudo_s", False)
PSEUDO = st.sidebar.toggle(T("Kundennamen pseudonymisieren", "Pseudonymise customer names"), value=ss.pseudo_s,
                           help=T("Ersetzt Kundennamen überall durch „Kunde 0123“, auch in Signalen, "
                                  "Briefing und bei Fragen an die KI.",
                                  "Replaces customer names everywhere with “Customer 0123”, including signals, "
                                  "the briefing and questions to the AI."))
ss.pseudo_s = PSEUDO
KEY = (ss.quelle_s, ss.pbi_neu, ss.upload_neu, PSEUDO, S.aktiv())       # Sprache: Texte in gecachten Ergebnissen


@st.cache_data(show_spinner=False, max_entries=8)
def pseudonymisiert(q):
    return L.pseudonymisieren(D_GESAMT)


if PSEUDO:
    D_GESAMT = pseudonymisiert(KEY)
if PBI_ABGLEICH is not None:
    gleich = (PBI_ABGLEICH.Ergebnis == "identisch").all()
    with st.sidebar.expander(T("✅ Abgleich mit SQLite: identisch", "✅ Check against SQLite: identical") if gleich
                             else T("⚠️ Abgleich mit SQLite: Abweichungen", "⚠️ Check against SQLite: differences"),
                             expanded=not gleich):
        st.table(PBI_ABGLEICH.set_index("Tabelle"))
        st.caption(T("Vergleicht je Tabelle Zeilen, Zahlen (auf 1 Cent), Datumswerte und Texte. "
                     "Abweichungen sind normal, wenn du im Power-BI-Modell Daten geändert hast.",
                     "Compares rows, numbers (to the cent), dates and texts per table. "
                     "Differences are expected if you changed data in the Power BI model."))


@st.cache_data(show_spinner=False, max_entries=16)
def mandant_daten(m: str, q):
    return L.mandant_daten(D_GESAMT, m)


# ------------------------------------------------------------------ Seitenleiste
tage = L.stichtage(D_GESAMT)
MODI = {"intern": T("Intern · eine Firma", "Internal · one company"),
        "extern": T("Extern · Berater mit Mandanten", "External · advisor with clients")}
# Auswahl in eigenen Session-Werten halten: Streamlit setzt Widgets beim Seitenwechsel per Code
# (st.switch_page) sonst auf den Standard zurück. Ohne key folgt das Widget immer dem gespeicherten Wert.
ss.setdefault("modus_s", "intern")
if ROLLE == "berater":
    modus = st.sidebar.radio(T("Modus", "Mode"), list(MODI), index=list(MODI).index(ss.modus_s), format_func=MODI.get)
else:
    modus = "extern" if ROLLE == "mandant" else "intern"
ss.modus_s = modus
MANDANT = None
if ROLLE == "mandant":
    MANDANT = NUTZER["mandant"]
elif modus == "extern":
    liste = L.mandanten(D_GESAMT)
    if ss.get("mandant_s") not in liste:
        ss.mandant_s = liste[0]
    MANDANT = st.sidebar.selectbox(T("Mandant", "Client"), liste, index=liste.index(ss.mandant_s),
                                   format_func=lambda m: f"Unicorn {m}")
    ss.mandant_s = MANDANT
D_ = mandant_daten(MANDANT, KEY) if MANDANT else D_GESAMT
M.setze(MANDANT, ss.setdefault("massnahmen_demo", {}) if DEMO else None)
st.sidebar.caption((T(f"{D_GESAMT.name}-Daten · Region {MANDANT} als Mandant", f"{D_GESAMT.name} data · region {MANDANT} as client")
                    if MANDANT else T(f"{D_GESAMT.name}-Daten · Gesamtfirma", f"{D_GESAMT.name} data · whole company"))
                   + T(" · Quelle: ", " · source: ") + QUELLE_TEXT)
if ss.get("stichtag_s") not in tage:      # z. B. nach Wechsel der Datenquelle
    ss.stichtag_s = tage[-1]
stichtag = st.sidebar.selectbox(T("Stichtag (Monatsende)", "Reporting date (month end)"), tage,
                                index=tage.index(ss.stichtag_s), format_func=L.monat)
ss.stichtag_s = stichtag
st.sidebar.caption(T(f"Alle Werte: Jahr bis Stichtag (01.01.–{L.datum(stichtag)}).",
                     f"All values: year to date (1 Jan–{L.datum(stichtag)})."))
st.sidebar.info(T("Fiktive Übungsdaten (Tableau Sample Superstore, im Kurs „Unicorn“). Plan, Fixkosten und "
                  "Zahlungen sind zusätzlich simuliert.",
                  "Fictional training data (Tableau Sample Superstore, “Unicorn” in the course). Plan, fixed costs "
                  "and payments are simulated on top.")
                + (T(" Fixkosten, Entnahme und Startkasse sind per Umlage nach Planumsatz auf die Mandanten verteilt.",
                     " Fixed costs, owner drawings and opening cash are allocated to clients by planned revenue.")
                   if MANDANT else ""), icon="ℹ️")


def _sw_key():
    return tuple(sorted(L.schwellen().items()))


@st.cache_data(show_spinner=False, max_entries=64)
def prognose(s, szen: tuple | None = None, sw=None, m=None, q=None):   # m: Mandant, gehört zum Cache-Schlüssel
    return L.liquiditaet_prognose(D_, s, szen=dict(szen) if szen else None)


@st.cache_data(show_spinner=False, max_entries=16)
def signal_verlauf(s, sw=None, m=None, q=None):
    return L.signal_verlauf(D_, s)


@st.cache_data(show_spinner=False, max_entries=16)
def portfolio(s, sw=None, q=None):
    return L.portfolio(D_GESAMT, s)


@st.cache_data(show_spinner=False, max_entries=16)
def benchmark(s, q=None):
    return L.benchmark(D_GESAMT, s)




def zeige(fig, aussage: str):
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    st.markdown(f'<div class="aussage">💬 {aussage}</div>', unsafe_allow_html=True)


def sql_zeigen(namen: list[str], s):
    """Ausklapper mit den SQL-Abfragen hinter den Zahlen dieser Seite (nur Firmenwerte, SQLite)."""
    if D_.mandant:
        return
    with st.expander(T("🧾 SQL hinter diesen Zahlen", "🧾 SQL behind these figures")):
        st.caption(T("Die App rechnet mit pandas; dieselben Zahlen entstehen direkt in der SQLite-Datenbank mit "
                     "diesen Abfragen (Ordner sql/, automatisch gegeneinander getestet)."
                     + (" Bei der aufbereiteten Datei läuft die Abfrage auf einer Datenbank im Speicher."
                        if ss.quelle_s == "upload" else ""),
                     "The app calculates with pandas; the same figures come straight from the SQLite database with "
                     "these queries (folder sql/, automatically tested against each other)."
                     + (" For the prepared file the query runs on an in-memory database."
                        if ss.quelle_s == "upload" else "")))
        for n in namen:
            st.markdown(f"**`sql/{n}.sql`**")
            st.code(SQL.text(n), language="sql")
            try:
                df = SQL.ausfuehren(n, s, db=ss.upload_sqlite if ss.quelle_s == "upload" else None)
            except Exception as e:  # noqa: BLE001
                st.warning(T("Abfrage nicht ausführbar: ", "Query failed: ") + str(e))
                continue
            if PSEUDO and "kunde_id" in df:
                df["kunde"] = T("Kunde ", "Customer ") + df.kunde_id.astype(str).str.zfill(4)
            df = df.drop(columns=["kunde_id"], errors="ignore")
            for c in df.select_dtypes("number"):
                ganz = (df[c].dropna() % 1 == 0).all()
                nk = 0 if ganz else (1 if c.endswith(("proz", "tage")) else 2)
                df[c] = df[c].map(lambda v, nk=nk, ganz=ganz: "" if pd.isna(v)
                                  else (str(int(v)) if c in ("positionen", "rang") else L.zahl(v, nk)))
            st.dataframe(df, hide_index=True, use_container_width=True)


def delta(wert: float, text: str):
    """Delta-Text für st.metric. Streamlit erkennt Rückgänge nur am ASCII-Minus am Anfang; unsere Formate nutzen „−“."""
    if round(wert, 6) == 0:
        return None
    text = text.lstrip("−-+ ")
    return ("-" if wert < 0 else "+") + text


def kachel(spalte, name, wert, sub, stufe):
    spalte.markdown(
        f'<div class="kachel" style="border-color:{AMPEL_RAND[stufe]}">'
        f'<div class="name">{AMPEL_PUNKT[stufe]} {name}</div><div class="wert">{wert}</div>'
        f'<div class="sub" style="color:{AMPEL_TEXT[stufe]}">{sub}</div></div>', unsafe_allow_html=True)


def signal_box(x: L.Signal):
    st.markdown(
        f'<div class="signal" style="border-color:{AMPEL_RAND[x.stufe]}">'
        f'{AMPEL_PUNKT[x.stufe]} <b>{x.titel}</b> <span style="color:{GRAU}">· {S.B(x.bereich)}</span><br>{x.text}</div>',
        unsafe_allow_html=True)


# ------------------------------------------------------------------ Seiten
def ueberblick():
    s = stichtag
    k = L.kennzahlen(D_, s)
    prog = L.liquiditaet_prognose(D_, s)
    kopf(f"{D_.name} · " + T("Lage", "Status"), T("Überblick", "Overview"))
    st.markdown(f'<div class="lage"><b>{T("Lage zum", "Status as of")} {L.datum(s)}:</b> {L.kurztext(D_, s)}</div>',
                unsafe_allow_html=True)

    c = st.columns(4)
    kachel(c[0], T("Umsatz", "Revenue"), L.geld(k["umsatz"]),
           T(f"{L.proz(k['umsatz_abw'])} gegen Plan · {L.proz(k['umsatz_vj_abw'])} gegen Vorjahr",
             f"{L.proz(k['umsatz_abw'])} vs. plan · {L.proz(k['umsatz_vj_abw'])} vs. prior year"), L.ampel(k["umsatz_abw"]))
    kachel(c[1], T("DB I", "Contribution margin I"), L.geld(k["db1"]),
           T(f"{L.proz(k['db1_abw'])} gegen Plan · Marge {L.proz(k['marge'], False)} (Plan {L.proz(k['marge_plan'], False)})",
             f"{L.proz(k['db1_abw'])} vs. plan · margin {L.proz(k['marge'], False)} (plan {L.proz(k['marge_plan'], False)})"),
           L.ampel(k["db1_abw"]))
    kachel(c[2], "EBIT", L.geld(k["ebit"]),
           f"{T('Plan', 'Plan')} {L.geld(k['ebit_plan'])} · {L.proz(k['ebit_abw'])}", L.ampel(k["ebit_abw"]))
    kachel(c[3], T("Kontostand", "Bank balance"), L.geld(k["kontostand"]),
           T(f"Tief in 13 Wochen {L.geld(prog['minimum'])} · Puffer {L.geld(prog['puffer'])}",
             f"Low in 13 weeks {L.geld(prog['minimum'])} · buffer {L.geld(prog['puffer'])}"), L.liq_ampel(prog))
    g = L.zahl(-L.AMPEL_GELB * 100, 1).replace(",0", "").replace(".0", "")
    st.caption(T(f"Ampel: grün = auf oder über Plan · gelb = bis {g} % darunter · rot = mehr als {g} % darunter. "
                 f"Kontostand: rot unter 0, gelb unter Puffer ({L.zahl(L.PUFFER_MONATE, 1)} Monat(e) Fixkosten + Entnahme). "
                 "Schwellen änderst du unter Frühwarnung.",
                 f"Traffic light: green = on or above plan · amber = up to {g}% below · red = more than {g}% below. "
                 f"Bank balance: red below 0, amber below buffer ({L.zahl(L.PUFFER_MONATE, 1)} month(s) of fixed costs + owner drawings). "
                 "Thresholds can be changed under Early warning."))

    links, rechts = st.columns([3, 2])
    with links:
        st.subheader(T("Umsatz im Jahresverlauf", "Revenue over the year"))
        t = L.plan_ist_monate(D_, s)
        n_ueber = int((t.umsatz >= t.umsatz_plan).sum())
        zeige(D.monate_ist_plan(t),
              T(f"{n_ueber} von {len(t)} Monaten liegen über Plan; in Summe {L.proz(k['umsatz_abw'])} "
                f"({L.geld(k['umsatz'] - k['umsatz_plan'])}).",
                f"{n_ueber} of {len(t)} months are above plan; in total {L.proz(k['umsatz_abw'])} "
                f"({L.geld(k['umsatz'] - k['umsatz_plan'])})."))
    with rechts:
        st.subheader(T("Signale", "Signals"))
        for x in L.signale(D_, s):
            signal_box(x)
    sql_zeigen(["01_kennzahlen_plan_ist", "05_kontostand"], s)


def plan_ist():
    s = stichtag
    k = L.kennzahlen(D_, s)
    kopf("Controlling", T("Plan-Ist", "Plan vs. actual"))
    st.caption(T(f"Jahr bis Stichtag {L.datum(s)}. Plan simuliert.", f"Year to {L.datum(s)}. Plan is simulated."))

    st.subheader(T("Woher kommt die DB-I-Abweichung?", "Where does the contribution margin gap come from?"))
    z = L.db_zerlegung(D_, s)
    groesst = max((T("Menge", "volume"), z["menge"]), ("Mix", z["mix"]), (T("Preis/Rabatt", "price/discount"), z["preis"]),
                  key=lambda x: abs(x[1]))
    zeige(D.db_wasserfall(z),
          T(f"DB I liegt {L.geld(abs(z['ist'] - z['plan']))} {'unter' if z['ist'] < z['plan'] else 'über'} Plan; "
            f"den größten Ausschlag gibt der Effekt „{groesst[0]}“ mit {L.geld(groesst[1])}.",
            f"CM I is {L.geld(abs(z['ist'] - z['plan']))} {'below' if z['ist'] < z['plan'] else 'above'} plan; "
            f"the largest driver is the {groesst[0]} effect at {L.geld(groesst[1])}."))
    with st.expander(T("So ist die Zerlegung gerechnet", "How the breakdown is calculated")):
        st.markdown(T(
            "Segmente = Region × Kategorie.  \n"
            "**Menge:** (Umsatz Ist − Umsatz Plan) × Plan-Marge gesamt  \n"
            "**Mix:** Verschiebung zwischen Segmenten mit unterschiedlicher Plan-Marge  \n"
            "**Preis/Rabatt:** Umsatz Ist × (Marge Ist − Marge Plan) je Segment  \n"
            "Die drei Effekte ergeben zusammen genau die Abweichung.",
            "Segments = region × category.  \n"
            "**Volume:** (actual revenue − plan revenue) × overall plan margin  \n"
            "**Mix:** shift between segments with different plan margins  \n"
            "**Price/discount:** actual revenue × (actual margin − plan margin) per segment  \n"
            "Together the three effects add up exactly to the gap."))

    rp = L.rabatt_profil(D_, s)
    h = rp[rp.rabattstufe == "> 20 %"].set_index("zeitraum")
    st.subheader(T("Rabatte", "Discounts"))
    zeige(D.rabatt_stufen(rp),
          T(f"Aufträge mit mehr als 20 % Rabatt kosten {L.geld(-h.db1['Ist'])} DB I "
            f"(Vorjahr {L.geld(-h.db1['Vorjahr'])}) – bei nur {L.proz(h.anteil['Ist'], False)} des Umsatzes.",
            f"Orders with more than 20% discount cost {L.geld(-h.db1['Ist'])} of CM I "
            f"(prior year {L.geld(-h.db1['Vorjahr'])}) – on only {L.proz(h.anteil['Ist'], False)} of revenue."))

    a, b = st.columns(2) if not MANDANT else (None, st.container())
    if a is not None:
      with a:
        st.subheader(T("Regionen", "Regions"))
        reg = L.plan_ist_nach(D_, s, "region")
        w = reg.iloc[0]
        zeige(D.abweichung_balken(reg, "region", T("Umsatz je Region gegen Plan", "Revenue by region vs. plan")),
              T(f"{w.region} liegt am weitesten hinter Plan ({L.proz(w.abw_proz)}); "
                f"{reg.iloc[-1].region} am weitesten davor ({L.proz(reg.iloc[-1].abw_proz)}).",
                f"{w.region} is furthest behind plan ({L.proz(w.abw_proz)}); "
                f"{reg.iloc[-1].region} is furthest ahead ({L.proz(reg.iloc[-1].abw_proz)})."))
    with b:
        st.subheader(T("Kategorien", "Categories"))
        kat = L.plan_ist_nach(D_, s, "kategorie")
        zeige(D.abweichung_balken(kat, "kategorie", T("Umsatz je Kategorie gegen Plan", "Revenue by category vs. plan")),
              T(f"{kat.iloc[-1].kategorie} trägt das Plus ({L.proz(kat.iloc[-1].abw_proz)}), "
                f"{kat.iloc[0].kategorie} bleibt mit {L.proz(kat.iloc[0].abw_proz)} am schwächsten.",
                f"{kat.iloc[-1].kategorie} drives the upside ({L.proz(kat.iloc[-1].abw_proz)}), "
                f"{kat.iloc[0].kategorie} is weakest at {L.proz(kat.iloc[0].abw_proz)}."))

    st.subheader(T("Fixkosten", "Fixed costs"))
    ZR = {"4": T("letzte 4 Monate", "last 4 months"), "ytd": T("Jahr bis Stichtag", "year to date")}
    zeitraum = st.radio(T("Zeitraum", "Period"), list(ZR), format_func=ZR.get, horizontal=True)
    fx = L.fix_plan_ist(D_, s, 4 if zeitraum == "4" else None)
    top = fx.iloc[0]
    zeige(D.fixkosten_balken(fx, T(f"Fixkosten gegen Plan ({ZR[zeitraum]})", f"Fixed costs vs. plan ({ZR[zeitraum]})"),
                             L.FIX_SIGNAL, L.FIX_SIGNAL_ROT),
          T(f"{top.kostenart} weicht prozentual am stärksten ab ({L.proz(top.abw_proz)}, {L.geld(top.abw)}); "
            f"insgesamt {L.geld(fx.ist.sum())} statt {L.geld(fx.plan.sum())}.",
            f"{S.B(top.kostenart)} deviates most in % ({L.proz(top.abw_proz)}, {L.geld(top.abw)}); "
            f"in total {L.geld(fx.ist.sum())} instead of {L.geld(fx.plan.sum())}."))

    with st.expander(T("Tabelle: Monate Plan-Ist", "Table: months plan vs. actual")):
        t = L.plan_ist_monate(D_, s)
        st.dataframe(pd.DataFrame({
            T("Monat", "Month"): t.monat.map(L.monat), T("Umsatz Ist", "Revenue actual"): t.umsatz.map(L.geld),
            T("Umsatz Plan", "Revenue plan"): t.umsatz_plan.map(L.geld), T("Abw.", "Var."): t.abw_proz.map(L.proz),
            T("DB I Ist", "CM I actual"): t.db1.map(L.geld), T("DB I Plan", "CM I plan"): t.db1_plan.map(L.geld)}),
            hide_index=True, use_container_width=True)
    sql_zeigen(["02_rabattstufen", "03_regionen_plan_ist"], s)


def liquiditaet():
    s = stichtag
    prog = L.liquiditaet_prognose(D_, s)
    kopf("Controlling", T("Liquidität", "Liquidity"))
    st.caption(T("13-Wochen-Vorschau ab Stichtag. Einzahlungen aus offenen Rechnungen (mit bisherigem Kundenverzug) "
                 "und Plan-Umsatz; Auszahlungen für Ware, Versand, Fixkosten laut Plan und Entnahme.",
                 "13-week forecast from the reporting date. Inflows from open invoices (with each customer's past delay) "
                 "and planned revenue; outflows for goods, shipping, planned fixed costs and owner drawings."))
    c = st.columns(4)
    c[0].metric(T("Kontostand Stichtag", "Balance at reporting date"), L.geld(prog["start"]))
    c[1].metric(T("Tiefster Stand (13 W.)", "Lowest point (13 wks)"), L.geld(prog["minimum"]),
                T("heute", "today") if prog["minimum_tag"] == s else L.datum(prog["minimum_tag"]), delta_color="off")
    c[2].metric(T("Stand in 13 Wochen", "Balance in 13 weeks"), L.geld(prog["ende"]),
                delta(prog["ende"] - prog["start"], L.geld(prog["ende"] - prog["start"])))
    c[3].metric(T("Offene Forderungen", "Open receivables"), L.geld(prog["op_summe"]))

    abstand = prog["minimum"] - prog["puffer"]
    if S.en():
        satz = ((f"Over the next 13 weeks the balance does not fall below today's level of {L.geld(prog['minimum'])}; "
                 if prog["minimum_tag"] == s else
                 f"Over the next 13 weeks the balance falls to {L.geld(prog['minimum'])} "
                 f"({L.datum(prog['minimum_tag'])}); ")
                + f"that is {L.geld(abs(abstand))} {'above' if abstand >= 0 else 'below'} the buffer."
                + (f" The account is overdrawn: without a credit line up to {L.geld(-prog['minimum'])} is missing."
                   if prog["minimum"] < 0 else "")
                + (f" Hindsight: it actually ended at {L.geld(prog['tatsaechlich'].iloc[-1])}."
                   if len(prog["tatsaechlich"]) > 80 else ""))
    else:
        satz = ((f"Der Kontostand fällt in den nächsten 13 Wochen nicht unter den heutigen Stand von {L.geld(prog['minimum'])}; "
                 if prog["minimum_tag"] == s else
                 f"Der Kontostand fällt in den nächsten 13 Wochen bis auf {L.geld(prog['minimum'])} "
                 f"({L.datum(prog['minimum_tag'])}); ")
                + f"das sind {L.geld(abs(abstand))} {'über' if abstand >= 0 else 'unter'} dem Puffer."
                + (f" Das Konto ist im Minus: Ohne Kreditlinie fehlen bis zu {L.geld(-prog['minimum'])}."
                   if prog["minimum"] < 0 else "")
                + (f" Rückblick: tatsächlich wurden es {L.geld(prog['tatsaechlich'].iloc[-1])}."
                   if len(prog["tatsaechlich"]) > 80 else ""))
    zeige(D.liquiditaet(prog, s), satz)

    with st.expander(T("Wochenwerte", "Weekly values")):
        w = prog["woche"]
        st.dataframe(pd.DataFrame({
            T("Woche bis", "Week ending"): [L.datum(x) for x in w.index],
            T("Einzahlungen", "Inflows"): w.einzahlungen.map(L.geld),
            T("Auszahlungen", "Outflows"): w.auszahlungen.map(L.geld),
            T("Kontostand", "Balance"): w.kontostand.map(L.geld)}),
            hide_index=True, use_container_width=True)

    st.subheader(T("Zahlungsverhalten", "Payment behaviour"))
    vz = L.verzug_verteilung(D_, s)
    anteil_spaet = (vz > 30).mean()
    zeige(D.verzug_verteilung(vz),
          T(f"Die Hälfte der Rechnungen wird höchstens {L.zahl(vz.median(), 0)} Tage nach Fälligkeit bezahlt, "
            f"aber {L.proz(anteil_spaet, False)} der Rechnungen kommen erst nach mehr als 30 Tagen.",
            f"Half of all invoices are paid at most {L.zahl(vz.median(), 0)} days after the due date, "
            f"but {L.proz(anteil_spaet, False)} of invoices take more than 30 days."))

    a, b = st.columns(2)
    strich = lambda v: "–" if pd.isna(v) else L.zahl(v)
    with a:
        st.subheader(T("Säumige Kunden", "Overdue customers"))
        sk = L.saeumige_kunden(D_, s)
        if sk.empty:
            st.success(T("Keine überfälligen Rechnungen.", "No overdue invoices."))
        else:
            st.dataframe(pd.DataFrame({
                T("Kunde", "Customer"): sk.kunde, "Segment": sk.segment, "Region": sk.region,
                T("Offen", "Open"): sk.offen.map(L.geld), T("Rechn.", "Inv."): sk.rechnungen,
                T("Tage überfällig", "Days overdue"): sk.max_tage,
                T("Ø Verzug vorher", "Avg. delay before"): sk.verzug_vorher.map(strich),
                T("Ø Verzug 6 Mon.", "Avg. delay 6 mo."): sk.verzug_6m.map(strich)}),
                hide_index=True, use_container_width=True)
    with b:
        st.subheader(T("Kunden, die später zahlen als früher", "Customers paying later than before"))
        vt = L.verzug_trend(D_, s)
        vt = vt[vt.delta >= L.VERZUG_SIGNAL_TAGE]
        if vt.empty:
            st.success(T("Kein Kunde zahlt deutlich später als vorher.", "No customer pays notably later than before."))
        else:
            st.dataframe(pd.DataFrame({
                T("Kunde", "Customer"): vt.kunde, "Segment": vt.segment, "Region": vt.hauptregion,
                T("Ø Tage vorher", "Avg. days before"): vt.verzug_vorher.map(L.zahl),
                T("Ø Tage letzte 6 Mon.", "Avg. days last 6 mo."): vt.verzug_6m.map(L.zahl),
                T("Veränderung", "Change"): vt.delta.map(lambda v: "+" + L.zahl(v))}),
                hide_index=True, use_container_width=True)
        op = L.offene_posten(D_, s)
        un = op[op.status == "uneinbringlich"]
        if len(un):
            st.warning(T(f"{len(un)} Rechnungen über {L.geld(un.betrag.sum())} gelten als uneinbringlich.",
                         f"{len(un)} invoices totalling {L.geld(un.betrag.sum())} are considered uncollectible."))
    sql_zeigen(["04_forderungslaufzeit", "06_saeumige_kunden"], s)


def briefing():
    s = stichtag
    kopf(T("Steuern", "Act"), T("Montags-Briefing", "Monday briefing"))
    st.caption(T("Fertige Wochen-E-Mail. „Im E-Mail-Programm öffnen“ legt einen Entwurf in deinem Mailprogramm an; "
                 "du prüfst ihn und schickst ihn selbst ab.",
                 "Ready-made weekly e-mail. “Open in mail app” creates a draft in your mail program; "
                 "you review it and send it yourself."))
    text = L.montags_briefing(D_, s)
    st.text_area(T("E-Mail-Text", "E-mail text"), text, height=560)
    an = st.text_input(T("Empfänger (optional, mehrere mit Komma)", "Recipients (optional, comma-separated)"), "")
    def mailto(t: str) -> str:
        z = t.split("\n")
        betreff, rumpf = z[0].split(": ", 1)[-1], "\n".join(z[2:])
        return (f"mailto:{urllib.parse.quote(an, safe='@,')}?subject={urllib.parse.quote(betreff)}"
                f"&body={urllib.parse.quote(rumpf)}")

    # Viele Mailprogramme unter Windows schneiden mailto-Links ab ca. 2.000 Zeichen ab.
    GRENZE = 1800
    link, kurz = mailto(text), False
    if len(link) > GRENZE:
        link, kurz = mailto(L.montags_briefing(D_, s, kurz=True)), True
    a, b = st.columns(2)
    if len(link) <= GRENZE:
        a.link_button(T("✉️ Im E-Mail-Programm öffnen", "✉️ Open in mail app")
                      + (T(" (Kurzfassung)", " (short version)") if kurz else ""), link, use_container_width=True)
    else:
        a.button(T("✉️ Zu lang für das Mailprogramm", "✉️ Too long for the mail app"), disabled=True, use_container_width=True)
    b.download_button(T("Als Textdatei herunterladen", "Download as text file"), text.encode("utf-8"),
                      file_name=f"briefing_{s:%Y-%m-%d}.txt", mime="text/plain", use_container_width=True)
    if kurz:
        st.caption(T("Der volle Text ist zu lang für die Übergabe ans Mailprogramm. Der Button öffnet deshalb eine "
                     "Kurzfassung (nur Signal-Titel, Top 3 Säumige). Den vollen Text kopierst du oben oder lädst ihn herunter.",
                     "The full text is too long to hand over to the mail app, so the button opens a short version "
                     "(signal titles, top 3 overdue). Copy the full text above or download it."))


# ------------------------------------------------------------------ Schritt 2
def was_waere_wenn():
    s = stichtag
    kopf(T("Steuern", "Act"), T("Was wäre wenn?", "What if?"))
    st.caption(T("Hochrechnung auf ein Jahr mit den Ist-Zahlen der letzten 12 Monate bis Stichtag. "
                 "Alle Hebel stehen am Anfang auf „heute“; stell sie ein, die Diagramme rechnen neu.",
                 "Annualised projection based on the actuals of the last 12 months. "
                 "All levers start at “today”; adjust them and the charts recalculate."))
    with st.container(border=True):
        a, b = st.columns(2)
        with a:
            deckel_an = st.toggle(T("Rabatte deckeln", "Cap discounts"), value=False)
            deckel = st.slider(T("Höchstrabatt", "Maximum discount"), 0, 50, 20, 5, format="%d %%", disabled=not deckel_an) / 100
            verlust = st.slider(T("Davon gehen verloren (Kunden kaufen nicht mehr)", "Share lost (customers stop buying)"),
                                0, 100, 40, 5, format="%d %%", disabled=not deckel_an,
                                help=T("Anteil der Aufträge mit höherem Rabatt, die ohne den Rabatt wegfallen.",
                                       "Share of orders with a higher discount that are lost without it.")) / 100
        with b:
            menge = st.slider(T("Umsatzmenge insgesamt", "Overall sales volume"), -30, 30, 0, 1, format="%+d %%",
                              help=T("Mehr oder weniger Aufträge bei gleicher Marge.", "More or fewer orders at the same margin.")) / 100
            fix = st.slider(T("Fixkosten", "Fixed costs"), -20, 20, 0, 1, format="%+d %%") / 100
            verzug = st.slider(T("Kunden zahlen später/früher", "Customers pay later/earlier"), -15, 30, 0, 1,
                               format=T("%+d Tage", "%+d days"),
                               help=T("Wirkt nur auf die Liquidität, nicht aufs EBIT.", "Affects liquidity only, not EBIT."))
    z = L.szenario(D_, s, deckel if deckel_an else None, verlust if deckel_an else 0.0, menge, fix, verzug)
    b0, n0 = z["basis"], z["szenario"]

    c = st.columns(4)
    c[0].metric(T("Umsatz / Jahr", "Revenue / year"), L.geld(n0["umsatz"]),
                delta(n0["umsatz"] - b0["umsatz"], L.geld(n0["umsatz"] - b0["umsatz"])))
    c[1].metric(T("DB I-Marge", "CM I margin"), L.proz(n0["marge"], False),
                delta(n0['marge'] - b0['marge'], f"{L.zahl((n0['marge'] - b0['marge']) * 100, 1)} " + T("Pp.", "pp")))
    c[2].metric(T("EBIT / Jahr", "EBIT / year"), L.geld(n0["ebit"]),
                delta(n0["ebit"] - b0["ebit"], L.geld(n0["ebit"] - b0["ebit"])))
    c[3].metric(T("Break-even-Umsatz", "Break-even revenue"), L.geld(n0["break_even"]),
                delta(n0["break_even"] - b0["break_even"], L.geld(n0["break_even"] - b0["break_even"])), delta_color="inverse")
    if deckel_an and z["betroffen_n"]:
        st.caption(T(f"Vom Rabatt-Deckel betroffen: {L.zahl(z['betroffen_n'])} Positionen mit "
                     f"{L.proz(z['betroffen_anteil'], False)} des Umsatzes. Annahme: Wareneinsatz und Versand bleiben gleich.",
                     f"Affected by the discount cap: {L.zahl(z['betroffen_n'])} line items with "
                     f"{L.proz(z['betroffen_anteil'], False)} of revenue. Assumption: cost of goods and shipping stay the same."))

    links, rechts = st.columns(2)
    br = z["bruecke"]
    groesster = max(br, key=lambda k: abs(br[k]))
    namen = {"rabatt": T("der Rabatt-Deckel", "the discount cap"), "verlust": T("der Mengenverlust", "the volume loss"),
             "menge": T("die Umsatzmenge", "sales volume"), "fix": T("die Fixkosten", "fixed costs")}
    with links:
        st.subheader(T("EBIT-Brücke", "EBIT bridge"))
        diff = n0["ebit"] - b0["ebit"]
        zeige(D.ebit_bruecke(z),
              T("Mit diesen Hebeln bleibt das EBIT gleich.", "With these levers EBIT stays the same.") if abs(diff) < 1 else
              T(f"Das EBIT {'steigt' if diff > 0 else 'sinkt'} um {L.geld(abs(diff))} auf {L.geld(n0['ebit'])}; "
                f"den größten Anteil hat {namen[groesster]} ({L.geld(br[groesster])}).",
                f"EBIT {'rises' if diff > 0 else 'falls'} by {L.geld(abs(diff))} to {L.geld(n0['ebit'])}; "
                f"the largest share comes from {namen[groesster]} ({L.geld(br[groesster])})."))
    with rechts:
        st.subheader("Break-even")
        gleich = abs(n0['sicherheit'] - b0['sicherheit']) < 0.005
        zeige(D.break_even(z),
              T(f"Ab {L.geld(n0['break_even'])} Umsatz sind die Fixkosten gedeckt. Sicherheitsabstand "
                f"{L.proz(n0['sicherheit'], False, 0)}: So stark darf der Umsatz sinken, bevor Verlust entsteht"
                + ("." if gleich else f" (heute {L.proz(b0['sicherheit'], False, 0)})."),
                f"From {L.geld(n0['break_even'])} of revenue the fixed costs are covered. Safety margin "
                f"{L.proz(n0['sicherheit'], False, 0)}: revenue can fall this much before a loss occurs"
                + ("." if gleich else f" (today {L.proz(b0['sicherheit'], False, 0)}).")))

    st.subheader(T("Liquidität im Szenario", "Liquidity in the scenario"))
    p0 = prognose(s, sw=_sw_key(), m=MANDANT, q=KEY)
    p1 = prognose(s, tuple(sorted((k, round(float(v), 6)) for k, v in z["liq"].items())), sw=_sw_key(), m=MANDANT, q=KEY)
    unveraendert = abs(p1['minimum'] - p0['minimum']) < 1 and abs(p1['ende'] - p0['ende']) < 1
    plus = lambda x: "+" if x >= 0 else ""
    if S.en():
        satz = ((f"Without the scenario the lowest balance in the next 13 weeks is {L.geld(p0['minimum'])}"
                 if unveraendert else
                 f"In the scenario the balance in 13 weeks is {L.geld(p1['ende'])} "
                 f"({plus(p1['ende'] - p0['ende'])}{L.geld(p1['ende'] - p0['ende'])} vs. no scenario). "
                 f"The lowest point is {L.geld(p1['minimum'])}"
                 + (f" ({plus(p1['minimum'] - p0['minimum'])}{L.geld(p1['minimum'] - p0['minimum'])})"
                    if abs(p1['minimum'] - p0['minimum']) >= 1 else ""))
                + f", {'above' if p1['minimum'] >= p1['puffer'] else 'below'} the buffer of {L.geld(p1['puffer'])}.")
    else:
        satz = ((f"Ohne Szenario liegt der tiefste Kontostand der nächsten 13 Wochen bei {L.geld(p0['minimum'])}"
                 if unveraendert else
                 f"Im Szenario steht das Konto in 13 Wochen bei {L.geld(p1['ende'])} "
                 f"({plus(p1['ende'] - p0['ende'])}{L.geld(p1['ende'] - p0['ende'])} gegenüber ohne Szenario). "
                 f"Der tiefste Stand liegt bei {L.geld(p1['minimum'])}"
                 + (f" ({plus(p1['minimum'] - p0['minimum'])}{L.geld(p1['minimum'] - p0['minimum'])})"
                    if abs(p1['minimum'] - p0['minimum']) >= 1 else ""))
                + f" und damit {'über' if p1['minimum'] >= p1['puffer'] else 'unter'} dem Puffer von {L.geld(p1['puffer'])}.")
    zeige(D.liq_vergleich(p0, p1, s), satz)

    with st.expander(T("Szenario als Maßnahme übernehmen", "Turn the scenario into an action")):
        teile = ([T(f"Rabatte auf {L.proz(deckel, False, 0)} deckeln", f"Cap discounts at {L.proz(deckel, False, 0)}")]
                 if deckel_an else []) + \
                ([T(f"Umsatzmenge {L.proz(menge, nachkomma=0)}", f"Sales volume {L.proz(menge, nachkomma=0)}")] if menge else []) + \
                ([T(f"Fixkosten {L.proz(fix, nachkomma=0)}", f"Fixed costs {L.proz(fix, nachkomma=0)}")] if fix else [])
        titel = st.text_input(T("Titel", "Title"), "; ".join(teile) or T("Szenario", "Scenario"))
        if st.button(T("Als Maßnahme anlegen", "Create action"), type="primary"):
            M.anlegen(titel, "Szenario", n0["ebit"] - b0["ebit"],
                      notiz=T(f"EBIT-Effekt laut Szenario bei {L.proz(verlust, False, 0)} Mengenverlust",
                              f"EBIT effect per scenario at {L.proz(verlust, False, 0)} volume loss"), quelle="Was wäre wenn?")
            st.success(T("Angelegt. Du findest sie unter Maßnahmen.", "Created. You'll find it under Actions."))
            st.toast(T("Maßnahme angelegt", "Action created"), icon="✅")


def fruehwarnung():
    s = stichtag
    kopf(T("Steuern", "Act"), T("Frühwarnung", "Early warning"))
    if msg := st.session_state.pop("toast", None):
        st.toast(msg, icon="✅")
    sw = L.schwellen()
    with st.expander(T("⚙️ Schwellen einstellen", "⚙️ Set thresholds"), expanded=False):
        a, b = st.columns(2)
        gelb = a.number_input(T("Ampel rot ab … % unter Plan", "Traffic light red from … % below plan"),
                              1.0, 30.0, -sw["AMPEL_GELB"] * 100, 0.5, format="%.1f")
        puffer = a.number_input(T("Liquiditätspuffer in Monaten (Fixkosten + Entnahme)",
                                  "Liquidity buffer in months (fixed costs + owner drawings)"),
                                0.5, 6.0, sw["PUFFER_MONATE"], 0.5, format="%.1f")
        fx = b.number_input(T("Fixkosten-Signal ab … % über Plan", "Fixed-cost signal from … % above plan"),
                            1.0, 50.0, sw["FIX_SIGNAL"] * 100, 1.0, format="%.0f")
        fx_rot = b.number_input(T("… rot ab … % über Plan", "… red from … % above plan"),
                                2.0, 100.0, sw["FIX_SIGNAL_ROT"] * 100, 1.0, format="%.0f")
        vz = b.number_input(T("Kunde zahlt … Tage später als früher", "Customer pays … days later than before"),
                            5, 90, int(sw["VERZUG_SIGNAL_TAGE"]), 1)
        x, y = st.columns(2)
        darf = ROLLE != "mandant" and not DEMO
        if DEMO:
            st.caption(T("In der Online-Demo sind die Schwellen fest, damit alle Besucher dasselbe sehen. "
                         "Lokal gestartet lassen sie sich speichern.",
                         "In the online demo the thresholds are fixed so every visitor sees the same thing. "
                         "When run locally they can be saved."))
        elif not darf:
            st.caption(T("Die Schwellen legt dein Berater fest; du kannst sie hier nur ansehen.",
                         "Your advisor sets the thresholds; you can only view them here."))
        if x.button(T("Speichern", "Save"), type="primary", use_container_width=True, disabled=not darf):
            neu = {"AMPEL_GELB": -gelb / 100, "PUFFER_MONATE": puffer, "FIX_SIGNAL": fx / 100,
                   "FIX_SIGNAL_ROT": max(fx_rot, fx) / 100, "VERZUG_SIGNAL_TAGE": int(vz)}
            EINST.write_text(json.dumps(neu, indent=2), encoding="utf-8")
            L.setze_schwellen(neu)
            st.rerun()
        if y.button(T("Auf Standard zurücksetzen", "Reset to defaults"), use_container_width=True, disabled=not darf):
            EINST.unlink(missing_ok=True)
            L.setze_schwellen(L.SCHWELLEN_STANDARD)
            st.rerun()
    st.caption(T(f"Aktiv: Ampel gelb bis {L.proz(L.AMPEL_GELB, nachkomma=1)}, Fixkosten ab {L.proz(L.FIX_SIGNAL, nachkomma=0)} "
                 f"(rot ab {L.proz(L.FIX_SIGNAL_ROT, nachkomma=0)}), Zahlungsverzug +{L.VERZUG_SIGNAL_TAGE} Tage, "
                 f"Puffer {L.zahl(L.PUFFER_MONATE, 1)} Monat(e).",
                 f"Active: amber down to {L.proz(L.AMPEL_GELB, nachkomma=1)}, fixed costs from {L.proz(L.FIX_SIGNAL, nachkomma=0)} "
                 f"(red from {L.proz(L.FIX_SIGNAL_ROT, nachkomma=0)}), payment delay +{L.VERZUG_SIGNAL_TAGE} days, "
                 f"buffer {L.zahl(L.PUFFER_MONATE, 1)} month(s)."))

    t = signal_verlauf(s, sw=_sw_key(), m=MANDANT, q=KEY).copy()
    t["summe"] = t.rot + t.gelb
    vor = t.summe.iloc[:-3].mean() if len(t) > 3 else t.summe.mean()
    jetzt = t.summe.iloc[-3:].mean()
    lage = (T("verschärft sich", "is getting worse") if jetzt > vor * 1.2 else
            T("entspannt sich", "is easing") if jetzt < vor * 0.8 else T("ist stabil", "is stable"))
    zeige(D.warn_verlauf(t),
          T(f"In den letzten 3 Monaten gab es im Schnitt {L.zahl(jetzt, 1)} Warnsignale je Monat, davor "
            f"{L.zahl(vor, 1)}: die Lage {lage}.",
            f"In the last 3 months there were on average {L.zahl(jetzt, 1)} warning signals per month, before that "
            f"{L.zahl(vor, 1)}: the situation {lage}."))

    st.subheader(T(f"Signale zum {L.datum(s)}", f"Signals as of {L.datum(s)}"))
    vorhanden = set(M.laden().quelle.dropna())
    for i, x in enumerate(L.signale(D_, s)):
        a, b = st.columns([6, 1])
        with a:
            signal_box(x)
        if x.stufe != "grün":
            schl = f"Signal: {x.id}"
            if schl in vorhanden:
                b.caption(T("✅ Maßnahme angelegt", "✅ Action created"))
            elif b.button(T("➕ Maßnahme", "➕ Action"), key=f"sig{i}", use_container_width=True):
                M.anlegen(x.titel, x.bereich, 0.0, notiz=x.text, quelle=schl, faellig=date.today() + timedelta(days=14))
                st.session_state["toast"] = T(f"Maßnahme „{x.titel}“ angelegt – fällig in 14 Tagen. Siehe Maßnahmen.",
                                              f"Action “{x.titel}” created – due in 14 days. See Actions.")
                st.rerun()


BEREICHE = ["Marge", "Umsatz", "Region", "Fixkosten", "Forderungen", "Liquidität", "Szenario", "Sonstiges"]


def massnahmen_seite():
    kopf(T("Steuern", "Act"), T("Maßnahmen", "Actions"))
    t = M.laden()
    k = M.kennzahlen(t)
    c = st.columns(4)
    c[0].metric(T("Offen / in Arbeit", "Open / in progress"), k["aktiv"])
    c[1].metric(T("Überfällig", "Overdue"), k["ueberfaellig"])
    c[2].metric(T("Erledigt", "Done"), k["erledigt"])
    c[3].metric(T("Erwarteter EBIT-Effekt (offen)", "Expected EBIT effect (open)"), L.geld(k["effekt_aktiv"]))
    st.caption(T("Direkt in der Tabelle bearbeiten, neue Zeile unten anfügen, dann speichern. "
                 "Fälligkeit gegen das heutige Datum; Maßnahmen entstehen auch aus Signalen (Frühwarnung) und Szenarien.",
                 "Edit directly in the table, add a new row at the bottom, then save. "
                 "Due dates are checked against today; actions are also created from signals (Early warning) and scenarios."))
    if DEMO:
        st.info(T("Online-Demo: Deine Maßnahmen gelten nur in dieser Sitzung und sind für andere Besucher nicht sichtbar.",
                  "Online demo: your actions exist only in this session and are not visible to other visitors."), icon="🔒")
    # Werte bleiben intern deutsch; angezeigt wird in der aktiven Sprache
    zeige_t = t.drop(columns=["id"]).copy()
    status_opt = [S.B(x) for x in M.STATUS]
    bereich_opt = [S.B(x) if x != "Sonstiges" else T("Sonstiges", "Other") for x in BEREICHE]
    zurueck_status = dict(zip(status_opt, M.STATUS))
    zurueck_bereich = dict(zip(bereich_opt, BEREICHE))
    zeige_t["status"] = zeige_t.status.map(lambda v: S.B(v) if v in M.STATUS else v)
    zeige_t["bereich"] = zeige_t.bereich.map(lambda v: bereich_opt[BEREICHE.index(v)] if v in BEREICHE else v)
    ed = st.data_editor(
        zeige_t, num_rows="dynamic", hide_index=True, use_container_width=True, key=f"mass_{S.aktiv()}",
        column_config={
            "titel": st.column_config.TextColumn(T("Maßnahme", "Action"), required=True, width="large"),
            "bereich": st.column_config.SelectboxColumn(T("Bereich", "Area"), options=bereich_opt),
            "verantwortlich": st.column_config.TextColumn(T("Wer", "Owner")),
            "faellig": st.column_config.DateColumn(T("Fällig", "Due"), format=T("DD.MM.YYYY", "YYYY-MM-DD")),
            "status": st.column_config.SelectboxColumn("Status", options=status_opt, required=True, default=status_opt[0]),
            "effekt": st.column_config.NumberColumn(T("Effekt $/Jahr", "Effect $/year"), format="%.0f"),
            "notiz": st.column_config.TextColumn(T("Notiz", "Note"), width="large"),
            "quelle": st.column_config.TextColumn(T("Quelle", "Source"), disabled=True),
            "angelegt": st.column_config.DateColumn(T("Angelegt", "Created"), format=T("DD.MM.YYYY", "YYYY-MM-DD"),
                                                    disabled=True),
        })
    if st.button(T("💾 Speichern", "💾 Save"), type="primary"):
        ed = ed.copy()
        ed["status"] = ed.status.map(lambda v: zurueck_status.get(v, v))
        ed["bereich"] = ed.bereich.map(lambda v: zurueck_bereich.get(v, v))
        M.speichern(ed)
        st.success(T("Gespeichert.", "Saved."))
        st.rerun()
    heute = date.today()
    ueber = t[t.status.isin(["offen", "in Arbeit"]) & t.faellig.notna()]
    ueber = ueber[ueber.faellig < heute]
    if len(ueber):
        st.warning(T("Überfällig: ", "Overdue: ") + "; ".join(
            T(f"{r.titel} (seit {(heute - r.faellig).days} Tagen)", f"{r.titel} ({(heute - r.faellig).days} days)")
            for r in ueber.itertuples()))


def beispiele():
    return [T("Warum liegt der DB I unter Plan, obwohl der Umsatz darüber liegt?",
              "Why is contribution margin below plan although revenue is above?"),
            T("Welche Region sollte ich mir zuerst anschauen und warum?", "Which region should I look at first, and why?"),
            T("Welche drei Maßnahmen bringen am meisten fürs EBIT?", "Which three actions would help EBIT most?"),
            T("Reicht das Geld in den nächsten drei Monaten?", "Will the cash last for the next three months?")]


def ki_fragen():
    s = stichtag
    kopf(T("Steuern", "Act"), T("Frag dein Cockpit", "Ask your cockpit"))
    fakten = ki.faktenzettel(D_, s, M.laden())
    fragen = beispiele()
    if not ki.schluessel():
        st.markdown(T('<span class="badge-modus">🔧 Modus: Beispielantworten, regelbasiert – keine KI angebunden</span>',
                      '<span class="badge-modus">🔧 Mode: example answers, rule-based – no AI connected</span>'),
                    unsafe_allow_html=True)
        if DEMO:
            st.info(T("In der Online-Demo ist keine KI angebunden. Unten siehst du, welche Art Antwort das Fragefeld "
                      "liefert: Die Beispiele werden ohne KI direkt aus den Cockpit-Zahlen erzeugt und stimmen für "
                      "jeden Mandanten und Stichtag.",
                      "No AI is connected in the online demo. Below you can see the kind of answer the question field "
                      "gives: the examples are generated without AI, directly from the cockpit numbers, and are correct "
                      "for every client and reporting date."), icon="💡")
        else:
            st.info(T("Für das KI-Fragefeld brauchst du einen API-Schlüssel von Anthropic. Leg ihn im Terminal fest, "
                      "in dem du die App startest, und starte sie dann neu.\n\n"
                      "**PowerShell** (Standard im VS-Code-Terminal unter Windows):\n\n"
                      "`$env:ANTHROPIC_API_KEY=\"sk-ant-…\"`\n\n"
                      "**Eingabeaufforderung (cmd)**:\n\n`set ANTHROPIC_API_KEY=sk-ant-…`\n\n"
                      "Danach: `python -m streamlit run app.py`. Der Schlüssel gilt nur für dieses Terminalfenster. "
                      "Bis dahin zeigen die Beispiele unten Antworten, die ohne KI aus den Zahlen erzeugt werden.",
                      "The AI question field needs an Anthropic API key. Set it in the terminal you start the app from, "
                      "then restart.\n\n**PowerShell:** `$env:ANTHROPIC_API_KEY=\"sk-ant-…\"`\n\n"
                      "**cmd:** `set ANTHROPIC_API_KEY=sk-ant-…`\n\nThen: `python -m streamlit run app.py`. "
                      "Until then the examples below show answers generated from the numbers without AI."), icon="🔑")
        for i, nr in enumerate((0, 1, 3)):
            with st.expander(fragen[nr], expanded=(i == 0)):
                st.markdown(ki.beispiel_antwort(min(nr, 2), D_, s))
                st.caption(T("Beispielantwort ohne KI, erzeugt aus den Cockpit-Zahlen.",
                             "Example answer without AI, generated from the cockpit numbers."))
        with st.expander(T("Faktenzettel ansehen (das bekäme die KI)", "View the fact sheet (what the AI would receive)")):
            st.code(fakten, language=None)
        return
    st.caption(T(f"Die KI sieht nur den Faktenzettel zum {L.datum(s)} (verdichtete Kennzahlen, Signale, Top-Säumige "
                 f"mit Kundennamen), keine Rohdaten. Modell: {ki.MODELL}. Antworten immer gegenprüfen.",
                 f"The AI only sees the fact sheet as of {L.datum(s)} (aggregated KPIs, signals, top overdue customers "
                 f"by name), no raw data. Model: {ki.MODELL}. Always double-check the answers."))
    if "chat" not in st.session_state or st.session_state.get("chat_tag") != (s, MANDANT, S.aktiv()):
        st.session_state.chat, st.session_state.chat_tag = [], (s, MANDANT, S.aktiv())
    cols = st.columns(len(fragen))
    vorschlag = None
    for c, b in zip(cols, fragen):
        if c.button(b, use_container_width=True):
            vorschlag = b
    for m in st.session_state.chat:
        with st.chat_message(m["role"], avatar="🧭" if m["role"] == "assistant" else "🙂"):
            st.markdown(m["content"])
    eingabe = st.chat_input(T("Frag nach Zahlen, Ursachen oder Maßnahmen …", "Ask about numbers, causes or actions …")) or vorschlag
    if eingabe:
        with st.chat_message("user", avatar="🙂"):
            st.markdown(eingabe)
        with st.chat_message("assistant", avatar="🧭"):
            try:
                with st.spinner(T("Denke nach …", "Thinking …")):
                    antwort = ki.frage(eingabe, fakten, st.session_state.chat[-8:])
                st.markdown(antwort)
                st.session_state.chat += [{"role": "user", "content": eingabe}, {"role": "assistant", "content": antwort}]
            except ki.KIFehler as e:
                st.error(str(e))
    if st.session_state.chat and st.button(T("Verlauf löschen", "Clear history")):
        st.session_state.chat = []
        st.rerun()
    with st.expander(T("Faktenzettel ansehen (das bekommt die KI)", "View the fact sheet (what the AI receives)")):
        st.code(fakten, language=None)


# ------------------------------------------------------------------ Schritt 3: Mandanten und Benchmark
def mandanten_uebersicht():
    s = stichtag
    kopf(T("Berater", "Advisor"), T("Mandanten-Übersicht", "Client overview"))
    pf = portfolio(s, sw=_sw_key(), q=KEY)
    n_rot = int((pf.liq_ampel == "rot").sum())
    schwach = pf.sort_values("umsatz_abw").iloc[0]
    st.markdown(
        f'<div class="lage"><b>{T("Stand", "As of")} {L.datum(s)}:</b> '
        + T(f"{len(pf)} Mandanten, zusammen {L.geld(pf.umsatz.sum())} Umsatz und {L.geld(pf.ebit.sum())} EBIT. "
            f"Am weitesten hinter Plan: <b>Unicorn {schwach.mandant}</b> ({L.proz(schwach.umsatz_abw)}). ",
            f"{len(pf)} clients, together {L.geld(pf.umsatz.sum())} revenue and {L.geld(pf.ebit.sum())} EBIT. "
            f"Furthest behind plan: <b>Unicorn {schwach.mandant}</b> ({L.proz(schwach.umsatz_abw)}). ")
        + (T(f"{n_rot} Mandant(en) mit Liquiditätsampel rot.", f"{n_rot} client(s) with a red liquidity light.") if n_rot else
           T("Kein Mandant mit roter Liquiditätsampel.", "No client with a red liquidity light."))
        + "</div>", unsafe_allow_html=True)

    for _, r in pf.sort_values(["rot", "umsatz_abw"], ascending=[False, True]).iterrows():
        c = st.columns([2.1, 1.9, 1.9, 1.9, 2.4, 1.8])
        c[0].markdown(f"**Unicorn {r.mandant}**  \n{r.rot} {T('rot', 'red')} · {r.gelb} {T('gelb', 'amber')}")
        c[1].markdown(f"{AMPEL_PUNKT[L.ampel(r.umsatz_abw)]} {T('Umsatz', 'Revenue')}  \n**{L.geld(r.umsatz)}** ({L.proz(r.umsatz_abw)})")
        c[2].markdown(f"{AMPEL_PUNKT[L.ampel(r.db1_abw)]} {T('DB I', 'CM I')}  \n**{L.geld(r.db1)}** ({L.proz(r.db1_abw)})")
        ebit_abw = (r.ebit - r.ebit_plan) / abs(r.ebit_plan) if r.ebit_plan else 0
        c[3].markdown(f"{AMPEL_PUNKT[L.ampel(ebit_abw)]} EBIT  \n**{L.geld(r.ebit)}** ({T('Plan', 'plan')} {L.geld(r.ebit_plan)})")
        c[4].markdown(f"{AMPEL_PUNKT[r.liq_ampel]} {T('Konto', 'Cash')}  \n**{L.geld(r.kontostand)}** · "
                      f"{T('Tief 13 Wo.', 'Low 13 wks')} {L.geld(r.liq_min)}")
        if c[5].button(T("Öffnen", "Open"), key=f"oeffne_{r.mandant}",
                       help=T(f"Cockpit von {r.mandant} öffnen", f"Open the {r.mandant} cockpit"), use_container_width=True):
            st.session_state["mandant_s"] = r.mandant
            st.switch_page(SEITE_UEBERBLICK)
        st.caption(T("Dringendstes Signal: ", "Most urgent signal: ") + r.top_signal)
        st.divider()

    st.subheader(T("Mandanten im Vergleich", "Clients compared"))
    best = pf.loc[(pf.ebit - pf.ebit_plan).idxmax()]
    zeige(D.mandanten_lage(pf),
          T(f"Unicorn {schwach.mandant} verfehlt den Umsatzplan am deutlichsten ({L.proz(schwach.umsatz_abw)}); "
            f"Unicorn {best.mandant} übertrifft den EBIT-Plan am stärksten ({L.geld(best.ebit - best.ebit_plan)} darüber).",
            f"Unicorn {schwach.mandant} misses its revenue plan by the most ({L.proz(schwach.umsatz_abw)}); "
            f"Unicorn {best.mandant} beats its EBIT plan by the most ({L.geld(best.ebit - best.ebit_plan)} above)."))
    st.caption(T("Diese Seite sieht nur der Berater. Im Benchmark sehen Mandanten die anderen nur anonym (Mandant A, B, C).",
                 "Only the advisor sees this page. In the benchmark, clients see the others only anonymously (Client A, B, C)."))


def benchmark_seite():
    s = stichtag
    bm = benchmark(s, q=KEY)
    b = L.branche(s.year)
    if MANDANT:
        eigen, name = MANDANT, D_.name
        andere = [m for m in L.mandanten(D_GESAMT) if m != MANDANT]
        namen = {m: T("Mandant ", "Client ") + chr(65 + i) for i, m in enumerate(andere)}
        kopf(f"{name} · " + T("Vergleich", "Comparison"), "Benchmark")
    else:
        eigen, name = "gesamt", T("Unicorn gesamt", "Unicorn total")
        namen = {m: f"Region {m}" for m in L.mandanten(D_GESAMT)}
        kopf("Unicorn · " + T("Vergleich", "Comparison"), "Benchmark")
    von = (s - pd.DateOffset(months=12) + pd.Timedelta(days=1))
    st.caption(T(f"{name}: letzte 12 Monate ({L.datum(von)}–{L.datum(s)}) gegen den deutschen Einzelhandel "
                 f"{b['jahr']} (Bundesbank) und gegen " + ("die anderen Mandanten (anonym)." if MANDANT else "die vier Regionen."),
                 f"{name}: last 12 months ({L.datum(von)}–{L.datum(s)}) vs. German retail {b['jahr']} "
                 f"(Deutsche Bundesbank) and vs. " + ("the other clients (anonymised)." if MANDANT else "the four regions.")))
    if s.year != b["jahr"]:
        st.info(T(f"Für {s.year} liegen keine passenden Branchenwerte vor; verglichen wird mit {b['jahr']}.",
                  f"No industry values are available for {s.year}; comparing with {b['jahr']}."), icon="ℹ️")
    if "wachstum" not in set(bm.kz):
        st.info(T("Umsatzwachstum fehlt: Dafür braucht es 12 volle Vergleichsmonate vor dem Zeitraum. "
                  "Die Daten beginnen 01/2015, Wachstum gibt es deshalb ab Stichtag 12/2016.",
                  "Revenue growth is missing: it needs 12 full comparison months before the period. "
                  "The data starts in Jan 2015, so growth is available from Dec 2016."), icon="ℹ️")
    zeige(D.benchmark_punkte(bm, eigen, namen, name), L.bench_aussage(bm, eigen, name))

    zeilen = []
    for _, r in bm.iterrows():
        einh = T(" Tage", " days") if r.einheit == "Tage" else T(" %", "%")
        f = lambda v: L.zahl(v, 1) + einh
        z = {T("Kennzahl", "KPI"): r.titel, name: f(r[eigen]), T("Branche", "Industry"): f(r.branche),
             (T("Median Mandanten", "Median clients") if MANDANT else T("Median Regionen", "Median regions")): f(r["median"])}
        if MANDANT:
            werte = sorted((r[m] for m in L.mandanten(D_GESAMT)), reverse=r.hoch_gut)
            z[T("Rang", "Rank")] = T(f"{werte.index(r[eigen]) + 1} von {len(werte)}", f"{werte.index(r[eigen]) + 1} of {len(werte)}")
        z[T("besser ist", "better is")] = T("höher", "higher") if r.hoch_gut else T("niedriger", "lower")
        zeilen.append(z)
    st.dataframe(pd.DataFrame(zeilen), hide_index=True, use_container_width=True, height=36 * (len(zeilen) + 1) + 4)

    with st.expander(T("Woher kommen die Branchenwerte, und wie vergleichbar ist das?",
                       "Where do the industry values come from, and how comparable are they?")):
        st.markdown(T(
            f"**Quelle:** {L.BRANCHE_QUELLE}. Hochgerechnete Werte für alle Unternehmen der Branche.  \n"
            "**Rohertragsquote:** bei uns (Umsatz − Wareneinsatz) / Umsatz; Branche: 100 % − Materialaufwand "
            "(in % der Gesamtleistung).  \n"
            "**Personalkostenquote:** Personalkosten / Umsatz. Achtung: Unicorn ist inhabergeführt, der "
            "Unternehmerlohn fehlt in den Personalkosten. Die Quote sieht dadurch besser aus, als sie ist.  \n"
            "**Umsatzrendite:** bei uns EBIT / Umsatz, Branche: Jahresergebnis vor Gewinnsteuern / Umsatz. "
            "Auch hier fehlt bei uns der Unternehmerlohn.  \n"
            "**Forderungslaufzeit:** offene Forderungen am Stichtag / Umsatz × 365; Branche: Forderungen aus "
            "Lieferungen und Leistungen / Umsatz × 365.  \n"
            "**Umsatzwachstum:** letzte 12 Monate gegen die 12 Monate davor; Branche: Jahresumsatz gegen Vorjahr.  \n\n"
            "**Grenzen:** Unicorn ist ein US-Händler mit Werten in Dollar, die Branche ist der deutsche "
            "Einzelhandel in Euro. Quoten sind trotzdem vergleichbar, Beträge nicht. Fixkosten sind bei den "
            "Mandanten per Umlage verteilt; Unterschiede in Personal- und Fixkostenquote kommen daher nur aus "
            "unterschiedlicher Planerfüllung. Plan, Fixkosten und Zahlungsziele sind simuliert.",
            f"**Source:** {L.BRANCHE_QUELLE} (Deutsche Bundesbank, financial statements statistics, extrapolated "
            "figures for all companies in German retail excl. motor vehicles).  \n"
            "**Gross margin:** ours (revenue − cost of goods) / revenue; industry: 100% − cost of materials "
            "(% of total output).  \n"
            "**Staff cost ratio:** staff costs / revenue. Note: Unicorn is owner-managed and the owner's salary "
            "is not in staff costs, so the ratio looks better than it is.  \n"
            "**EBIT margin:** ours EBIT / revenue; industry: profit before income taxes / revenue. The owner's "
            "salary is missing here too.  \n"
            "**Days sales outstanding:** open receivables at the reporting date / revenue × 365; industry: trade "
            "receivables / revenue × 365.  \n"
            "**Revenue growth:** last 12 months vs. the 12 months before; industry: annual revenue vs. prior year.  \n\n"
            "**Limits:** Unicorn is a US retailer reporting in dollars; the industry is German retail in euros. "
            "Ratios are still comparable, amounts are not. Fixed costs are allocated to clients by planned revenue, "
            "so differences in staff and fixed-cost ratios only reflect plan attainment. Plan, fixed costs and "
            "payment terms are simulated."))


# ------------------------------------------------------------------ Schritt 0: Daten aufbereiten
UEBUNG_DATEI = Path(__file__).resolve().parent / "daten" / "uebung" / "unicorn_export_schmutzig.csv"


@st.cache_data(show_spinner=False, max_entries=4)
def _lies(inhalt: bytes, name: str, blatt):
    return BR.lies_datei(inhalt, name, blatt)


@st.cache_data(show_spinner=False, max_entries=4)
def _bereinige(inhalt: bytes, name: str, blatt, zuordnung: tuple, einst: tuple):
    return BR.bereinige(_lies(inhalt, name, blatt), dict(zuordnung), BR.Einstellungen(**dict(einst)))


def _regel(r: str) -> str:
    return T(*BR.REGELN[r])


def _feld(f: str) -> str:
    if f in BR.FELDER:
        return BR.FELDER[f]["de"] if not S.en() else BR.FELDER[f]["en"]
    return f


def _feldliste(text: str) -> str:
    return ", ".join(_feld(x.strip()) if x.strip() in BR.FELDER else x for x in str(text).split(","))


def aufbereitung():
    kopf(T("Schritt 0 · Daten", "Step 0 · Data"), T("Daten aufbereiten", "Prepare data"))
    st.markdown('<div class="lage">' + T(
        "Lade einen Export mit <b>einer Zeile je Bestellposition</b> hoch (CSV oder Excel). Die App erkennt die "
        "Spalten, vereinheitlicht Datum, Zahlen und Schreibweisen und sortiert unbrauchbare Zeilen mit Grund aus. "
        "<b>Nichts wird geschätzt oder aufgefüllt.</b> Jede Änderung steht im Protokoll. Danach rechnet das Cockpit "
        "mit den bereinigten Daten; Plan, Fixkosten und Zahlungen werden wie bei Unicorn simuliert.",
        "Upload an export with <b>one row per order line</b> (CSV or Excel). The app detects the columns, "
        "standardises dates, numbers and spellings and sets aside unusable rows with a reason. "
        "<b>Nothing is estimated or filled in.</b> Every change is logged. The cockpit then runs on the cleaned "
        "data; plan, fixed costs and payments are simulated as for Unicorn.") + "</div>", unsafe_allow_html=True)

    # ---------------------------------------------------------- 1 Datei
    st.subheader(T("1 · Datei wählen", "1 · Choose a file"))
    links, rechts = st.columns([3, 2])
    hoch = links.file_uploader(T("Export hochladen", "Upload export"), type=["csv", "txt", "xlsx", "xlsm", "xls"])
    with rechts:
        st.caption(T("Noch keine eigene Datei? Die Übungsdatei ist der Unicorn-Export mit typischen Fehlern: "
                     "gemischte Datumsformate, Dollarzeichen, Prozentangaben, Dubletten, Leer- und Summenzeilen.",
                     "No file of your own yet? The practice file is the Unicorn export with typical errors: "
                     "mixed date formats, dollar signs, percentages, duplicates, empty and total rows."))
        a, b = st.columns(2)
        if a.button(T("Übungsdatei verwenden", "Use practice file"), use_container_width=True):
            ss.aufb_datei = (UEBUNG_DATEI.name, UEBUNG_DATEI.read_bytes())
        b.download_button(T("Übungsdatei herunterladen", "Download practice file"), UEBUNG_DATEI.read_bytes(),
                          UEBUNG_DATEI.name, "text/csv", use_container_width=True)
    if hoch is not None and ss.get("aufb_hoch_id") != hoch.file_id:      # neue Datei im Upload-Feld
        ss.aufb_hoch_id = hoch.file_id
        ss.aufb_datei = (hoch.name, hoch.getvalue())
    if DEMO:
        st.warning(T("Öffentliche Demo: Bitte **keine echten Kunden- oder Firmendaten** hochladen. Die Datei bleibt "
                     "nur in deiner Sitzung im Arbeitsspeicher und wird nicht gespeichert, läuft aber über einen "
                     f"fremden Server (Streamlit Community Cloud). Höchstens {UPLOAD_MAX_MB} MB.",
                     "Public demo: please **do not upload real customer or company data**. The file stays only in "
                     "your session's memory and is not stored, but it passes through a third-party server "
                     f"(Streamlit Community Cloud). {UPLOAD_MAX_MB} MB at most."), icon="🔒")
    if not ss.get("aufb_datei"):
        st.info(T("Wähle eine Datei oder nimm die Übungsdatei.", "Choose a file or use the practice file."), icon="📄")
        return
    name, inhalt = ss.aufb_datei
    if DEMO and len(inhalt) > UPLOAD_MAX_MB * 1024 * 1024:
        st.error(T(f"Die Datei ist größer als {UPLOAD_MAX_MB} MB. In der Online-Demo ist das die Grenze; "
                   "lokal gestartet gibt es sie nicht.",
                   f"The file is larger than {UPLOAD_MAX_MB} MB. That is the limit in the online demo; "
                   "there is none when run locally."))
        ss.aufb_datei = None
        return
    blatt = 0
    if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        blaetter = BR.excel_blaetter(inhalt)
        blatt = st.selectbox(T("Tabellenblatt", "Sheet"), blaetter) if len(blaetter) > 1 else blaetter[0]
    try:
        roh = _lies(inhalt, name, blatt)
    except Exception as e:  # noqa: BLE001
        st.error(T("Die Datei konnte nicht gelesen werden: ", "The file could not be read: ") + str(e))
        return
    st.caption(T(f"**{name}** · {L.zahl(len(roh))} Zeilen · {len(roh.columns)} Spalten · Quelle bleibt unverändert",
                 f"**{name}** · {L.zahl(len(roh))} rows · {len(roh.columns)} columns · source stays unchanged"))
    with st.expander(T("Vorschau der Originaldatei (erste 20 Zeilen)", "Preview of the original file (first 20 rows)")):
        st.dataframe(roh.head(20), hide_index=True)

    # ---------------------------------------------------------- 2 Zuordnung und Regeln
    st.subheader(T("2 · Spalten zuordnen und Regeln einstellen", "2 · Map columns and set rules"))
    auto = BR.erkenne_spalten(list(roh.columns))
    fehlt_auto = [f for f, d in BR.FELDER.items() if d["pflicht"] and f not in auto]
    KEINE = T("– nicht vorhanden –", "– not available –")
    zuordnung = {}
    with st.expander(T(f"Spaltenzuordnung · {len(auto)} von {len(BR.FELDER)} Feldern automatisch erkannt",
                       f"Column mapping · {len(auto)} of {len(BR.FELDER)} fields detected automatically"),
                     expanded=bool(fehlt_auto)):
        optionen = [KEINE, *roh.columns]
        spalten = st.columns(3)
        for n, (f, d) in enumerate(BR.FELDER.items()):
            wahl = spalten[n % 3].selectbox(_feld(f) + (" *" if d["pflicht"] else ""), optionen,
                                            index=optionen.index(auto[f]) if f in auto else 0,
                                            key=f"zuo_{name}_{f}")
            if wahl != KEINE:
                zuordnung[f] = wahl
        st.caption(T("* Pflichtfeld. Die Erkennung nutzt Namen wie „Order Date“, „Bestelldatum“ oder „auftragsdatum“.",
                     "* Required. Detection uses names like “Order Date”, “Bestelldatum” or “auftragsdatum”."))
    doppelt = {c for c in zuordnung.values() if list(zuordnung.values()).count(c) > 1}
    fehlt = [f for f, d in BR.FELDER.items() if d["pflicht"] and f not in zuordnung]

    c1, c2, c3 = st.columns(3)
    dinfo = BR.datum_reihenfolge([roh[zuordnung[f]] for f, d in BR.FELDER.items()
                                  if d["typ"] == "datum" and f in zuordnung])
    erkannt = {"MDY": T("Monat/Tag", "month/day"), "DMY": T("Tag/Monat", "day/month")}[dinfo["reihenfolge"]]
    schraeg = c1.radio(T("Datum mit Schrägstrich (03/04/2018)", "Dates with slashes (03/04/2018)"),
                       ["auto", "MDY", "DMY"],
                       format_func={"auto": T(f"automatisch (erkannt: {erkannt})", f"automatic (detected: {erkannt})"),
                                    "MDY": T("Monat/Tag (US)", "month/day (US)"),
                                    "DMY": T("Tag/Monat", "day/month")}.get,
                       help=T("Die App sucht Werte, die nur eine Lesart zulassen (13/04 kann nur Tag/Monat sein), "
                              "und wendet die Mehrheit auf Werte wie 03/04 an.",
                              "The app looks for values with only one possible reading (13/04 can only be "
                              "day/month) and applies the majority to values like 03/04."))
    belege = T(f"Belege in der Datei: {L.zahl(dinfo['belege_mdy'])} × nur Monat/Tag möglich, "
               f"{L.zahl(dinfo['belege_dmy'])} × nur Tag/Monat möglich.",
               f"Evidence in the file: {L.zahl(dinfo['belege_mdy'])} × only month/day possible, "
               f"{L.zahl(dinfo['belege_dmy'])} × only day/month possible.")
    if dinfo["belege_mdy"] + dinfo["belege_dmy"] == 0:
        c1.caption(T("Keine eindeutigen Schrägstrich-Daten gefunden; es gilt Monat/Tag. Bitte prüfen.",
                     "No unambiguous slash dates found; month/day is used. Please check."))
    elif not dinfo["eindeutig"]:
        c1.warning(belege + T(" Die Datei mischt beide Reihenfolgen – mehrdeutige Werte werden einzeln gemeldet.",
                              " The file mixes both orders – ambiguous values are listed one by one."))
    elif schraeg not in ("auto", dinfo["reihenfolge"]):
        c1.warning(belege + T(" Deine Einstellung widerspricht der Datei.", " Your setting contradicts the file."))
    else:
        c1.caption(belege)
    dezimal = c2.radio(T("Dezimalzeichen in Zahlen", "Decimal separator"), ["auto", "komma", "punkt"],
                       format_func={"auto": T("automatisch je Spalte", "automatic per column"),
                                    "komma": T("Komma (1.234,50)", "comma (1.234,50)"),
                                    "punkt": T("Punkt (1,234.50)", "point (1,234.50)")}.get)
    innen = c3.toggle(T("Doppelte Leerzeichen im Text zusammenfassen", "Collapse double spaces in text"), value=True)
    dubl = c3.toggle(T("Identische Zeilen entfernen", "Remove identical rows"), value=True)
    faktor = c3.select_slider(T("Ausreißer-Grenze (×IQR, log)", "Outlier fence (×IQR, log)"),
                              [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], 1.5, format_func=lambda v: L.zahl(v, 1),
                              help=T("Tukey-Zaun auf logarithmierten Umsätzen und Mengen. Ausreißer bleiben drin und "
                                     "werden nur markiert.",
                                     "Tukey fence on logged sales and quantities. Outliers stay in and are only flagged."))
    if fehlt or doppelt:
        if fehlt:
            st.error(T("Bitte noch zuordnen: ", "Please map: ") + ", ".join(_feld(f) for f in fehlt))
        if doppelt:
            st.error(T("Mehrfach zugeordnet: ", "Mapped more than once: ") + ", ".join(sorted(doppelt)))
        return
    einst = BR.Einstellungen(datum_schraeg=schraeg, dezimal=dezimal, leerzeichen_innen=innen,
                             dubletten_entfernen=dubl, ausreisser_faktor=float(faktor))
    lauf = (name, len(inhalt), tuple(sorted(zuordnung.items())), tuple(sorted(vars(einst).items())))

    # ---------------------------------------------------------- 3 Bereinigen und prüfen
    st.subheader(T("3 · Bereinigen und Ergebnis prüfen", "3 · Clean and check the result"))
    if st.button(T("🧹 Bereinigung starten", "🧹 Start cleaning"), type="primary"):
        with st.spinner(T("Prüfe und bereinige …", "Checking and cleaning …")):
            try:
                ss.aufb_ergebnis = _bereinige(inhalt, name, blatt, lauf[2], lauf[3])
                ss.aufb_lauf = lauf
            except Exception as e:  # noqa: BLE001
                st.error(T("Bereinigung nicht möglich: ", "Cleaning not possible: ") + str(e))
                return
    if ss.get("aufb_lauf") is None or ss.aufb_lauf[0] != name:
        st.caption(T("Noch nicht gestartet.", "Not started yet."))
        return
    if ss.aufb_lauf != lauf:
        st.warning(T("Zuordnung oder Regeln wurden geändert. Starte die Bereinigung neu, damit das Ergebnis passt.",
                     "Mapping or rules changed. Start cleaning again so the result matches."))
    e: BR.Ergebnis = ss.aufb_ergebnis
    k = e.kennzahlen
    m = st.columns(6)
    m[0].metric(T("Zeilen gelesen", "Rows read"), L.zahl(k["zeilen_gelesen"]))
    m[1].metric(T("übernommen", "kept"), L.zahl(k["zeilen_uebernommen"]))
    m[2].metric(T("ausgeschlossen", "excluded"), L.zahl(k["zeilen_ausgeschlossen"]))
    m[3].metric(T("Werte vereinheitlicht", "Values standardised"), L.zahl(k["werte_geaendert"]))
    m[4].metric(T("Hinweise", "Notes"), L.zahl(k["hinweise"]))
    m[5].metric(T("Werte aufgefüllt", "Values filled in"), L.zahl(k["werte_aufgefuellt"]))
    if k["zeilen_uebernommen"]:
        von, bis = k["zeitraum"]
        st.caption(T(f"Zeitraum {L.datum(von)}–{L.datum(bis)} · Umsatz {L.geld(k['umsatz'])} · DB I {L.geld(k['db1'])}",
                     f"Period {L.datum(von)}–{L.datum(bis)} · sales {L.geld(k['umsatz'])} · profit {L.geld(k['db1'])}"))
    dk = k.get("datum", {})
    if dk.get("mehrdeutig") and "H03" not in set(e.hinweise.regel):
        st.caption(T(f"📅 {L.zahl(dk['mehrdeutig'])} Datumswerte wie 03/04/2018 waren für sich allein mehrdeutig. "
                     f"Die Datei belegt die Reihenfolge eindeutig ({L.zahl(max(dk['belege_mdy'], dk['belege_dmy']))} "
                     "Werte lassen nur eine Lesart zu), deshalb stehen sie nicht einzeln in den Hinweisen.",
                     f"📅 {L.zahl(dk['mehrdeutig'])} dates such as 03/04/2018 were ambiguous on their own. The file "
                     f"settles the order clearly ({L.zahl(max(dk['belege_mdy'], dk['belege_dmy']))} values allow "
                     "only one reading), so they are not listed one by one in the notes."))
    regeln = e.regel_uebersicht()
    if len(regeln):
        quote = k["zeilen_ausgeschlossen"] / max(k["zeilen_gelesen"], 1)
        zeige(D.bereinigung_regeln(regeln, k["zeilen_gelesen"], {r: _regel(r) for r in BR.REGELN}),
              T(f"Von {L.zahl(k['zeilen_gelesen'])} Zeilen gehen {L.zahl(k['zeilen_uebernommen'])} ins Cockpit; "
                f"{L.zahl(k['zeilen_ausgeschlossen'])} ({L.proz(quote, False, 2)}) fallen mit Grund heraus. "
                f"{L.zahl(k['werte_geaendert'])} Werte wurden vereinheitlicht, keiner wurde erfunden.",
                f"Of {L.zahl(k['zeilen_gelesen'])} rows, {L.zahl(k['zeilen_uebernommen'])} go into the cockpit; "
                f"{L.zahl(k['zeilen_ausgeschlossen'])} ({L.proz(quote, False, 2)}) are set aside with a reason. "
                f"{L.zahl(k['werte_geaendert'])} values were standardised, none was made up."))

    t1, t2, t3, t4 = st.tabs([
        T("Qualitätsprofil", "Quality profile"),
        T(f"Geänderte Werte ({L.zahl(len(e.aenderungen))})", f"Changed values ({L.zahl(len(e.aenderungen))})"),
        T(f"Ausgeschlossene Zeilen ({L.zahl(len(e.ausgeschlossen))})", f"Excluded rows ({L.zahl(len(e.ausgeschlossen))})"),
        T(f"Hinweise ({L.zahl(len(e.hinweise))})", f"Notes ({L.zahl(len(e.hinweise))})")])
    with t1:
        p = e.profil.copy()
        p["feld"] = p.feld.map(_feld)
        p["pflicht"] = p.pflicht.map({True: "✓", False: ""})
        st.dataframe(p.rename(columns={
            "feld": T("Feld", "Field"), "quellspalte": T("Spalte in der Datei", "Column in file"),
            "typ": T("Typ", "Type"), "pflicht": T("Pflicht", "Required"), "leer": T("leer", "empty"),
            "nicht_lesbar": T("nicht lesbar", "unreadable"), "geaendert": T("geändert", "changed"),
            "hinweise": T("Hinweise", "notes"), "verschiedene_werte": T("verschiedene Werte", "distinct values"),
            "beispiel": T("Beispiel", "example")}), hide_index=True, use_container_width=True)
        st.caption(T("„leer“ und „nicht lesbar“ zählen in der Originaldatei, „geändert“ und „verschiedene Werte“ "
                     "in den übernommenen Zeilen.",
                     "“empty” and “unreadable” count in the original file, “changed” and “distinct values” in the "
                     "kept rows."))
    with t2:
        a = e.aenderungen.copy()
        f1, f2 = st.columns(2)
        r_wahl = f1.multiselect(T("Regel", "Rule"), sorted(a.regel.unique()), format_func=_regel)
        f_wahl = f2.multiselect(T("Feld", "Field"), sorted(a.feld.unique()), format_func=_feld)
        if r_wahl:
            a = a[a.regel.isin(r_wahl)]
        if f_wahl:
            a = a[a.feld.isin(f_wahl)]
        a["regel"] = a.regel.map(_regel)
        a["feld"] = a.feld.map(_feld)
        st.dataframe(a.rename(columns={"quellzeile": T("Zeile", "Row"), "feld": T("Feld", "Field"),
                                       "vorher": T("vorher", "before"), "nachher": T("nachher", "after"),
                                       "regel": T("Regel", "Rule")}),
                     hide_index=True, use_container_width=True, height=380)
    with t3:
        x = e.ausgeschlossen.copy()
        if len(x):
            x.insert(1, T("Grund", "Reason"), x.regel.map(_regel))
            x["detail"] = x.detail.map(_feldliste)
            x = x.drop(columns="regel").rename(columns={"quellzeile": T("Zeile", "Row"), "detail": T("Detail", "Detail")})
        st.dataframe(x, hide_index=True, use_container_width=True, height=380)
        st.caption(T("Mit allen Originalwerten. „= 123“ heißt: gleich wie Zeile 123.",
                     "With all original values. “= 123” means: same as row 123."))
    with t4:
        h = e.hinweise.copy()
        h["regel"] = h.regel.map(_regel)
        h["feld"] = h.feld.map(_feld)
        st.dataframe(h.rename(columns={"quellzeile": T("Zeile", "Row"), "feld": T("Feld", "Field"),
                                       "wert": T("Wert", "Value"), "regel": T("Hinweis", "Note")}),
                     hide_index=True, use_container_width=True, height=380)
        st.caption(T("Hinweise sind keine Fehler. Die Zeilen bleiben im Cockpit; prüfe sie bei Bedarf in der Quelle.",
                     "Notes are not errors. The rows stay in the cockpit; check them in the source if needed."))

    # ---------------------------------------------------------- 4 Übernehmen und exportieren
    st.subheader(T("4 · Ins Cockpit übernehmen", "4 · Load into the cockpit"))
    if k["zeilen_uebernommen"] == 0:
        st.error(T("Keine Zeile ist übrig geblieben.", "No row is left."))
        return
    if k["zeilen_ausgeschlossen"] / max(k["zeilen_gelesen"], 1) > 0.05:
        st.warning(T("Mehr als 5 % der Zeilen sind ausgeschlossen. Prüfe Zuordnung und Datumsformat, bevor du "
                     "übernimmst.", "More than 5% of rows are excluded. Check mapping and date format before loading."))
    standard = "Unicorn" if name == UEBUNG_DATEI.name else Path(name).stem.replace("_", " ")[:30]
    firma = st.text_input(T("Name der Firma im Cockpit", "Company name in the cockpit"), standard, max_chars=30)
    geprueft = st.checkbox(T("Ich habe ausgeschlossene Zeilen und Hinweise angesehen.",
                             "I have looked at excluded rows and notes."))
    if st.button(T("✅ Ins Cockpit übernehmen", "✅ Load into the cockpit"), type="primary", disabled=not geprueft):
        with st.spinner(T("Baue die Cockpit-Tabellen …", "Building the cockpit tables …")):
            try:
                d, tab = A.cockpit_daten(BR.als_rohexport(e), name=firma.strip() or standard)
                _ = L.stichtage(d)[-1]                         # prüft nur, ob es einen Stichtag gibt (sonst Fehler)
                ss.upload_sqlite = SQL.als_sqlite(tab)          # für „SQL hinter diesen Zahlen“
                ss.upload_dateien = {}                          # Downloads werden erst beim Klick gebaut
            except Exception as ex:  # noqa: BLE001
                st.error(T("Das Cockpit kann mit diesen Daten nicht rechnen. Es braucht mindestens zwei "
                           "Kalenderjahre (Plan = Vorjahr + Wachstum). ",
                           "The cockpit cannot work with this data. It needs at least two calendar years "
                           "(plan = prior year + growth). ") + f"({type(ex).__name__}: {ex})")
                return
        ss.upload_daten, ss.upload_tab, ss.upload_name = d, tab, name
        ss.upload_ergebnis = e
        # Cache-Schlüssel aus dem Inhalt: gleiche Daten -> gleiche Ergebnisse, nie die Daten einer anderen Sitzung
        ss.upload_neu = BR._sha(inhalt + repr(lauf).encode() + d.name.encode())[:16]
        ss.quelle_s = "upload"
        ss.stichtag_s = L.stichtage(d)[-1]
        ss.toast_aufb = T("Übernommen. Das Cockpit rechnet jetzt mit der aufbereiteten Datei.",
                          "Loaded. The cockpit now runs on the prepared file.")
        st.rerun()
    if msg := ss.pop("toast_aufb", None):
        st.success(msg)

    if ss.get("upload_ergebnis") is e:
        st.caption(T("Diese Daten sind übernommen. Wechsel jederzeit in der Seitenleiste unter „Datenquelle“ "
                     "zurück zur SQLite-Datei.",
                     "This data is loaded. Switch back to the SQLite file any time under “Data source” in the sidebar."))
        try:
            vergleich = Q.abgleich({n: getattr(ss.upload_daten, Q.FELD[n]) for n in Q.TABELLEN}, daten_sqlite())
            with st.expander(T("Abgleich mit der SQLite-Datei", "Check against the SQLite file")):
                st.table(vergleich.assign(Zeilen=vergleich["Zeilen"].map(L.zahl)).set_index("Tabelle"))
                st.caption(T("Bei der Übungsdatei sind alle Zahlen identisch. Nur Produktnamen unterscheiden sich, "
                             "weil doppelte und geschützte Leerzeichen zusammengefasst wurden.",
                             "With the practice file all numbers are identical. Only product names differ because "
                             "double and non-breaking spaces were collapsed."))
        except Exception:  # noqa: BLE001 – ohne SQLite-Datei kein Abgleich
            pass
        excel, paket, csv = _download_bauer(ss.setdefault("upload_dateien", {}), e, name, inhalt,
                                            ss.upload_tab, _bericht(e, name))
        x1, x2, x3 = st.columns(3)
        x1.download_button(T("📦 Prüfpaket (ZIP)", "📦 Audit package (ZIP)"), paket,
                           f"{Path(name).stem}_pruefpaket.zip", "application/zip", on_click="ignore",
                           use_container_width=True)
        x2.download_button(T("📊 Excel für Power BI", "📊 Excel for Power BI"), excel,
                           f"{Path(name).stem}_cockpit_powerbi.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", on_click="ignore",
                           use_container_width=True)
        x3.download_button(T("📄 Bereinigte Positionen (CSV)", "📄 Cleaned lines (CSV)"), csv,
                           f"{Path(name).stem}_bereinigt.csv", "text/csv", on_click="ignore",
                           use_container_width=True)
        st.caption(T("Die Dateien werden erst beim Klick erstellt; das Excel braucht ein paar Sekunden.",
                     "Files are built when you click; the Excel takes a few seconds."))
        st.caption(T("Das Prüfpaket enthält bereinigte Daten, ausgeschlossene Zeilen, Änderungsprotokoll, Hinweise, "
                     "Qualitätsprofil, einen Bericht und ein Manifest mit SHA-256-Prüfsumme je Datei.",
                     "The audit package holds cleaned data, excluded rows, change log, notes, quality profile, a "
                     "report and a manifest with a SHA-256 checksum per file."))


@st.cache_data(show_spinner=False)
def daten_sqlite():
    return {n: getattr(L.lade_daten(), Q.FELD[n]) for n in Q.TABELLEN}


def _download_bauer(ablage: dict, e, name: str, inhalt: bytes, tab: dict, bericht: str):
    """Drei Funktionen für st.download_button, die ihre Datei erst beim Klick bauen und in `ablage` merken.

    Streamlit ruft sie in einem eigenen Thread auf; darum alles Nötige hier festhalten statt Session-State lesen.
    """
    def excel() -> bytes:
        if "xlsx" not in ablage:
            puffer = io.BytesIO()
            Q.exportiere_excel({n: tab[n] for n in Q.TABELLEN}, puffer)
            ablage["xlsx"] = puffer.getvalue()
        return ablage["xlsx"]

    def paket() -> bytes:
        schluessel = ("zip", bericht)                   # Bericht hängt von der Sprache ab
        if schluessel not in ablage:
            ablage[schluessel] = BR.pruefpaket(e, name, inhalt, tab, bericht, excel=excel())
        return ablage[schluessel]

    def csv() -> bytes:
        if "csv" not in ablage:
            ablage["csv"] = BR.als_csv(e.sauber)
        return ablage["csv"]

    return excel, paket, csv


def _bericht(e, name: str) -> str:
    k = e.kennzahlen
    von, bis = k["zeitraum"]
    zeilen = [f"# {T('Datenaufbereitung', 'Data preparation')} · {name}", "",
              f"- {T('Zeilen gelesen', 'Rows read')}: {L.zahl(k['zeilen_gelesen'])}",
              f"- {T('übernommen', 'kept')}: {L.zahl(k['zeilen_uebernommen'])}",
              f"- {T('ausgeschlossen', 'excluded')}: {L.zahl(k['zeilen_ausgeschlossen'])}",
              f"- {T('Werte vereinheitlicht', 'Values standardised')}: {L.zahl(k['werte_geaendert'])}",
              f"- {T('Werte aufgefüllt', 'Values filled in')}: 0",
              f"- {T('Zeitraum', 'Period')}: {L.datum(von)}–{L.datum(bis)}",
              f"- {T('Umsatz', 'Sales')}: {L.geld(k['umsatz'])} · DB I: {L.geld(k['db1'])}", "",
              f"## {T('Regeln', 'Rules')}", "", f"| {T('Regel', 'Rule')} | {T('Anzahl', 'Count')} |", "|---|---:|"]
    zeilen += [f"| {r.regel} {_regel(r.regel)} | {L.zahl(r.anzahl)} |" for r in e.regel_uebersicht().itertuples()]
    zeilen += ["", T("Plan, Fixkosten und Zahlungen im Cockpit sind simuliert (siehe daten_dokumentation.md).",
                     "Plan, fixed costs and payments in the cockpit are simulated (see daten_dokumentation.md).")]
    return "\n".join(zeilen)


BERATER_SICHT = modus == "extern" and ROLLE == "berater"
SEITE_UEBERBLICK = st.Page(ueberblick, title=T("Überblick", "Overview"), icon="🧭", default=not BERATER_SICHT,
                           url_path="ueberblick")
lage = [SEITE_UEBERBLICK,
        st.Page(plan_ist, title=T("Plan-Ist", "Plan vs. actual"), icon="📊", url_path="plan_ist"),
        st.Page(liquiditaet, title=T("Liquidität", "Liquidity"), icon="💧", url_path="liquiditaet"),
        st.Page(benchmark_seite, title="Benchmark", icon="📐", url_path="benchmark")]
steuern = [
    st.Page(was_waere_wenn, title=T("Was wäre wenn?", "What if?"), icon="🧪", url_path="was_waere_wenn"),
    st.Page(fruehwarnung, title=T("Frühwarnung", "Early warning"), icon="🚨", url_path="fruehwarnung"),
    st.Page(massnahmen_seite, title=T("Maßnahmen", "Actions"), icon="✅", url_path="massnahmen"),
    st.Page(ki_fragen, title=T("Frag dein Cockpit", "Ask your cockpit")
            + ("" if ki.schluessel() else T(" (Beispiele)", " (examples)")), icon="💬", url_path="ki"),
    st.Page(briefing, title=T("Montags-Briefing", "Monday briefing"), icon="✉️", url_path="briefing"),
]
G_LAGE, G_STEUERN, G_DATEN = T("Lage", "Status"), T("Steuern", "Act"), T("Daten", "Data")
daten_seiten = {} if ROLLE == "mandant" else {G_DATEN: [
    st.Page(aufbereitung, title=T("Daten aufbereiten", "Prepare data"), icon="🧹", url_path="aufbereitung")]}
if BERATER_SICHT:
    seiten = st.navigation({
        **daten_seiten,
        T("Berater", "Advisor"): [st.Page(mandanten_uebersicht, title=T("Mandanten-Übersicht", "Client overview"),
                                          icon="🗂️", default=True, url_path="mandanten")],
        f"{G_LAGE} · {D_.name}": lage,
        G_STEUERN: steuern,
    })
else:
    seiten = st.navigation({**daten_seiten, G_LAGE: lage, G_STEUERN: steuern})
try:
    seiten.run()
except Exception as e:  # noqa: BLE001
    # st.switch_page, st.rerun und st.stop steuern den Ablauf über eigene Ausnahmen: durchlassen
    if type(e).__module__.startswith("streamlit"):
        raise
    seitenfehler(e)
