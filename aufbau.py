"""Aus bereinigten Bestellpositionen die Tabellen des Cockpits bauen.

Eingang: eine Zeile je Bestellposition mit den Spalten des Unicorn-Exports
(order_details_id, order_id, order_date, … , order_sales, order_profits), siehe ROH_SPALTEN.
Ausgang: die Tabellen aus quelle.TABELLEN (plus dim_produkt), so wie sie in unicorn_cockpit.sqlite liegen.

ECHT       = Umsatz, Menge, Rabatt, DB I je Position (aus dem Eingang)
SIMULIERT  = Plan, Fixkosten, Zahlungen, Kontostand (Annahmen siehe daten/daten_dokumentation.md)

Mit den Unicorn-Positionen und Seed 42 entsteht exakt die heutige SQLite-Datei (siehe Test).
Für andere Zeiträume oder Regionen gelten Standardannahmen (z. B. 10 % Planwachstum).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42

# Spalten des Rohexports (cockpit_export.sql) und ihre deutschen Namen im Cockpit
ROH_SPALTEN = {
    "order_details_id": "position_id", "order_id": "auftrag_id",
    "order_date": "auftragsdatum", "shipping_date": "versanddatum",
    "shipping_mode": "versandart", "shipping_region": "region",
    "shipping_state": "bundesstaat", "shipping_city": "stadt",
    "customer_id": "kunde_id", "customer_name": "kunde", "customer_segment": "segment",
    "product_id": "produkt_id", "product_name": "produkt",
    "product_category": "kategorie", "product_subcategory": "subkategorie",
    "quantity": "menge", "order_discount": "rabatt",
    "order_sales": "umsatz", "order_profits": "db1",
}

# ---------------------------------------------------------------- Annahmen (Unicorn) und Standardwerte
WACHSTUM = {  # Planwachstum je Region, so wie es die Geschäftsführung festgelegt hätte
    2016: {"West": .10, "East": .08, "Central": .06, "South": .06},
    2017: {"West": .12, "East": .10, "Central": .08, "South": .10},
    2018: {"West": .20, "East": .15, "Central": .08, "South": .15},
    2019: {"West": .15, "East": .12, "Central": .05, "South": .12},
}
WACHSTUM_STANDARD = .10
MARGEN_ZIEL_PP = {"Furniture": .015, "Office Supplies": .005, "Technology": .005}
MARGEN_ZIEL_STANDARD = .005
FIX_JAHR = {2015: 45_000, 2016: 48_000, 2017: 56_000, 2018: 64_000, 2019: 70_000}
FIX_QUOTE_STANDARD = .09          # Fixkostenbudget ≈ 9 % vom Vorjahresumsatz (Unicorn 2015: 45 Tsd. / 497 Tsd.)
FIX_ANTEIL = {"Personal": .62, "Miete": .14, "Marketing": .12, "IT & Verwaltung": .12}
FIX_ZAHLTAG = {"Personal": 28, "Miete": 1, "Marketing": 15, "IT & Verwaltung": 15}
VERSAND_SATZ = {"Same Day": 0.06, "First Class": 0.04, "Second Class": 0.03, "Standard Class": 0.02}
VERSAND_SATZ_STANDARD = 0.03
ZIEL_TAGE = {"Consumer": 0, "Home Office": 14, "Corporate": 30}
ZIEL_TAGE_STANDARD = 14
STARTKASSE = 60_000
ENTNAHME_MONAT = 1_000


def roh_aus_fakt(fakt_umsatz: pd.DataFrame) -> pd.DataFrame:
    """Rohexport aus der Tabelle fakt_umsatz zurückgewinnen (alle 19 Spalten sind dort enthalten)."""
    return fakt_umsatz[list(ROH_SPALTEN.values())].rename(columns={v: k for k, v in ROH_SPALTEN.items()})


def _fixbudget(jahr: int, umsatz_jahr: pd.Series) -> float:
    if jahr in FIX_JAHR:
        return FIX_JAHR[jahr]
    basis = umsatz_jahr.get(jahr - 1, umsatz_jahr.get(jahr, umsatz_jahr.iloc[-1]))
    return float(round(basis * FIX_QUOTE_STANDARD, -3))


def erzeuge_tabellen(roh: pd.DataFrame, seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Baut alle Cockpit-Tabellen aus den bereinigten Positionen (Spalten wie ROH_SPALTEN)."""
    rng = np.random.default_rng(seed)
    d = roh.rename(columns=ROH_SPALTEN).copy()
    for c in ("auftragsdatum", "versanddatum"):
        d[c] = pd.to_datetime(d[c])

    # ------------------------------------------------------------ 1 Ist-Umsatz
    d["rabattstufe"] = pd.cut(d.rabatt, [-1, 0, 0.2, 1], labels=["0 %", "1–20 %", "> 20 %"]).astype(str)
    d["listenumsatz"] = (d.umsatz / (1 - d.rabatt)).round(2)
    d["rabattbetrag"] = (d.listenumsatz - d.umsatz).round(2)
    # SIMULIERT: variable Kosten (Umsatz − DB I) in Versand und Wareneinsatz aufteilen
    var_kosten = d.umsatz - d.db1
    satz = d.versandart.map(VERSAND_SATZ).fillna(VERSAND_SATZ_STANDARD)
    d["versandkosten"] = np.minimum((d.umsatz * satz).round(2), var_kosten.clip(lower=0))
    d["wareneinsatz"] = (var_kosten - d.versandkosten).round(2)
    d["jahr"] = d.auftragsdatum.dt.year
    d["monat"] = d.auftragsdatum.dt.to_period("M").dt.to_timestamp()

    jahre = sorted(d.jahr.unique())
    erstes, letztes = int(jahre[0]), int(jahre[-1])
    plan_jahre = range(erstes + 1, letztes + 2)          # Plan je Folgejahr, auch für das kommende Jahr
    umsatz_jahr = d.groupby("jahr").umsatz.sum()

    # ------------------------------------------------------------ 2 Planung (SIMULIERT)
    plan_rows = []
    for jahr in plan_jahre:
        wg = WACHSTUM.get(jahr, {})
        vj = d[d.jahr == jahr - 1]
        hist = d[d.jahr < jahr]
        if vj.empty:
            continue
        saison = (hist.groupby([hist.auftragsdatum.dt.month, "kategorie"]).umsatz.sum()
                  .groupby(level="kategorie").transform(lambda s: s / s.sum()))
        basis = vj.groupby(["region", "kategorie"]).agg(u=("umsatz", "sum"), g=("db1", "sum"))
        for (reg, kat), r in basis.iterrows():
            jahresplan = r.u * (1 + wg.get(reg, WACHSTUM_STANDARD))
            marge = (r.g / r.u if r.u else 0) + MARGEN_ZIEL_PP.get(kat, MARGEN_ZIEL_STANDARD)
            for m in range(1, 13):
                u = round(jahresplan * saison.get((m, kat), 1 / 12), 2)
                plan_rows.append(dict(monat=pd.Timestamp(jahr, m, 1), region=reg, kategorie=kat,
                                      umsatz_plan=u, db1_plan=round(u * marge, 2)))
    plan = pd.DataFrame(plan_rows, columns=["monat", "region", "kategorie", "umsatz_plan", "db1_plan"])

    # ------------------------------------------------------------ 3 Fixkosten (SIMULIERT)
    # Inhabergeführter Händler; Unternehmerlohn ist NICHT enthalten. Eingebaute Signale im letzten Ist-Jahr.
    mk_saison = np.array([.6, .6, 1.0, .8, .8, .8, .8, .9, 1.4, 1.2, 1.6, 1.5])
    mk_saison /= mk_saison.sum()
    fix_rows = []
    for jahr in range(erstes, letztes + 2):
        summe = _fixbudget(jahr, umsatz_jahr)
        for art, a in FIX_ANTEIL.items():
            for m in range(1, 13):
                p = summe * a * (mk_saison[m - 1] if art == "Marketing" else 1 / 12)
                if jahr > letztes:
                    ist = np.nan  # Zukunft
                else:
                    abw = rng.normal(0, .04)
                    if art == "Marketing" and jahr == letztes and m >= 9:
                        abw += .25          # Signal: Marketing überzieht im Herbst
                    if art == "Personal" and jahr == letztes and m >= 7:
                        abw += .08          # Signal: Aushilfe ab Juli
                    ist = round(p * (1 + abw), 2)
                fix_rows.append(dict(monat=pd.Timestamp(jahr, m, 1), kostenart=art, plan=round(p, 2), ist=ist))
    fix = pd.DataFrame(fix_rows)

    # ------------------------------------------------------------ 4 Rechnungen & Zahlungen (SIMULIERT)
    rech = (d.groupby("auftrag_id")
              .agg(kunde_id=("kunde_id", "first"), segment=("segment", "first"), region=("region", "first"),
                   auftragsdatum=("auftragsdatum", "first"), rechnungsdatum=("versanddatum", "first"),
                   betrag=("umsatz", "sum"))
              .reset_index())
    rech["zahlungsziel_tage"] = rech.segment.map(ZIEL_TAGE).fillna(ZIEL_TAGE_STANDARD).astype(int)
    rech["faellig_am"] = rech.rechnungsdatum + pd.to_timedelta(rech.zahlungsziel_tage, "D")

    kunden = rech.kunde_id.unique()
    verhalten = pd.Series(rng.choice(["pünktlich", "mäßig", "langsam"], len(kunden), p=[.7, .2, .1]),
                          index=kunden)
    # Signal: fünf große Firmenkunden der schwächsten Region zahlen ab Juli des letzten Jahres später
    grosse = (rech[(rech.segment == "Corporate") & (rech.region == "Central")]
              .groupby("kunde_id").betrag.sum().nlargest(5).index)
    ab = pd.Timestamp(letztes, 7, 1)

    def verzug(row):
        if row.segment == "Consumer":
            return 0
        v = verhalten[row.kunde_id]
        t = {"pünktlich": rng.integers(-2, 4), "mäßig": rng.integers(5, 21), "langsam": rng.integers(20, 61)}[v]
        if row.kunde_id in grosse and row.rechnungsdatum >= ab:
            t += int(rng.integers(30, 60))
        return int(t)

    rech["verzug_tage"] = rech.apply(verzug, axis=1)
    rech["bezahlt_am"] = rech.faellig_am + pd.to_timedelta(rech.verzug_tage, "D")
    rech.loc[rech.segment == "Consumer", "bezahlt_am"] = rech.auftragsdatum   # Kartenzahlung bei Bestellung
    ausfall = (rech.segment != "Consumer") & (rng.random(len(rech)) < .005)
    rech.loc[ausfall, "bezahlt_am"] = pd.NaT
    rech["status"] = np.where(ausfall, "uneinbringlich", "bezahlt")

    # ------------------------------------------------------------ 5 Liquidität je Tag (SIMULIERT)
    start, ende = pd.Timestamp(erstes, 1, 1), pd.Timestamp(letztes, 12, 31)
    ein = rech.dropna(subset=["bezahlt_am"]).groupby("bezahlt_am").betrag.sum()
    aus_ware = d.groupby("auftragsdatum").wareneinsatz.sum()
    aus_versand = d.groupby("versanddatum").versandkosten.sum()
    fx = fix.dropna(subset=["ist"]).copy()
    fx["datum"] = fx.apply(lambda r: r.monat + pd.Timedelta(days=FIX_ZAHLTAG[r.kostenart] - 1), axis=1)
    aus_fix = fx.groupby("datum").ist.sum()
    entnahme = pd.Series(ENTNAHME_MONAT, index=pd.date_range(start + pd.offsets.MonthEnd(0), ende, freq="ME"))

    tage = pd.date_range(start, ende, freq="D")
    liq = pd.DataFrame(index=tage)
    liq["einzahlungen"] = ein.reindex(tage, fill_value=0)
    liq["auszahlungen_ware"] = aus_ware.reindex(tage, fill_value=0)
    liq["auszahlungen_versand"] = aus_versand.reindex(tage, fill_value=0)
    liq["auszahlungen_fix"] = aus_fix.reindex(tage, fill_value=0)
    liq["privatentnahme"] = entnahme.reindex(tage, fill_value=0)
    liq["saldo_tag"] = liq.einzahlungen - liq[["auszahlungen_ware", "auszahlungen_versand",
                                               "auszahlungen_fix", "privatentnahme"]].sum(axis=1)
    liq["kontostand"] = STARTKASSE + liq.saldo_tag.cumsum()
    liq = liq.round(2).rename_axis("datum").reset_index()

    # ------------------------------------------------------------ 6 Ausgabe
    umsatz_cols = ["position_id", "auftrag_id", "auftragsdatum", "versanddatum", "monat", "jahr", "versandart",
                   "region", "bundesstaat", "stadt", "kunde_id", "kunde", "segment", "produkt_id", "produkt",
                   "kategorie", "subkategorie", "menge", "rabatt", "rabattstufe", "listenumsatz", "rabattbetrag",
                   "umsatz", "wareneinsatz", "versandkosten", "db1"]
    return {
        "fakt_umsatz": d[umsatz_cols],
        "fakt_plan": plan,
        "fakt_fixkosten": fix,
        "fakt_rechnungen": rech.drop(columns=["segment", "region"]),
        "fakt_liquiditaet_tag": liq,
        "dim_kunde": d.groupby("kunde_id").agg(kunde=("kunde", "first"), segment=("segment", "first"),
                                               hauptregion=("region", lambda s: s.mode()[0])).reset_index()
                      .assign(zahlungsverhalten_sim=lambda x: x.kunde_id.map(verhalten)),
        "dim_produkt": d.groupby("produkt_id").agg(produkt=("produkt", "first"), kategorie=("kategorie", "first"),
                                                   subkategorie=("subkategorie", "first")).reset_index(),
    }


def cockpit_daten(roh: pd.DataFrame, name: str = "Unicorn", seed: int = SEED):
    """Bereinigte Positionen -> logik.Daten, genau so normalisiert wie beim Laden aus SQLite."""
    import logik as L
    import quelle as Q
    tab = erzeuge_tabellen(roh, seed)
    return L.Daten(**{Q.FELD[n]: Q.normalisiere(tab[n], n) for n in Q.TABELLEN}, name=name), tab
