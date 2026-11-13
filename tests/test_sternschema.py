"""Prüft das Sternschema für Power BI: gleiche Zahlen wie das Cockpit, saubere Schlüssel, gültiges Projekt.

Power BI Desktop selbst läuft hier nicht. Darum prüfen die Tests alles, was sich ohne Power BI prüfen lässt:
Daten (Summen über die Joins), Beziehungen, jeden Verweis in DAX, M und Bericht, und dass powerbi/ zum Code passt.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HIER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HIER))
import aufbau as A  # noqa: E402
import bereinigung as B  # noqa: E402
import logik as L  # noqa: E402
import quelle as Q  # noqa: E402
import sternschema as S  # noqa: E402

UEBUNG = HIER / "daten" / "uebung" / "unicorn_export_schmutzig.csv"


@pytest.fixture(scope="module")
def alt():
    if not Path(L.DB_PFAD).exists():
        pytest.skip(f"Datenbank fehlt: {L.DB_PFAD}")
    return Q.lade_sqlite(L.DB_PFAD)


@pytest.fixture(scope="module")
def stern(alt):
    return S.baue_stern(alt)


@pytest.fixture(scope="module")
def dateien(stern):
    return S.projekt_dateien(stern)


# ---------------------------------------------------------------- Daten
def test_nichts_verloren(alt, stern):
    for n in ["fakt_umsatz", "fakt_plan", "fakt_fixkosten", "fakt_rechnungen", "fakt_liquiditaet_tag"]:
        assert len(stern[n]) == len(alt[n]), n
    for spalte in ["umsatz", "db1", "wareneinsatz", "versandkosten", "menge", "rabattbetrag"]:
        assert stern["fakt_umsatz"][spalte].sum() == pytest.approx(alt["fakt_umsatz"][spalte].sum()), spalte


def test_summen_ueber_joins_wie_im_cockpit(alt, stern):
    """Umsatz und DB I je Region, Kategorie, Segment und Jahr – einmal flach, einmal über das Sternschema."""
    u = (stern["fakt_umsatz"]
         .merge(stern["dim_ort"], on="ort_id", validate="m:1")
         .merge(stern["dim_produkt"], on="produkt_id", validate="m:1")
         .merge(stern["dim_kunde"], on="kunde_id", validate="m:1")
         .merge(stern["dim_datum"], left_on="auftragsdatum", right_on="datum", validate="m:1"))
    flach = alt["fakt_umsatz"]
    for stern_sp, flach_sp in [("region", "region"), ("kategorie", "kategorie"), ("segment", "segment"),
                               ("jahr", "jahr"), ("stadt", "stadt"), ("subkategorie", "subkategorie")]:
        a = u.groupby(stern_sp)[["umsatz", "db1"]].sum().sort_index()
        b = flach.groupby(flach_sp)[["umsatz", "db1"]].sum().sort_index()
        pd.testing.assert_frame_equal(a, b, check_names=False, check_dtype=False)


def test_plan_ist_ueber_gemeinsame_dimensionen(alt, stern):
    """Plan und Ist treffen sich nur über dim_datum, dim_region und dim_kategorie – genau wie im Cockpit."""
    ist = (stern["fakt_umsatz"].merge(stern["dim_ort"], on="ort_id").merge(stern["dim_produkt"], on="produkt_id")
           .assign(monat=lambda x: x.auftragsdatum.dt.to_period("M").dt.to_timestamp())
           .groupby(["monat", "region", "kategorie"]).umsatz.sum())
    erwartet = alt["fakt_umsatz"].groupby(["monat", "region", "kategorie"]).umsatz.sum()
    pd.testing.assert_series_equal(ist.sort_index(), erwartet.sort_index(), check_names=False,
                                   check_index_type=False)
    plan = stern["fakt_plan"]
    assert set(plan.region) <= set(stern["dim_region"].region)
    assert set(plan.kategorie) <= set(stern["dim_kategorie"].kategorie)


def test_datumstabelle_lueckenlos(stern):
    d = stern["dim_datum"]
    assert d.datum.is_unique and d.datum.is_monotonic_increasing
    assert (d.datum.diff().dropna() == pd.Timedelta(days=1)).all()
    assert d.datum.min().strftime("%m-%d") == "01-01" and d.datum.max().strftime("%m-%d") == "12-31"
    assert d.loc[d.datum == "2018-12-31", ["monatsname", "wochentag", "kalenderwoche"]].values.tolist() == \
        [["Dez", "Mo", 1]]


@pytest.mark.parametrize("von_tab, von_sp, zu_tab, zu_sp, aktiv, _h", S.BEZIEHUNGEN)
def test_beziehung_passt(stern, von_tab, von_sp, zu_tab, zu_sp, aktiv, _h):
    eins, viele = stern[zu_tab][zu_sp], stern[von_tab][von_sp]
    assert eins.is_unique, f"{zu_tab}.{zu_sp} ist nicht eindeutig"
    assert eins.notna().all()
    leer = int(viele.isna().sum())
    assert not leer, f"{von_tab}.{von_sp}: {leer} leere Schlüssel, Power BI zeigt sonst \"(Blank)\" in {zu_tab}"
    fehlend = set(viele) - set(eins)
    assert not fehlend, f"{von_tab}.{von_sp}: {len(fehlend)} Werte ohne Partner, z. B. {sorted(fehlend)[:3]}"
    assert S._typ(eins)[0] == S._typ(viele)[0]


def test_genau_ein_aktiver_weg_je_paar():
    paare = [(v, z) for v, _, z, _, aktiv, _ in S.BEZIEHUNGEN if aktiv]
    assert len(paare) == len(set(paare)), "zwei aktive Beziehungen zwischen denselben Tabellen"


def test_keine_fakt_an_fakt_beziehung():
    assert not [b for b in S.BEZIEHUNGEN if b[0].startswith("fakt_") and b[2].startswith("fakt_")]


def test_stern_aus_upload_wie_aus_sqlite(alt, stern):
    """Nach der Datenaufbereitung (Übungsdatei) entsteht dasselbe Sternschema wie aus der SQLite-Datei."""
    e = B.bereinige(B.lies_datei(UEBUNG.read_bytes(), UEBUNG.name))
    _, tab = A.cockpit_daten(e.sauber)
    neu = S.baue_stern(tab)
    assert list(neu) == list(stern)
    for n in stern:
        assert list(neu[n].columns) == list(stern[n].columns), n
        assert [S._typ(neu[n][c])[0] for c in neu[n]] == [S._typ(stern[n][c])[0] for c in stern[n]], n
    assert neu["fakt_umsatz"].umsatz.sum() == stern["fakt_umsatz"].umsatz.sum()


# ---------------------------------------------------------------- Excel
def test_excel_mit_beziehungen(stern):
    puffer = io.BytesIO()
    S.exportiere_stern_excel(stern, puffer)
    blaetter = pd.read_excel(io.BytesIO(puffer.getvalue()), sheet_name=None)
    assert list(blaetter) == [*stern, "beziehungen"]
    assert len(blaetter["beziehungen"]) == len(S.BEZIEHUNGEN)
    assert len(blaetter["fakt_umsatz"]) == len(stern["fakt_umsatz"])
    assert blaetter["fakt_umsatz"].umsatz.sum() == stern["fakt_umsatz"].umsatz.sum()


# ---------------------------------------------------------------- Power-BI-Projekt
def _tmdl(dateien: dict[str, str]) -> dict[str, dict]:
    """Tabellen, Spalten und Kennzahlen aus den TMDL-Dateien lesen (nur was die Tests brauchen)."""
    modell = {}
    for pfad, text in dateien.items():
        if "/tables/" not in pfad:
            continue
        name = re.match(r"table (\S+)", text).group(1)
        modell[name] = {
            "spalten": re.findall(r"^\tcolumn (\S+)$", text, re.M),
            "kennzahlen": [m.strip("'") for m in re.findall(r"^\tmeasure ('[^']+'|\S+) =", text, re.M)],
            "text": text}
    return modell


def test_json_dateien_lesbar(dateien):
    for pfad, text in dateien.items():
        if pfad.endswith((".json", ".pbip", ".pbir", ".pbism", ".platform")):
            json.loads(text)


def test_tmdl_einrueckung_nur_tabs(dateien):
    for pfad, text in dateien.items():
        if pfad.endswith(".tmdl"):
            for i, zeile in enumerate(text.split("\n"), 1):
                assert not re.match(r"^\t* +\S", zeile) or zeile.startswith("\t\t\t"), f"{pfad}:{i} {zeile!r}"


def test_tmdl_vollstaendig(stern, dateien):
    modell = _tmdl(dateien)
    assert set(modell) == set(stern)
    m = dateien[f"{S.PROJEKT}.SemanticModel/definition/model.tmdl"]
    assert re.findall(r"^ref table (\S+)$", m, re.M) == list(stern)
    for n, df in stern.items():
        assert modell[n]["spalten"] == list(df.columns), n
        assert f'[Item="{n}",Kind="Sheet"]' in modell[n]["text"]
    ids = re.findall(r"lineageTag: (\S+)", "".join(dateien.values()))
    assert len(ids) == len(set(ids))


def test_dax_verweise_existieren(dateien):
    modell = _tmdl(dateien)
    kennzahlen = {k for t in modell.values() for k in t["kennzahlen"]}
    assert len(kennzahlen) == len(S.KENNZAHLEN)
    for _, name, dax, _, _ in S.KENNZAHLEN:
        for tab, spalte in re.findall(r"(\w+)\[([^\]]+)\]", dax):
            assert spalte in modell[tab]["spalten"], f"{name}: {tab}[{spalte}] fehlt"
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax):
            assert ref in kennzahlen, f"{name}: Kennzahl [{ref}] fehlt"


def test_kennzahl_heisst_nicht_wie_eine_spalte(dateien):
    """Power BI Desktop lehnt das Projekt ab, wenn eine Kennzahl wie eine Spalte heißt (Groß-/Kleinschreibung egal)."""
    modell = _tmdl(dateien)
    spalten = {s.lower() for t in modell.values() for s in t["spalten"]}
    namen = [k.lower() for t in modell.values() for k in t["kennzahlen"]]
    assert len(namen) == len(set(namen))
    assert not spalten & set(namen), sorted(spalten & set(namen))


def test_beziehungen_und_sortierung_im_tmdl(dateien):
    modell = _tmdl(dateien)
    rel = dateien[f"{S.PROJEKT}.SemanticModel/definition/relationships.tmdl"]
    for tab, spalte in re.findall(r"Column: (\w+)\.(\w+)", rel):
        assert spalte in modell[tab]["spalten"]
    assert rel.count("relationship ") == len(S.BEZIEHUNGEN)
    assert rel.count("isActive: false") == sum(not b[4] for b in S.BEZIEHUNGEN)
    for (tab, _), nach in S.SORTIERUNG.items():
        assert nach in modell[tab]["spalten"]
    assert "dataCategory: Time" in modell["dim_datum"]["text"] and "\t\tisKey" in modell["dim_datum"]["text"]


def _seiten(dateien) -> dict[str, list[dict]]:
    seiten: dict[str, list[dict]] = {}
    for p, t in dateien.items():
        if p.endswith("visual.json"):
            seiten.setdefault(p.split("/pages/")[1].split("/")[0], []).append(json.loads(t))
    return seiten


def test_bericht_verweist_auf_vorhandene_felder(dateien):
    modell = _tmdl(dateien)
    seiten = _seiten(dateien)
    assert list(seiten) and set(seiten) == {s[0] for s in S.SEITEN}
    for sid, visuals in seiten.items():
        for v in visuals:
            q = v["visual"].get("query", {})
            felder = [p["field"] for teil in q.get("queryState", {}).values() for p in teil["projections"]]
            felder += [x["field"] for x in q.get("sortDefinition", {}).get("sort", [])]
            for feld in felder:
                (art, f), = feld.items()
                tab, name = f["Expression"]["SourceRef"]["Entity"], f["Property"]
                liste = modell[tab]["kennzahlen" if art == "Measure" else "spalten"]
                assert name in liste, f"{sid}/{v['name']}: {tab}.{name}"


def test_bericht_layout_ohne_ueberlappung(dateien):
    """Jede Seite: Titel, Filter, 5 Kennzahlkarten, 2 Flächen, Navigation; alles im Rahmen, nichts überdeckt sich."""
    pages = json.loads(dateien[f"{S.PROJEKT}.Report/definition/pages/pages.json"])
    assert pages["pageOrder"] == [s[0] for s in S.SEITEN]
    for sid, visuals in _seiten(dateien).items():
        typen = [v["visual"]["visualType"] for v in visuals]
        assert typen.count("pageNavigator") == 1 and typen.count("textbox") == 1, sid
        assert typen.count("card") == 5 and typen.count("slicer") >= 1, sid
        kaesten = []
        for v in visuals:
            p = v["position"]
            assert 0 <= p["x"] and p["x"] + p["width"] <= S.BREITE, f"{sid}/{v['name']} zu breit"
            assert 0 <= p["y"] and p["y"] + p["height"] <= S.HOEHE, f"{sid}/{v['name']} zu hoch"
            kaesten.append((v["name"], p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]))
        for i, a in enumerate(kaesten):
            for b in kaesten[i + 1:]:
                ueber = a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]
                assert not ueber, f"{sid}: {a[0]} überdeckt {b[0]}"


def test_region_filter_nur_wo_zahlen_je_region_gelten():
    """Fixkosten, Forderungen und Konto haben keine Region; dort darf kein Region-Filter stehen."""
    ohne_region = {"fakt_fixkosten", "fakt_rechnungen", "fakt_liquiditaet_tag"}
    for sid, _, _, filter_, kpis, links, rechts, in S.SEITEN:
        tabellen = {t for t, _ in kpis} | {t for t, _ in links[3]} | {t for t, _ in rechts[3]}
        if tabellen & ohne_region:
            assert all(f[0] != "dim_region" for f in filter_), sid


def test_theme_in_app_farben(dateien):
    thema = json.loads(dateien[f"{S.PROJEKT}.Report/StaticResources/RegisteredResources/{S.THEMA_NAME}"])
    assert thema["dataColors"][:2] == [S.STIL["blau"], S.STIL["orange"]]
    seite = thema["visualStyles"]["page"]["*"]["background"][0]["color"]["solid"]["color"]
    assert seite == S.STIL["seite"]
    report = json.loads(dateien[f"{S.PROJEKT}.Report/definition/report.json"])
    assert report["themeCollection"]["customTheme"]["name"] == S.THEMA_NAME


def test_powerbi_ordner_passt_zum_code(dateien):
    """powerbi/ im Repository ist mit  python sternschema.py  aus diesem Code erzeugt."""
    ordner = HIER / "powerbi"
    vorhanden = {p.relative_to(ordner).as_posix() for p in ordner.rglob("*") if p.is_file()
                 and ".pbi/" not in p.relative_to(ordner).as_posix()}
    assert vorhanden == set(dateien)
    for pfad, text in dateien.items():
        assert (ordner / pfad).read_text(encoding="utf-8") == text, f"{pfad} veraltet: python sternschema.py"


def test_zip(stern):
    excel = b"PK-test"
    z = zipfile.ZipFile(io.BytesIO(S.projekt_zip(stern, excel, "meine_daten_sternschema.xlsx")))
    namen = z.namelist()
    assert f"{S.PROJEKT}.pbip" in namen and "meine_daten_sternschema.xlsx" in namen and "LIESMICH.txt" in namen
    ausdruck = z.read(f"{S.PROJEKT}.SemanticModel/definition/expressions.tmdl").decode()
    assert r'"C:\Cockpit\meine_daten_sternschema.xlsx"' in ausdruck


def test_kennzahlen_wie_cockpit_fuer_ein_jahr(alt, stern):
    """Die einfachen DAX-Kennzahlen in pandas nachgerechnet: Jahr 2018 wie die Cockpit-Rechnung."""
    u, f = stern["fakt_umsatz"], stern["fakt_fixkosten"]
    j = u[u.auftragsdatum.dt.year == 2018]
    ebit = j.db1.sum() - f[f.monat.dt.year == 2018].ist.sum()
    flach = alt["fakt_umsatz"].query("jahr == 2018")
    assert ebit == pytest.approx(flach.db1.sum() - alt["fakt_fixkosten"].query("monat.dt.year == 2018").ist.sum())
    assert np.isclose(j.db1.sum() / j.umsatz.sum(), flach.db1.sum() / flach.umsatz.sum())


def test_diagramme_haben_lesbar_wenige_beschriftungen(stern):
    """Jede Zahl im Diagramm soll lesbar sein: höchstens 40 Beschriftungen (Kategorien x Reihen) je Diagramm."""
    for sid, *_, links, rechts in S.SEITEN:
        for typ, titel, kategorien, kennzahlen, _ in (links, rechts):
            if typ == "tableEx":
                continue
            t, s, _ = kategorien[0]
            n = stern[t][s].nunique() * len(kennzahlen)
            assert n <= 40, f"{sid}: '{titel}' hätte {n} Beschriftungen"
