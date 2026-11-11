"""Automatische Prüfung der Kernzahlen des Unternehmer-Cockpits.

Start im Ordner 11_cockpit_app:   python -m pytest -q
Die Sollwerte stammen aus den geprüften Ständen von Schritt 1–4 (Stichtag 31.12.2018).
Schlägt ein Test fehl, hat eine Änderung eine Zahl verschoben – erst klären, dann Sollwert anpassen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import logik as L  # noqa: E402
import quelle as Q  # noqa: E402

S = pd.Timestamp("2018-12-31")


@pytest.fixture(scope="session")
def d():
    if not Path(L.DB_PFAD).exists():
        pytest.skip(f"Datenbank fehlt: {L.DB_PFAD}")
    return L.lade_daten()


@pytest.fixture(scope="session")
def mandanten(d):
    return {m: L.mandant_daten(d, m) for m in L.mandanten(d)}


# ---------------------------------------------------------------- Datenbasis
def test_datenbasis_wie_quelle(d):
    u = d.umsatz
    assert len(u) == 9997
    assert u.auftrag_id.nunique() == 5013
    assert u.kunde_id.nunique() == 793
    assert u.umsatz.sum() == 2_307_249
    assert u.db1.sum() == 289_956
    assert u.groupby("jahr").umsatz.sum().to_dict() == {2015: 497_371, 2016: 470_425,
                                                        2017: 607_904, 2018: 731_549}


def test_variable_kosten_ergeben_db1(d):
    u = d.umsatz
    assert (u.umsatz - u.wareneinsatz - u.versandkosten - u.db1).abs().max() < 0.02


# ---------------------------------------------------------------- Schritt 1/2: Kennzahlen und Signale
def test_kennzahlen_2018(d):
    k = L.kennzahlen(d, S)
    assert k["umsatz"] == 731_549
    assert k["db1"] == 92_943
    assert k["umsatz_abw"] == pytest.approx(0.0478, abs=5e-4)
    assert k["db1_abw"] == pytest.approx(-0.0627, abs=5e-4)
    assert k["ebit"] == pytest.approx(26_624.63, abs=0.01)
    assert k["ebit_plan"] == pytest.approx(35_165.96, abs=0.01)
    assert k["kontostand"] == pytest.approx(42_958.44, abs=0.01)


def test_signale_2018(d):
    titel = [x.titel for x in L.signale(d, S)]
    for erwartet in ("Umsatz über Plan, DB I darunter", "Central unter Plan",
                     "Marketing über Plan", "Personal über Plan", "Laura Armstrong zahlt später"):
        assert erwartet in titel


# ---------------------------------------------------------------- Schritt 3: Mandanten und Benchmark
def test_mandanten_ergeben_firma(d, mandanten):
    assert sorted(mandanten) == ["Central", "East", "South", "West"]
    ebit = sum(L.kennzahlen(m, S)["ebit"] for m in mandanten.values())
    assert ebit == pytest.approx(L.kennzahlen(d, S)["ebit"], abs=0.5)
    konto = sum(m.liq.kontostand.iloc[-1] for m in mandanten.values())
    assert konto == pytest.approx(d.liq.kontostand.iloc[-1], abs=0.5)


def test_portfolio_2018(d):
    pf = L.portfolio(d, S).set_index("mandant")
    assert pf.loc["Central", "umsatz_abw"] == pytest.approx(-0.0762, abs=5e-4)
    assert pf.loc["Central", "ebit"] == pytest.approx(-7_563.54, abs=0.01)
    assert pf.loc["Central", "kontostand"] == pytest.approx(-10_817.73, abs=0.01)
    assert pf.loc["Central", "liq_min"] == pytest.approx(-14_265.29, abs=0.01)
    assert pf.loc["Central", "liq_ampel"] == "rot"
    assert pf.loc["South", "umsatz_abw"] == pytest.approx(0.1579, abs=5e-4)
    assert pf.loc["East", "ebit"] == pytest.approx(13_018.84, abs=0.01)
    assert pf.loc["West", "ebit"] == pytest.approx(22_407.92, abs=0.01)


def test_benchmark_2018(d):
    bm = L.benchmark(d, S).set_index("kz")
    assert bm.loc["rohertrag", "branche"] == pytest.approx(33.1, abs=0.01)
    assert bm.loc["dso", "branche"] == pytest.approx(11.47, abs=0.01)
    assert bm.loc["dso", "gesamt"] == pytest.approx(20.11, abs=0.01)
    assert bm.loc["rendite", "Central"] == pytest.approx(-5.14, abs=0.01)
    besser = sum((bm.gesamt > bm.branche) == bm.hoch_gut)
    assert besser == 3


def test_benchmark_ohne_volles_vorjahr(d):
    bm = L.benchmark(d, pd.Timestamp("2016-01-31"))
    assert "wachstum" not in set(bm.kz)                    # Vorjahr 02/2014–01/2015 fehlt
    assert set(L.benchmark(d, pd.Timestamp("2016-12-31")).kz) >= {"wachstum"}


def test_branche_jahr_begrenzt():
    assert L.branche(2014) == L.branche(2015)
    assert L.branche(2025) == L.branche(2018)


# ---------------------------------------------------------------- Schritt 4: Quellen-Abgleich
def _wie_powerbi(tab: dict) -> dict:
    """Simuliert, was Power BI liefert: Spalten als tabelle[spalte], Ganzzahlen als Kommazahl,
    Datum mal als Excel-Seriennummer, mal mit anderer Genauigkeit, andere Zeilenfolge."""
    aus = {}
    for n, df in tab.items():
        x = df.copy()
        for c in Q.TABELLEN[n]["datum"]:
            if n == "fakt_fixkosten":
                x[c] = (x[c] - pd.Timestamp("1899-12-30")).dt.days.astype(float)
            else:
                x[c] = x[c].astype("datetime64[us]")
        for c in Q.TABELLEN[n]["ganz"]:
            x[c] = x[c].astype(float)
        x = x.rename(columns=lambda c: f"{n}[{c.upper()}]").sample(frac=1, random_state=1)
        aus[n] = Q.normalisiere(x, n)
    return aus


def test_abgleich_identisch(d):
    sq = Q.lade_sqlite(L.DB_PFAD)
    erg = Q.abgleich(_wie_powerbi(sq), sq)
    assert (erg.Ergebnis == "identisch").all(), erg.to_string()


def test_abgleich_findet_abweichung():
    sq = Q.lade_sqlite(L.DB_PFAD)
    pb = _wie_powerbi(sq)
    pb["fakt_umsatz"].loc[0, "umsatz"] += 1
    erg = Q.abgleich(pb, sq).set_index("Tabelle")
    assert "umsatz" in erg.loc["fakt_umsatz", "Ergebnis"]
    assert erg.loc["dim_kunde", "Ergebnis"] == "identisch"


def test_powerbi_quelle_rechnet_gleich(d, monkeypatch):
    pb = _wie_powerbi(Q.lade_sqlite(L.DB_PFAD))
    monkeypatch.setattr(Q, "lade_powerbi", lambda port: pb)
    d2 = L.lade_daten(quelle="powerbi", port=1)
    assert L.portfolio(d2, S).equals(L.portfolio(d, S))


def test_fehlende_spalte_meldet_verstaendlich():
    df = pd.DataFrame({"monat": ["2018-01-01"], "kostenart": ["Miete"], "plan": [1.0]})
    with pytest.raises(Q.QuellenFehler, match="ist"):
        Q.normalisiere(df, "fakt_fixkosten")


# ---------------------------------------------------------------- Formate
def test_deutsche_zahlenformate():
    assert L.geld(731549) == "731.549 $"
    assert L.proz(0.0478) == "+4,8 %"


# ---------------------------------------------------------------- Datenschutz und Zugänge
def test_pseudonymisieren_ohne_klarnamen(d):
    p = L.pseudonymisieren(d)
    namen = set(d.kunde.kunde)
    texte = " ".join(x.titel + " " + x.text for x in L.signale(p, S)) + L.montags_briefing(p, S)
    assert not any(n in texte for n in namen if len(n) > 5)
    assert "Kunde 0" in texte
    assert L.kennzahlen(p, S) == L.kennzahlen(d, S)          # Zahlen unverändert
    assert set(d.kunde.kunde) == namen                        # Original nicht verändert


def test_zugaenge(tmp_path, monkeypatch):
    import zugang as Z
    monkeypatch.setattr(Z, "DATEI", tmp_path / "zugaenge.json")
    Z.speichern(Z.demo_anlegen())
    z = Z.laden()
    assert "demo-berater" not in (tmp_path / "zugaenge.json").read_text()   # kein Klartext
    assert Z.pruefen(z, "Central", "demo-central") == {"name": "central", "rolle": "mandant", "mandant": "Central"}
    assert Z.pruefen(z, "central", "falsch") is None
    assert Z.pruefen(z, "unbekannt", "demo-central") is None
    assert Z.pruefen(z, "berater", "demo-berater")["rolle"] == "berater"
    with pytest.raises(ValueError):
        Z.anlegen(z, "x", "mandant", "langespasswort", "Nord")
    with pytest.raises(ValueError):
        Z.anlegen(z, "x", "berater", "kurz")


# ---------------------------------------------------------------- Zweisprachigkeit und Online-Demo
def test_englisch_formate_und_texte(d):
    import sprache as Sp
    try:
        Sp.setze("en")
        assert L.geld(-10818.4) == "−$10,818"
        assert L.proz(0.0478) == "+4.8%"
        assert L.datum(S) == "31 Dec 2018"
        assert "Revenue up to Dec 2018 is $731,549" in L.kurztext(d, S)
        ids_en = [x.id for x in L.signale(d, S)]
    finally:
        Sp.setze("de")
    assert ids_en == [x.id for x in L.signale(d, S)]          # Schlüssel unabhängig von der Sprache
    assert L.geld(-10818.4) == "−10.818 $"


def test_massnahmen_nur_in_der_sitzung(tmp_path, monkeypatch):
    import massnahmen as Mn
    monkeypatch.setattr(Mn, "PFAD", tmp_path / "m.sqlite")
    sitzung = {}
    Mn.setze("Central", sitzung)
    Mn.anlegen("Rabatte deckeln", "Marge", 1000.0)
    assert len(Mn.laden()) == 1
    Mn.setze("Central", None)                                    # Datei: bleibt leer
    assert len(Mn.laden()) == 0
    Mn.setze("East", sitzung)                                    # anderer Mandant sieht nichts
    assert len(Mn.laden()) == 0


@pytest.mark.parametrize("stichtag", ["2018-12-31", "2017-06-30"])
def test_sql_rechnet_wie_python(d, stichtag):
    """Die SQL-Dateien in sql/ liefern dieselben Zahlen wie die pandas-Logik."""
    import sql_abfragen as Q_SQL
    s = pd.Timestamp(stichtag)
    k = L.kennzahlen(d, s)
    a = Q_SQL.ausfuehren("01_kennzahlen_plan_ist", s).iloc[0]
    for spalte, wert in (("umsatz", k["umsatz"]), ("umsatz_plan", k["umsatz_plan"]), ("db1", k["db1"]),
                         ("db1_plan", k["db1_plan"]), ("fixkosten", k["fix"]), ("ebit", k["ebit"]),
                         ("ebit_plan", k["ebit_plan"])):
        assert a[spalte] == pytest.approx(wert, abs=0.01), spalte

    r = Q_SQL.ausfuehren("02_rabattstufen", s).set_index("rabattstufe")
    p = L.rabatt_profil(d, s).query("zeitraum == 'Ist'").set_index("rabattstufe")
    assert (r.umsatz == p.umsatz).all() and (r.db1 == p.db1).all() and (r.positionen == p.n).all()

    reg = Q_SQL.ausfuehren("03_regionen_plan_ist", s).set_index("region")
    pr = L.plan_ist_nach(d, s, "region").set_index("region")
    assert reg.umsatz_plan.round(2).equals(pr.umsatz_plan.round(2).reindex(reg.index))

    dso = Q_SQL.ausfuehren("04_forderungslaufzeit", s).iloc[0]
    assert dso.forderungslaufzeit_tage == pytest.approx(L.bench_kennzahlen(d, s)["dso"], abs=0.05)

    kto = Q_SQL.ausfuehren("05_kontostand", s).iloc[0]
    assert kto.kontostand == pytest.approx(k["kontostand"], abs=0.01)

    sk = Q_SQL.ausfuehren("06_saeumige_kunden", s)
    vt = L.verzug_trend(d, s).head(len(sk))
    assert sk.zunahme_tage.tolist() == pytest.approx(vt.delta.tolist(), abs=0.051)


def test_alle_sql_dateien_laufen():
    import sql_abfragen as Q_SQL
    for f in Q_SQL.dateien():
        assert len(Q_SQL.ausfuehren(f.stem, S)) > 0, f.name
