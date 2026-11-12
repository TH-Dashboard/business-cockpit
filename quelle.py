"""Datenquellen für das Unternehmer-Cockpit: SQLite-Datei oder geöffnetes Power-BI-Desktop-Modell.

Beide Quellen liefern dieselben sechs Tabellen. `normalisiere` bringt sie in gleiche Spalten,
Datentypen und Sortierung, damit die App mit beiden exakt gleich rechnet.

Power BI Desktop startet für jede geöffnete .pbix einen lokalen Analysis-Services-Server
(msmdsrv.exe) auf einem zufälligen Port. Den Port schreibt Power BI in eine Datei
msmdsrv.port.txt im Arbeitsordner. Die App liest den Port, verbindet sich über die
ADOMD-Bibliothek von Power BI und holt jede Tabelle mit DAX: EVALUATE 'tabelle'.
Dafür braucht Python das Paket pythonnet (siehe requirements-powerbi.txt).
"""
from __future__ import annotations

import glob
import os
import re
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- Tabellenbeschreibung
# Spalten in fester Reihenfolge, Datumsspalten, ganzzahlige Spalten, Sortierschlüssel
TABELLEN: dict[str, dict] = {
    "fakt_umsatz": dict(
        spalten=["position_id", "auftrag_id", "auftragsdatum", "versanddatum", "monat", "jahr",
                 "versandart", "region", "bundesstaat", "stadt", "kunde_id", "kunde", "segment",
                 "produkt_id", "produkt", "kategorie", "subkategorie", "menge", "rabatt",
                 "rabattstufe", "listenumsatz", "rabattbetrag", "umsatz", "wareneinsatz",
                 "versandkosten", "db1"],
        datum=["auftragsdatum", "versanddatum", "monat"],
        ganz=["position_id", "jahr", "kunde_id", "produkt_id", "menge", "umsatz", "db1"],
        sort=["position_id"]),
    "fakt_plan": dict(
        spalten=["monat", "region", "kategorie", "umsatz_plan", "db1_plan"],
        datum=["monat"], ganz=[], sort=["monat", "region", "kategorie"]),
    "fakt_fixkosten": dict(
        spalten=["monat", "kostenart", "plan", "ist"],
        datum=["monat"], ganz=[], sort=["monat", "kostenart"]),
    "fakt_rechnungen": dict(
        spalten=["auftrag_id", "kunde_id", "auftragsdatum", "rechnungsdatum", "betrag",
                 "zahlungsziel_tage", "faellig_am", "verzug_tage", "bezahlt_am", "status"],
        datum=["auftragsdatum", "rechnungsdatum", "faellig_am", "bezahlt_am"],
        ganz=["kunde_id", "betrag", "zahlungsziel_tage", "verzug_tage"],
        sort=["auftrag_id"]),
    "fakt_liquiditaet_tag": dict(
        spalten=["datum", "einzahlungen", "auszahlungen_ware", "auszahlungen_versand",
                 "auszahlungen_fix", "privatentnahme", "saldo_tag", "kontostand"],
        datum=["datum"], ganz=["einzahlungen", "privatentnahme"], sort=["datum"]),
    "dim_kunde": dict(
        spalten=["kunde_id", "kunde", "segment", "hauptregion", "zahlungsverhalten_sim"],
        datum=[], ganz=["kunde_id"], sort=["kunde_id"]),
}
FELD = {"fakt_umsatz": "umsatz", "fakt_plan": "plan", "fakt_fixkosten": "fix",
        "fakt_rechnungen": "rech", "fakt_liquiditaet_tag": "liq", "dim_kunde": "kunde"}


class QuellenFehler(RuntimeError):
    """Verständliche Fehlermeldung für die App."""


class PaketFehlt(QuellenFehler):
    """pythonnet ist nicht installiert; die App bietet dann einen Installations-Knopf an."""


PYTHONNET = "pythonnet>=3.2.1"


