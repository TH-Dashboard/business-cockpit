"""Prüft die Datenaufbereitung: Übungsdatei rein -> bereinigte Daten -> dieselben Cockpit-Zahlen wie heute.

Start:  python -m pytest -q
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

HIER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HIER))
import aufbau as A  # noqa: E402
import bereinigung as B  # noqa: E402
import logik as L  # noqa: E402
import quelle as Q  # noqa: E402

UEBUNG = HIER / "daten" / "uebung" / "unicorn_export_schmutzig.csv"


@pytest.fixture(scope="session")
def alt():
    if not Path(L.DB_PFAD).exists():
        pytest.skip(f"Datenbank fehlt: {L.DB_PFAD}")
    return Q.lade_sqlite(L.DB_PFAD)


@pytest.fixture(scope="session")
def ergebnis():
    return B.bereinige(B.lies_datei(UEBUNG.read_bytes(), UEBUNG.name))


# ---------------------------------------------------------------- Aufbau der Tabellen
def test_aufbau_reproduziert_sqlite(alt):
    d, _ = A.cockpit_daten(A.roh_aus_fakt(alt["fakt_umsatz"]))
    vergleich = Q.abgleich({n: getattr(d, Q.FELD[n]) for n in Q.TABELLEN}, alt)
    assert (vergleich.Ergebnis == "identisch").all(), vergleich.to_string()


def test_uebungsdatei_ist_aktuell(alt):
    """Die Datei im Repository entspricht dem Generator (sonst: neu erzeugen, siehe README)."""
    schmutzig, _ = B.schmutzig_machen(A.roh_aus_fakt(alt["fakt_umsatz"]))
    datei = B.lies_datei(UEBUNG.read_bytes(), UEBUNG.name)
    assert datei.equals(schmutzig.astype(str))


# ---------------------------------------------------------------- Bereinigung
def test_spalten_erkannt(ergebnis):
    assert set(ergebnis.zuordnung) == set(B.FELDER)
    assert ergebnis.zuordnung["order_sales"] == "Sales"
    assert ergebnis.zuordnung["product_subcategory"] == "Sub-Category"


def test_ausgeschlossen_mit_grund(ergebnis):
    k = ergebnis.kennzahlen
    assert (k["zeilen_gelesen"], k["zeilen_uebernommen"], k["zeilen_ausgeschlossen"]) == (10_019, 9_997, 22)
    assert ergebnis.ausgeschlossen.regel.value_counts().to_dict() == {
        "A05": 8, "A03": 5, "A07": 3, "A10": 2, "A09": 2, "A01": 1, "A02": 1}
    # Originalwerte bleiben erhalten
    assert {"Row ID", "Sales", "Order Date"} <= set(ergebnis.ausgeschlossen.columns)


def test_nichts_aufgefuellt(ergebnis):
    assert ergebnis.kennzahlen["werte_aufgefuellt"] == 0
    assert not ergebnis.sauber[[f for f, d in B.FELDER.items() if d["pflicht"]]].isna().any().any()


def test_bereinigt_gleich_original(alt, ergebnis):
    """Bis auf Leerzeichen in Produktnamen kommen genau die Originalwerte heraus."""
    ref = A.roh_aus_fakt(alt["fakt_umsatz"]).copy()
    ref["product_name"] = ref.product_name.str.replace(r"[\s ]+", " ", regex=True).str.strip()
    ref = ref.sort_values("order_details_id").reset_index(drop=True)
    sauber = B.als_rohexport(ergebnis)
    for c in ref.columns:
        assert (sauber[c].astype(str).values == ref[c].astype(str).values).all(), c


def test_cockpit_zahlen_wie_heute(alt, ergebnis):
    d, _ = A.cockpit_daten(B.als_rohexport(ergebnis))
    vergleich = Q.abgleich({n: getattr(d, Q.FELD[n]) for n in Q.TABELLEN}, alt).set_index("Tabelle").Ergebnis
    assert vergleich.drop("fakt_umsatz").eq("identisch").all()
    assert vergleich["fakt_umsatz"] == "produkt: 257 Texte anders"
    s = pd.Timestamp("2018-12-31")
    assert L.kennzahlen(d, s)["ebit"] == pytest.approx(L.kennzahlen(L.lade_daten(), s)["ebit"], abs=0.01)


def test_protokoll_je_regel(ergebnis):
    n = ergebnis.regel_uebersicht().set_index("regel").anzahl
    assert n["R03"] == 9_998       # Datumswerte, die nicht im Format JJJJ-MM-TT standen
    assert n["R05"] > 1_000        # Rabatt als Prozent
    assert n["R06"] == 65          # klein geschriebene Kundennamen
    assert set(ergebnis.aenderungen.quellzeile) <= set(ergebnis.sauber.quellzeile)


# ---------------------------------------------------------------- Einzelregeln
@pytest.mark.parametrize("text, stil, erwartet", [
    ("$1,234.00", "punkt", 1234.0), ("1.234,50 $", "punkt", 1234.5), ("837,5", "punkt", 837.5),
    ("1,234", "punkt", 1234.0), ("1,234", "komma", 1.234), ("(12)", "punkt", -12.0),
    ("12-", "punkt", -12.0), ("20%", "punkt", 20.0), ("EUR 3.000", "komma", 3000.0), ("abc", "punkt", None)])
def test_zahlen(text, stil, erwartet):
    assert B.lies_zahl(text, stil) == erwartet


@pytest.mark.parametrize("text, einst, erwartet, mehrdeutig", [
    ("2018-03-04", "MDY", "2018-03-04", False), ("04.03.2018", "MDY", "2018-03-04", False),
    ("03/04/2018", "MDY", "2018-03-04", True), ("03/04/2018", "DMY", "2018-04-03", True),
    ("13/04/2018", "MDY", "2018-04-13", False), ("43163", "MDY", "2018-03-04", False),
    ("4.3.18", "MDY", "2018-03-04", False)])
def test_datum(text, einst, erwartet, mehrdeutig):
    d, m = B.lies_datum(text, einst)
    assert (d.strftime("%Y-%m-%d"), m) == (erwartet, mehrdeutig)


def test_excel_upload_und_eigene_spaltennamen():
    df = pd.DataFrame({
        "Positions-ID": [1, 2, 2], "Auftragsnummer": ["A1", "A2", "A2"],
        "Bestelldatum": [pd.Timestamp("2020-01-05")] * 3, "Versanddatum": ["07.01.2020"] * 3,
        "Versandart": ["standard", "Same day", "Same day"], "Region": ["ost", "West", "West"],
        "Kundennummer": [7, 8, 8], "Segment": ["Corporate"] * 3, "Artikelnummer": [1, 2, 2],
        "Kategorie": ["Technology"] * 3, "Menge": [1, 2, 2], "Rabatt": ["0", "10 %", "10 %"],
        "Umsatz": ["100,00", "50", "50"], "Gewinn": ["10", "-5", "-5"]})
    puffer = io.BytesIO()
    df.to_excel(puffer, index=False)
    e = B.bereinige(B.lies_datei(puffer.getvalue(), "test.xlsx"))
    assert e.kennzahlen["zeilen_uebernommen"] == 2 and e.kennzahlen["dubletten"] == 1
    assert e.sauber.shipping_mode.tolist() == ["Standard Class", "Same Day"]
    assert e.sauber.shipping_region.tolist() == ["East", "West"]
    assert e.sauber.order_discount.tolist() == [0.0, 0.1]
    assert e.sauber.order_sales.tolist() == [100, 50]


def test_pruefpaket(ergebnis):
    _, tab = A.cockpit_daten(B.als_rohexport(ergebnis))
    zip_ = B.pruefpaket(ergebnis, UEBUNG.name, UEBUNG.read_bytes(), tab, "# Bericht")
    with zipfile.ZipFile(io.BytesIO(zip_)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert "01_bereinigt/cockpit_tabellen_powerbi.xlsx" in z.namelist()
        for name, info in manifest["dateien"].items():
            assert B._sha(z.read(name)) == info["sha256"]


def test_sql_auf_aufbereiteten_daten(ergebnis):
    """Die SQL-Abfragen laufen auch auf der aufbereiteten Datei und liefern dieselben Zahlen wie die Datei."""
    import sql_abfragen as SQL
    _, tab = A.cockpit_daten(B.als_rohexport(ergebnis))
    db = SQL.als_sqlite({n: tab[n] for n in Q.TABELLEN})
    for datei in SQL.dateien():
        neu = SQL.ausfuehren(datei.stem, "2018-12-31", db=db)
        alt = SQL.ausfuehren(datei.stem, "2018-12-31")
        pd.testing.assert_frame_equal(neu, alt, check_dtype=False)


# ---------------------------------------------------------------- Datumsreihenfolge
def _datumsdatei(bestell: list[str], versand: list[str]) -> pd.DataFrame:
    n = len(bestell)
    return pd.DataFrame({
        "Row ID": range(1, n + 1), "Order ID": [f"A{i}" for i in range(n)], "Order Date": bestell,
        "Ship Date": versand, "Ship Mode": ["Standard Class"] * n, "Region": ["West"] * n,
        "Customer ID": ["1"] * n, "Segment": ["Consumer"] * n, "Product ID": ["1"] * n,
        "Category": ["Technology"] * n, "Quantity": ["1"] * n, "Discount": ["0"] * n,
        "Sales": ["10"] * n, "Profit": ["1"] * n})


def test_datum_reihenfolge_automatisch_tag_monat():
    roh = _datumsdatei(["25/03/2020", "03/04/2020", "05/06/2020"], ["28/03/2020", "06/04/2020", "07/06/2020"])
    e = B.bereinige(roh.astype(str))
    assert e.kennzahlen["datum"]["verwendet"] == "DMY"
    assert e.sauber.order_date.dt.strftime("%Y-%m-%d").tolist() == ["2020-03-25", "2020-04-03", "2020-06-05"]
    assert (e.hinweise.regel == "H03").sum() == 0            # Datei belegt die Reihenfolge: keine Einzelhinweise
    assert e.kennzahlen["datum"]["mehrdeutig"] == 4


def test_datum_einstellung_gegen_datei_meldet_einzeln(ergebnis):
    assert ergebnis.kennzahlen["datum"]["verwendet"] == "MDY" and (ergebnis.hinweise.regel == "H03").sum() == 0
    roh = B.lies_datei(UEBUNG.read_bytes(), UEBUNG.name)
    falsch = B.bereinige(roh, einst=B.Einstellungen(datum_schraeg="DMY"))
    assert (falsch.hinweise.regel == "H03").sum() > 0


def test_datum_gemischte_datei_meldet_einzeln():
    roh = _datumsdatei(["25/03/2020", "03/25/2020", "03/04/2020"], ["26/03/2020", "03/26/2020", "03/05/2020"])
    e = B.bereinige(roh.astype(str))
    assert not e.kennzahlen["datum"]["eindeutig"]
    assert (e.hinweise.regel == "H03").sum() == 2


# ---------------------------------------------------------------- Formel-Schutz in Exporten
def test_exporte_ohne_formeln():
    import openpyxl
    df = pd.DataFrame({"name": ["=HYPERLINK(\"http://x\")", "+49 30", "@summe", "-12", "normal"], "zahl": [1, 2, 3, 4, 5]})
    sicher = B.entschaerfe(df)
    assert sicher.name.tolist() == ["'=HYPERLINK(\"http://x\")", "'+49 30", "'@summe", "-12", "normal"]
    assert df.name.iloc[0].startswith("=")                    # Original bleibt unverändert
    puffer = io.BytesIO()
    Q.exportiere_excel({"t": df}, puffer)
    puffer.seek(0)
    blatt = openpyxl.load_workbook(puffer).active
    assert all(z.data_type != "f" for zeile in blatt.iter_rows() for z in zeile)
    zeilen = pd.read_csv(io.BytesIO(B.als_csv(df)), encoding="utf-8-sig").name.tolist()
    assert zeilen[0].startswith("'=") and str(zeilen[3]) == "-12"


def test_haeufigste_schreibweise_bei_gleichstand_die_erste():
    # zwei Schreibweisen gleich oft: die zuerst vorkommende gewinnt (wie vorher value_counts)
    assert B._haeufigste(["a", "a", "a", "a", "b"], ["x", "X", "X", "x", "Y"]) == {"a": "x", "b": "Y"}
    assert B._haeufigste(["a", "a", "a"], ["X", "x", "x"]) == {"a": "x"}


def test_pruefpaket_uebernimmt_fertige_excel(ergebnis):
    excel = b"PK-schon-gebaut"
    zip_ = B.pruefpaket(ergebnis, UEBUNG.name, UEBUNG.read_bytes(), None, "", excel=excel)
    with zipfile.ZipFile(io.BytesIO(zip_)) as z:
        assert z.read("01_bereinigt/cockpit_tabellen_powerbi.xlsx") == excel
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["dateien"]["01_bereinigt/cockpit_tabellen_powerbi.xlsx"]["bytes"] == len(excel)


def test_excel_export_rundreise():
    # schneller xlsxwriter-Export: Typen und Lücken kommen unverändert zurück, Texte bleiben Texte
    df = pd.DataFrame({
        "datum": pd.to_datetime(["2024-01-31", None, "2024-03-01"]),
        "anzahl": pd.array([1, None, 3], dtype="Int64"),
        "betrag": [1.5, float("nan"), -2.25],
        "aktiv": [True, False, True],
        "text": ["=1+1", None, "https://x.de"],
        "nummer": ["007", "12", "abc"],
    })
    puffer = io.BytesIO()
    Q.exportiere_excel({"t": df, "leer": df.iloc[:0]}, puffer)
    zurueck = pd.read_excel(io.BytesIO(puffer.getvalue()), sheet_name=None, dtype={"nummer": str})
    t = zurueck["t"]
    assert list(t.columns) == list(df.columns) and len(zurueck["leer"]) == 0
    assert t.datum.isna().tolist() == [False, True, False] and t.datum.iloc[0] == pd.Timestamp("2024-01-31")
    assert t.anzahl.isna().tolist() == [False, True, False] and t.anzahl.iloc[2] == 3
    assert t.betrag.iloc[2] == -2.25 and t.aktiv.tolist() == [True, False, True]
    assert t.text.iloc[0] == "'=1+1" and t.text.iloc[2] == "https://x.de" and t.nummer.tolist() == ["007", "12", "abc"]
