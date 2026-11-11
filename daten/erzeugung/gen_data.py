"""
Unternehmer-Cockpit · Datengrundlage aus dem Unicorn-Projekt
=============================================================
Eingang : cockpit_export_positionen.csv  (Beekeeper-Export, 9.997 Positionen, ECHT)
Ausgang : out/*.csv + out/unicorn_cockpit.sqlite

ECHT       = unverändert aus der Unicorn-Datenbank
SIMULIERT  = für Übungszwecke ergänzt, Annahmen siehe daten_dokumentation.md
Reproduzierbar über SEED.
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "raw.csv")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "out")
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------------ 1 Ist-Umsatz
d = pd.read_csv(SRC, parse_dates=["order_date", "shipping_date"])
d = d.rename(columns={
    "order_details_id": "position_id", "order_id": "auftrag_id",
    "order_date": "auftragsdatum", "shipping_date": "versanddatum",
    "shipping_mode": "versandart", "shipping_region": "region",
    "shipping_state": "bundesstaat", "shipping_city": "stadt",
    "customer_id": "kunde_id", "customer_name": "kunde", "customer_segment": "segment",
    "product_id": "produkt_id", "product_name": "produkt",
    "product_category": "kategorie", "product_subcategory": "subkategorie",
    "quantity": "menge", "order_discount": "rabatt",
    "order_sales": "umsatz", "order_profits": "db1",
})
assert len(d) == 9997 and d.umsatz.sum() == 2_307_249 and d.db1.sum() == 289_956

d["rabattstufe"] = pd.cut(d.rabatt, [-1, 0, 0.2, 1], labels=["0 %", "1–20 %", "> 20 %"]).astype(str)
d["listenumsatz"] = (d.umsatz / (1 - d.rabatt)).round(2)
d["rabattbetrag"] = (d.listenumsatz - d.umsatz).round(2)

# SIMULIERT: Aufteilung der variablen Kosten (Umsatz − DB I) in Versand und Wareneinsatz
versand_satz = {"Same Day": 0.06, "First Class": 0.04, "Second Class": 0.03, "Standard Class": 0.02}
var_kosten = d.umsatz - d.db1
d["versandkosten"] = np.minimum((d.umsatz * d.versandart.map(versand_satz)).round(2), var_kosten.clip(lower=0))
d["wareneinsatz"] = (var_kosten - d.versandkosten).round(2)
d["jahr"] = d.auftragsdatum.dt.year
d["monat"] = d.auftragsdatum.dt.to_period("M").dt.to_timestamp()

# ------------------------------------------------------------------ 2 Planung (SIMULIERT)
# Jeder Plan wird Ende des Vorjahres aus den Vorjahres-Istwerten gebaut.
wachstum = {  # Planwachstum je Region, so wie es die Geschäftsführung festgelegt hätte
    2016: {"West": .10, "East": .08, "Central": .06, "South": .06},
    2017: {"West": .12, "East": .10, "Central": .08, "South": .10},
    2018: {"West": .20, "East": .15, "Central": .08, "South": .15},
    2019: {"West": .15, "East": .12, "Central": .05, "South": .12},
}
margen_ziel_pp = {"Furniture": .015, "Office Supplies": .005, "Technology": .005}  # Margen-Verbesserungsziel

plan_rows = []
for jahr, wg in wachstum.items():
    vj = d[d.jahr == jahr - 1]
    hist = d[d.jahr < jahr]
    saison = (hist.groupby([hist.auftragsdatum.dt.month, "kategorie"]).umsatz.sum()
                  .groupby(level="kategorie").transform(lambda s: s / s.sum()))
    basis = vj.groupby(["region", "kategorie"]).agg(u=("umsatz", "sum"), g=("db1", "sum"))
    for (reg, kat), r in basis.iterrows():
        jahresplan = r.u * (1 + wg[reg])
        marge = r.g / r.u + margen_ziel_pp[kat]
        for m in range(1, 13):
            u = round(jahresplan * saison.loc[(m, kat)], 2)
            plan_rows.append(dict(monat=pd.Timestamp(jahr, m, 1), region=reg, kategorie=kat,
                                  umsatz_plan=u, db1_plan=round(u * marge, 2)))
plan = pd.DataFrame(plan_rows)

# ------------------------------------------------------------------ 3 Fixkosten (SIMULIERT)
# Inhabergeführter Online-Händler; Unternehmerlohn ist NICHT enthalten (kalkulatorisch separat).
fix_jahr = {2015: 45_000, 2016: 48_000, 2017: 56_000, 2018: 64_000, 2019: 70_000}
anteil = {"Personal": .62, "Miete": .14, "Marketing": .12, "IT & Verwaltung": .12}
mk_saison = np.array([.6, .6, 1.0, .8, .8, .8, .8, .9, 1.4, 1.2, 1.6, 1.5]); mk_saison /= mk_saison.sum()
fix_rows = []
for jahr, summe in fix_jahr.items():
    for art, a in anteil.items():
        for m in range(1, 13):
            p = summe * a * (mk_saison[m - 1] if art == "Marketing" else 1 / 12)
            if jahr == 2019:
                ist = np.nan  # Zukunft
            else:
                abw = rng.normal(0, .04)
                if art == "Marketing" and jahr == 2018 and m >= 9:
                    abw += .25          # eingebautes Signal: Marketing-Überziehung Q4/2018
                if art == "Personal" and jahr == 2018 and m >= 7:
                    abw += .08          # eingebautes Signal: Aushilfe ab Juli 2018
                ist = round(p * (1 + abw), 2)
            fix_rows.append(dict(monat=pd.Timestamp(jahr, m, 1), kostenart=art,
                                 plan=round(p, 2), ist=ist))
fix = pd.DataFrame(fix_rows)

# ------------------------------------------------------------------ 4 Rechnungen & Zahlungen (SIMULIERT)
rech = (d.groupby("auftrag_id")
          .agg(kunde_id=("kunde_id", "first"), segment=("segment", "first"), region=("region", "first"),
               auftragsdatum=("auftragsdatum", "first"), rechnungsdatum=("versanddatum", "first"),
               betrag=("umsatz", "sum"))
          .reset_index())
ziel = {"Consumer": 0, "Home Office": 14, "Corporate": 30}
rech["zahlungsziel_tage"] = rech.segment.map(ziel)
rech["faellig_am"] = rech.rechnungsdatum + pd.to_timedelta(rech.zahlungsziel_tage, "D")

kunden = rech.kunde_id.unique()
verhalten = pd.Series(rng.choice(["pünktlich", "mäßig", "langsam"], len(kunden), p=[.7, .2, .1]), index=kunden)
# eingebautes Signal: fünf große Corporate-Kunden in Central zahlen ab Juli 2018 deutlich später
grosse_central = (rech[(rech.segment == "Corporate") & (rech.region == "Central")]
                  .groupby("kunde_id").betrag.sum().nlargest(5).index)

def verzug(row):
    if row.segment == "Consumer":
        return 0
    v = verhalten[row.kunde_id]
    t = {"pünktlich": rng.integers(-2, 4), "mäßig": rng.integers(5, 21), "langsam": rng.integers(20, 61)}[v]
    if row.kunde_id in grosse_central and row.rechnungsdatum >= pd.Timestamp(2018, 7, 1):
        t += int(rng.integers(30, 60))
    return int(t)

rech["verzug_tage"] = rech.apply(verzug, axis=1)
rech["bezahlt_am"] = rech.faellig_am + pd.to_timedelta(rech.verzug_tage, "D")
rech.loc[rech.segment == "Consumer", "bezahlt_am"] = rech.auftragsdatum   # Kartenzahlung bei Bestellung
ausfall = (rech.segment != "Consumer") & (rng.random(len(rech)) < .005)
rech.loc[ausfall, "bezahlt_am"] = pd.NaT
rech["status"] = np.where(ausfall, "uneinbringlich", "bezahlt")

# ------------------------------------------------------------------ 5 Liquidität je Tag (SIMULIERT)
STARTKASSE = 60_000
ENTNAHME_MONAT = 1_000   # Privatentnahme Inhaber, Monatsende
ein = rech.dropna(subset=["bezahlt_am"]).groupby("bezahlt_am").betrag.sum()
aus_ware = d.groupby("auftragsdatum").wareneinsatz.sum()           # Einkauf auf Ziel ≈ bei Auftrag fällig
aus_versand = d.groupby("versanddatum").versandkosten.sum()
fx = fix.dropna(subset=["ist"]).copy()
tag = {"Personal": 28, "Miete": 1, "Marketing": 15, "IT & Verwaltung": 15}
fx["datum"] = fx.apply(lambda r: r.monat + pd.Timedelta(days=tag[r.kostenart] - 1), axis=1)
aus_fix = fx.groupby("datum").ist.sum()
entnahme = pd.Series(ENTNAHME_MONAT, index=pd.date_range("2015-01-31", "2018-12-31", freq="ME"))

tage = pd.date_range("2015-01-01", "2018-12-31", freq="D")
liq = pd.DataFrame(index=tage)
liq["einzahlungen"] = ein.reindex(tage, fill_value=0)
liq["auszahlungen_ware"] = aus_ware.reindex(tage, fill_value=0)
liq["auszahlungen_versand"] = aus_versand.reindex(tage, fill_value=0)
liq["auszahlungen_fix"] = aus_fix.reindex(tage, fill_value=0)
liq["privatentnahme"] = entnahme.reindex(tage, fill_value=0)
liq["saldo_tag"] = liq.einzahlungen - liq[["auszahlungen_ware", "auszahlungen_versand", "auszahlungen_fix", "privatentnahme"]].sum(axis=1)
liq["kontostand"] = STARTKASSE + liq.saldo_tag.cumsum()
liq = liq.round(2).rename_axis("datum").reset_index()
# Rechnungen, die erst 2019 bezahlt werden, bleiben in den Daten (offene Posten zum 31.12.2018)

# ------------------------------------------------------------------ 6 Ausgabe
umsatz_cols = ["position_id", "auftrag_id", "auftragsdatum", "versanddatum", "monat", "jahr", "versandart",
               "region", "bundesstaat", "stadt", "kunde_id", "kunde", "segment", "produkt_id", "produkt",
               "kategorie", "subkategorie", "menge", "rabatt", "rabattstufe", "listenumsatz", "rabattbetrag",
               "umsatz", "wareneinsatz", "versandkosten", "db1"]
tabellen = {
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
con = sqlite3.connect(OUT / "unicorn_cockpit.sqlite")
for name, t in tabellen.items():
    t.to_csv(OUT / f"{name}.csv", index=False)
    t.to_sql(name, con, if_exists="replace", index=False)
con.close()
for name, t in tabellen.items():
    print(f"{name:24s} {len(t):>6} Zeilen")
