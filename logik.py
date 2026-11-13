"""Berechnungen für das Unternehmer-Cockpit (Unicorn-Daten).

Alle Zahlen kommen aus unicorn_cockpit.sqlite oder aus Power BI Desktop (quelle.py). Plan, Fixkosten und Zahlungsziele
sind simuliert (siehe 10_cockpit_daten/daten_dokumentation.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import sprache as S
from sprache import T

# ---------------------------------------------------------------- Einstellungen
HIER = Path(__file__).resolve().parent
# Reihenfolge: Umgebungsvariable COCKPIT_DB, Projektordner (lokal), Kopie im Repository (online, Tests)
_KANDIDATEN = [HIER.parent / "10_cockpit_daten" / "unicorn_cockpit.sqlite", HIER / "daten" / "unicorn_cockpit.sqlite"]
DB_PFAD = Path(os.environ.get("COCKPIT_DB") or next((p for p in _KANDIDATEN if p.exists()), _KANDIDATEN[-1]))

AMPEL_GELB = -0.05          # bis −5 % unter Plan: gelb, darunter rot
FIX_SIGNAL = 0.05           # Fixkostenart > +5 % über Plan -> Signal
VERZUG_SIGNAL_TAGE = 20     # Kunde zahlt im Schnitt 20+ Tage später als früher
ENTNAHME_MONAT = 1000.0     # simulierte Privatentnahme
PUFFER_MONATE = 1.0         # Liquiditätspuffer = so viele Monate Fixkosten + Entnahme
FIX_SIGNAL_ROT = 0.15       # Fixkostenart ab +15 % über Plan: rot
ZIEL_TAGE = {"Consumer": 0, "Home Office": 14, "Corporate": 30}

# Schwellen, die in der App unter „Frühwarnung“ einstellbar sind
SCHWELLEN_STANDARD = {
    "AMPEL_GELB": AMPEL_GELB, "FIX_SIGNAL": FIX_SIGNAL, "FIX_SIGNAL_ROT": FIX_SIGNAL_ROT,
    "VERZUG_SIGNAL_TAGE": VERZUG_SIGNAL_TAGE, "PUFFER_MONATE": PUFFER_MONATE,
}


def schwellen() -> dict:
    return {k: globals()[k] for k in SCHWELLEN_STANDARD}


def setze_schwellen(werte: dict) -> None:
    """Überschreibt die Schwellen für alle folgenden Berechnungen (nur bekannte Schlüssel)."""
    for k, v in werte.items():
        if k in SCHWELLEN_STANDARD:
            globals()[k] = type(SCHWELLEN_STANDARD[k])(v)


# ---------------------------------------------------------------- Formatierung
def zahl(x: float, nachkomma: int = 0) -> str:
    """Deutsch 1.234,5 · Englisch 1,234.5 (je nach aktiver Sprache)"""
    s = f"{x:,.{nachkomma}f}"
    if not S.en():
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s.replace("-", "−")


def geld(x: float) -> str:
    if S.en():
        z = zahl(abs(x))
        return f"−${z}" if round(x) < 0 else f"${z}"
    return f"{zahl(x)} $"


def tsd(x: float) -> str:
    return T(f"{zahl(x / 1000, 1)} Tsd. $", f"${zahl(x / 1000, 1)}k")


def proz(x: float, vorzeichen: bool = True, nachkomma: int = 1) -> str:
    s = zahl(x * 100, nachkomma)
    if vorzeichen and x > 0:
        s = "+" + s
    return s + T(" %", "%")


def datum(d) -> str:
    return pd.Timestamp(d).strftime(T("%d.%m.%Y", "%d %b %Y"))


def monat(d) -> str:
    return pd.Timestamp(d).strftime(T("%m/%Y", "%b %Y"))


# ---------------------------------------------------------------- Daten laden
@dataclass
class Daten:
    umsatz: pd.DataFrame
    plan: pd.DataFrame
    fix: pd.DataFrame
    rech: pd.DataFrame
    liq: pd.DataFrame
    kunde: pd.DataFrame
    name: str = "Unicorn"              # Firmen- bzw. Mandantenname
    entnahme: float = ENTNAHME_MONAT   # Privatentnahme je Monat
    mandant: str | None = None         # Region, wenn die Daten ein Mandant sind


def lade_daten(pfad: Path | str = DB_PFAD, quelle: str = "sqlite", port: int | None = None) -> Daten:
    """Lädt die sechs Tabellen aus der SQLite-Datei oder aus Power BI Desktop (siehe quelle.py)."""
    import quelle as Q
    tab = Q.lade_powerbi(port) if quelle == "powerbi" else Q.lade_sqlite(pfad)
    return Daten(**{Q.FELD[n]: df for n, df in tab.items()})


def pseudonymisieren(d: Daten) -> Daten:
    """Ersetzt Kundennamen durch „Kunde 0123“ (aus der Kunden-ID). Alle Auswertungen bleiben gleich."""
    from dataclasses import replace
    k = d.kunde.copy()
    k["kunde"] = T("Kunde ", "Customer ") + k.kunde_id.astype(str).str.zfill(4)
    u = d.umsatz.copy()
    u["kunde"] = T("Kunde ", "Customer ") + u.kunde_id.astype(str).str.zfill(4)
    return replace(d, kunde=k, umsatz=u)


def stichtage(d: Daten) -> list[pd.Timestamp]:
    """Monatsenden, für die es Ist und Plan gibt."""
    erster_plan = d.plan.monat.min()
    letzter_ist = d.umsatz.monat.max()
    monate = pd.date_range(erster_plan, letzter_ist, freq="MS")
    return [m + pd.offsets.MonthEnd(0) for m in monate]


def _ytd(df: pd.DataFrame, spalte: str, stichtag: pd.Timestamp, vorjahr=False):
    s = stichtag - pd.DateOffset(years=1) if vorjahr else stichtag
    start = pd.Timestamp(s.year, 1, 1)
    return df[(df[spalte] >= start) & (df[spalte] <= s)]


# ---------------------------------------------------------------- KPIs
def ampel(abw: float) -> str:
    if abw >= 0:
        return "grün"
    return "gelb" if abw >= AMPEL_GELB else "rot"


def kennzahlen(d: Daten, s: pd.Timestamp) -> dict:
    u, u_vj = _ytd(d.umsatz, "monat", s), _ytd(d.umsatz, "monat", s, True)
    p = _ytd(d.plan, "monat", s)
    f = _ytd(d.fix, "monat", s)
    k = {
        "umsatz": u.umsatz.sum(), "umsatz_plan": p.umsatz_plan.sum(), "umsatz_vj": u_vj.umsatz.sum(),
        "db1": u.db1.sum(), "db1_plan": p.db1_plan.sum(), "db1_vj": u_vj.db1.sum(),
        "fix": f.ist.sum(), "fix_plan": f.plan.sum(),
    }
    k["ebit"] = k["db1"] - k["fix"]
    k["ebit_plan"] = k["db1_plan"] - k["fix_plan"]
    k["marge"] = k["db1"] / k["umsatz"]
    k["marge_plan"] = k["db1_plan"] / k["umsatz_plan"]
    for x in ("umsatz", "db1"):
        k[f"{x}_abw"] = k[x] / k[f"{x}_plan"] - 1
        k[f"{x}_vj_abw"] = k[x] / k[f"{x}_vj"] - 1 if k[f"{x}_vj"] else np.nan
    k["ebit_abw"] = (k["ebit"] - k["ebit_plan"]) / abs(k["ebit_plan"])
    k["kontostand"] = d.liq.loc[d.liq.datum <= s, "kontostand"].iloc[-1]
    return k


# ---------------------------------------------------------------- Plan-Ist
SEGMENT = ["region", "kategorie"]


def plan_ist_segmente(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    ist = _ytd(d.umsatz, "monat", s).groupby(SEGMENT)[["umsatz", "db1"]].sum()
    plan = _ytd(d.plan, "monat", s).groupby(SEGMENT)[["umsatz_plan", "db1_plan"]].sum()
    return ist.join(plan, how="outer").fillna(0).reset_index()


def plan_ist_nach(d: Daten, s: pd.Timestamp, dim: str) -> pd.DataFrame:
    t = plan_ist_segmente(d, s).groupby(dim)[["umsatz", "umsatz_plan", "db1", "db1_plan"]].sum()
    t["abw"] = t.umsatz - t.umsatz_plan
    t["abw_proz"] = t.umsatz / t.umsatz_plan - 1
    t["db1_abw"] = t.db1 - t.db1_plan
    return t.sort_values("abw_proz").reset_index()


def plan_ist_monate(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    ist = _ytd(d.umsatz, "monat", s).groupby("monat")[["umsatz", "db1"]].sum()
    plan = _ytd(d.plan, "monat", s).groupby("monat")[["umsatz_plan", "db1_plan"]].sum()
    t = ist.join(plan, how="outer").fillna(0)
    t["abw_proz"] = t.umsatz / t.umsatz_plan - 1
    return t.reset_index()


def db_zerlegung(d: Daten, s: pd.Timestamp) -> dict:
    """DB-I-Abweichung = Mengen- + Mix- + Preis/Rabatt-Effekt (exakt, Segmente Region × Kategorie).

    Menge: (U_ist − U_plan) · Marge_plan gesamt
    Mix:   Σ U_ist,i · m_plan,i − U_ist · Marge_plan gesamt
    Preis/Rabatt: Σ U_ist,i · (m_ist,i − m_plan,i)
    """
    t = plan_ist_segmente(d, s)
    t = t[t.umsatz_plan > 0]
    m_plan_i = t.db1_plan / t.umsatz_plan
    m_ist_i = np.where(t.umsatz > 0, t.db1 / t.umsatz.replace(0, np.nan), m_plan_i)
    m_plan = t.db1_plan.sum() / t.umsatz_plan.sum()
    u_ist = t.umsatz.sum()
    menge = (u_ist - t.umsatz_plan.sum()) * m_plan
    mix = (t.umsatz * m_plan_i).sum() - u_ist * m_plan
    preis = (t.umsatz * (m_ist_i - m_plan_i)).sum()
    rest = (t.db1.sum() - t.db1_plan.sum()) - (menge + mix + preis)
    return {"plan": t.db1_plan.sum(), "menge": menge, "mix": mix,
            "preis": preis + rest, "ist": t.db1.sum()}


def rabatt_profil(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    """Umsatzanteil und DB I je Rabattstufe, YTD gegen Vorjahr."""
    zeilen = []
    for lbl, vj in (("Ist", False), ("Vorjahr", True)):
        u = _ytd(d.umsatz, "monat", s, vj)
        g = u.groupby("rabattstufe")[["umsatz", "db1", "rabattbetrag"]].sum()
        g["anteil"] = g.umsatz / g.umsatz.sum()
        g["n"] = u.groupby("rabattstufe").size()
        g["zeitraum"] = lbl
        zeilen.append(g.reset_index())
    return pd.concat(zeilen, ignore_index=True)


def fix_plan_ist(d: Daten, s: pd.Timestamp, monate: int | None = None) -> pd.DataFrame:
    f = _ytd(d.fix, "monat", s)
    if monate:
        f = f[f.monat > (s - pd.DateOffset(months=monate))]
    t = f.groupby("kostenart")[["plan", "ist"]].sum()
    t["abw"] = t.ist - t.plan
    t["abw_proz"] = t.ist / t.plan - 1
    return t.sort_values("abw_proz", ascending=False).reset_index()


# ---------------------------------------------------------------- Forderungen & Verzug
def offene_posten(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    r = d.rech[(d.rech.rechnungsdatum <= s) &
               ((d.rech.bezahlt_am > s) | d.rech.bezahlt_am.isna())].copy()
    r["ueberfaellig_tage"] = (s - r.faellig_am).dt.days.clip(lower=0)
    return r.merge(d.kunde[["kunde_id", "kunde", "segment", "hauptregion"]], on="kunde_id")


def saeumige_kunden(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    op = offene_posten(d, s)
    op = op[(op.ueberfaellig_tage > 0) & (op.status != "uneinbringlich")]
    if op.empty:
        return pd.DataFrame(columns=["kunde_id", "kunde", "segment", "region", "offen",
                                     "rechnungen", "max_tage", "verzug_vorher", "verzug_6m"])
    g = op.groupby(["kunde_id", "kunde", "segment", "hauptregion"]).agg(
        offen=("betrag", "sum"), rechnungen=("auftrag_id", "count"),
        max_tage=("ueberfaellig_tage", "max")).reset_index()
    g = g.rename(columns={"hauptregion": "region"})
    trend = verzug_trend(d, s)
    g = g.merge(trend[["kunde_id", "verzug_vorher", "verzug_6m"]], on="kunde_id", how="left")
    return g.sort_values(["offen", "max_tage"], ascending=False)


def verzug_trend(d: Daten, s: pd.Timestamp, min_rech: int = 3) -> pd.DataFrame:
    """Durchschnittlicher Zahlungsverzug je Kunde: letzte 6 Monate vs. die 12 Monate davor."""
    r = d.rech[(d.rech.status == "bezahlt") & (d.rech.bezahlt_am <= s) & (d.rech.zahlungsziel_tage > 0)]
    grenze = s - pd.DateOffset(months=6)
    neu = r[r.faellig_am > grenze].groupby("kunde_id").verzug_tage.agg(["mean", "count"])
    alt = r[(r.faellig_am <= grenze) & (r.faellig_am > grenze - pd.DateOffset(months=12))] \
        .groupby("kunde_id").verzug_tage.agg(["mean", "count"])
    t = neu.join(alt, lsuffix="_6m", rsuffix="_vorher", how="inner")
    t = t[(t.count_6m >= 1) & (t.count_vorher >= 1) & (t.count_6m + t.count_vorher >= min_rech)]
    t = t.rename(columns={"mean_6m": "verzug_6m", "mean_vorher": "verzug_vorher"})
    t["delta"] = t.verzug_6m - t.verzug_vorher
    return t.reset_index().merge(d.kunde[["kunde_id", "kunde", "segment", "hauptregion"]], on="kunde_id") \
        .sort_values("delta", ascending=False)


def verzug_verteilung(d: Daten, s: pd.Timestamp) -> pd.Series:
    """Verzugstage der Rechnungen mit Zahlungsziel, bezahlt in den 12 Monaten vor Stichtag."""
    r = d.rech[(d.rech.status == "bezahlt") & (d.rech.zahlungsziel_tage > 0) &
               (d.rech.bezahlt_am <= s) & (d.rech.bezahlt_am > s - pd.DateOffset(months=12))]
    return r.verzug_tage


# ---------------------------------------------------------------- Liquidität 13 Wochen
def liquiditaet_prognose(d: Daten, s: pd.Timestamp, wochen: int = 13, szen: dict | None = None) -> dict:
    """Tagesgenaue Fortschreibung des Kontostands, wöchentlich zusammengefasst.

    Einzahlungen: offene Rechnungen zum erwarteten Zahltag (fällig + bisheriger Kundenverzug;
                  bereits überfällige ab Stichtag + Kundenverzug, uneinbringliche gar nicht)
                + Neugeschäft laut Plan, nach Segment-Mix der letzten 12 Monate verzögert.
    Auszahlungen: Wareneinsatz + Versand (Quote der letzten 12 Monate) auf Plan-Umsatz,
                  Fixkosten laut Plan, Privatentnahme am Monatsende.
    szen (optional, aus szenario()): umsatz_faktor, kosten_quote, fix_faktor, verzug_extra.
    """
    szen = szen or {}
    u_faktor = szen.get("umsatz_faktor", 1.0)
    fix_faktor = szen.get("fix_faktor", 1.0)
    extra = int(szen.get("verzug_extra", 0))
    ende = s + pd.Timedelta(weeks=wochen)
    tage = pd.date_range(s + pd.Timedelta(days=1), ende, freq="D")
    ein = pd.Series(0.0, index=tage)
    aus = pd.Series(0.0, index=tage)

    # 1) offene Posten
    hist = d.rech[(d.rech.status == "bezahlt") & (d.rech.bezahlt_am <= s) & (d.rech.zahlungsziel_tage > 0)]
    kunden_verzug = hist[hist.faellig_am > s - pd.DateOffset(months=6)].groupby("kunde_id").verzug_tage.mean()
    op = offene_posten(d, s)
    op = op[op.status != "uneinbringlich"]
    vz = op.kunde_id.map(kunden_verzug).fillna(0) + extra
    erwartet = op.faellig_am + pd.to_timedelta(vz.round(), "D")
    erwartet = erwartet.where(erwartet > s, s + pd.Timedelta(days=1) + pd.to_timedelta(vz.round(), "D"))
    for t, b in zip(erwartet, op.betrag):
        if t in ein.index:
            ein[t] += b
    op_summe = op.betrag.sum()

    # 2) Neugeschäft laut Plan
    letzte12 = d.umsatz[(d.umsatz.auftragsdatum > s - pd.DateOffset(months=12)) & (d.umsatz.auftragsdatum <= s)]
    seg_anteil = letzte12.groupby("segment").umsatz.sum() / letzte12.umsatz.sum()
    kosten_quote = szen.get("kosten_quote",
                            (letzte12.wareneinsatz.sum() + letzte12.versandkosten.sum()) / letzte12.umsatz.sum())
    seg_verzug = hist[hist.faellig_am > s - pd.DateOffset(months=12)] \
        .merge(d.kunde[["kunde_id", "segment"]], on="kunde_id").groupby("segment").verzug_tage.mean()
    plan_m = d.plan.groupby("monat").umsatz_plan.sum()
    fix_m = d.fix.groupby("monat").plan.sum()
    for t in tage:
        m = t.to_period("M").to_timestamp()
        tage_im_monat = t.days_in_month
        u_tag = plan_m.get(m, np.nan)
        if np.isnan(u_tag):          # kein Plan mehr: Vorjahresmonat Ist
            u_tag = d.umsatz[d.umsatz.monat == m - pd.DateOffset(years=1)].umsatz.sum()
        u_tag = u_tag / tage_im_monat * u_faktor
        aus[t] += u_tag * kosten_quote
        for seg, anteil in seg_anteil.items():
            zahltag = t + pd.Timedelta(days=int(ZIEL_TAGE.get(seg, 0) + round(seg_verzug.get(seg, 0)) + extra))
            if zahltag in ein.index:
                ein[zahltag] += u_tag * anteil
        aus[t] += fix_m.get(m, fix_m.iloc[-1]) / tage_im_monat * fix_faktor
        if t == t + pd.offsets.MonthEnd(0):
            aus[t] += d.entnahme

    start = d.liq.loc[d.liq.datum <= s, "kontostand"].iloc[-1]
    stand = start + (ein - aus).cumsum()
    woche = pd.DataFrame({"einzahlungen": ein, "auszahlungen": aus}).resample("W-SUN").sum()
    woche["kontostand"] = stand.resample("W-SUN").last()
    puffer = PUFFER_MONATE * (fix_m.get((s + pd.Timedelta(days=1)).to_period("M").to_timestamp(), fix_m.iloc[-1])
                              + d.entnahme)

    vergangen = d.liq[(d.liq.datum > s - pd.Timedelta(weeks=wochen)) & (d.liq.datum <= s)] \
        .set_index("datum").kontostand
    tatsaechlich = d.liq[(d.liq.datum > s) & (d.liq.datum <= ende)].set_index("datum").kontostand
    # tiefster Stand ab heute: der Kontostand am Stichtag zählt mit
    if start <= stand.min():
        minimum, minimum_tag = start, s
    else:
        minimum, minimum_tag = stand.min(), stand.idxmin()
    return {
        "start": start, "tag": stand, "woche": woche, "puffer": puffer,
        "minimum": minimum, "minimum_tag": minimum_tag, "ende": stand.iloc[-1],
        "vergangen": vergangen, "tatsaechlich": tatsaechlich,
        "op_summe": op_summe, "kosten_quote": kosten_quote,
    }


def liq_ampel(prog: dict) -> str:
    if prog["minimum"] < 0:
        return "rot"
    return "gelb" if prog["minimum"] < prog["puffer"] else "grün"


# ---------------------------------------------------------------- Signale
@dataclass
class Signal:
    stufe: str      # rot / gelb / grün
    bereich: str    # interner Bereich (deutsch); Anzeige über sprache.B()
    titel: str      # in der aktiven Sprache
    text: str       # in der aktiven Sprache
    id: str = ""    # fester Schlüssel (deutscher Titel), z. B. für Maßnahmen aus Signalen


def _sig(stufe, bereich, titel_de, titel_en, text_de, text_en) -> "Signal":
    return Signal(stufe, bereich, T(titel_de, titel_en), T(text_de, text_en), id=titel_de)


def _am(prog: dict, s: pd.Timestamp) -> str:
    t = prog["minimum_tag"]
    return T(f"am {datum(t)} (heute)", f"on {datum(t)} (today)") if t == s else T(f"am {datum(t)}", f"on {datum(t)}")


def signale(d: Daten, s: pd.Timestamp) -> list[Signal]:
    k = kennzahlen(d, s)
    out: list[Signal] = []
    zr = T(f"Jan–{monat(s)}", f"Jan–{monat(s)}")

    # Umsatz und Marge
    rp = rabatt_profil(d, s)
    hoch = rp[rp.rabattstufe == "> 20 %"].set_index("zeitraum")
    db_hoch, db_hoch_vj = hoch.db1.get("Ist", 0), hoch.db1.get("Vorjahr", 0)
    m_hoch = db_hoch / hoch.umsatz.get("Ist", 1)
    m_hoch_vj = db_hoch_vj / hoch.umsatz.get("Vorjahr", 1)
    zer = db_zerlegung(d, s)
    if k["umsatz_abw"] >= 0 and k["db1_abw"] < 0:
        out.append(_sig(ampel(k["db1_abw"]), "Marge",
            "Umsatz über Plan, DB I darunter", "Revenue above plan, contribution margin below",
            f"Umsatz {proz(k['umsatz_abw'])} gegen Plan, DB I aber {proz(k['db1_abw'])} "
            f"({geld(k['db1'])} statt {geld(k['db1_plan'])}). Der Preis-/Rabatteffekt kostet "
            f"{geld(abs(zer['preis']))}. Treiber: Rabatte über 20 % – DB I in dieser Stufe {geld(db_hoch)} "
            f"(Vorjahr {geld(db_hoch_vj)}), Marge {proz(m_hoch)} (Vorjahr {proz(m_hoch_vj)}).",
            f"Revenue {proz(k['umsatz_abw'])} vs. plan, but contribution margin (CM I) {proz(k['db1_abw'])} "
            f"({geld(k['db1'])} instead of {geld(k['db1_plan'])}). The price/discount effect costs "
            f"{geld(abs(zer['preis']))}. Driver: discounts above 20% – CM I in this tier {geld(db_hoch)} "
            f"(prior year {geld(db_hoch_vj)}), margin {proz(m_hoch)} (prior year {proz(m_hoch_vj)})."))
    else:
        out.append(_sig(ampel(k["umsatz_abw"]), "Umsatz", "Umsatz gegen Plan", "Revenue vs. plan",
            f"Umsatz {zr}: {geld(k['umsatz'])}, {proz(k['umsatz_abw'])} gegen Plan; "
            f"DB I {proz(k['db1_abw'])} gegen Plan.",
            f"Revenue {zr}: {geld(k['umsatz'])}, {proz(k['umsatz_abw'])} vs. plan; "
            f"CM I {proz(k['db1_abw'])} vs. plan."))

    # Regionen
    reg = plan_ist_nach(d, s, "region")
    for _, r in (reg[reg.abw_proz < AMPEL_GELB] if len(reg) > 1 else reg.iloc[0:0]).iterrows():
        out.append(_sig("rot", "Region", f"{r.region} unter Plan", f"{r.region} below plan",
            f"{r.region} liegt {proz(abs(r.abw_proz), False)} unter Plan ({geld(abs(r.abw))} weniger Umsatz). "
            f"DB I-Lücke: {geld(abs(r.db1_abw))}.",
            f"{r.region} is {proz(abs(r.abw_proz), False)} below plan ({geld(abs(r.abw))} less revenue). "
            f"CM I gap: {geld(abs(r.db1_abw))}."))

    # Fixkosten (letzte 4 Monate)
    fx = fix_plan_ist(d, s, monate=4)
    for _, r in fx[fx.abw_proz > FIX_SIGNAL].iterrows():
        out.append(_sig("rot" if r.abw_proz > FIX_SIGNAL_ROT else "gelb", "Fixkosten",
            f"{r.kostenart} über Plan", f"{S.BEGRIFFE.get(r.kostenart, r.kostenart)} above plan",
            f"{r.kostenart} in den letzten 4 Monaten {proz(r.abw_proz)} über Plan, das sind {geld(r.abw)} mehr als geplant.",
            f"{S.BEGRIFFE.get(r.kostenart, r.kostenart)} over the last 4 months {proz(r.abw_proz)} above plan, "
            f"{geld(r.abw)} more than planned."))

    # Zahlungsverhalten
    vt = verzug_trend(d, s)
    for _, r in vt[vt.delta >= VERZUG_SIGNAL_TAGE].head(5).iterrows():
        out.append(_sig("gelb", "Forderungen", f"{r.kunde} zahlt später", f"{r.kunde} is paying later",
            f"{r.kunde} ({r.segment}, {r.hauptregion}) zahlt im Schnitt {zahl(r.verzug_6m)} Tage "
            f"nach Fälligkeit, vorher {zahl(r.verzug_vorher)} Tage (+{zahl(r.delta)}).",
            f"{r.kunde} ({r.segment}, {r.hauptregion}) now pays on average {zahl(r.verzug_6m)} days "
            f"after the due date, previously {zahl(r.verzug_vorher)} days (+{zahl(r.delta)})."))
    op = offene_posten(d, s)
    unein = op[op.status == "uneinbringlich"]
    if len(unein):
        out.append(_sig("gelb", "Forderungen", "Uneinbringliche Rechnungen", "Bad debts",
            f"{len(unein)} Rechnungen über {geld(unein.betrag.sum())} gelten als uneinbringlich.",
            f"{len(unein)} invoices totalling {geld(unein.betrag.sum())} are considered uncollectible."))

    # Liquidität
    prog = liquiditaet_prognose(d, s)
    st = liq_ampel(prog)
    if st != "grün":
        out.append(_sig(st, "Liquidität", "Kontostand unter Puffer", "Cash below buffer",
            f"Tiefster Stand in 13 Wochen: {geld(prog['minimum'])} {_am(prog, s)} "
            f"(Puffer {geld(prog['puffer'])} = {zahl(PUFFER_MONATE, 1)} Monat(e) Fixkosten + Entnahme).",
            f"Lowest balance in 13 weeks: {geld(prog['minimum'])} {_am(prog, s)} "
            f"(buffer {geld(prog['puffer'])} = {zahl(PUFFER_MONATE, 1)} month(s) of fixed costs + owner drawings)."))
    else:
        out.append(_sig("grün", "Liquidität", "Liquidität gesichert", "Liquidity secured",
            f"Tiefster Stand in 13 Wochen: {geld(prog['minimum'])} {_am(prog, s)}, über dem Puffer von {geld(prog['puffer'])}.",
            f"Lowest balance in 13 weeks: {geld(prog['minimum'])} {_am(prog, s)}, above the buffer of {geld(prog['puffer'])}."))

    reihenfolge = {"rot": 0, "gelb": 1, "grün": 2}
    return sorted(out, key=lambda x: reihenfolge[x.stufe])


def kurztext(d: Daten, s: pd.Timestamp) -> str:
    """Zwei, drei Sätze Lagebild für die Startseite."""
    k = kennzahlen(d, s)
    sig = signale(d, s)
    teile = [T(f"Bis {monat(s)} liegt der Umsatz bei {geld(k['umsatz'])} "
               f"({proz(k['umsatz_abw'])} gegen Plan, {proz(k['umsatz_vj_abw'])} gegen Vorjahr).",
               f"Revenue up to {monat(s)} is {geld(k['umsatz'])} "
               f"({proz(k['umsatz_abw'])} vs. plan, {proz(k['umsatz_vj_abw'])} vs. prior year).")]
    marge = next((x for x in sig if x.bereich == "Marge"), None)
    if marge:
        teile.append(T(f"Die Marge hält nicht mit: DB I {proz(k['db1_abw'])} gegen Plan, getrieben von Rabatten über 20 %.",
                       f"Margin is lagging: CM I {proz(k['db1_abw'])} vs. plan, driven by discounts above 20%."))
    else:
        teile.append(T(f"DB I {proz(k['db1_abw'])} gegen Plan, EBIT {geld(k['ebit'])}.",
                       f"CM I {proz(k['db1_abw'])} vs. plan, EBIT {geld(k['ebit'])}."))
    rot = [x for x in sig if x.stufe == "rot" and x.bereich != "Marge"]
    if rot:
        teile.append(T("Größte Baustellen: ", "Biggest issues: ") + ", ".join(x.titel for x in rot[:3]) + ".")
    return " ".join(teile)


def montags_briefing(d: Daten, s: pd.Timestamp, kurz: bool = False) -> str:
    """kurz=True: nur Signal-Titel und Top 3 Säumige (passt in einen mailto-Link)."""
    k = kennzahlen(d, s)
    prog = liquiditaet_prognose(d, s)
    sig = signale(d, s)
    saeumig = saeumige_kunden(d, s)
    montag = s + pd.offsets.Week(weekday=0)
    z = [T(f"Betreff: {d.name} – Wochenbriefing {datum(montag)}", f"Subject: {d.name} – weekly briefing {datum(montag)}"), "",
         T("Guten Morgen,", "Good morning,"), "",
         T(f"hier der Stand zum {datum(s)} (Jahr bis Stichtag):", f"here is the status as of {datum(s)} (year to date):"), "",
         T(f"• Umsatz:  {geld(k['umsatz'])}  ({proz(k['umsatz_abw'])} gegen Plan)",
           f"• Revenue: {geld(k['umsatz'])}  ({proz(k['umsatz_abw'])} vs. plan)"),
         T(f"• DB I:    {geld(k['db1'])}  ({proz(k['db1_abw'])} gegen Plan, Marge {proz(k['marge'], False)})",
           f"• CM I:    {geld(k['db1'])}  ({proz(k['db1_abw'])} vs. plan, margin {proz(k['marge'], False)})"),
         T(f"• EBIT:    {geld(k['ebit'])}  (Plan {geld(k['ebit_plan'])})",
           f"• EBIT:    {geld(k['ebit'])}  (plan {geld(k['ebit_plan'])})"),
         T(f"• Konto:   {geld(k['kontostand'])}; tiefster Stand in 13 Wochen {geld(prog['minimum'])} {_am(prog, s)}",
           f"• Cash:    {geld(k['kontostand'])}; lowest balance in 13 weeks {geld(prog['minimum'])} {_am(prog, s)}"), "",
         T("Was diese Woche Aufmerksamkeit braucht:", "What needs attention this week:")]
    for i, x in enumerate([x for x in sig if x.stufe != "grün"][:5], 1):
        z.append(f"{i}. [{S.B(x.stufe).upper()}] {x.titel}" + ("" if kurz else f": {x.text}"))
    n_top = 3 if kurz else 5
    if not saeumig.empty:
        z += ["", T(f"Offene, überfällige Rechnungen (Top {n_top}):", f"Open overdue invoices (top {n_top}):")]
        for _, r in saeumig.head(n_top).iterrows():
            z.append(T(f"• {r.kunde}: {geld(r.offen)}, seit {int(r.max_tage)} Tagen überfällig",
                       f"• {r.kunde}: {geld(r.offen)}, overdue for {int(r.max_tage)} days"))
    if kurz:
        z += ["", T("Details im Cockpit unter Frühwarnung.", "Details in the cockpit under Early warning.")]
    z += ["", T("Viele Grüße", "Best regards"), T("Dein Unternehmer-Cockpit", "Your Business Cockpit"), "",
          T("Hinweis: Plan, Fixkosten und Zahlungsziele sind simuliert.",
            "Note: plan, fixed costs and payment terms are simulated.")]
    return "\n".join(z)


# ---------------------------------------------------------------- Frühwarnung: Verlauf
def signal_verlauf(d: Daten, s: pd.Timestamp, monate: int = 12) -> pd.DataFrame:
    """Anzahl roter und gelber Signale je Stichtag (letzte n Monate bis s)."""
    alle = [t for t in stichtage(d) if t <= s][-monate:]
    zeilen = []
    for t in alle:
        sig = signale(d, t)
        zeilen.append({"stichtag": t, "rot": sum(x.stufe == "rot" for x in sig),
                       "gelb": sum(x.stufe == "gelb" for x in sig)})
    return pd.DataFrame(zeilen)


# ---------------------------------------------------------------- Was-wäre-wenn
def szenario(d: Daten, s: pd.Timestamp, rabatt_deckel: float | None = None, mengenverlust: float = 0.0,
             umsatz_proz: float = 0.0, fix_proz: float = 0.0, verzug_extra: int = 0) -> dict:
    """Hochrechnung auf Basis der letzten 12 Monate bis Stichtag.

    1. Rabatt-Deckel: Positionen mit Rabatt über dem Deckel bekommen nur noch den Deckel.
       Umsatz = Listenumsatz · (1 − Deckel); Wareneinsatz und Versand bleiben, also steigt DB I um den Mehrumsatz.
    2. Mengenverlust: Anteil dieser gekappten Positionen, der wegfällt (Kunden kaufen nicht mehr).
    3. Umsatzmenge: alle Umsätze ± x %, Marge unverändert.
    4. Fixkosten: ± x % auf die Ist-Fixkosten der letzten 12 Monate.
    """
    u = d.umsatz[(d.umsatz.monat > s - pd.DateOffset(months=12)) & (d.umsatz.monat <= s)].copy()
    f = d.fix[(d.fix.monat > s - pd.DateOffset(months=12)) & (d.fix.monat <= s)].ist.sum()

    def kennz(umsatz, db1, kosten, fix):
        marge = db1 / umsatz if umsatz else 0.0
        be = fix / marge if marge > 0 else np.nan
        return {"umsatz": umsatz, "db1": db1, "kosten": kosten, "fix": fix, "ebit": db1 - fix, "marge": marge,
                "break_even": be, "sicherheit": (umsatz - be) / umsatz if umsatz and be == be else np.nan}

    kosten_basis = u.wareneinsatz.sum() + u.versandkosten.sum()
    basis = kennz(u.umsatz.sum(), u.db1.sum(), kosten_basis, f)

    # 1 + 2 Rabatt-Deckel und Mengenverlust
    betroffen = pd.Series(False, index=u.index)
    if rabatt_deckel is not None:
        betroffen = u.rabatt > rabatt_deckel + 1e-9
        neu_umsatz = u.listenumsatz * (1 - rabatt_deckel)
        mehr = (neu_umsatz - u.umsatz).where(betroffen, 0.0)
        u["umsatz"] = u.umsatz + mehr
        u["db1"] = u.db1 + mehr
    rabatt_effekt = u.db1.sum() - basis["db1"]
    anteil_betroffen = basis_betroffen = 0.0
    if betroffen.any():
        anteil_betroffen = d.umsatz.loc[u.index[betroffen], "umsatz"].sum() / basis["umsatz"]
        basis_betroffen = int(betroffen.sum())
    behalten = np.where(betroffen, 1 - mengenverlust, 1.0)
    db_vor = u.db1.sum()
    for c in ("umsatz", "db1", "wareneinsatz", "versandkosten"):
        u[c] = u[c] * behalten
    verlust_effekt = u.db1.sum() - db_vor

    # 3 Umsatzmenge
    db_vor = u.db1.sum()
    for c in ("umsatz", "db1", "wareneinsatz", "versandkosten"):
        u[c] = u[c] * (1 + umsatz_proz)
    menge_effekt = u.db1.sum() - db_vor

    # 4 Fixkosten
    fix_neu = f * (1 + fix_proz)
    neu = kennz(u.umsatz.sum(), u.db1.sum(), u.wareneinsatz.sum() + u.versandkosten.sum(), fix_neu)
    return {
        "basis": basis, "szenario": neu, "zeitraum": (u.monat.min(), u.monat.max()),
        "bruecke": {"rabatt": rabatt_effekt, "verlust": verlust_effekt, "menge": menge_effekt,
                    "fix": -(fix_neu - f)},
        "betroffen_n": basis_betroffen, "betroffen_anteil": anteil_betroffen,
        "liq": {"umsatz_faktor": neu["umsatz"] / basis["umsatz"], "kosten_quote": neu["kosten"] / neu["umsatz"],
                "fix_faktor": 1 + fix_proz, "verzug_extra": verzug_extra},
    }


# ---------------------------------------------------------------- Schritt 3: Mandanten
# Externer Modus: Jede Region tritt als eigener Mandant auf. Umsatz, Plan und Rechnungen
# gehören eindeutig zu einer Region. Fixkosten, Privatentnahme und Anfangsbestand der Kasse
# sind Firmenwerte; sie werden per Umlage nach Planumsatz des Jahres verteilt
# (2015 ohne Plan: Ist-Umsatzanteil 2015). Der Kontostand je Mandant wird aus seinen eigenen
# Zahlungsströmen neu aufgebaut, genau wie in gen_data.py. Summe der Mandanten = Firma.
STARTKASSE = 60_000.0
ZAHLTAG_FIX = {"Personal": 28, "Miete": 1, "Marketing": 15, "IT & Verwaltung": 15}


def mandanten(d: Daten) -> list[str]:
    return sorted(d.umsatz.region.unique())


def umlage_schluessel(d: Daten) -> pd.DataFrame:
    """Anteil je Region und Jahr (Spalten = Regionen, Index = Jahr)."""
    p = d.plan.assign(jahr=d.plan.monat.dt.year).groupby(["jahr", "region"]).umsatz_plan.sum().unstack()
    i = d.umsatz.groupby(["jahr", "region"]).umsatz.sum().unstack()
    t = p.combine_first(i)          # Plan, wo vorhanden, sonst Ist
    return t.div(t.sum(axis=1), axis=0)


def mandant_daten(d: Daten, region: str) -> Daten:
    """Schneidet die Firmendaten auf einen Mandanten (Region) zu."""
    sl = umlage_schluessel(d)[region]
    u = d.umsatz[d.umsatz.region == region].copy()
    p = d.plan[d.plan.region == region].copy()
    auftraege = set(u.auftrag_id)
    r = d.rech[d.rech.auftrag_id.isin(auftraege)].copy()
    f = d.fix.copy()
    anteil = f.monat.dt.year.map(sl)
    f["plan"] = (f.plan * anteil).round(2)
    f["ist"] = (f.ist * anteil).round(2)
    entnahme = ENTNAHME_MONAT * sl.get(d.liq.datum.max().year, sl.iloc[-1])

    # Kontostand je Tag aus den eigenen Zahlungsströmen
    tage = pd.DatetimeIndex(d.liq.datum)
    ein = r.dropna(subset=["bezahlt_am"]).groupby("bezahlt_am").betrag.sum()
    fx = f.dropna(subset=["ist"]).copy()
    fx["datum"] = fx.monat + pd.to_timedelta(fx.kostenart.map(ZAHLTAG_FIX) - 1, "D")
    ent = pd.Series([ENTNAHME_MONAT * sl.get(t.year, sl.iloc[-1]) for t in tage], index=tage)
    ent = ent[ent.index == ent.index + pd.offsets.MonthEnd(0)]
    liq = pd.DataFrame(index=tage)
    liq["einzahlungen"] = ein.reindex(tage, fill_value=0)
    liq["auszahlungen_ware"] = u.groupby("auftragsdatum").wareneinsatz.sum().reindex(tage, fill_value=0)
    liq["auszahlungen_versand"] = u.groupby("versanddatum").versandkosten.sum().reindex(tage, fill_value=0)
    liq["auszahlungen_fix"] = fx.groupby("datum").ist.sum().reindex(tage, fill_value=0)
    liq["privatentnahme"] = ent.reindex(tage, fill_value=0)
    liq["saldo_tag"] = liq.einzahlungen - liq[["auszahlungen_ware", "auszahlungen_versand",
                                               "auszahlungen_fix", "privatentnahme"]].sum(axis=1)
    start = STARTKASSE * sl.get(tage.min().year, sl.iloc[0])
    liq["kontostand"] = start + liq.saldo_tag.cumsum()
    liq = liq.rename_axis("datum").reset_index()
    return Daten(umsatz=u, plan=p, fix=f, rech=r, liq=liq, kunde=d.kunde,
                 name=f"Unicorn {region}", entnahme=entnahme, mandant=region)


# ---------------------------------------------------------------- Schritt 3: Benchmark
# Branchenwerte: U.S. Census Bureau, Annual Retail Trade Survey (ARTS) 2018, veröffentlicht Feb. 2020,
# Zeile „Retail ... total (excl. motor vehicle and parts dealers)“ der Tabellen sales.xls, gmper.xls,
# exp.xls und arr.xls (https://www.census.gov/data/tables/2018/econ/arts/annual-report.html).
# Rohertragsquote = Gross margin as a percentage of sales.
# Operative Marge = Rohertragsquote − Betriebskosten / Umsatz (Näherung für EBIT / Umsatz).
# Forderungslaufzeit = Forderungen am Jahresende / Umsatz · 365. Wachstum = Umsatz gegen Vorjahr.
# Betriebskosten und Forderungen enthalten nur Firmen mit Angestellten, der Umsatz auch Firmen ohne.
BRANCHE_QUELLE = ("U.S. Census Bureau, Annual Retail Trade Survey 2018 (Feb. 2020), "
                  "Retail excl. motor vehicle and parts dealers")
BRANCHE_ROH = {  # Jahr: (Umsatz Mio $, Rohertrag % Umsatz, Betriebskosten Mio $, Forderungen Mio $)
    2015: (3_631_881, 32.1, 907_367, 33_089),
    2016: (3_712_344, 32.5, 949_787, 33_734),
    2017: (3_880_784, 32.5, 1_000_531, 33_123),
    2018: (4_078_147, 32.6, 1_038_256, 33_434),
}
BRANCHE_VJ_UMSATZ = {2015: 3_618_589}   # Umsatz 2014 (Mio $), Basis für das Wachstum 2015

# Kennzahl: (Titel, Einheit, höher ist besser)
BENCH_KZ = {
    "rohertrag": ("Rohertragsquote", "%", True),
    "rendite": ("Umsatzrendite (EBIT)", "%", True),
    "dso": ("Forderungslaufzeit", "Tage", False),
    "wachstum": ("Umsatzwachstum", "%", True),
}
BENCH_KZ_EN = {"rohertrag": "Gross margin", "rendite": "EBIT margin",
               "dso": "Days sales outstanding", "wachstum": "Revenue growth"}


def branche(jahr: int) -> dict:
    j = min(max(jahr, min(BRANCHE_ROH)), max(BRANCHE_ROH))
    u, roh, kosten, ford = BRANCHE_ROH[j]
    u_vj = BRANCHE_ROH[j - 1][0] if j - 1 in BRANCHE_ROH else BRANCHE_VJ_UMSATZ[j]
    return {"jahr": j, "rohertrag": roh, "rendite": roh - kosten / u * 100,
            "dso": ford / u * 365, "wachstum": (u / u_vj - 1) * 100}


def bench_kennzahlen(d: Daten, s: pd.Timestamp) -> dict:
    """Kennzahlen der letzten 12 Monate bis Stichtag, vergleichbar mit den Branchenwerten."""
    von = s - pd.DateOffset(months=12)
    u = d.umsatz[(d.umsatz.monat > von) & (d.umsatz.monat <= s)]
    u_vj = d.umsatz[(d.umsatz.monat > von - pd.DateOffset(months=12)) & (d.umsatz.monat <= von)]
    f = d.fix[(d.fix.monat > von) & (d.fix.monat <= s)]
    umsatz = u.umsatz.sum()
    op = offene_posten(d, s)
    forderungen = op.loc[op.status != "uneinbringlich", "betrag"].sum()
    return {
        "umsatz": umsatz,
        "rohertrag": (umsatz - u.wareneinsatz.sum()) / umsatz * 100,
        "rendite": (u.db1.sum() - f.ist.sum()) / umsatz * 100,
        "dso": forderungen / umsatz * 365,
        # Wachstum nur, wenn die 12 Vergleichsmonate vollständig in den Daten liegen
        "wachstum": (umsatz / u_vj.umsatz.sum() - 1) * 100 if u_vj.monat.nunique() == 12 else np.nan,
    }


def benchmark(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    """Je Kennzahl: Wert je Mandant, Median der Mandanten, Branchenwert."""
    werte = {m: bench_kennzahlen(mandant_daten(d, m), s) for m in mandanten(d)}
    gesamt = bench_kennzahlen(d, s)
    b = branche(s.year)
    zeilen = []
    for kz, (titel, einheit, hoch_gut) in BENCH_KZ.items():
        if np.isnan(gesamt[kz]) or any(np.isnan(w[kz]) for w in werte.values()):
            continue    # z. B. Wachstum, solange kein volles Vorjahr in den Daten liegt
        z = {"kz": kz, "titel": T(titel, BENCH_KZ_EN[kz]), "einheit": einheit, "hoch_gut": hoch_gut, "branche": b[kz],
             "median": float(np.median([w[kz] for w in werte.values()]))}
        z.update({m: w[kz] for m, w in werte.items()})
        z["gesamt"] = gesamt[kz]
        zeilen.append(z)
    return pd.DataFrame(zeilen)


def portfolio(d: Daten, s: pd.Timestamp) -> pd.DataFrame:
    """Je Mandant die Lage-Kennzahlen mit Ampel (für die Mandanten-Übersicht)."""
    zeilen = []
    for m in mandanten(d):
        dm = mandant_daten(d, m)
        k = kennzahlen(dm, s)
        prog = liquiditaet_prognose(dm, s)
        sig = signale(dm, s)
        zeilen.append({
            "mandant": m, "name": dm.name, "umsatz": k["umsatz"], "umsatz_abw": k["umsatz_abw"],
            "db1": k["db1"], "db1_abw": k["db1_abw"], "ebit": k["ebit"], "ebit_plan": k["ebit_plan"],
            "kontostand": k["kontostand"], "liq_min": prog["minimum"], "liq_ampel": liq_ampel(prog),
            "rot": sum(x.stufe == "rot" for x in sig), "gelb": sum(x.stufe == "gelb" for x in sig),
            "top_signal": next((x.titel for x in sig if x.stufe != "grün"), "–"),
        })
    return pd.DataFrame(zeilen)


def bench_aussage(bm: pd.DataFrame, eigen: str, name: str) -> str:
    """Ein Satz: bei wie vielen Kennzahlen besser als die Branche, wo die größte Lücke ist."""
    einh = lambda r: T(" Tage", " days") if r.einheit == "Tage" else T(" %", "%")
    diff = []
    for _, r in bm.iterrows():
        d_ = (r[eigen] - r.branche) if r.hoch_gut else (r.branche - r[eigen])
        diff.append((d_ / max(abs(r.branche), 1e-9), r))
    besser = sum(1 for x, r in diff if round(r[eigen], 1) != round(r.branche, 1) and x > 0)
    sl = min(diff, key=lambda x: x[0])[1]
    be = max(diff, key=lambda x: x[0])[1]
    w = lambda r, sp: f"{zahl(r[sp], 1)}{einh(r)}"
    return T(f"{name} liegt bei {besser} von {len(bm)} Kennzahlen besser als die Branche. "
             f"Größte Lücke: {sl.titel} ({w(sl, eigen)} statt {w(sl, 'branche')}); "
             f"stärkster Wert: {be.titel} ({w(be, eigen)} gegen {w(be, 'branche')}).",
             f"{name} beats the industry on {besser} of {len(bm)} KPIs. "
             f"Largest gap: {sl.titel} ({w(sl, eigen)} vs. {w(sl, 'branche')}); "
             f"strongest: {be.titel} ({w(be, eigen)} vs. {w(be, 'branche')}).")
