"""Schritt 0 des Cockpits: hochgeladene Bestellpositionen prüfen und bereinigen.

Ersetzt die Fleißarbeit in Power Query: Spalten erkennen, Text, Datum und Zahlen vereinheitlichen,
Dubletten und unbrauchbare Zeilen aussortieren – nachvollziehbar und ohne Werte zu erfinden.

Grundsätze
- Die Quelldatei bleibt unverändert. Jede Zeile behält ihre Zeilennummer (`quellzeile`).
- Jede Änderung an einem Wert steht im Änderungsprotokoll (vorher, nachher, Regel).
- Nichts wird geschätzt oder aufgefüllt. Fehlt ein Pflichtwert, wird die Zeile ausgeschlossen –
  mit Grund und allen Originalwerten.
- Auffälliges, das kein Fehler sein muss (Ausreißer, unbekannte Kategorien), wird nur markiert.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import aufbau

VERSION = "1.0"

# ---------------------------------------------------------------- Zielschema (Unicorn-Export)
# typ: ganz · text · kategorie · datum · zahl · anteil
FELDER: dict[str, dict] = {
    "order_details_id": dict(de="Positions-ID", en="Line ID", typ="ganz", pflicht=True,
                             syn=["position_id", "positions_id", "row_id", "line_id", "order_line_id",
                                  "order_details_id", "zeilen_id", "id"]),
    "order_id": dict(de="Auftrags-ID", en="Order ID", typ="text", pflicht=True,
                     syn=["auftrag_id", "auftragsnummer", "bestellnummer", "bestell_id", "order_no", "order_number"]),
    "order_date": dict(de="Auftragsdatum", en="Order date", typ="datum", pflicht=True,
                       syn=["auftragsdatum", "bestelldatum", "order_date", "orderdate", "datum"]),
    "shipping_date": dict(de="Versanddatum", en="Ship date", typ="datum", pflicht=True,
                          syn=["versanddatum", "ship_date", "lieferdatum", "shipdate", "shipping_date"]),
    "shipping_mode": dict(de="Versandart", en="Ship mode", typ="kategorie", pflicht=True,
                          syn=["versandart", "ship_mode", "versand", "shipmode"]),
    "shipping_region": dict(de="Region", en="Region", typ="kategorie", pflicht=True, syn=["region", "gebiet"]),
    "shipping_state": dict(de="Bundesstaat", en="State", typ="text", pflicht=False,
                           syn=["bundesstaat", "state", "bundesland", "staat"]),
    "shipping_city": dict(de="Stadt", en="City", typ="text", pflicht=False, syn=["stadt", "city", "ort"]),
    "customer_id": dict(de="Kunden-ID", en="Customer ID", typ="ganz", pflicht=True,
                        syn=["kunde_id", "kunden_id", "kundennummer", "customer_no", "customer_number"]),
    "customer_name": dict(de="Kunde", en="Customer", typ="text", pflicht=False,
                          syn=["kunde", "kundenname", "customer", "name"]),
    "customer_segment": dict(de="Segment", en="Segment", typ="kategorie", pflicht=True,
                             syn=["segment", "kundensegment", "kundengruppe"]),
    "product_id": dict(de="Produkt-ID", en="Product ID", typ="ganz", pflicht=True,
                       syn=["produkt_id", "artikel_id", "artikelnummer", "product_no"]),
    "product_name": dict(de="Produkt", en="Product", typ="text", pflicht=False,
                         syn=["produkt", "produktname", "artikel", "artikelname", "product"]),
    "product_category": dict(de="Kategorie", en="Category", typ="kategorie", pflicht=True,
                             syn=["kategorie", "category", "warengruppe", "produktkategorie"]),
    "product_subcategory": dict(de="Unterkategorie", en="Sub-category", typ="text", pflicht=False,
                                syn=["subkategorie", "unterkategorie", "sub_category", "subcategory"]),
    "quantity": dict(de="Menge", en="Quantity", typ="ganz", pflicht=True, syn=["menge", "anzahl", "stueck", "qty"]),
    "order_discount": dict(de="Rabatt", en="Discount", typ="anteil", pflicht=True,
                           syn=["rabatt", "discount", "nachlass"]),
    "order_sales": dict(de="Umsatz", en="Sales", typ="zahl", pflicht=True,
                        syn=["umsatz", "sales", "erloes", "betrag", "revenue", "netto_umsatz"]),
    "order_profits": dict(de="DB I", en="Profit", typ="zahl", pflicht=True,
                          syn=["db1", "db_i", "gewinn", "profit", "deckungsbeitrag", "profits"]),
}

# Bekannte Schreibweisen je Kategorie (Schlüssel: vereinfachte Form, siehe _schluessel)
KATEGORIEN: dict[str, dict[str, str]] = {
    "shipping_mode": {"standardclass": "Standard Class", "standard": "Standard Class",
                      "secondclass": "Second Class", "2ndclass": "Second Class", "second": "Second Class",
                      "firstclass": "First Class", "1stclass": "First Class", "first": "First Class",
                      "sameday": "Same Day"},
    "shipping_region": {"east": "East", "west": "West", "south": "South", "central": "Central",
                        "ost": "East", "sued": "South", "zentral": "Central", "mitte": "Central"},
    "customer_segment": {"consumer": "Consumer", "corporate": "Corporate", "homeoffice": "Home Office",
                         "privatkunde": "Consumer", "firmenkunde": "Corporate"},
    "product_category": {"furniture": "Furniture", "officesupplies": "Office Supplies",
                         "technology": "Technology", "moebel": "Furniture", "buerobedarf": "Office Supplies",
                         "technik": "Technology"},
}

# Regeln: Kennung -> (Deutsch, Englisch)
REGELN: dict[str, tuple[str, str]] = {
    "R01": ("Leerzeichen und unsichtbare Zeichen bereinigt", "Whitespace and invisible characters cleaned"),
    "R02": ("Kategorie auf einheitliche Schreibweise gebracht", "Category mapped to one spelling"),
    "R03": ("Datum in einheitliches Format gebracht", "Date converted to one format"),
    "R04": ("Zahl lesbar gemacht (Währung, Tausender, Dezimalkomma)", "Number made readable (currency, thousands, decimal comma)"),
    "R05": ("Rabatt von Prozent in Anteil umgerechnet", "Discount converted from percent to share"),
    "R06": ("Schreibweise je ID vereinheitlicht (häufigste Form)", "Spelling unified per ID (most frequent form)"),
    "R07": ("Ganzzahl bereinigt (z. B. 3,0 → 3)", "Whole number cleaned (e.g. 3.0 → 3)"),
    "A01": ("Leerzeile", "Empty row"),
    "A02": ("Summen- oder Fußzeile", "Total or footer row"),
    "A03": ("Pflichtwert fehlt", "Required value missing"),
    "A04": ("Wert nicht lesbar", "Value not readable"),
    "A05": ("Identische Zeile (Dublette)", "Identical row (duplicate)"),
    "A06": ("Positions-ID doppelt mit anderem Inhalt", "Line ID repeated with different content"),
    "A07": ("Menge nicht größer als 0", "Quantity not greater than 0"),
    "A08": ("Umsatz negativ", "Sales negative"),
    "A09": ("Rabatt außerhalb von 0 bis unter 100 %", "Discount outside 0 to below 100%"),
    "A10": ("Versand vor Auftrag", "Shipped before ordered"),
    "H01": ("Statistischer Ausreißer (bleibt drin)", "Statistical outlier (kept)"),
    "H02": ("Unbekannter Kategoriewert (bleibt drin)", "Unknown category value (kept)"),
    "H03": ("Mehrdeutiges Datum, gelesen nach Einstellung", "Ambiguous date, read per setting"),
    "H04": ("Gleiche ID mit verschiedenen Angaben", "Same ID with different details"),
    "H05": ("DB I größer als Umsatz", "Profit greater than sales"),
}


@dataclass
class Einstellungen:
    datum_schraeg: str = "auto"        # 03/04/2018: "auto" (aus der Datei erkannt), "MDY" Monat/Tag, "DMY" Tag/Monat
    dezimal: str = "auto"              # "auto", "komma" oder "punkt"
    leerzeichen_innen: bool = True     # doppelte und geschützte Leerzeichen im Text zu einem
    dubletten_entfernen: bool = True
    ausreisser_faktor: float = 1.5     # Tukey-Zaun auf log-Werten: Q1 − k·IQR bis Q3 + k·IQR


@dataclass
class Ergebnis:
    sauber: pd.DataFrame               # Zielspalten + quellzeile
    ausgeschlossen: pd.DataFrame       # quellzeile, regel, detail, Originalwerte
    aenderungen: pd.DataFrame          # quellzeile, feld, vorher, nachher, regel
    hinweise: pd.DataFrame             # quellzeile, feld, wert, regel
    profil: pd.DataFrame               # je Feld
    zuordnung: dict[str, str]          # Zielfeld -> Quellspalte
    einstellungen: Einstellungen
    kennzahlen: dict = field(default_factory=dict)

    def regel_uebersicht(self) -> pd.DataFrame:
        n = pd.concat([self.aenderungen.regel, self.ausgeschlossen.regel, self.hinweise.regel]).value_counts()
        return pd.DataFrame([{"regel": r, "anzahl": int(n.get(r, 0))} for r in REGELN if n.get(r, 0)])


# ---------------------------------------------------------------- Datei lesen
def lies_datei(inhalt: bytes, dateiname: str, blatt: str | int | None = 0) -> pd.DataFrame:
    """CSV oder Excel als reine Texte einlesen (nichts wird beim Lesen schon umgewandelt)."""
    if dateiname.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(inhalt), sheet_name=blatt or 0, dtype=object, header=0)
        return df.map(_zelle_als_text)
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = inhalt.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    kopf = text.splitlines()[0] if text else ""
    trenner = max([";", ",", "\t", "|"], key=kopf.count)
    return pd.read_csv(io.StringIO(text), sep=trenner, dtype=str, keep_default_na=False,
                       skip_blank_lines=False, quotechar='"')


def excel_blaetter(inhalt: bytes) -> list[str]:
    return list(pd.ExcelFile(io.BytesIO(inhalt)).sheet_names)


def _zelle_als_text(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).strftime("%Y-%m-%d") if pd.Timestamp(v).time().isoformat() == "00:00:00" \
            else pd.Timestamp(v).isoformat(sep=" ")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---------------------------------------------------------------- Spalten erkennen
def _schluessel(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).replace("ß", "ss")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def erkenne_spalten(spalten: list[str]) -> dict[str, str]:
    """Ordnet jedem Zielfeld die passendste Quellspalte zu (Name, Synonyme, dann Ähnlichkeit)."""
    quellen = {_schluessel(c): c for c in spalten}
    zuordnung: dict[str, str] = {}
    vergeben: set[str] = set()
    # 1. exakte Treffer (Feldname, deutscher/englischer Name, Synonyme)
    for feld, f in FELDER.items():
        kandidaten = [feld, f["de"], f["en"], aufbau.ROH_SPALTEN[feld], *f["syn"]]
        for k in map(_schluessel, kandidaten):
            if k in quellen and quellen[k] not in vergeben:
                zuordnung[feld] = quellen[k]
                vergeben.add(quellen[k])
                break
    # 2. Ähnlichkeit für den Rest
    for feld, f in FELDER.items():
        if feld in zuordnung:
            continue
        frei = [k for k, c in quellen.items() if c not in vergeben]
        kandidaten = [_schluessel(x) for x in (feld, f["de"], f["en"], *f["syn"])]
        bester = max(((difflib.SequenceMatcher(None, k, q).ratio(), q) for k in kandidaten for q in frei),
                     default=(0, None))
        if bester[0] >= 0.85:
            zuordnung[feld] = quellen[bester[1]]
            vergeben.add(quellen[bester[1]])
    return zuordnung


# ---------------------------------------------------------------- Werte lesen
_UNSICHTBAR = dict.fromkeys(map(ord, "​‌‍﻿"), None)


def _text(v: str, innen: bool) -> str:
    s = str(v).translate(_UNSICHTBAR)
    if innen:
        s = re.sub(r"[\s ]+", " ", s)
    return s.strip()


_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]00:00(?::00(?:\.0+)?)?)?$")
_PUNKT = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$")
_SCHRAEG = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_JMT = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


def _jahr(j: str) -> int:
    j = int(j)
    return j + (2000 if j < 70 else 1900) if j < 100 else j


def lies_datum(s: str, schraeg: str = "MDY") -> tuple[pd.Timestamp | None, bool]:
    """-> (Datum oder None, mehrdeutig?)"""
    if not s:
        return None, False
    try:
        if m := _ISO.match(s):
            return pd.Timestamp(int(m[1]), int(m[2]), int(m[3])), False
        if m := _PUNKT.match(s):
            return pd.Timestamp(_jahr(m[3]), int(m[2]), int(m[1])), False
        if m := _JMT.match(s):
            return pd.Timestamp(int(m[1]), int(m[2]), int(m[3])), False
        if m := _SCHRAEG.match(s):
            a, b, j = int(m[1]), int(m[2]), _jahr(m[3])
            if a > 12:                      # nur Tag/Monat möglich
                return pd.Timestamp(j, b, a), False
            if b > 12:                      # nur Monat/Tag möglich
                return pd.Timestamp(j, a, b), False
            mehrdeutig = a != b
            return (pd.Timestamp(j, a, b) if schraeg == "MDY" else pd.Timestamp(j, b, a)), mehrdeutig
        if re.fullmatch(r"\d{5}(\.0+)?", s) and 20000 <= float(s) <= 80000:   # Excel-Seriennummer
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(float(s))), False
        t = pd.to_datetime(s, dayfirst=schraeg == "DMY", format="mixed")
        return (None, False) if pd.isna(t) else (t.normalize().tz_localize(None), False)
    except (ValueError, OverflowError, TypeError):
        return None, False


def datum_reihenfolge(spalten: list[pd.Series]) -> dict:
    """Stimmt über alle Datumsspalten ab, ob 03/04/2018 Monat/Tag oder Tag/Monat ist.

    Belege sind Werte, bei denen nur eine Lesart möglich ist (13/04 → Tag/Monat, 04/13 → Monat/Tag).
    -> {"reihenfolge": "MDY"|"DMY", "belege_mdy": n, "belege_dmy": n, "eindeutig": bool}
    """
    mdy = dmy = 0
    for s in spalten:
        m = s.astype(str).str.strip().str.extract(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$").dropna().astype(int)
        dmy += int((m[0] > 12).sum())
        mdy += int((m[1] > 12).sum())
    return {"reihenfolge": "DMY" if dmy > mdy else "MDY", "belege_mdy": mdy, "belege_dmy": dmy,
            "eindeutig": (mdy > 0) != (dmy > 0)}


def _dezimal_stil(werte: pd.Series) -> str:
    """Stimmt je Spalte ab, ob Komma oder Punkt das Dezimalzeichen ist."""
    w = werte[werte != ""]
    komma = w.str.contains(r"(?:^|[^\d])\-?\d+,\d{1,2}(?:\D*$)|\.\d{3},").sum()
    punkt = w.str.contains(r"(?:^|[^\d])\-?\d+\.\d{1,2}(?:\D*$)|,\d{3}\.").sum()
    return "komma" if komma > punkt else "punkt"


def lies_zahl(s: str, stil: str) -> float | None:
    if not s:
        return None
    t = s.strip().replace(" ", "").replace(" ", "").replace("'", "")
    t = re.sub(r"(?i)usd|eur|\$|€|£", "", t)
    neg = False
    if re.fullmatch(r"\(.*\)", t):
        neg, t = True, t[1:-1]
    if t.endswith("-") and not t.startswith("-"):
        neg, t = True, t[:-1]
    t = t.replace("%", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if stil == "komma" or not re.fullmatch(r"-?\d{1,3}(,\d{3})+", t) \
            else t.replace(",", "")
    elif stil == "komma" and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        x = float(t)
    except ValueError:
        return None
    return -x if neg else x


def _ist_standardzahl(s: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", s))


def _texte(s: pd.Series, innen: bool) -> pd.Series:
    """Wie _text, aber für eine ganze Spalte auf einmal."""
    t = s.astype(str).str.translate(_UNSICHTBAR)
    if innen:
        t = t.str.replace(r"[\s ]+", " ", regex=True)
    return t.str.strip()


def _haeufigste(schluessel: list, werte: list) -> dict:
    """Häufigster Wert je Schlüssel; bei Gleichstand der zuerst vorkommende."""
    zaehler: dict = {}
    for k, w in zip(schluessel, werte):
        zaehler.setdefault(k, {})
        zaehler[k][w] = zaehler[k].get(w, 0) + 1          # dict behält die Reihenfolge des ersten Auftretens
    return {k: max(z, key=z.get) for k, z in zaehler.items()}


# ---------------------------------------------------------------- Bereinigen
def bereinige(roh: pd.DataFrame, zuordnung: dict[str, str] | None = None,
              einst: Einstellungen | None = None) -> Ergebnis:
    einst = einst or Einstellungen()
    zuordnung = zuordnung or erkenne_spalten(list(roh.columns))
    fehlend = [f for f, d in FELDER.items() if d["pflicht"] and f not in zuordnung]
    if fehlend:
        raise ValueError("Pflichtspalten nicht zugeordnet: " + ", ".join(fehlend))

    roh = roh.fillna("").astype(str)
    quellzeile = pd.Series(np.arange(len(roh)) + 2, index=roh.index)   # Zeile 1 = Überschrift
    n_zeilen, qz = len(roh), list(range(2, len(roh) + 2))
    aend, hinw = [], []
    werte: dict[str, pd.Series] = {}
    unlesbar: dict[str, pd.Series] = {}
    datum_info = datum_reihenfolge([roh[zuordnung[f]] for f, d in FELDER.items()
                                    if d["typ"] == "datum" and f in zuordnung])
    datum_info["eingestellt"] = einst.datum_schraeg
    schraeg = datum_info["reihenfolge"] if einst.datum_schraeg == "auto" else einst.datum_schraeg
    datum_info["verwendet"] = schraeg
    # Mehrdeutige Werte (03/04) einzeln melden nur, wenn die Datei die Reihenfolge nicht klar belegt
    # oder die Einstellung den Belegen widerspricht. Sonst genügt die Zusammenfassung.
    datum_einzeln = not datum_info["eindeutig"] or schraeg != datum_info["reihenfolge"]
    mehrdeutig_zeilen: list[int] = []

    for feld, f in FELDER.items():
        if feld not in zuordnung:
            werte[feld] = pd.Series(None, index=roh.index, dtype=object)
            unlesbar[feld] = pd.Series(False, index=roh.index)
            continue
        orig_s = roh[zuordnung[feld]].fillna("")
        txt_s = _texte(orig_s, einst.leerzeichen_innen)
        # Ab hier mit einfachen Listen statt Einzelzugriffen auf pandas – gleiche Regeln, viel schneller
        orig, txt = orig_s.tolist(), txt_s.tolist()
        bad = [False] * n_zeilen

        if f["typ"] == "text":
            for i in range(n_zeilen):
                if txt[i] != orig[i] and txt[i] != "":
                    aend.append((qz[i], feld, orig[i], txt[i], "R01"))
            out = txt_s.where(txt_s != "", None)
        elif f["typ"] == "kategorie":
            bekannt = KATEGORIEN.get(feld, {})
            gefuellt = [i for i in range(n_zeilen) if txt[i] != ""]
            schluessel = {i: _schluessel(txt[i]) for i in gefuellt}
            # häufigste Schreibweise je vereinfachter Form (für unbekannte Werte)
            haeufig = _haeufigste([schluessel[i] for i in gefuellt], [txt[i] for i in gefuellt])
            werte_liste: list = [None] * n_zeilen
            for i in gefuellt:
                k = schluessel[i]
                neu = bekannt.get(k) or haeufig.get(k, txt[i])
                if neu != orig[i]:
                    aend.append((qz[i], feld, orig[i], neu, "R02" if neu != txt[i] else "R01"))
                werte_liste[i] = neu
                if bekannt and k not in bekannt:
                    hinw.append((qz[i], feld, neu, "H02"))
            out = pd.Series(werte_liste, index=roh.index, dtype=object)
        elif f["typ"] == "datum":
            werte_liste = [pd.NaT] * n_zeilen
            for i in range(n_zeilen):
                t = txt[i]
                if t == "":
                    continue
                d, mehrdeutig = lies_datum(t, schraeg)
                if d is None:
                    bad[i] = True
                    continue
                werte_liste[i] = d
                if not _ISO.match(t):
                    aend.append((qz[i], feld, orig[i], d.strftime("%Y-%m-%d"), "R03"))
                if mehrdeutig:
                    mehrdeutig_zeilen.append(qz[i])
                    if datum_einzeln:
                        hinw.append((qz[i], feld, t, "H03"))
            out = pd.Series(pd.to_datetime(werte_liste), index=roh.index).astype("datetime64[ns]")
        else:   # ganz, zahl, anteil
            stil = _dezimal_stil(txt_s) if einst.dezimal == "auto" else einst.dezimal
            werte_liste = [np.nan] * n_zeilen
            for i in range(n_zeilen):
                t = txt[i]
                if t == "":
                    continue
                x = lies_zahl(t, stil)
                if x is None:
                    bad[i] = True
                    continue
                regel = None if _ist_standardzahl(orig[i]) else "R04"
                if f["typ"] == "anteil" and ("%" in t or 1 <= abs(x) <= 100):
                    x, regel = round(x / 100, 10), "R05"
                if f["typ"] == "ganz":
                    if not float(x).is_integer():
                        bad[i] = True
                        continue
                    if regel in (None, "R04") and re.fullmatch(r"-?\d+\.0+", t):
                        regel = "R07"
                werte_liste[i] = x
                if regel:
                    neu = str(int(x)) if f["typ"] == "ganz" or float(x).is_integer() else repr(float(x))
                    aend.append((qz[i], feld, orig[i], neu, regel))
            out = pd.Series(werte_liste, index=roh.index, dtype="float64")
        werte[feld] = out
        unlesbar[feld] = pd.Series(bad, index=roh.index)

    df = pd.DataFrame(werte)
    df.insert(0, "quellzeile", quellzeile)

    # ------------------------------------------------ Zeilen aussortieren (Grund + Originalwerte)
    aus = []   # (index, regel, detail)
    leer = (roh.apply(lambda s: s.str.strip()) == "").all(axis=1)
    fuss = ~leer & df.order_id.isna()
    if fuss.any():   # Summenzeilen erkennen: nur die wenigen Zeilen ohne Bestellnummer durchsuchen
        alle_text = roh[fuss].apply(lambda s: s.str.lower()).agg(" ".join, axis=1)
        fuss &= alle_text.str.contains(r"\b(?:summe|gesamt|total|sum)\b").reindex(roh.index, fill_value=False)
    for i in roh.index[leer]:
        aus.append((i, "A01", ""))
    for i in roh.index[fuss]:
        aus.append((i, "A02", ""))
    raus = leer | fuss
    pflicht = [f for f, d in FELDER.items() if d["pflicht"]]
    ub = pd.DataFrame(unlesbar)[list(FELDER)]
    leer_pflicht = df[pflicht].isna()
    for i in roh.index[~raus & (ub.any(axis=1) | leer_pflicht.any(axis=1))]:
        nicht_lesbar = [f for f in FELDER if ub.at[i, f]]
        if nicht_lesbar:
            aus.append((i, "A04", ", ".join(nicht_lesbar)))
            raus[i] = True
            continue
        fehlt = [f for f in pflicht if leer_pflicht.at[i, f]]
        if fehlt:
            aus.append((i, "A03", ", ".join(fehlt)))
            raus[i] = True
    ok = ~raus
    for regel, maske, detail in (
            ("A07", df.quantity <= 0, "quantity"),
            ("A08", df.order_sales < 0, "order_sales"),
            ("A09", (df.order_discount < 0) | (df.order_discount >= 1), "order_discount"),
            ("A10", df.shipping_date < df.order_date, "shipping_date < order_date")):
        for i in roh.index[ok & maske.fillna(False)]:
            aus.append((i, regel, detail))
            raus[i] = True
        ok = ~raus

    # Dubletten: erst identische Zeilen, dann gleiche Positions-ID mit anderem Inhalt
    felder = list(FELDER)
    if einst.dubletten_entfernen:
        teile = [df.loc[ok, c].map(lambda v: "" if pd.isna(v) else str(v)) for c in felder]
        sig = teile[0].str.cat(teile[1:], sep="␟")
        erste: dict = {}
        for i, s in zip(sig.index, sig.tolist()):
            if s in erste:
                aus.append((i, "A05", f"= {int(quellzeile[erste[s]])}"))
                raus[i] = True
            else:
                erste[s] = i
        ok = ~raus
    pid = df.order_details_id.where(ok)
    for i in roh.index[ok & pid.duplicated(keep="first") & pid.notna()]:
        j = pid[pid == pid[i]].index[0]
        aus.append((i, "A06", f"= {int(quellzeile[j])}"))
        raus[i] = True
    ok = ~raus

    sauber = df[ok].copy()

    # ------------------------------------------------ Schreibweise je ID vereinheitlichen (nur Groß/klein)
    for id_feld, text_felder in (("customer_id", ["customer_name"]),
                                 ("product_id", ["product_name", "product_subcategory"])):
        for tf in text_felder:
            if tf not in zuordnung:
                continue
            s = sauber[[id_feld, tf, "quellzeile"]].dropna()
            ids, texte, zeilen = s[id_feld].tolist(), s[tf].tolist(), s["quellzeile"].tolist()
            schluessel = list(zip(ids, (t.casefold() for t in texte)))
            form = _haeufigste(schluessel, texte)
            neu_liste = [form[k] for k in schluessel]
            for z, alt, neu in zip(zeilen, texte, neu_liste):
                if neu != alt:
                    aend.append((z, tf, alt, neu, "R06"))
            sauber.loc[s.index, tf] = neu_liste

    # ------------------------------------------------ Hinweise (bleiben drin)
    for id_feld, felder_ in (("customer_id", ["customer_name", "customer_segment"]),
                             ("product_id", ["product_name", "product_category"]),
                             ("order_id", ["order_date", "customer_id"])):
        for tf in felder_:
            g = sauber.groupby(id_feld)
            n, erste_zeile = g[tf].nunique(), g["quellzeile"].first()
            for wert in n[n > 1].index:
                hinw.append((int(erste_zeile[wert]), tf, f"{id_feld} {wert}: {int(n[wert])}", "H04"))
    # Ausreißer: Tukey-Zaun auf logarithmierten Werten (Umsätze und Mengen sind stark rechtsschief)
    for feld in ("order_sales", "quantity"):
        x = sauber[feld].astype(float)
        lx = np.log1p(x.clip(lower=0))
        q1, q3 = lx.quantile([.25, .75])
        k = einst.ausreisser_faktor * (q3 - q1)
        for i in sauber.index[(lx < q1 - k) | (lx > q3 + k)]:
            hinw.append((int(sauber.at[i, "quellzeile"]), feld, _fmt(x[i]), "H01"))
    for i in sauber.index[sauber.order_profits > sauber.order_sales]:
        hinw.append((int(sauber.at[i, "quellzeile"]), "order_profits", _fmt(sauber.at[i, "order_profits"]), "H05"))

    # Datentypen wie im Unicorn-Export
    for feld, f in FELDER.items():
        if f["typ"] == "ganz":
            sauber[feld] = sauber[feld].astype("int64")
        elif f["typ"] == "zahl" and len(sauber) and (sauber[feld] % 1 == 0).all():
            sauber[feld] = sauber[feld].astype("int64")      # ganze Beträge bleiben ganzzahlig wie im Export
    sauber = sauber.sort_values("order_details_id", kind="stable").reset_index(drop=True)

    ausgeschlossen = pd.DataFrame(
        [{"quellzeile": int(quellzeile[i]), "regel": r, "detail": d,
          **{c: roh.at[i, c] for c in roh.columns}} for i, r, d in aus]).sort_values("quellzeile") \
        if aus else pd.DataFrame(columns=["quellzeile", "regel", "detail", *roh.columns])
    aenderungen = pd.DataFrame(aend, columns=["quellzeile", "feld", "vorher", "nachher", "regel"])
    # Änderungen an ausgeschlossenen Zeilen gehören nicht ins Protokoll der übernommenen Daten
    aenderungen = aenderungen[aenderungen.quellzeile.isin(sauber.quellzeile)].sort_values(
        ["quellzeile", "feld"], kind="stable").reset_index(drop=True)
    hinweise = pd.DataFrame(hinw, columns=["quellzeile", "feld", "wert", "regel"])
    hinweise = hinweise[hinweise.quellzeile.isin(sauber.quellzeile)].reset_index(drop=True)

    datum_info["mehrdeutig"] = int(pd.Series(mehrdeutig_zeilen, dtype="int64").isin(sauber.quellzeile).sum())
    profil = _profil(roh, df, sauber, zuordnung, unlesbar, aenderungen, hinweise)
    kz = {
        "zeilen_gelesen": int(len(roh)),
        "zeilen_uebernommen": int(len(sauber)),
        "zeilen_ausgeschlossen": int(len(ausgeschlossen)),
        "dubletten": int((ausgeschlossen.regel == "A05").sum()) if len(ausgeschlossen) else 0,
        "werte_geaendert": int(len(aenderungen)),
        "werte_aufgefuellt": 0,
        "hinweise": int(len(hinweise)),
        "ausreisser": int((hinweise.regel == "H01").sum()),
        "zeitraum": (sauber.order_date.min(), sauber.order_date.max()) if len(sauber) else (None, None),
        "umsatz": float(sauber.order_sales.sum()),
        "db1": float(sauber.order_profits.sum()),
        "datum": datum_info,
    }
    return Ergebnis(sauber, ausgeschlossen.reset_index(drop=True), aenderungen, hinweise, profil,
                    zuordnung, einst, kz)


def _fmt(x) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}"


def _profil(roh, df, sauber, zuordnung, unlesbar, aend, hinw) -> pd.DataFrame:
    zeilen = []
    for feld, f in FELDER.items():
        q = zuordnung.get(feld)
        leer = int((roh[q].str.strip() == "").sum()) if q else len(roh)
        zeilen.append({
            "feld": feld, "quellspalte": q or "–", "typ": f["typ"], "pflicht": f["pflicht"],
            "leer": leer, "nicht_lesbar": int(unlesbar[feld].sum()),
            "geaendert": int((aend.feld == feld).sum()),
            "hinweise": int((hinw.feld == feld).sum()),
            "verschiedene_werte": int(sauber[feld].nunique()) if len(sauber) else 0,
            "beispiel": str(sauber[feld].dropna().iloc[0])[:40] if len(sauber) and sauber[feld].notna().any() else "",
        })
    return pd.DataFrame(zeilen)


def als_rohexport(e: Ergebnis) -> pd.DataFrame:
    """Bereinigte Zeilen in den Spalten des Unicorn-Exports (Eingang für aufbau.erzeuge_tabellen)."""
    return e.sauber[list(FELDER)].copy()


# ---------------------------------------------------------------- Übungsdatei
SUPERSTORE_KOPF = {
    "order_details_id": "Row ID", "order_id": "Order ID", "order_date": "Order Date", "shipping_date": "Ship Date",
    "shipping_mode": "Ship Mode", "shipping_region": "Region", "shipping_state": "State", "shipping_city": "City",
    "customer_id": "Customer ID", "customer_name": "Customer Name", "customer_segment": "Segment",
    "product_id": "Product ID", "product_name": "Product Name", "product_category": "Category",
    "product_subcategory": "Sub-Category", "quantity": "Quantity", "order_discount": "Discount",
    "order_sales": "Sales", "order_profits": "Profit",
}


def schmutzig_machen(roh: pd.DataFrame, seed: int = 7) -> tuple[pd.DataFrame, dict]:
    """Baut aus sauberen Positionen eine typische „schmutzige“ Exportdatei.

    Reparierbare Fehler stecken in den echten Zeilen. Unbrauchbare Zeilen kommen zusätzlich dazu,
    sodass nach der Bereinigung wieder genau die Ausgangsdaten übrig bleiben.
    """
    rng = np.random.default_rng(seed)
    r = roh.copy().reset_index(drop=True)
    n = len(r)
    out = pd.DataFrame(index=r.index)
    pick = lambda anteil: rng.random(n) < anteil  # noqa: E731

    out["order_details_id"] = r.order_details_id.astype(str)
    out["order_id"] = r.order_id
    # Datum: gemischte Formate
    def datum(s: pd.Series) -> pd.Series:
        art = rng.choice(["iso", "us", "de", "zeit"], n, p=[.45, .3, .2, .05])
        return pd.Series(np.select(
            [art == "us", art == "de", art == "zeit"],
            [s.dt.strftime("%m/%d/%Y"), s.dt.strftime("%d.%m.%Y"), s.dt.strftime("%Y-%m-%d 00:00:00")],
            s.dt.strftime("%Y-%m-%d")), index=s.index)
    out["order_date"] = datum(r.order_date)
    out["shipping_date"] = datum(r.shipping_date)
    # Kategorien: Groß/klein, Kurzformen, Leerzeichen
    varianten = {"Standard Class": ["Standard", "standard class", "STANDARD CLASS"],
                 "Second Class": ["2nd Class", "second class"], "First Class": ["1st Class", "first class"],
                 "Same Day": ["Same day", "same day"]}
    m = r.shipping_mode.copy()
    for i in m.index[pick(.08)]:
        m[i] = rng.choice(varianten[m[i]])
    out["shipping_mode"] = m
    for feld in ("shipping_region", "customer_segment", "product_category"):
        s = r[feld].copy()
        idx = s.index[pick(.04)]
        s[idx] = [rng.choice([v.lower(), v.upper(), f" {v}", f"{v} "]) for v in s[idx]]
        out[feld] = s
    for feld in ("shipping_state", "shipping_city", "product_subcategory"):
        s = r[feld].copy()
        idx = s.index[pick(.02)]
        s[idx] = [f"  {v}" if k else f"{v}  " for v, k in zip(s[idx], rng.random(len(idx)) < .5)]
        out[feld] = s
    out["customer_id"] = r.customer_id.astype(str)
    # Kundennamen: je Kunde mit mindestens 3 Zeilen höchstens eine Zeile klein geschrieben
    name = r.customer_name.copy()
    mehrfach = r.groupby("customer_id").filter(lambda g: len(g) >= 3)
    for _, g in list(mehrfach.groupby("customer_id"))[::12]:
        name[g.index[1]] = name[g.index[1]].lower()
    out["customer_name"] = name
    out["product_id"] = r.product_id.astype(str)
    out["product_name"] = r.product_name
    # Zahlen: Ganzzahl als 3,0 · Rabatt als Prozent · Umsatz mit Währung und Tausenderpunkt
    q = r.quantity.astype(str)
    komma = pick(.03)
    q[komma] = q[komma] + ".0"
    out["quantity"] = q
    rab = r.order_discount.map(lambda x: f"{x:g}")
    i1, i2 = pick(.25) & (r.order_discount > 0), pick(.05) & (r.order_discount > 0)
    rab[i1] = (r.order_discount[i1] * 100).round().astype(int).astype(str) + "%"
    rab[i2 & ~i1] = (r.order_discount[i2 & ~i1] * 100).round().astype(int).astype(str)
    out["order_discount"] = rab
    s = r.order_sales.astype(str)
    usd, de = pick(.10), pick(.06)
    s[usd] = r.order_sales[usd].map(lambda x: f"${x:,.2f}")
    s[de & ~usd] = r.order_sales[de & ~usd].map(lambda x: f"{x:,.2f} $".replace(",", "§").replace(".", ",")
                                                .replace("§", "."))
    out["order_sales"] = s
    p = r.order_profits.astype(str)
    klammer = pick(.3) & (r.order_profits < 0)
    p[klammer] = r.order_profits[klammer].map(lambda x: f"({abs(x)})")
    out["order_profits"] = p

    # unbrauchbare Zusatzzeilen (Kopien echter Zeilen mit neuer ID)
    max_id = int(r.order_details_id.max())
    extra, nr = [], max_id
    def kopie(**aend):
        nonlocal nr
        nr += 1
        z = out.iloc[int(rng.integers(n))].copy()
        z["order_details_id"] = str(nr)
        for k, v in aend.items():
            z[k] = v
        extra.append(z)
    for _ in range(3):
        kopie(customer_id="")
    for _ in range(3):
        kopie(quantity=str(-int(rng.integers(1, 5))))
    for _ in range(2):
        kopie(shipping_date="2014-01-01")
    for _ in range(2):
        kopie(order_discount="150%")
    for _ in range(2):
        kopie(order_sales="")
    extra.append(pd.Series({c: "" for c in out.columns}))
    summe = pd.Series({c: "" for c in out.columns})
    summe["order_details_id"], summe["order_sales"] = "Summe", f"{r.order_sales.sum()}"
    extra.append(summe)
    dubletten = [out.iloc[int(i)] for i in rng.choice(n, 8, replace=False)]

    zeilen = list(out.itertuples(index=False, name=None))
    for z in extra[:-1] + dubletten:
        zeilen.insert(int(rng.integers(len(zeilen))), tuple(z[c] for c in out.columns))
    zeilen.append(tuple(extra[-1][c] for c in out.columns))   # Summenzeile ganz unten
    schmutzig = pd.DataFrame(zeilen, columns=[SUPERSTORE_KOPF[c] for c in out.columns])
    info = {"zeilen": len(schmutzig), "echte_zeilen": n, "zusatzzeilen": len(extra), "dubletten": len(dubletten)}
    return schmutzig, info


# ---------------------------------------------------------------- Export-Schutz
_FORMEL_START = ("=", "+", "-", "@", "\t", "\r")
_ZAHL = re.compile(r"^[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?$")


def entschaerfe(df: pd.DataFrame) -> pd.DataFrame:
    """Schützt Exporte vor Formel-Einschleusung (CSV/Formula Injection).

    Text, der mit = + - @ oder Tab/Zeilenumbruch beginnt, würde Excel als Formel ausführen.
    Solche Texte bekommen ein vorangestelltes Hochkomma; echte Zahlen wie "-12" bleiben unverändert.
    Nur für Dateien, die das Tool verlassen – die Daten im Cockpit bleiben unberührt.
    """
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(_FORMEL_START)
                                and not _ZAHL.match(v) else v)
    return out


def als_csv(df: pd.DataFrame) -> bytes:
    return entschaerfe(df).to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8-sig")


# ---------------------------------------------------------------- Prüfpaket (ZIP)
def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pruefpaket(e: Ergebnis, quelle_name: str, quelle_bytes: bytes, tabellen: dict | None = None,
               bericht: str = "", excel: bytes | None = None) -> bytes:
    """ZIP mit bereinigten Daten, Prüfberichten und Manifest (SHA-256 je Datei).

    excel: schon erzeugte Power-BI-Datei; spart das zweite Schreiben (dauert sonst mehrere Sekunden).
    """
    import quelle as Q
    dateien: dict[str, bytes] = {}

    def csv(df: pd.DataFrame) -> bytes:
        return als_csv(df)

    dateien["01_bereinigt/positionen_bereinigt.csv"] = csv(e.sauber)
    if excel is None and tabellen:
        puffer = io.BytesIO()
        Q.exportiere_excel({n: tabellen[n] for n in Q.TABELLEN}, puffer)
        excel = puffer.getvalue()
    if excel is not None:
        dateien["01_bereinigt/cockpit_tabellen_powerbi.xlsx"] = excel
    dateien["02_pruefung/ausgeschlossene_zeilen.csv"] = csv(e.ausgeschlossen.assign(
        grund=e.ausgeschlossen.regel.map(lambda r: REGELN[r][0])))
    dateien["02_pruefung/aenderungsprotokoll.csv"] = csv(e.aenderungen.assign(
        regel_text=e.aenderungen.regel.map(lambda r: REGELN[r][0])))
    dateien["02_pruefung/hinweise.csv"] = csv(e.hinweise.assign(
        hinweis=e.hinweise.regel.map(lambda r: REGELN[r][0])))
    dateien["02_pruefung/qualitaetsprofil.csv"] = csv(e.profil)
    dateien["02_pruefung/regeln.csv"] = csv(e.regel_uebersicht().assign(
        beschreibung=lambda x: x.regel.map(lambda r: REGELN[r][0])))
    if bericht:
        dateien["bericht.md"] = bericht.encode("utf-8")
    manifest = {
        "werkzeug": f"Unternehmer-Cockpit · Datenaufbereitung {VERSION}",
        "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quelle": {"datei": quelle_name, "bytes": len(quelle_bytes), "sha256": _sha(quelle_bytes)},
        "einstellungen": asdict(e.einstellungen),
        "zuordnung": e.zuordnung,
        "kennzahlen": {k: (v if not isinstance(v, tuple) else [str(x)[:10] for x in v])
                       for k, v in e.kennzahlen.items()},
        "dateien": {n: {"bytes": len(b), "sha256": _sha(b)} for n, b in dateien.items()},
    }
    dateien["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in dateien.items():
            z.writestr(n, b)
    return puffer.getvalue()
