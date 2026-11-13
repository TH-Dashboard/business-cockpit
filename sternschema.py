"""Sternschema für Power BI: Dimensionen, schlanke Faktentabellen, Beziehungen und ein fertiges Power-BI-Projekt.

Ausgang sind die Cockpit-Tabellen aus quelle.TABELLEN (aus der SQLite-Datei oder nach dem Upload).

    baue_stern(tab)            -> {Tabellenname: DataFrame}, erst Dimensionen, dann Fakten
    beziehungen()              -> DataFrame mit allen Verknüpfungen (Blatt "beziehungen" im Excel)
    exportiere_stern_excel()   -> Excel mit einem Blatt je Tabelle plus "beziehungen"
    projekt_dateien()          -> Power-BI-Projekt (.pbip, TMDL-Modell, Bericht) als {Pfad: Text}
    projekt_zip()              -> ZIP mit Projekt und Excel zum Herunterladen

Aufruf  python sternschema.py  schreibt das Projekt nach powerbi/ und das Excel nach daten/ (aus der SQLite-Datei).
"""
from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path

import pandas as pd

import quelle as Q

PROJEKT = "Unternehmer-Cockpit"
EXCEL_STANDARD = r"C:\Cockpit\unicorn_sternschema.xlsx"
VORLAGE = Path(__file__).with_name("powerbi_vorlage")
_NS = uuid.UUID("5b0e7d1c-2f43-4c6a-9a51-6a3c0d1e7f21")       # feste IDs: gleicher Inhalt -> gleiche Dateien

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# ---------------------------------------------------------------- Tabellen
def _datumsbereich(tab: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    werte = [tab[n][c].dropna() for n in Q.TABELLEN for c in Q.TABELLEN[n]["datum"] if n in tab]
    alle = pd.concat(werte)
    return pd.Timestamp(alle.min().year, 1, 1), pd.Timestamp(alle.max().year, 12, 31)


def dim_datum(von: pd.Timestamp, bis: pd.Timestamp) -> pd.DataFrame:
    """Lückenloser Kalender ganzer Jahre; Grundlage für Vorjahr, YTD und gleitende 12 Monate."""
    d = pd.DataFrame({"datum": pd.date_range(von, bis, freq="D")})
    t = d["datum"].dt
    iso = t.isocalendar()
    return d.assign(
        jahr=t.year.astype("int64"),
        quartal="Q" + t.quarter.astype(str),
        jahr_quartal=t.year.astype(str) + " Q" + t.quarter.astype(str),
        monat_nr=t.month.astype("int64"),
        monatsname=t.month.map(lambda m: MONATE[m - 1]),
        jahr_monat=t.strftime("%Y-%m"),
        monatsanfang=t.to_period("M").dt.to_timestamp(),
        wochentag_nr=(t.dayofweek + 1).astype("int64"),
        wochentag=t.dayofweek.map(lambda w: TAGE[w]),
        kalenderwoche=iso["week"].astype("int64"),
    )


def baue_stern(tab: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Cockpit-Tabellen -> Sternschema. Keine Zeile geht verloren, keine Zahl wird verändert."""
    tab = {n: Q.normalisiere(tab[n], n) for n in Q.TABELLEN}     # gleiche Datentypen für SQLite und Upload
    u = tab["fakt_umsatz"]
    orte = (u[["region", "bundesstaat", "stadt"]].drop_duplicates()
            .sort_values(["region", "bundesstaat", "stadt"]).reset_index(drop=True))
    orte.insert(0, "ort_id", range(1, len(orte) + 1))
    ort_id = u.merge(orte, on=["region", "bundesstaat", "stadt"], how="left", validate="m:1")["ort_id"]
    produkte = (u.groupby("produkt_id", as_index=False)
                .agg(produkt=("produkt", "first"), subkategorie=("subkategorie", "first"),
                     kategorie=("kategorie", "first")))
    regionen = sorted(set(u["region"]) | set(tab["fakt_plan"]["region"]))
    kategorien = sorted(set(u["kategorie"]) | set(tab["fakt_plan"]["kategorie"]))
    von, bis = _datumsbereich(tab)

    umsatz = u.assign(ort_id=ort_id.to_numpy())[
        ["position_id", "auftrag_id", "auftragsdatum", "versanddatum", "kunde_id", "produkt_id", "ort_id",
         "versandart", "rabattstufe", "menge", "rabatt", "listenumsatz", "rabattbetrag", "umsatz",
         "wareneinsatz", "versandkosten", "db1"]]
    r = tab["fakt_rechnungen"]
    rechnungen = r[["auftrag_id", "kunde_id", "rechnungsdatum", "faellig_am", "bezahlt_am", "betrag",
                    "zahlungsziel_tage", "verzug_tage", "status"]]
    return {
        "dim_datum": dim_datum(von, bis),
        "dim_kunde": tab["dim_kunde"].copy(),
        "dim_produkt": produkte,
        "dim_kategorie": pd.DataFrame({"kategorie": kategorien}),
        "dim_ort": orte[["ort_id", "stadt", "bundesstaat", "region"]],
        "dim_region": pd.DataFrame({"region": regionen}),
        "dim_kostenart": pd.DataFrame({"kostenart": sorted(tab["fakt_fixkosten"]["kostenart"].unique())}),
        "fakt_umsatz": umsatz.reset_index(drop=True),
        "fakt_plan": tab["fakt_plan"].copy(),
        "fakt_fixkosten": tab["fakt_fixkosten"].copy(),
        "fakt_rechnungen": rechnungen.reset_index(drop=True),
        "fakt_liquiditaet_tag": tab["fakt_liquiditaet_tag"].copy(),
    }


# ---------------------------------------------------------------- Beziehungen
# (von Tabelle, von Spalte [n-Seite], zu Tabelle, zu Spalte [1-Seite], aktiv, Hinweis)
BEZIEHUNGEN = [
    ("fakt_umsatz", "auftragsdatum", "dim_datum", "datum", True, "Umsatz nach Auftragsdatum"),
    ("fakt_umsatz", "versanddatum", "dim_datum", "datum", False, "inaktiv; bei Bedarf mit USERELATIONSHIP"),
    ("fakt_umsatz", "kunde_id", "dim_kunde", "kunde_id", True, ""),
    ("fakt_umsatz", "produkt_id", "dim_produkt", "produkt_id", True, ""),
    ("fakt_umsatz", "ort_id", "dim_ort", "ort_id", True, ""),
    ("dim_produkt", "kategorie", "dim_kategorie", "kategorie", True, "Schneeflocke: Kategorie filtert Produkte"),
    ("dim_ort", "region", "dim_region", "region", True, "Schneeflocke: Region filtert Orte"),
    ("fakt_plan", "monat", "dim_datum", "datum", True, "Plan je Monatsanfang"),
    ("fakt_plan", "region", "dim_region", "region", True, "Plan-Ist je Region"),
    ("fakt_plan", "kategorie", "dim_kategorie", "kategorie", True, "Plan-Ist je Kategorie"),
    ("fakt_fixkosten", "monat", "dim_datum", "datum", True, "Fixkosten gelten für die ganze Firma, nicht je Region"),
    ("fakt_fixkosten", "kostenart", "dim_kostenart", "kostenart", True, ""),
    ("fakt_rechnungen", "rechnungsdatum", "dim_datum", "datum", True, "Rechnungen nach Rechnungsdatum"),
    ("fakt_rechnungen", "faellig_am", "dim_datum", "datum", False, "inaktiv; bei Bedarf mit USERELATIONSHIP"),
    # bezahlt_am bewusst ohne Beziehung: offene Rechnungen haben kein Zahlungsdatum, ein leerer
    # Schlüssel erzeugt in Power BI eine Zeile "(Blank)" im Kalender. Kennzahlen lesen die Spalte direkt.
    ("fakt_rechnungen", "kunde_id", "dim_kunde", "kunde_id", True, ""),
    ("fakt_liquiditaet_tag", "datum", "dim_datum", "datum", True, ""),
]


def beziehungen() -> pd.DataFrame:
    return pd.DataFrame(
        [(vt, vs, zt, zs, "n:1", "ja" if aktiv else "nein", "einfach (1 → n)", h)
         for vt, vs, zt, zs, aktiv, h in BEZIEHUNGEN],
        columns=["von_tabelle", "von_spalte", "zu_tabelle", "zu_spalte", "kardinalitaet", "aktiv",
                 "filterrichtung", "hinweis"])


def exportiere_stern_excel(stern: dict[str, pd.DataFrame], ziel):
    return Q.exportiere_excel({**stern, "beziehungen": beziehungen()}, ziel)


# ---------------------------------------------------------------- Kennzahlen (DAX)
GELD = r"\$ #,0"
PROZENT = "0.0 %"
# (Tabelle, Name, DAX, Format, Ordner)
KENNZAHLEN = [
    ("fakt_umsatz", "Umsatz gesamt", "SUM ( fakt_umsatz[umsatz] )", GELD, "Ergebnis"),
    ("fakt_umsatz", "Wareneinsatz gesamt", "SUM ( fakt_umsatz[wareneinsatz] )", GELD, "Ergebnis"),
    ("fakt_umsatz", "Versandkosten gesamt", "SUM ( fakt_umsatz[versandkosten] )", GELD, "Ergebnis"),
    ("fakt_umsatz", "DB I", "SUM ( fakt_umsatz[db1] )", GELD, "Ergebnis"),
    ("fakt_umsatz", "Marge", "DIVIDE ( [DB I], [Umsatz gesamt] )", PROZENT, "Ergebnis"),
    ("fakt_umsatz", "Rabatt gesamt", "SUM ( fakt_umsatz[rabattbetrag] )", GELD, "Ergebnis"),
    ("fakt_umsatz", "Aufträge", "DISTINCTCOUNT ( fakt_umsatz[auftrag_id] )", "#,0", "Ergebnis"),
    ("fakt_umsatz", "Umsatz YTD", "TOTALYTD ( [Umsatz gesamt], dim_datum[datum] )", GELD, "Zeitvergleich"),
    ("fakt_umsatz", "Umsatz Vorjahr", "CALCULATE ( [Umsatz gesamt], SAMEPERIODLASTYEAR ( dim_datum[datum] ) )", GELD,
     "Zeitvergleich"),
    ("fakt_umsatz", "Umsatz ggü. Vorjahr %",
     "VAR vj = [Umsatz Vorjahr]\nRETURN IF ( NOT ISBLANK ( vj ), DIVIDE ( [Umsatz gesamt] - vj, vj ) )", PROZENT,
     "Zeitvergleich"),
    ("fakt_umsatz", "Umsatz 12 Monate",
     "VAR letzter = CALCULATE ( MAX ( fakt_umsatz[auftragsdatum] ), REMOVEFILTERS () )\n"
     "VAR stichtag = MIN ( MAX ( dim_datum[datum] ), letzter )\n"
     "RETURN IF ( MIN ( dim_datum[datum] ) <= letzter,\n"
     "    CALCULATE ( [Umsatz gesamt], DATESINPERIOD ( dim_datum[datum], stichtag, -12, MONTH ) ) )", GELD,
     "Zeitvergleich"),
    ("fakt_plan", "Umsatz Plan", "SUM ( fakt_plan[umsatz_plan] )", GELD, "Plan-Ist"),
    ("fakt_plan", "DB I Plan", "SUM ( fakt_plan[db1_plan] )", GELD, "Plan-Ist"),
    ("fakt_plan", "Umsatz Abweichung %",
     # nur Monate mit Ist und Plan vergleichen (Plan reicht ein Jahr weiter als Ist)
     "VAR monate = FILTER ( VALUES ( dim_datum[jahr_monat] ), NOT ISBLANK ( [Umsatz gesamt] ) && NOT ISBLANK ( [Umsatz Plan] ) )\n"
     "VAR ist = CALCULATE ( [Umsatz gesamt], monate )\n"
     "VAR p = CALCULATE ( [Umsatz Plan], monate )\n"
     "RETURN IF ( NOT ISBLANK ( p ), DIVIDE ( ist - p, p ) )", PROZENT, "Plan-Ist"),
    ("fakt_plan", "DB I Abweichung %",
     "VAR monate = FILTER ( VALUES ( dim_datum[jahr_monat] ), NOT ISBLANK ( [DB I] ) && NOT ISBLANK ( [DB I Plan] ) )\n"
     "VAR ist = CALCULATE ( [DB I], monate )\n"
     "VAR p = CALCULATE ( [DB I Plan], monate )\n"
     "RETURN IF ( NOT ISBLANK ( p ), DIVIDE ( ist - p, p ) )", PROZENT, "Plan-Ist"),
    ("fakt_fixkosten", "Fixkosten", "SUM ( fakt_fixkosten[ist] )", GELD, "Ergebnis"),
    ("fakt_fixkosten", "Fixkosten Plan", "SUM ( fakt_fixkosten[plan] )", GELD, "Plan-Ist"),
    ("fakt_fixkosten", "EBIT", "[DB I] - [Fixkosten]", GELD, "Ergebnis"),
    ("fakt_fixkosten", "EBIT Plan", "[DB I Plan] - [Fixkosten Plan]", GELD, "Plan-Ist"),
    ("fakt_rechnungen", "Rechnungsbetrag", "SUM ( fakt_rechnungen[betrag] )", GELD, "Forderungen"),
    ("fakt_rechnungen", "Offene Forderungen",
     "VAR letzter = CALCULATE ( MAX ( fakt_umsatz[auftragsdatum] ), REMOVEFILTERS () )\n"
     "VAR stichtag = MIN ( MAX ( dim_datum[datum] ), letzter )\n"
     "RETURN IF ( MIN ( dim_datum[datum] ) <= letzter,\n"
     "    CALCULATE (\n"
     "        SUM ( fakt_rechnungen[betrag] ),\n"
     "        REMOVEFILTERS ( dim_datum ),\n"
     "        fakt_rechnungen[rechnungsdatum] <= stichtag,\n"
     "        fakt_rechnungen[status] <> \"uneinbringlich\",\n"
     "        ISBLANK ( fakt_rechnungen[bezahlt_am] ) || fakt_rechnungen[bezahlt_am] > stichtag\n"
     "    ) )", GELD, "Forderungen"),
    ("fakt_rechnungen", "Forderungslaufzeit (Tage)",
     "DIVIDE ( [Offene Forderungen], [Umsatz 12 Monate] ) * 365", "0", "Forderungen"),
    ("fakt_rechnungen", "Ø Zahlungsverzug (Tage)",
     "CALCULATE ( AVERAGE ( fakt_rechnungen[verzug_tage] ), fakt_rechnungen[zahlungsziel_tage] > 0 )", "0.0",
     "Forderungen"),
    ("fakt_liquiditaet_tag", "Kontostand Stichtag",
     "LASTNONBLANKVALUE ( dim_datum[datum], SUM ( fakt_liquiditaet_tag[kontostand] ) )", GELD, "Liquidität"),
    ("fakt_liquiditaet_tag", "Einzahlungen gesamt", "SUM ( fakt_liquiditaet_tag[einzahlungen] )", GELD, "Liquidität"),
    ("fakt_liquiditaet_tag", "Auszahlungen",
     "SUM ( fakt_liquiditaet_tag[auszahlungen_ware] ) + SUM ( fakt_liquiditaet_tag[auszahlungen_versand] )"
     " + SUM ( fakt_liquiditaet_tag[auszahlungen_fix] ) + SUM ( fakt_liquiditaet_tag[privatentnahme] )", GELD,
     "Liquidität"),
]

FORMAT = {name: fmt for _, name, _, fmt, _ in KENNZAHLEN}

# Sortierung von Textspalten nach einer Zahlenspalte
SORTIERUNG = {("dim_datum", "monatsname"): "monat_nr", ("dim_datum", "wochentag"): "wochentag_nr"}


# ---------------------------------------------------------------- TMDL
def _id(*teile: str) -> str:
    return str(uuid.uuid5(_NS, "/".join(teile)))


def _name(n: str) -> str:
    """TMDL-Bezeichner: nur einfache Namen ohne Anführungszeichen."""
    return n if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) else "'" + n.replace("'", "''") + "'"


def _typ(s: pd.Series) -> tuple[str, str, str]:
    """(TMDL-Datentyp, Power-Query-Typ, Format) einer Spalte."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return "dateTime", "type date", "dd.MM.yyyy"
    if pd.api.types.is_bool_dtype(s):
        return "boolean", "type logical", ""
    if pd.api.types.is_integer_dtype(s):
        return "int64", "Int64.Type", "0"
    if pd.api.types.is_numeric_dtype(s):
        return "double", "type number", "#,0.00"
    return "string", "type text", ""


def _schluessel(tabelle: str) -> set[str]:
    return {vs for vt, vs, *_ in BEZIEHUNGEN if vt == tabelle} | {zs for _, _, zt, zs, *_ in BEZIEHUNGEN
                                                                  if zt == tabelle}


def _m_quelle(name: str, df: pd.DataFrame) -> str:
    typen = ", ".join(f'{{"{c}", {_typ(df[c])[1]}}}' for c in df.columns)
    return "\n".join([
        "let",
        "    Quelle = Excel.Workbook(File.Contents(ExcelDatei), null, true),",
        f'    Blatt = Quelle{{[Item="{name}",Kind="Sheet"]}}[Data],',
        "    Kopf = Table.PromoteHeaders(Blatt, [PromoteAllScalars=true]),",
        f"    Typen = Table.TransformColumnTypes(Kopf, {{{typen}}})",
        "in",
        "    Typen"])


def _tabelle_tmdl(name: str, df: pd.DataFrame) -> str:
    z = [f"table {_name(name)}", f"\tlineageTag: {_id('t', name)}"]
    if name == "dim_datum":
        z.append("\tdataCategory: Time")
    z.append("")
    for t, m, dax, fmt, ordner in KENNZAHLEN:
        if t != name:
            continue
        zeilen = dax.split("\n")
        if len(zeilen) == 1:
            z.append(f"\tmeasure {_name(m)} = {dax}")
        else:
            z.append(f"\tmeasure {_name(m)} =")
            z += [f"\t\t\t{x}" for x in zeilen]
        z += [f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {ordner}", f"\t\tlineageTag: {_id('m', m)}", ""]
    schl = _schluessel(name)
    for c in df.columns:
        typ, _, fmt = _typ(df[c])
        z.append(f"\tcolumn {_name(c)}")
        z.append(f"\t\tdataType: {typ}")
        if name == "dim_datum" and c == "datum":
            z.append("\t\tisKey")
        if fmt:
            z.append(f"\t\tformatString: {fmt}")
        if name.startswith("fakt_") and c in schl and typ != "dateTime":
            z.append("\t\tisHidden")
        z.append(f"\t\tlineageTag: {_id('c', name, c)}")
        zahl = typ in ("int64", "double") and not (c.endswith("_id") or c.endswith("_nr")
                                                    or c.endswith("_tage") or c in ("jahr", "kalenderwoche"))
        z.append(f"\t\tsummarizeBy: {'sum' if zahl else 'none'}")
        z.append(f"\t\tsourceColumn: {c}")
        if (name, c) in SORTIERUNG:
            z.append(f"\t\tsortByColumn: {SORTIERUNG[(name, c)]}")
        z.append("")
        z.append(f"\t\tannotation SummarizationSetBy = {'Automatic' if zahl else 'User'}")
        if typ == "dateTime":
            z += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        z.append("")
    z += [f"\tpartition {_name(name)} = m", "\t\tmode: import", "\t\tsource ="]
    z += [f"\t\t\t\t{x}" for x in _m_quelle(name, df).split("\n")]
    z += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(z) + "\n"


def _model_tmdl(namen: list[str]) -> str:
    reihenfolge = json.dumps(["ExcelDatei", *namen], ensure_ascii=False)
    return "\n".join([
        "model Model", "\tculture: de-DE", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: de-DE", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
        "", "annotation __PBI_TimeIntelligenceEnabled = 0", "",
        f"annotation PBI_QueryOrder = {reihenfolge}", "",
        'annotation PBI_ProTooling = ["DevMode"]', "",
        *[f"ref table {_name(n)}" for n in namen], ""]) + "\n"


def _expressions_tmdl(excel_pfad: str) -> str:
    return "\n".join([
        f'expression ExcelDatei = "{excel_pfad}" meta [IsParameterQuery=true, Type="Text", '
        'IsParameterQueryRequired=true]',
        f"\tlineageTag: {_id('p', 'ExcelDatei')}", "",
        "\tannotation PBI_NavigationStepName = Navigation", "",
        "\tannotation PBI_ResultType = Text", ""]) + "\n"


def _relationships_tmdl() -> str:
    z = []
    for vt, vs, zt, zs, aktiv, _ in BEZIEHUNGEN:
        z.append(f"relationship {_id('r', vt, vs, zt, zs)}")
        if not aktiv:
            z.append("\tisActive: false")
        z += [f"\tfromColumn: {_name(vt)}.{_name(vs)}", f"\ttoColumn: {_name(zt)}.{_name(zs)}", ""]
    return "\n".join(z) + "\n"


# ---------------------------------------------------------------- Bericht (PBIR)
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"

# ---------------------------------------------------------------- Berichtsstil (Farben wie die Streamlit-App)
STIL = {
    "navy": "#0A2342", "blau": "#1A63B7", "hellblau": "#7DB9FF", "orange": "#F28C28", "grau": "#3D5470",
    "seite": "#E2E8F1", "karte": "#FFFFFF", "rand": "#C3CEDC", "kopf": "#E8EEF6", "zeile": "#F5F8FC",
    "summe": "#FDE6D2", "gruen": "#2E9E5B", "rot": "#D0435E",
}
DATENFARBEN = [STIL["blau"], STIL["orange"], STIL["hellblau"], STIL["gruen"], STIL["navy"], STIL["rot"],
               "#9FB4CC", "#F6B98A"]
THEMA_NAME = "Cockpit_TH.json"
UNTERTITEL = "Unternehmer-Cockpit · TH-Dashboard"

# Raster 1280 x 720: Kopf, Kennzahlreihe, zwei Inhaltsflächen, Navigation
RAND, LUECKE = 24, 16
KOPF_Y, KOPF_H = 16, 64
KPI_Y, KPI_H, KPI_N = 96, 104, 5
INHALT_Y, INHALT_H = 216, 432
NAV_Y, NAV_H = 664, 40
BREITE, HOEHE = 1280, 720

# Seiten: (id, Name, Titel, Filter, Kennzahlen, linke Fläche, rechte Fläche)
# Fläche: (Typ, Titel, Kategorie-Feld(er), Kennzahlen, chronologisch sortieren)
# Region-Filter nur dort, wo alle Zahlen je Region gelten (Fixkosten, Forderungen, Konto gibt es nur gesamt).
J, R = ("dim_datum", "jahr", "Jahr"), ("dim_region", "region", "Region")
QUARTAL = ("dim_datum", "jahr_quartal", "Quartal")    # Quartale statt Monate: wenige Punkte, jede Zahl lesbar
SEITEN = [
    ("ueberblick", "Überblick", "Überblick", [J, R],
     [("fakt_umsatz", "Umsatz gesamt"), ("fakt_umsatz", "DB I"), ("fakt_umsatz", "Marge"),
      ("fakt_umsatz", "Aufträge"), ("fakt_plan", "Umsatz Abweichung %")],
     ("clusteredColumnChart", "Umsatz Ist und Plan je Jahr", [J],
      [("fakt_umsatz", "Umsatz gesamt"), ("fakt_plan", "Umsatz Plan")], True),
     ("clusteredBarChart", "DB I Ist und Plan je Region", [R],
      [("fakt_umsatz", "DB I"), ("fakt_plan", "DB I Plan")], False)),
    ("planist", "Plan-Ist", "Plan und Ist", [J, R],
     [("fakt_plan", "Umsatz Plan"), ("fakt_plan", "Umsatz Abweichung %"), ("fakt_plan", "DB I Plan"),
      ("fakt_plan", "DB I Abweichung %"), ("fakt_umsatz", "Umsatz gesamt")],
     ("tableEx", "Plan-Ist je Kategorie", [("dim_kategorie", "kategorie", "Kategorie")],
      [("fakt_umsatz", "Umsatz gesamt"), ("fakt_plan", "Umsatz Plan"), ("fakt_plan", "Umsatz Abweichung %"),
       ("fakt_plan", "DB I Abweichung %")], False),
     ("clusteredColumnChart", "Umsatz-Abweichung zum Plan je Quartal", [QUARTAL],
      [("fakt_plan", "Umsatz Abweichung %")], True)),
    ("produkte", "Produkte", "Produkte und Kategorien", [J, R],
     [("fakt_umsatz", "Umsatz gesamt"), ("fakt_umsatz", "Wareneinsatz gesamt"), ("fakt_umsatz", "Rabatt gesamt"),
      ("fakt_umsatz", "Marge"), ("fakt_umsatz", "Aufträge")],
     ("tableEx", "Kennzahlen je Kategorie", [("dim_kategorie", "kategorie", "Kategorie")],
      [("fakt_umsatz", "Umsatz gesamt"), ("fakt_umsatz", "DB I"), ("fakt_umsatz", "Marge"),
       ("fakt_umsatz", "Aufträge")], False),
     ("clusteredBarChart", "Umsatz je Unterkategorie", [("dim_produkt", "subkategorie", "Unterkategorie")],
      [("fakt_umsatz", "Umsatz gesamt")], False)),
    ("regionen", "Regionen", "Regionen", [J, R],
     [("fakt_umsatz", "Umsatz gesamt"), ("fakt_umsatz", "DB I"), ("fakt_umsatz", "Marge"),
      ("fakt_plan", "Umsatz Plan"), ("fakt_umsatz", "Aufträge")],
     ("tableEx", "Kennzahlen je Region", [R],
      [("fakt_umsatz", "Umsatz gesamt"), ("fakt_plan", "Umsatz Plan"), ("fakt_umsatz", "DB I"),
       ("fakt_umsatz", "Marge")], False),
     ("clusteredBarChart", "Marge je Region", [R],
      [("fakt_umsatz", "Marge")], False)),
    ("forderungen", "Forderungen", "Forderungen", [J],
     [("fakt_rechnungen", "Rechnungsbetrag"), ("fakt_rechnungen", "Offene Forderungen"),
      ("fakt_rechnungen", "Forderungslaufzeit (Tage)"), ("fakt_rechnungen", "Ø Zahlungsverzug (Tage)"),
      ("fakt_umsatz", "Umsatz 12 Monate")],
     ("tableEx", "Rechnungen nach Status", [("fakt_rechnungen", "status", "Status")],
      [("fakt_rechnungen", "Rechnungsbetrag")], False),
     ("clusteredColumnChart", "Offene Forderungen zum Jahresende", [J],
      [("fakt_rechnungen", "Offene Forderungen")], True)),
    ("liquiditaet", "Liquidität", "Liquidität", [J],
     [("fakt_liquiditaet_tag", "Kontostand Stichtag"), ("fakt_liquiditaet_tag", "Einzahlungen gesamt"),
      ("fakt_liquiditaet_tag", "Auszahlungen"), ("fakt_fixkosten", "Fixkosten"), ("fakt_fixkosten", "EBIT")],
     ("lineChart", "Kontostand je Quartal", [QUARTAL],
      [("fakt_liquiditaet_tag", "Kontostand Stichtag")], True),
     ("clusteredColumnChart", "Ein- und Auszahlungen je Jahr", [J],
      [("fakt_liquiditaet_tag", "Einzahlungen gesamt"), ("fakt_liquiditaet_tag", "Auszahlungen")], True)),
]


def _feld(tabelle: str, name: str, art: str) -> dict:
    return {art: {"Expression": {"SourceRef": {"Entity": tabelle}}, "Property": name}}


def _proj(tabelle: str, name: str, art: str = "Measure", aktiv: bool = False, anzeige: str | None = None) -> dict:
    p = {"field": _feld(tabelle, name, art), "queryRef": f"{tabelle}.{name}", "nativeQueryRef": name}
    if anzeige:
        p["displayName"] = anzeige
    return {**p, "active": True} if aktiv else p


def _an(wert: str) -> dict:
    return {"expr": {"Literal": {"Value": wert}}}


def _farbe(hexwert: str) -> dict:
    return {"solid": {"color": _an(f"'{hexwert}'")}}


def _visual(name: str, x: int, y: int, b: int, h: int, typ: str, abfrage: dict | None = None,
            beschriftung: bool = False, titel: str | None = None, objekte: dict | None = None,
            sortierung: dict | None = None) -> dict:
    v = {"visualType": typ, "drillFilterOtherVisuals": True}
    if abfrage:
        v["query"] = {"queryState": abfrage}
        if sortierung:
            v["query"]["sortDefinition"] = sortierung
    o = dict(objekte or {})
    if beschriftung:
        o["labels"] = [{"properties": {"show": _an("true")}}]
    if o:
        v["objects"] = o
    if titel:
        v["visualContainerObjects"] = {"title": [{"properties": {"show": _an("true"), "text": _an(f"'{titel}'")}}]}
    return {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.13.0/schema.json", "name": name,
            "position": {"x": x, "y": y, "z": 0, "height": h, "width": b, "tabOrder": 0}, "visual": v}


def _titelzeile(text: str) -> dict:
    absaetze = [
        {"textRuns": [{"value": text, "textStyle": {"fontWeight": "bold", "fontSize": "20pt",
                                                     "color": STIL["navy"]}}]},
        {"textRuns": [{"value": UNTERTITEL, "textStyle": {"fontSize": "9pt", "color": STIL["grau"]}}]},
    ]
    return {"general": [{"properties": {"paragraphs": absaetze}}]}


def _flaeche(name: str, x: int, b: int, art: tuple) -> dict:
    typ, titel, kategorien, kennzahlen, chrono = art
    kat = [_proj(t, s, "Column", typ != "tableEx", a) for t, s, a in kategorien]
    werte = [_proj(t, m) for t, m in kennzahlen]
    if typ == "tableEx":
        abfrage = {"Values": {"projections": kat + werte}}
    else:
        abfrage = {"Category": {"projections": kat}, "Y": {"projections": werte}}
    if chrono:      # Zeitachsen links nach rechts
        t, s, _ = kategorien[0]
        sort = {"field": _feld(t, s, "Column"), "direction": "Ascending"}
    else:           # sonst größter Wert zuerst
        t, m = kennzahlen[0]
        sort = {"field": _feld(t, m, "Measure"), "direction": "Descending"}
    sortierung = {"sort": [sort], "isDefaultSort": True}
    objekte = None
    if typ != "tableEx" and all(FORMAT[m] == GELD for _, m in kennzahlen):
        # Geld in Tausend ohne Nachkommastelle: $ 497K statt $ 0,5M, so bleibt jeder Wert unterscheidbar
        objekte = {"labels": [{"properties": {"show": _an("true"), "labelDisplayUnits": _an("1000D"),
                                              "labelPrecision": _an("0L")}}]}
    return _visual(name, x, INHALT_Y, b, INHALT_H, typ, abfrage, beschriftung=typ != "tableEx" and not objekte,
                   titel=titel, objekte=objekte, sortierung=sortierung)


def _seiten_visuals(seite: tuple) -> list[dict]:
    sid, _, titel, filter_, kpis, links, rechts = seite
    innen = BREITE - 2 * RAND
    vis = [_visual("titel", RAND, KOPF_Y, 560, KOPF_H, "textbox", objekte=_titelzeile(titel))]
    fb = 190
    for i, (t, s, a) in enumerate(reversed(filter_)):
        x = BREITE - RAND - (i + 1) * fb - i * LUECKE
        vis.append(_visual(f"filter{a}", x, KOPF_Y, fb, KOPF_H, "slicer",
                           {"Values": {"projections": [_proj(t, s, "Column", True, a)]}},
                           objekte={"data": [{"properties": {"mode": _an("'Dropdown'")}}]}))
    kb = (innen - (KPI_N - 1) * LUECKE) // KPI_N
    for i, (t, m) in enumerate(kpis):
        vis.append(_visual(f"kpi{i + 1}", RAND + i * (kb + LUECKE), KPI_Y, kb, KPI_H, "card",
                           {"Values": {"projections": [_proj(t, m)]}}))
    lb = (innen - LUECKE) // 2
    vis.append(_flaeche("links", RAND, lb, links))
    vis.append(_flaeche("rechts", RAND + lb + LUECKE, innen - lb - LUECKE, rechts))
    vis.append(_visual("navigation", RAND, NAV_Y, innen, NAV_H, "pageNavigator"))
    for i, v in enumerate(vis):
        v["position"]["z"] = v["position"]["tabOrder"] = i * 1000
    return vis


def _bericht_visuals() -> dict[str, list[dict]]:
    """Visuals je Seiten-ID."""
    return {s[0]: _seiten_visuals(s) for s in SEITEN}


def _theme() -> dict:
    """Power-BI-Theme in den Farben der App: grau-blaue Seite, weiße Karten mit runden Ecken, Navy-Schrift."""
    s = STIL

    def f(c):
        return {"solid": {"color": c}}

    karte = {"background": [{"show": True, "color": f(s["karte"]), "transparency": 0}],
             "border": [{"show": True, "color": f(s["rand"]), "radius": 12}],
             "dropShadow": [{"show": True, "color": f(s["navy"]), "position": "Outer", "preset": "Custom",
                             "shadowSpread": 0, "shadowBlur": 14, "angle": 90, "shadowDistance": 4,
                             "transparency": 82}],
             "title": [{"show": True, "fontColor": f(s["navy"]), "fontSize": 12, "bold": True,
                        "fontFamily": "Segoe UI Semibold"}],
             "padding": [{"top": 10, "bottom": 10, "left": 14, "right": 14}],
             "visualHeader": [{"show": False}]}
    ohne = {"background": [{"show": False}], "border": [{"show": False}], "dropShadow": [{"show": False}],
            "title": [{"show": False}], "visualHeader": [{"show": False}],
            "padding": [{"top": 0, "bottom": 0, "left": 0, "right": 0}]}
    tabelle = {"columnHeaders": [{"backColor": f(s["kopf"]), "fontColor": f(s["navy"]), "bold": True,
                                  "fontSize": 10}],
               "values": [{"backColorPrimary": f(s["karte"]), "backColorSecondary": f(s["zeile"]),
                           "fontColorPrimary": f(s["navy"]), "fontColorSecondary": f(s["navy"]), "fontSize": 10}],
               "total": [{"backColor": f(s["summe"]), "fontColor": f(s["navy"]), "bold": True}],
               "grid": [{"gridVertical": False, "gridHorizontal": False, "rowPadding": 4}]}
    achse = {"categoryAxis": [{"labelColor": f(s["grau"]), "fontSize": 10, "showAxisTitle": False}],
             "valueAxis": [{"show": False, "showAxisTitle": False, "gridlineShow": False}],
             "labels": [{"show": True, "color": f(s["navy"]), "fontSize": 11, "fontFamily": "Segoe UI Semibold",
                         "labelPosition": "OutsideEnd"}],
             "legend": [{"show": True, "position": "Top", "labelColor": f(s["grau"]), "fontSize": 10}]}
    return {
        "name": "Cockpit TH", "dataColors": DATENFARBEN, "foreground": s["navy"], "foregroundNeutralSecondary": s["grau"],
        "background": s["karte"], "backgroundLight": s["zeile"], "backgroundNeutral": s["rand"],
        "tableAccent": s["blau"], "good": s["gruen"], "neutral": s["orange"], "bad": s["rot"],
        "maximum": s["blau"], "center": s["hellblau"], "minimum": s["rot"],
        "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "color": s["navy"], "fontSize": 12},
                        "label": {"fontFace": "Segoe UI", "color": s["grau"], "fontSize": 10},
                        "callout": {"fontFace": "Segoe UI Semibold", "color": s["blau"], "fontSize": 26}},
        "visualStyles": {
            "page": {"*": {"background": [{"color": f(s["seite"]), "transparency": 0}],
                           "outspace": [{"color": f(s["seite"]), "transparency": 0}]}},
            "*": {"*": karte},
            "card": {"*": {**karte, "title": [{"show": False}],
                           "labels": [{"color": f(s["blau"]), "fontSize": 24, "labelDisplayUnits": 1,
                                       "fontFamily": "Segoe UI Semibold"}],
                           "categoryLabels": [{"show": True, "color": f(s["grau"]), "fontSize": 11}]}},
            "textbox": {"*": ohne},
            "slicer": {"*": {**karte, "title": [{"show": False}],
                             "header": [{"show": True, "fontColor": f(s["grau"]), "textSize": 10, "bold": True}],
                             "items": [{"fontColor": f(s["navy"]), "textSize": 11}]}},
            "pageNavigator": {"*": {**ohne,
                                    "fill": [{"$id": "default", "show": True, "fillColor": f(s["karte"])},
                                             {"$id": "hover", "fillColor": f(s["kopf"])},
                                             {"$id": "selected", "fillColor": f(s["navy"])}],
                                    "text": [{"$id": "default", "fontColor": f(s["navy"]), "bold": True,
                                              "fontSize": 11},
                                             {"$id": "selected", "fontColor": f(s["karte"])}],
                                    "outline": [{"$id": "default", "show": True, "lineColor": f(s["blau"]),
                                                 "weight": 1, "roundEdge": 8},
                                                {"$id": "selected", "lineColor": f(s["navy"])}]}},
            "tableEx": {"*": tabelle},
            "pivotTable": {"*": tabelle},
            "clusteredColumnChart": {"*": achse},
            "clusteredBarChart": {"*": achse},
            "lineChart": {"*": {**achse, "labels": [{"show": True, "color": f(s["navy"]), "fontSize": 10,
                                                     "fontFamily": "Segoe UI Semibold", "labelPosition": "Above",
                                                     "enableBackground": True, "backgroundColor": f(s["karte"]),
                                                     "backgroundTransparency": 0}],
                                "lineStyles": [{"strokeWidth": 3, "showMarker": True, "markerSize": 5}]}},
        },
    }


def _json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2) + "\n"


def projekt_dateien(stern: dict[str, pd.DataFrame], excel_pfad: str = EXCEL_STANDARD,
                    name: str = PROJEKT) -> dict[str, str]:
    """Alle Textdateien eines Power-BI-Projekts (PBIP) mit TMDL-Modell und PBIR-Bericht."""
    sm, rp = f"{name}.SemanticModel", f"{name}.Report"
    thema = THEMA_NAME
    seiten = _bericht_visuals()
    f = {
        f"{name}.pbip": _json({
            "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
            "artifacts": [{"report": {"path": rp}}], "settings": {"enableAutoRecovery": True}}),
        ".gitignore": "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n",
        f"{sm}/definition.pbism": _json({
            "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.0", "settings": {}}),
        f"{sm}/definition/database.tmdl": "database\n\tcompatibilityLevel: 1567\n\n",
        f"{sm}/definition/model.tmdl": _model_tmdl(list(stern)),
        f"{sm}/definition/expressions.tmdl": _expressions_tmdl(excel_pfad),
        f"{sm}/definition/relationships.tmdl": _relationships_tmdl(),
        f"{rp}/definition.pbir": _json({
            "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{sm}"}}}),
        f"{rp}/definition/version.json": _json({
            "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}),
        f"{rp}/definition/report.json": _json({
            "$schema": f"{SCHEMA}/item/report/definition/report/3.3.0/schema.json",
            "themeCollection": {
                "baseTheme": {"name": "CY24SU10", "type": "SharedResources",
                              "reportVersionAtImport": {"visual": "1.8.96", "report": "2.0.96", "page": "1.3.96"}},
                "customTheme": {"name": thema, "type": "RegisteredResources",
                                "reportVersionAtImport": {"visual": "1.8.96", "report": "2.0.96", "page": "1.3.96"}}},
            "objects": {"outspacePane": [{"properties": {"expanded": _an("false")}}]},
            "resourcePackages": [
                {"name": "SharedResources", "type": "SharedResources",
                 "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
                {"name": "RegisteredResources", "type": "RegisteredResources",
                 "items": [{"name": thema, "path": thema, "type": "CustomTheme"}]}],
            "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                         "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                         "useDefaultAggregateDisplayName": True}}),
        f"{rp}/definition/pages/pages.json": _json({
            "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [x[0] for x in SEITEN], "activePageName": SEITEN[0][0]}),
        f"{rp}/StaticResources/SharedResources/BaseThemes/CY24SU10.json":
            (VORLAGE / "CY24SU10.json").read_text(encoding="utf-8"),
        f"{rp}/StaticResources/RegisteredResources/{thema}": _json(_theme()),
    }
    for t, df in stern.items():
        f[f"{sm}/definition/tables/{t}.tmdl"] = _tabelle_tmdl(t, df)
    for sid, anzeige, *_ in SEITEN:
        f[f"{rp}/definition/pages/{sid}/page.json"] = _json({
            "$schema": f"{SCHEMA}/item/report/definition/page/2.1.0/schema.json", "name": sid,
            "displayName": anzeige, "displayOption": "FitToPage", "height": HOEHE, "width": BREITE})
        for v in seiten[sid]:
            f[f"{rp}/definition/pages/{sid}/visuals/{v['name']}/visual.json"] = _json(v)
    return f


def projekt_zip(stern: dict[str, pd.DataFrame], excel: bytes, excel_name: str, ordner: str = "C:\\Cockpit") -> bytes:
    """ZIP: Ordner mit .pbip-Projekt, dem Sternschema-Excel und einer kurzen Anleitung."""
    excel_name = re.sub(r"[^\w.\-]+", "_", excel_name)       # sicher für Pfad und M-Text
    pfad = f"{ordner}\\{excel_name}"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for p, text in projekt_dateien(stern, pfad).items():
            z.writestr(p, text.encode("utf-8"))
        z.writestr(excel_name, excel)
        z.writestr("LIESMICH.txt", ANLEITUNG.format(ordner=ordner, excel=excel_name, projekt=PROJEKT)
                   .replace("\n", "\r\n").encode("utf-8"))
    return puffer.getvalue()


ANLEITUNG = """Power-BI-Projekt Unternehmer-Cockpit (Sternschema)

1. ZIP erst entpacken (Rechtsklick > Alle extrahieren), nicht aus dem ZIP heraus öffnen.
   Ziel {ordner}, sodass dort {excel} liegt.
   Anderer Ordner: nach dem Öffnen Start > Daten transformieren > Parameter bearbeiten > ExcelDatei anpassen.
2. {projekt}.pbip mit Power BI Desktop öffnen (Version ab Juni 2024).
   Falls gefragt: Datei > Optionen > Vorschaufeatures > "Power BI-Projekt speichern" und
   "Speichern im TMDL-Format" bzw. "PBIR-Format" aktivieren und Power BI Desktop neu starten.
3. Start > Aktualisieren lädt die Daten aus dem Excel.

Enthalten: 7 Dimensionen, 5 Faktentabellen, 16 Beziehungen (Blatt "beziehungen" im Excel),
eine als Datumstabelle markierte dim_datum und Kennzahlen in DAX (Umsatz, DB I, Marge, EBIT, Plan-Abweichung,
Vorjahr, YTD, offene Forderungen, Forderungslaufzeit, Kontostand).
Beträge in US-Dollar wie in der Quelle. Plan, Fixkosten und Zahlungen sind simuliert.
"""


def schreibe_projekt(stern: dict[str, pd.DataFrame], ziel: Path, excel_pfad: str = EXCEL_STANDARD) -> list[Path]:
    geschrieben = []
    for p, text in projekt_dateien(stern, excel_pfad).items():
        datei = ziel / p
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(text, encoding="utf-8", newline="\n")
        geschrieben.append(datei)
    return geschrieben


if __name__ == "__main__":
    from logik import DB_PFAD
    stern = baue_stern(Q.lade_sqlite(DB_PFAD))
    basis = Path(__file__).parent
    schreibe_projekt(stern, basis / "powerbi")
    excel = exportiere_stern_excel(stern, Path(DB_PFAD).with_name("unicorn_sternschema.xlsx"))
    print(f"Projekt: {basis / 'powerbi'}\nExcel:   {excel}")