def installiere_pythonnet() -> tuple[bool, str]:
    """Installiert pythonnet in genau das Python, mit dem die App läuft."""
    import importlib
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pip", "install", PYTHONNET],
                       capture_output=True, text=True, timeout=600)
    importlib.invalidate_caches()
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def normalisiere(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Spaltennamen, Reihenfolge, Datentypen und Sortierung vereinheitlichen."""
    t = TABELLEN[name]
    # DAX liefert Spalten als  tabelle[spalte]  -> nur den Spaltennamen behalten, ohne Groß/klein
    df = df.rename(columns=lambda c: re.sub(r"^.*\[(.*)\]$", r"\1", str(c)).strip().lower())
    fehlt = [c for c in t["spalten"] if c not in df.columns]
    if fehlt:
        raise QuellenFehler(f"Tabelle {name}: Spalten fehlen: {', '.join(fehlt)}")
    df = df[t["spalten"]].copy()
    for c in t["datum"]:
        if pd.api.types.is_numeric_dtype(df[c]):   # Excel-Seriennummer (Tage seit 30.12.1899)
            df[c] = pd.to_datetime(df[c], unit="D", origin="1899-12-30")
        df[c] = pd.to_datetime(df[c]).dt.tz_localize(None).dt.normalize().astype("datetime64[ns]")
    for c in t["ganz"]:
        df[c] = pd.to_numeric(df[c]).round().astype("int64")
    for c in t["spalten"]:
        if c in t["datum"] or c in t["ganz"]:
            continue
        if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]):
            df[c] = pd.to_numeric(df[c]).astype("float64")
        else:
            df[c] = df[c].astype("object").where(df[c].notna(), None)
            df[c] = df[c].map(lambda v: None if v is None else str(v))
    return df.sort_values(t["sort"], kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------- SQLite
def lade_sqlite(pfad: Path | str) -> dict[str, pd.DataFrame]:
    pfad = Path(pfad)
    if not pfad.exists():
        raise FileNotFoundError(
            f"Datenbank nicht gefunden: {pfad}\n"
            "Lege die App neben den Ordner 10_cockpit_daten oder setze COCKPIT_DB.")
    con = sqlite3.connect(pfad)
    try:
        return {n: normalisiere(pd.read_sql(f"select * from {n}", con), n) for n in TABELLEN}
    finally:
        con.close()


# ---------------------------------------------------------------- Power BI Desktop
@dataclass
class PbiInstanz:
    port: int
    ordner: str          # Arbeitsordner von Power BI (ein Ordner je geöffneter .pbix)
    gestartet: float     # Zeitpunkt, an dem Power BI die Port-Datei geschrieben hat

    @property
    def text(self) -> str:
        zeit = pd.Timestamp(self.gestartet, unit="s", tz="UTC").tz_convert("Europe/Berlin")
        return f"Port {self.port} · geöffnet {zeit.strftime('%d.%m. %H:%M')}"


def _arbeitsordner() -> list[str]:
    lokal = os.environ.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    return [
        os.path.join(lokal, "Microsoft", "Power BI Desktop", "AnalysisServicesWorkspaces"),
        os.path.join(home, "Microsoft", "Power BI Desktop Store App", "AnalysisServicesWorkspaces"),
        os.path.join(lokal, "Packages", "Microsoft.MicrosoftPowerBIDesktop_8wekyb3d8bbwe",
                     "LocalCache", "Local", "Microsoft", "Power BI Desktop", "AnalysisServicesWorkspaces"),
    ]


def _lies_port(datei: str) -> int | None:
    roh = Path(datei).read_bytes()
    for kodierung in ("utf-16", "utf-8", "latin-1"):
        try:
            text = roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
        ziffern = re.sub(r"\D", "", text)
        if ziffern:
            return int(ziffern)
    return None


def _port_offen(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.3):
            return True
    except OSError:
        return False


def pbi_instanzen() -> list[PbiInstanz]:
    """Alle geöffneten Power-BI-Desktop-Modelle, neueste zuerst."""
    gefunden = []
    for basis in _arbeitsordner():
        for datei in glob.glob(os.path.join(basis, "*", "Data", "msmdsrv.port.txt")):
            try:
                port = _lies_port(datei)
            except OSError:
                continue
            if port and _port_offen(port):   # alte Port-Dateien geschlossener Sitzungen überspringen
                gefunden.append(PbiInstanz(port, str(Path(datei).parent.parent),
                                           os.path.getmtime(datei)))
    return sorted(gefunden, key=lambda i: -i.gestartet)


def _prozess_ordner() -> list[str]:
    """Ordner der laufenden Power-BI-Prozesse. Nötig für die Store-Version: deren Ordner unter
    WindowsApps darf man nicht durchsuchen, Dateien mit bekanntem Pfad aber lesen."""
    import subprocess
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process PBIDesktop,msmdsrv -ErrorAction SilentlyContinue).Path"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    ordner = []
    for zeile in r.stdout.splitlines():
        if zeile.strip():
            o = os.path.dirname(zeile.strip())
            for k in (o, os.path.join(os.path.dirname(o), "bin")):
                if k not in ordner:
                    ordner.append(k)
    return ordner


def _adomd_kandidaten() -> list[str]:
    dll = "Microsoft.AnalysisServices.AdomdClient.dll"
    direkt = [os.path.join(o, dll) for o in _prozess_ordner()]
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
          os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    muster = [os.environ.get("COCKPIT_ADOMD_DLL", "")]
    for p in pf:
        muster += [os.path.join(p, "Microsoft Power BI Desktop", "bin", dll),
                   os.path.join(p, "Microsoft Power BI Desktop", "bin", "Microsoft.PowerBI.AdomdClient.dll"),
                   os.path.join(p, "WindowsApps", "Microsoft.MicrosoftPowerBIDesktop_*", "bin", dll),
                   os.path.join(p, "DAX Studio", "bin", dll),
                   os.path.join(p, "DAX Studio", dll)]
    muster.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "assembly",
                               "GAC_MSIL", "Microsoft.AnalysisServices.AdomdClient", "*", dll))
    treffer = [p for p in direkt if os.path.isfile(p)]
    # Power BI Desktop liefert die Bibliothek als Microsoft.PowerBI.AdomdClient.dll mit
    for o in _prozess_ordner():
        for p in sorted(glob.glob(os.path.join(o, "*AdomdClient.dll"))):
            if p not in treffer:
                treffer.append(p)
    for m in muster:
        if m:
            try:
                treffer += sorted(glob.glob(m), reverse=True)
            except OSError:
                pass
    return treffer


_ADOMD = None


def _adomd():
    """Lädt die ADOMD-Bibliothek über pythonnet (einmal pro Python-Prozess)."""
    global _ADOMD
    if _ADOMD is not None:
        return _ADOMD
    try:
        import clr  # pythonnet
    except ImportError as e:
        raise PaketFehlt(
            "Das Python-Paket pythonnet fehlt. Im Terminal einmalig ausführen:\n"
            "python -m pip install -r requirements-powerbi.txt") from e
    fehler = []
    kandidaten = list(dict.fromkeys(_adomd_kandidaten()))
    for pfad in kandidaten:
        try:
            clr.AddReference(pfad)
            break
        except Exception as e:  # noqa: BLE001 – nächsten Kandidaten versuchen
            fehler.append(f"{pfad}: {e}")
    else:
        try:
            clr.AddReference("Microsoft.AnalysisServices.AdomdClient")
        except Exception as e:  # noqa: BLE001
            raise QuellenFehler(
                "Die ADOMD-Bibliothek von Power BI wurde nicht gefunden. Setze die Variable "
                "COCKPIT_ADOMD_DLL auf den Pfad von Microsoft.AnalysisServices.AdomdClient.dll "
                "(liegt im Ordner bin von Power BI Desktop)."
                + ("\nVersucht: " + "; ".join(fehler) if fehler else "")
                + ("\nPower-BI-Ordner: " + "; ".join(_prozess_ordner()) if not kandidaten else "")) from e
    from Microsoft.AnalysisServices.AdomdClient import AdomdConnection  # type: ignore
    _ADOMD = AdomdConnection
    return _ADOMD


def _netz_wert(v):
    """.NET-Werte in Python-Werte umwandeln (Datum, Decimal, leer)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    typ = v.GetType().FullName
    if typ == "System.DBNull":
        return None
    if typ == "System.DateTime":
        return pd.Timestamp(v.Year, v.Month, v.Day, v.Hour, v.Minute, v.Second)
    if typ in ("System.Decimal", "System.Double", "System.Single"):
        from System import Convert  # type: ignore
        return float(Convert.ToDouble(v))
    if typ.startswith("System.Int") or typ.startswith("System.UInt"):
        from System import Convert  # type: ignore
        return int(Convert.ToInt64(v))
    return str(v)


def _dax(con, abfrage: str) -> pd.DataFrame:
    cmd = con.CreateCommand()
    cmd.CommandText = abfrage
    leser = cmd.ExecuteReader()
    try:
        namen = [leser.GetName(i) for i in range(leser.FieldCount)]
        zeilen = []
        while leser.Read():
            zeilen.append([_netz_wert(leser.GetValue(i)) for i in range(len(namen))])
    finally:
        leser.Close()
    return pd.DataFrame(zeilen, columns=namen)


def lade_powerbi(port: int) -> dict[str, pd.DataFrame]:
    """Holt die sechs Tabellen aus dem geöffneten Power-BI-Desktop-Modell auf diesem Port."""
    Verbindung = _adomd()
    con = Verbindung(f"Data Source=localhost:{port};")
    try:
        con.Open()
    except Exception as e:  # noqa: BLE001
        raise QuellenFehler(f"Power BI Desktop auf Port {port} antwortet nicht. "
                            "Ist die .pbix noch geöffnet?") from e
    try:
        tabellen = {}
        for name in TABELLEN:
            try:
                roh = _dax(con, f"EVALUATE '{name}'")
            except Exception as e:  # noqa: BLE001
                try:
                    vorhanden = _dax(con, "SELECT [Name] FROM $SYSTEM.TMSCHEMA_TABLES").iloc[:, 0]
                    liste = ", ".join(sorted(str(v) for v in vorhanden if not str(v).startswith(
                        ("DateTableTemplate", "LocalDateTable")))) or "keine"
                except Exception:  # noqa: BLE001
                    liste = "unbekannt"
                raise QuellenFehler(
                    f"Im Power-BI-Modell fehlt die Tabelle '{name}'. Lade alle sechs Blätter aus "
                    "unicorn_cockpit_powerbi.xlsx und lass die Tabellennamen unverändert.\n"
                    f"Tabellen im geöffneten Modell: {liste}") from e
            tabellen[name] = normalisiere(roh, name)
        return tabellen
    finally:
        con.Close()


def pbi_modell(port: int) -> list[dict]:
    """Inhalt des geöffneten Modells: je Tabelle Zeilen, Spalten und drei Beispielzeilen."""
    con = _adomd()(f"Data Source=localhost:{port};")
    con.Open()
    try:
        tab = _dax(con, "SELECT [ID], [Name] FROM $SYSTEM.TMSCHEMA_TABLES")
        spa = _dax(con, "SELECT [TableID], [ExplicitName], [InferredName], [Type] FROM $SYSTEM.TMSCHEMA_COLUMNS")
        aus = []
        for _, t in tab.iterrows():
            name = str(t.iloc[1])
            if name.startswith(("DateTableTemplate", "LocalDateTable")):
                continue
            s = spa[spa.iloc[:, 0] == t.iloc[0]]
            spalten = [str(r.iloc[1] or r.iloc[2]) for _, r in s.iterrows()
                       if int(r.iloc[3]) != 3 and not str(r.iloc[1] or r.iloc[2]).startswith("RowNumber")]
            try:
                n = int(_dax(con, f"EVALUATE ROW(\"n\", COUNTROWS('{name}'))").iloc[0, 0] or 0)
                probe = _dax(con, f"EVALUATE TOPN(3, '{name}')")
                probe.columns = [re.sub(r"^.*\[(.*)\]$", r"\1", str(c)) for c in probe.columns]
            except Exception as e:  # noqa: BLE001
                n, probe = -1, pd.DataFrame({"Fehler": [str(e)[:200]]})
            aus.append({"tabelle": name, "zeilen": n, "spalten": spalten, "probe": probe})
        return aus
    finally:
        con.Close()


# ---------------------------------------------------------------- Abgleich und Export
def abgleich(a: dict[str, pd.DataFrame], b: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Vergleicht zwei Quellen je Tabelle: Zeilen, Summen der Zahlenspalten, Zeitraum."""
    zeilen = []
    for name, t in TABELLEN.items():
        x, y = a[name], b[name]
        abw = []
        if len(x) != len(y):
            abw.append(f"Zeilen {len(x)} statt {len(y)}")
        else:
            for c in t["spalten"]:
                if c in t["datum"]:
                    anders = int(((x[c] != y[c]) & ~(x[c].isna() & y[c].isna())).sum())
                    if anders:
                        abw.append(f"{c}: {anders} Datumswerte anders")
                elif pd.api.types.is_numeric_dtype(x[c]):
                    d = np.nanmax(np.abs(x[c].to_numpy(float) - y[c].to_numpy(float)), initial=0)
                    if d > 0.005 or (x[c].isna() != y[c].isna()).any():
                        abw.append(f"{c}: max. Abweichung " + f"{d:.2f}".replace(".", ","))
                elif not x[c].fillna("").equals(y[c].fillna("")):
                    abw.append(f"{c}: {int((x[c].fillna('') != y[c].fillna('')).sum())} Texte anders")
        zeilen.append({"Tabelle": name, "Zeilen": len(x),
                       "Ergebnis": "identisch" if not abw else "; ".join(abw)})
    return pd.DataFrame(zeilen)


def exportiere_excel(tabellen: dict[str, pd.DataFrame], ziel):
    """Schreibt die Tabellen als Blätter in eine Excel-Datei zum Laden in Power BI (Pfad oder Puffer).

    Direkt mit xlsxwriter, Spalte für Spalte: etwa dreimal so schnell wie DataFrame.to_excel.
    Texte werden nie als Formel, Link oder Zahl gedeutet; leere Werte bleiben leere Zellen.
    """
    import xlsxwriter
    from bereinigung import entschaerfe              # Texte wie "=..." nicht als Formel speichern
    ziel = ziel if hasattr(ziel, "write") else Path(ziel)
    wb = xlsxwriter.Workbook(ziel, {"strings_to_formulas": False, "strings_to_urls": False,
                                    "strings_to_numbers": False, "remove_timezone": True})
    kopf = wb.add_format({"bold": True})
    datum = wb.add_format({"num_format": "YYYY-MM-DD"})
    for name, df in tabellen.items():
        df = entschaerfe(df)
        ws = wb.add_worksheet(name)
        ws.write_row(0, 0, [str(c) for c in df.columns], kopf)
        ws.freeze_panes(1, 0)
        for j, spalte in enumerate(df.columns):
            s = df[spalte]
            if pd.api.types.is_datetime64_any_dtype(s):
                for i, v in enumerate(s.tolist(), 1):
                    if not pd.isna(v):
                        ws.write_datetime(i, j, v.to_pydatetime(), datum)
            elif pd.api.types.is_bool_dtype(s):
                for i, v in enumerate(s.tolist(), 1):
                    if not pd.isna(v):
                        ws.write_boolean(i, j, bool(v))
            elif pd.api.types.is_numeric_dtype(s):
                for i, v in enumerate(s.to_numpy(float, na_value=np.nan).tolist(), 1):
                    if v == v:                       # NaN überspringen
                        ws.write_number(i, j, v)
            else:
                for i, v in enumerate(s.tolist(), 1):
                    if not pd.isna(v):
                        ws.write_string(i, j, str(v))
    wb.close()
    return ziel


if __name__ == "__main__":
    # python quelle.py excel  -> schreibt 10_cockpit_daten/unicorn_cockpit_powerbi.xlsx neu
    import sys
    from logik import DB_PFAD
    if sys.argv[1:] == ["excel"]:
        ziel = exportiere_excel(lade_sqlite(DB_PFAD), Path(DB_PFAD).with_name("unicorn_cockpit_powerbi.xlsx"))
        print(f"Geschrieben: {ziel}")
    else:
        for i in pbi_instanzen():
            print(i.text, i.ordner)
        print("Aufruf: python quelle.py excel   (Excel-Datei für Power BI neu schreiben)")
