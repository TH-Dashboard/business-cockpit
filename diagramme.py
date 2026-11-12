"""Diagramme fürs Cockpit (matplotlib).

Regeln: CI-Farben der Slides, Werte direkt beschriften, Dezimalkomma, keine Überlappung,
Verteilungen als Histogramm + Dichte, zu jedem Diagramm ein Aussagesatz (kommt von der Seite).
"""
from __future__ import annotations

import logging

import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator

from logik import datum, geld, proz, zahl
from sprache import B, T


def _tm(d) -> str:
    """Tag und Monat kurz: 01.04. bzw. 01 Apr"""
    return d.strftime(T("%d.%m.", "%d %b"))

# Farben aus der Unicorn-Präsentation (Corporate Identity)
CI = {
    "navy": "#0A2342", "titel": "#0E2949", "blau": "#1A63B7", "hellblau": "#7DB9FF",
    "orange": "#F6A25E", "orange_text": "#C86419", "grau_text": "#556F8E",
    "hintergrund": "#F1F4F9", "karte": "#FFFFFF",
}
FARBE = {
    "ist": CI["blau"], "plan": "#7DB9FF", "gut": "#2E9E5B", "schlecht": "#D0435E",
    "gelb": "#F28C28", "lila": CI["blau"], "dichte": CI["navy"], "text": CI["navy"],
    "linie_rot": "#9A3550", "grau": "#556F8E", "pos_text": "#2E7348", "neg_text": "#9A3550",
}
MONATE_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONATE_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

plt.rcParams.update({
    "font.family": ["Inter", "Segoe UI", "Arial", "DejaVu Sans"],
    "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#556F8E", "axes.labelcolor": FARBE["text"], "axes.linewidth": 1.0,
    "patch.force_edgecolor": True, "patch.edgecolor": "#0A2342", "patch.linewidth": 0.6,
    "xtick.color": "#2C4260", "ytick.color": "#2C4260", "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "text.color": FARBE["text"],
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
    "figure.dpi": 110, "axes.titlecolor": CI["titel"], "savefig.bbox": "tight", "text.parse_math": False,
})

TSD = FuncFormatter(lambda v, _: zahl(v / 1000, 0) + T(" Tsd.", "k"))
GELD = FuncFormatter(lambda v, _: zahl(v, 0))


def _bbox(farbe="white"):
    return dict(boxstyle="round,pad=0.25", fc=farbe, ec="#C3CEDC", lw=0.6, alpha=0.95)


# ------------------------------------------------------------- Monate Ist vs Plan
def monate_ist_plan(t: pd.DataFrame):
    """Balken Ist je Monat, Plan als Strich, Ist-Wert über dem Balken."""
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(t))
    farben = [FARBE["gut"] if i >= p else FARBE["schlecht"] for i, p in zip(t.umsatz, t.umsatz_plan)]
    ax.bar(x, t.umsatz, color=farben, width=0.66, label=T("Ist (grün = über Plan, rot = darunter)", "Actual (green = above plan, red = below)"))
    ax.hlines(t.umsatz_plan, x - 0.38, x + 0.38, color=CI["navy"], lw=2, label=T("Plan", "Plan"))
    top = max(t.umsatz.max(), t.umsatz_plan.max())
    for xi, i, p, a in zip(x, t.umsatz, t.umsatz_plan, t.abw_proz):
        oben = i + top * 0.02
        if p > i and p - i < top * 0.18:      # Plan-Strich knapp über dem Balken: Text darüber setzen
            oben = p + top * 0.04
        ax.text(xi, oben, zahl(i / 1000, 1), ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.text(xi, oben + top * 0.075, proz(a, nachkomma=0), ha="center", va="bottom",
                fontsize=8, color=FARBE["pos_text"] if a >= 0 else FARBE["neg_text"])
    ax.set_xticks(x, [T(MONATE_DE[m.month - 1], MONATE_EN[m.month - 1]) for m in t.monat])
    ax.yaxis.set_major_formatter(TSD)
    ax.set_ylim(0, top * 1.28)
    ax.set_xlim(-0.6, max(len(t), 6) - 0.4)
    ax.set_title(T("Umsatz je Monat: Ist gegen Plan (Werte in Tsd. $)", "Monthly revenue: actual vs. plan ($k)"))
    ax.legend(loc="upper left", frameon=False, fontsize=9, ncol=2)
    summe = T(f"Summe Ist {zahl(t.umsatz.sum() / 1000, 1)} Tsd. | Plan {zahl(t.umsatz_plan.sum() / 1000, 1)} Tsd. | ",
              f"Total actual {zahl(t.umsatz.sum() / 1000, 1)}k | plan {zahl(t.umsatz_plan.sum() / 1000, 1)}k | ") \
        + proz(t.umsatz.sum() / t.umsatz_plan.sum() - 1)
    ax.text(1, 1.02, summe, transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color=CI["grau_text"])
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- DB-Wasserfall
def db_wasserfall(z: dict):
    schritte = [(T("DB I Plan", "CM I plan"), z["plan"], "summe"), (T("Menge", "Volume"), z["menge"], "delta"),
                ("Mix", z["mix"], "delta"), (T("Preis/Rabatt", "Price/discount"), z["preis"], "delta"),
                (T("DB I Ist", "CM I actual"), z["ist"], "summe")]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    stand = 0
    hoch = max(z["plan"], z["ist"])
    for i, (name, wert, art) in enumerate(schritte):
        if art == "summe":
            unten, h, farbe = 0, wert, FARBE["ist"] if i == len(schritte) - 1 else FARBE["plan"]
            stand = wert
            text = geld(wert)
        else:
            unten = stand if wert >= 0 else stand + wert
            h, farbe = abs(wert), FARBE["gut"] if wert >= 0 else FARBE["schlecht"]
            text = ("+" if wert >= 0 else "") + geld(wert)
            stand += wert
        ax.bar(i, h, bottom=unten, color=farbe, width=0.6)
        ax.text(i, unten + h + hoch * 0.02, text, ha="center", va="bottom", fontsize=10, fontweight="bold")
        if i < len(schritte) - 1:
            ax.plot([i + 0.3, i + 0.7], [stand, stand], color="#556F8E", lw=0.8, ls=":")
    ax.set_xticks(range(len(schritte)), [s[0] for s in schritte])
    ax.yaxis.set_major_formatter(TSD)
    unten_min = min(z["ist"], z["plan"]) * 0.6
    ax.set_ylim(unten_min, hoch * 1.22)
    ax.set_title(T("DB I: vom Plan zum Ist", "Contribution margin I: from plan to actual"))
    ax.text(0, -0.16, T(f"Achse beginnt bei {zahl(unten_min / 1000, 0)} Tsd. $, damit die Effekte sichtbar sind.",
                        f"Axis starts at ${zahl(unten_min / 1000, 0)}k so the effects are visible."),
            transform=ax.transAxes, fontsize=8, color="#3D5470")
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Abweichung je Dimension
def abweichung_balken(t: pd.DataFrame, dim: str, titel: str):
    """Horizontale Balken: Abweichung in %, beschriftet mit % und $."""
    t = t.sort_values("abw_proz")
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(t) + 1.4))
    y = np.arange(len(t))
    farben = [FARBE["gut"] if a >= 0 else FARBE["schlecht"] for a in t.abw_proz]
    ax.barh(y, t.abw_proz * 100, color=farben, height=0.6)
    spann = max(abs(t.abw_proz).max() * 100, 1)
    for yi, a, b in zip(y, t.abw_proz, t.abw):
        txt = f"{proz(a)}  ({'+' if b >= 0 else ''}{geld(b)})"
        ax.text(a * 100 + (spann * 0.03 if a >= 0 else -spann * 0.03), yi, txt,
                va="center", ha="left" if a >= 0 else "right", fontsize=9, fontweight="bold")
    ax.axvline(0, color="#556F8E", lw=1)
    ax.set_yticks(y, t[dim])
    ax.set_xlim(-spann * 2.1, spann * 2.1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 0) + T(" %", "%")))
    ax.set_title(titel)
    fig.tight_layout()
    return fig


def fixkosten_balken(t: pd.DataFrame, titel: str, gelb_ab: float = 0.05, rot_ab: float = 0.15):
    """Farben wie die Frühwarnung: grün bis gelb_ab, gelb bis rot_ab, darüber rot."""
    t = t.sort_values("abw_proz")
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(t) + 1.6))
    y = np.arange(len(t))
    farben = [FARBE["schlecht"] if a > rot_ab else FARBE["gelb"] if a > gelb_ab else FARBE["gut"] for a in t.abw_proz]
    ax.barh(y, t.abw_proz * 100, color=farben, height=0.6)
    spann = max(abs(t.abw_proz).max() * 100, 1)
    for yi, a, b, i in zip(y, t.abw_proz, t.abw, t.ist):
        txt = f"{proz(a)}  ({T('Ist', 'actual')} {geld(i)}, {'+' if b >= 0 else ''}{geld(b)})"
        # immer rechts neben der Null bzw. dem Balken -> verdeckt nie die Kostenart links
        ax.text(max(a, 0) * 100 + spann * 0.03, yi, txt, va="center", ha="left", fontsize=9, fontweight="bold",
                bbox=_bbox())
    g, r = gelb_ab * 100, rot_ab * 100
    ax.axvline(0, color="#556F8E", lw=1)
    ax.axvline(g, color=FARBE["gelb"], lw=1.4, ls="--", zorder=0)
    ax.axvline(r, color=FARBE["linie_rot"], lw=1.4, ls="--", zorder=0)
    ax.annotate(T(f"gelb ab +{zahl(g, 0)} %", f"amber from +{zahl(g, 0)}%"), (g, len(t) - 0.3), xytext=(5, 0), textcoords="offset points",
                color="#A84F0F", fontsize=8, va="bottom", ha="left")
    ax.annotate(T(f"rot ab +{zahl(r, 0)} %", f"red from +{zahl(r, 0)}%"), (r, len(t) - 0.3), xytext=(5, 0), textcoords="offset points",
                color=FARBE["neg_text"], fontsize=8, va="bottom", ha="left")
    ax.set_yticks(y, [B(k) for k in t.kostenart])
    ax.set_xlim(min(-spann * 0.15, t.abw_proz.min() * 100 * 2.5), max(spann * 1.75, r * 2.3))
    ax.set_ylim(-0.6, len(t) + 0.15)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 0) + T(" %", "%")))
    ax.set_title(titel)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Rabattstufen
def rabatt_stufen(rp: pd.DataFrame):
    """DB I je Rabattstufe, Ist vs Vorjahr, mit Marge, Umsatzanteil und Fallzahl."""
    stufen = ["0 %", "1–20 %", "> 20 %"]
    zeilen = []
    for s in stufen:
        for zr in ("Vorjahr", "Ist"):
            r = rp[(rp.rabattstufe == s) & (rp.zeitraum == zr)].iloc[0]
            zeilen.append((T(f"Rabatt {s} – {zr}", f"Discount {s.replace(' %', '%')} – {'actual' if zr == 'Ist' else 'prior year'}"),
                           zr, r.db1, r.db1 / r.umsatz, r.anteil, r.n))
    zeilen = zeilen[::-1]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    y = np.arange(len(zeilen)) + np.repeat([0, 0.35, 0.7], 2)[::-1][::-1]
    for yi, (name, zr, db, m, an, n) in zip(y, zeilen):
        farbe = FARBE["gelb"] if zr == "Ist" else FARBE["plan"]
        ax.barh(yi, db, color=farbe, height=0.75)
        txt = T(f"{geld(db)}  ·  Marge {proz(m, nachkomma=0)}  ·  {proz(an, False, 0)} Umsatz (n = {zahl(n)})",
                f"{geld(db)}  ·  margin {proz(m, nachkomma=0)}  ·  {proz(an, False, 0)} of revenue (n = {zahl(n)})")
        off = rp.db1.abs().max() * 0.02
        ax.text(max(db, 0) + off, yi, txt, va="center", ha="left",
                fontsize=8.5, fontweight="bold" if zr == "Ist" else "normal")
    ax.axvline(0, color="#556F8E", lw=1)
    ax.set_yticks(y, [z[0] for z in zeilen])
    ax.set_xlim(min(rp.db1.min() * 1.25, 0), rp.db1.max() * 2.05)
    ax.xaxis.set_major_formatter(TSD)
    ax.set_title(T("DB I je Rabattstufe: Ist gegen Vorjahr", "Contribution margin I by discount tier: actual vs. prior year"))
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Liquidität
def liquiditaet(prog: dict, stichtag: pd.Timestamp):
    fig, ax = plt.subplots(figsize=(10, 4.4))
    v, f = prog["vergangen"], prog["tag"]
    ax.plot(v.index, v.values, color=CI["blau"], lw=2.4, label=T("Kontostand Ist (13 Wochen zurück)", "Actual balance (13 weeks back)"))
    verbund = pd.concat([pd.Series([prog["start"]], index=[stichtag]), f])
    ax.plot(verbund.index, verbund.values, color="#F28C28", lw=2.6, ls="--", label=T("Prognose (13 Wochen)", "Forecast (13 weeks)"))
    if len(prog["tatsaechlich"]):
        ax.plot(prog["tatsaechlich"].index, prog["tatsaechlich"].values, color=FARBE["grau"], lw=1.2, ls=":",
                label=T("tatsächlich eingetreten (Rückblick)", "what actually happened (hindsight)"))
    ax.axhline(prog["puffer"], color=FARBE["linie_rot"], lw=1.4, ls="--")
    ax.axvline(stichtag, color="#8A9BB0", lw=1)
    mt = prog["minimum_tag"]
    alle = pd.concat([v, verbund])
    lo, hi = min(alle.min(), prog["puffer"], 0), max(alle.max(), prog["puffer"])
    rng = hi - lo
    unten = lo - rng * 0.22                    # Platz für Beschriftungen unter dem tiefsten Punkt
    ax.set_ylim(unten, hi + rng * 0.3)
    if alle.min() < 0:                         # Konto im Minus: Bereich unter 0 markieren
        ax.axhspan(unten, 0, color="#F9DADA", alpha=0.55, zorder=0, lw=0)
        ax.axhline(0, color=FARBE["grau"], lw=1)
        ax.text(f.index[-1] + pd.Timedelta(days=22), unten + rng * 0.03, T("rote Fläche: Konto im Minus", "red area: account overdrawn"),
                color=FARBE["neg_text"], fontsize=8.5, ha="right", va="bottom")
    ax.text(v.index[0] + pd.Timedelta(days=2), prog["puffer"] + rng * 0.02, T("Puffer ", "Buffer ") + geld(prog["puffer"]), color=FARBE["neg_text"], fontsize=8.5,
            va="bottom")
    ax.annotate(T("Stichtag ", "Reporting date ") + f"{datum(stichtag)}\n{geld(prog['start'])}"
                + (T("\n= tiefster Stand", "\n= lowest point") if mt == stichtag else ""),
                (stichtag, prog["start"]),
                xytext=(0, -62), textcoords="offset points", ha="center", fontsize=8.5, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color="#556F8E"), bbox=_bbox())
    mt, mv = prog["minimum_tag"], prog["minimum"]
    ende_t = f.index[-1]
    if mt > stichtag and (ende_t - mt).days > 10:
        ax.annotate(T("Tiefster Stand", "Lowest point") + f"\n{geld(mv)} ({_tm(mt)})", (mt, mv), xytext=(0, -34),
                    textcoords="offset points", ha="center", fontsize=8.5, bbox=_bbox(),
                    arrowprops=dict(arrowstyle="-", color="#556F8E"))
        ax.plot([mt], [mv], "o", color=CI["orange"], ms=5)
    if mt == ende_t:
        zusatz = T("\n= tiefster Stand", "\n= lowest point")
    elif mt > stichtag and (ende_t - mt).days <= 10:
        zusatz = T("\nTief ", "\nLow ") + f"{geld(mv)} ({_tm(mt)})"
        ax.plot([mt], [mv], "o", color=CI["orange"], ms=5)
    else:
        zusatz = ""
    ax.annotate(T("Prognose-Ende", "End of forecast") + f"\n{geld(f.iloc[-1])}" + zusatz,
                (ende_t, f.iloc[-1]), xytext=(8, 6), textcoords="offset points", ha="left", fontsize=8.5,
                fontweight="bold", bbox=_bbox())
    hoch_t = v.idxmax()
    links = (hoch_t - v.index[0]).days < 20
    ax.annotate(T("Hoch ", "High ") + geld(v.max()), (hoch_t, v.max()), xytext=(8 if links else -8, 10),
                textcoords="offset points", ha="left" if links else "right", fontsize=8.5, bbox=_bbox())
    ax.plot([hoch_t], [v.max()], "o", color=CI["blau"], ms=4)
    hp_t = f.idxmax()          # Spitze der Prognose
    if f.max() > max(prog["start"], f.iloc[-1]) * 1.05 and (ende_t - hp_t).days > 10:
        ax.plot([hp_t], [f.max()], "o", color=CI["orange"], ms=5)
        ax.annotate(T("Hoch Prognose ", "Forecast high ") + f"{geld(f.max())} ({_tm(hp_t)})", (hp_t, f.max()),
                    xytext=(0, 10), textcoords="offset points", ha="center", va="bottom", fontsize=8.5, bbox=_bbox())
    tief_t = v.idxmin()
    if (stichtag - tief_t).days > 14:          # sonst sitzt es auf der Stichtag-Beschriftung
        ax.plot([tief_t], [v.min()], "o", color=CI["blau"], ms=4)
        ax.annotate(T("Tief Ist ", "Actual low ") + f"{geld(v.min())} ({_tm(tief_t)})", (tief_t, v.min()),
                    xytext=(10, -24) if (stichtag - tief_t).days >= 45 else (-10, -24),   # nah am Stichtag: nach links
                    ha="left" if (stichtag - tief_t).days >= 45 else "right",
                    textcoords="offset points", va="top", fontsize=8.5, bbox=_bbox(),
                    arrowprops=dict(arrowstyle="-", color="#556F8E"))
    ax.yaxis.set_major_formatter(GELD)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(T("%d.%m.%y", "%d %b %y")))
    ax.set_xlim(v.index[0], ende_t + pd.Timedelta(days=24))
    ax.set_title(T("Kontostand: 13 Wochen zurück, 13 Wochen voraus (in $)", "Bank balance: 13 weeks back, 13 weeks ahead ($)"))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, fontsize=8.5, ncol=3)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Verteilung Verzug
def _kde(werte: np.ndarray, gitter: np.ndarray) -> np.ndarray:
    n = len(werte)
    sd = werte.std(ddof=1)
    iqr = np.subtract(*np.percentile(werte, [75, 25]))
    bw = 0.9 * min(sd, iqr / 1.34 if iqr > 0 else sd) * n ** (-1 / 5)
    bw = max(bw, 0.5)
    u = (gitter[:, None] - werte[None, :]) / bw
    return np.exp(-0.5 * u ** 2).sum(axis=1) / (n * bw * np.sqrt(2 * np.pi))


def verzug_verteilung(werte: pd.Series):
    w = werte.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    bins = np.arange(0, max(w.max(), 10) + 5, 5)
    ax.hist(w, bins=bins, density=True, color=FARBE["plan"], edgecolor="#FFFFFF", linewidth=0.8, label=T("Histogramm (5-Tage-Klassen)", "Histogram (5-day bins)"))
    g = np.linspace(0, w.max() + 5, 400)
    dichte = _kde(w, g)
    ax.plot(g, dichte, color=FARBE["dichte"], lw=2.4, label=T("Dichte", "Density"))
    mw, md, p90 = w.mean(), np.median(w), np.percentile(w, 90)
    top = max(dichte.max(), np.histogram(w, bins=bins, density=True)[0].max())
    ax.set_ylim(0, top * 1.45)
    for wert, name, farbe, hoehe in [(md, T("Median", "Median"), FARBE["pos_text"], 1.32), (mw, T("Mittelwert", "Mean"), CI["orange_text"], 1.18),
                                     (p90, T("90 %-Grenze", "90th percentile"), FARBE["neg_text"], 1.04)]:
        ax.axvline(wert, color=farbe, lw=1.3, ls="--")
        ax.text(wert, top * hoehe, f" {name} {zahl(wert, 1)} " + T("Tage", "days"), color=farbe, fontsize=9, fontweight="bold",
                ha="left", va="center", bbox=_bbox())
    if w.max() > 30:
        spaet = (w > 30).mean()
        ax.axvspan(30, g[-1], color=FARBE["schlecht"], alpha=0.08, lw=0)
        ax.text(31, top * 0.55, T(f"> 30 Tage: {proz(spaet, False)}\n({zahl((w > 30).sum())} von {zahl(len(w))} Rechnungen)",
                  f"> 30 days: {proz(spaet, False)}\n({zahl((w > 30).sum())} of {zahl(len(w))} invoices)"),
                color=FARBE["neg_text"], fontsize=9, fontweight="bold", ha="left", va="center", bbox=_bbox())
    ax.set_xlim(0, g[-1])
    ax.text(0.99, 0.97, f"n = {zahl(len(w))} " + T("Rechnungen", "invoices"), transform=ax.transAxes, ha="right", va="top",
            fontsize=9, color=CI["grau_text"])
    ax.set_xlabel(T("Tage nach Fälligkeit", "Days past due date"))
    ax.set_ylabel(T("Dichte", "Density"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 2)))
    ax.set_title(T("Zahlungsverzug der letzten 12 Monate (Rechnungen mit Zahlungsziel)", "Payment delays over the last 12 months (invoices with payment terms)"))
    ax.legend(loc="center right", frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Was-wäre-wenn: EBIT-Brücke
def ebit_bruecke(z: dict):
    """Wasserfall vom EBIT (letzte 12 Monate) zum EBIT im Szenario."""
    b = z["bruecke"]
    schritte = [(T("EBIT heute", "EBIT today"), z["basis"]["ebit"], "summe"),
                (T("Rabatt-\nDeckel", "Discount\ncap"), b["rabatt"], "delta"),
                (T("Mengen-\nverlust", "Volume\nloss"), b["verlust"], "delta"),
                (T("Umsatz-\nmenge", "Sales\nvolume"), b["menge"], "delta"),
                (T("Fix-\nkosten", "Fixed\ncosts"), b["fix"], "delta"),
                (T("EBIT\nSzenario", "EBIT\nscenario"), z["szenario"]["ebit"], "summe")]
    stand, staende = 0.0, []
    for _, w, art in schritte:
        stand = w if art == "summe" else stand + w
        staende.append(stand)
    alle = staende + [0]
    lo, hi = min(alle), max(alle)
    rng = (hi - lo) or 1
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    stand = 0.0
    for i, (name, wert, art) in enumerate(schritte):
        if art == "summe":
            unten, h = min(0, wert), abs(wert)
            farbe = FARBE["plan"] if i == 0 else FARBE["ist"]
            txt = geld(wert)
            stand = wert
        else:
            unten, h = (stand, wert) if wert >= 0 else (stand + wert, -wert)
            farbe = FARBE["gut"] if wert > 0 else FARBE["schlecht"] if wert < 0 else "#C3CEDC"
            txt = ("+" if wert > 0 else "") + geld(wert) if abs(wert) >= 0.5 else "±0 $"
            stand += wert
        ax.bar(i, max(h, rng * 0.004), bottom=unten, color=farbe, width=0.6)
        ax.text(i, unten + h + rng * 0.03, txt, ha="center", va="bottom", fontsize=9.5, fontweight="bold")
        if i < len(schritte) - 1:
            ax.plot([i + 0.3, i + 0.7], [stand, stand], color="#556F8E", lw=0.8, ls=":")
    ax.axhline(0, color="#556F8E", lw=1)
    ax.set_ylim(lo - rng * 0.08 if lo < 0 else 0, hi + rng * 0.2)
    ax.set_xticks(range(len(schritte)), [s[0] for s in schritte])
    ax.yaxis.set_major_formatter(TSD)
    ax.set_title(T("EBIT pro Jahr: von heute zum Szenario", "Annual EBIT: from today to the scenario"))
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Break-even
def break_even(z: dict):
    """DB-I-Gerade gegen Fixkosten; Schnittpunkt = Break-even-Umsatz."""
    b, n = z["basis"], z["szenario"]
    xmax = max(b["umsatz"], n["umsatz"], np.nan_to_num(b["break_even"]), np.nan_to_num(n["break_even"])) * 1.25
    x = np.linspace(0, xmax, 200)
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    gleich = abs(n["marge"] - b["marge"]) < 1e-6 and abs(n["fix"] - b["fix"]) < 0.5
    ax.plot(x, x * b["marge"], color=FARBE["plan"], lw=2.4, label=T("DB I heute (Marge ", "CM I today (margin ") + proz(b['marge'], False) + ")")
    ax.axhline(b["fix"], color=FARBE["linie_rot"], lw=1.6, ls="--", label=T("Fixkosten heute ", "Fixed costs today ") + geld(b['fix']))
    if not gleich:
        ax.plot(x, x * n["marge"], color=FARBE["ist"], lw=2.6, label=T("DB I Szenario (Marge ", "CM I scenario (margin ") + proz(n['marge'], False) + ")")
        if abs(n["fix"] - b["fix"]) >= 0.5:
            ax.axhline(n["fix"], color=FARBE["schlecht"], lw=1.6, ls=":", label=T("Fixkosten Szenario ", "Fixed costs scenario ") + geld(n['fix']))
    ymax = max(xmax * max(b["marge"], n["marge"]), b["fix"], n["fix"]) * 1.12
    ax.set_ylim(0, ymax)
    ax.set_xlim(0, xmax)
    punkte = [(b, T("heute", "today"), FARBE["plan"], -1)] + ([] if gleich else [(n, T("Szenario", "scenario"), FARBE["ist"], 1)])
    for k, name, farbe, seite in punkte:
        if k["break_even"] == k["break_even"]:
            ax.plot([k["break_even"]], [k["fix"]], "o", color=farbe, ms=8, mec=CI["navy"])
            ax.annotate(f"Break-even {name}\n{geld(k['break_even'])} " + T("Umsatz", "revenue"), (k["break_even"], k["fix"]),
                        xytext=(0, 34 if seite > 0 else -46), textcoords="offset points", ha="center",
                        fontsize=8.5, fontweight="bold", bbox=_bbox(), arrowprops=dict(arrowstyle="-", color="#556F8E"))
        ax.axvline(k["umsatz"], color=farbe, lw=1.1, ls="-.")
        ax.annotate(T(f"Umsatz {name} {geld(k['umsatz'])}\nEBIT {geld(k['ebit'])} · Sicherheitsabstand {proz(k['sicherheit'], False, 0)}",
                      f"Revenue {name} {geld(k['umsatz'])}\nEBIT {geld(k['ebit'])} · safety margin {proz(k['sicherheit'], False, 0)}"),
                    (k["umsatz"], ymax * (0.93 if seite > 0 else 0.78)), xytext=(-6, 0), textcoords="offset points",
                    ha="right", va="center", fontsize=8.5, bbox=_bbox())
    ax.xaxis.set_major_formatter(TSD)
    ax.yaxis.set_major_formatter(TSD)
    ax.set_xlabel(T("Umsatz pro Jahr ($)", "Annual revenue ($)"))
    ax.set_title(T("Break-even: ab welchem Umsatz die Fixkosten gedeckt sind", "Break-even: the revenue at which fixed costs are covered"))
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Liquidität Basis vs Szenario
def liq_vergleich(p0: dict, p1: dict, stichtag: pd.Timestamp):
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    werte = pd.concat([p0["tag"], p1["tag"]])
    lo, hi = min(werte.min(), p1["puffer"], p0["start"]), max(werte.max(), p0["start"])
    rng = (hi - lo) or 1
    ende0, ende1 = p0["tag"].iloc[-1], p1["tag"].iloc[-1]
    gleich = abs(ende0 - ende1) < 1 and abs(p0["minimum"] - p1["minimum"]) < 1
    HEUTE = T("heute", "today")
    kurven = [(p0, HEUTE, FARBE["plan"], "-")] + ([] if gleich else [(p1, T("Szenario", "scenario"), "#F28C28", "--")])
    for p, name, farbe, ls in kurven:
        r = pd.concat([pd.Series([p["start"]], index=[stichtag]), p["tag"]])
        mt = HEUTE if p["minimum_tag"] == stichtag else _tm(p["minimum_tag"])
        ht = p["tag"].idxmax()
        ax.plot(r.index, r.values, color=farbe, lw=2.6, ls=ls,
                label=T(f"{name}: Ende {geld(r.iloc[-1])} · Tief {geld(p['minimum'])} ({mt}) · "
                        f"Hoch {geld(p['tag'].max())} ({_tm(ht)})",
                        f"{name}: end {geld(r.iloc[-1])} · low {geld(p['minimum'])} ({mt}) · "
                        f"high {geld(p['tag'].max())} ({_tm(ht)})"))
        ax.plot([r.index[-1]], [r.iloc[-1]], "o", color=farbe, ms=6, mec=CI["navy"])
        # Endwert: der höhere oben, der niedrigere unten -> keine Überlappung
        oben = gleich or (ende0 >= ende1 if name == HEUTE else ende1 > ende0)
        ax.annotate(geld(r.iloc[-1]), (r.index[-1], r.iloc[-1]), xytext=(-6, 12 if oben else -12),
                    textcoords="offset points", ha="right", va="bottom" if oben else "top",
                    fontsize=9, fontweight="bold", bbox=_bbox())
    ax.axhline(p1["puffer"], color=FARBE["linie_rot"], lw=1.4, ls="--")
    ax.set_ylim(lo - rng * 0.15, hi + rng * 0.25)
    ax.text(stichtag + pd.Timedelta(days=1), p1["puffer"] + rng * 0.02, T("Puffer ", "Buffer ") + geld(p1['puffer']),
            color=FARBE["neg_text"], fontsize=8.5, va="bottom")
    ax.set_xlim(stichtag, p0["tag"].index[-1] + pd.Timedelta(days=2))
    ax.yaxis.set_major_formatter(GELD)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(T("%d.%m.%y", "%d %b %y")))
    ax.set_title(T("Kontostand 13 Wochen voraus: heute gegen Szenario (in $)", "Bank balance 13 weeks ahead: today vs. scenario ($)"))
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.1), frameon=False, fontsize=9, ncol=1)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Frühwarnung: Verlauf
def warn_verlauf(t: pd.DataFrame, n_letzte: int = 3):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(t))
    summe = (t.rot + t.gelb).to_numpy(dtype=float)
    linie = np.full(len(t), np.nan)
    if len(t) > n_letzte:
        vor, jetzt = summe[:-n_letzte].mean(), summe[-n_letzte:].mean()
        k = len(t) - n_letzte
        ax.hlines(vor, -0.4, k - 0.6, color=CI["navy"], lw=1.6, ls="--", zorder=1.5,
                  label=T(f"Ø {k} Monate davor: {zahl(vor, 1)}", f"avg. {k} months before: {zahl(vor, 1)}"))
        ax.hlines(jetzt, k - 0.4, len(t) - 0.6, color=FARBE["neg_text"], lw=2, ls="-", zorder=1.5,
                  label=T(f"Ø letzte {n_letzte} Monate: {zahl(jetzt, 1)}", f"avg. last {n_letzte} months: {zahl(jetzt, 1)}"))
        linie[:k], linie[k:] = vor, jetzt
    ax.bar(x, t.rot, color=FARBE["schlecht"], width=0.62, label=T("rot", "red"), zorder=2)
    ax.bar(x, t.gelb, bottom=t.rot, color=FARBE["gelb"], width=0.62, label=T("gelb", "amber"), zorder=2)
    for xi, r, g in zip(x, t.rot, t.gelb):
        if r:
            ax.text(xi, r / 2, str(r), ha="center", va="center", fontsize=9, fontweight="bold", color="white")
        if g:
            ax.text(xi, r + g / 2, str(g), ha="center", va="center", fontsize=9, fontweight="bold", color=CI["navy"])
        y_s = r + g + 0.15
        if not np.isnan(linie[xi]) and r + g - 0.1 <= linie[xi] <= r + g + 0.75:
            y_s = linie[xi] + 0.18          # Σ über die Durchschnittslinie heben
        ax.text(xi, y_s, f"Σ {r + g}", ha="center", va="bottom", fontsize=8.5, color=CI["grau_text"])
    ax.set_xticks(x, [d.strftime("%m/%y") for d in t.stichtag])
    ax.set_ylim(0, (t.rot + t.gelb).max() * 1.25 + 0.5)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 0)))
    ax.set_ylabel(T("Anzahl Signale", "Number of signals"))
    ax.set_title(T("Warnsignale je Stichtag (letzte 12 Monate)", "Warning signals per reporting date (last 12 months)"))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False, fontsize=9, ncol=4)
    fig.tight_layout()
    return fig


# ------------------------------------------------------------- Schritt 3: Mandanten
def _entzerren(xs: list[float], abstand: float) -> list[float]:
    """Schiebt Beschriftungs-Positionen auseinander, bis zwischen zwei Labels mindestens `abstand` liegt."""
    if not xs:
        return []
    ordnung = np.argsort(xs)
    pos = np.array(xs, dtype=float)[ordnung]
    for _ in range(50):
        verschoben = False
        for i in range(1, len(pos)):
            luecke = pos[i] - pos[i - 1]
            if luecke < abstand:
                d = (abstand - luecke) / 2
                pos[i - 1] -= d
                pos[i] += d
                verschoben = True
        if not verschoben:
            break
    out = np.empty_like(pos)
    out[ordnung] = pos
    return out.tolist()


def mandanten_lage(pf: pd.DataFrame):
    """Links: Umsatz gegen Plan in % je Mandant. Rechts: EBIT Ist (Balken) gegen Plan (Strich)."""
    pf = pf.sort_values("umsatz_abw").reset_index(drop=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 0.75 * len(pf) + 1.8), sharey=True)
    y = np.arange(len(pf))
    # links
    w = pf.umsatz_abw * 100
    a1.barh(y, w, color=[FARBE["gut"] if v >= 0 else FARBE["schlecht"] for v in w], height=0.6)
    sp = max(abs(w).max(), 1)
    for yi, v, b in zip(y, w, pf.umsatz):
        a1.text(v + (sp * 0.04 if v >= 0 else -sp * 0.04), yi, f"{proz(v / 100)}  (" + T(f"{zahl(b / 1000, 1)} Tsd. $", f"${zahl(b / 1000, 1)}k") + ")",
                va="center", ha="left" if v >= 0 else "right", fontsize=9, fontweight="bold")
    a1.axvline(0, color=FARBE["grau"], lw=1)
    a1.set_xlim(-sp * 2.4, sp * 2.4)
    a1.xaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 0) + T(" %", "%")))
    a1.set_yticks(y, pf.mandant)
    a1.set_title(T("Umsatz gegen Plan (Jahr bis Stichtag)", "Revenue vs. plan (year to date)"))
    # rechts
    e, p = pf.ebit, pf.ebit_plan
    a2.barh(y, e, color=[FARBE["gut"] if i >= q else FARBE["schlecht"] for i, q in zip(e, p)], height=0.6,
            label=T("EBIT Ist", "EBIT actual"))
    a2.vlines(p, y - 0.36, y + 0.36, color=CI["navy"], lw=2.2, label=T("EBIT Plan", "EBIT plan"))
    lo, hi = min(e.min(), p.min(), 0), max(e.max(), p.max(), 0)
    sp2 = hi - lo
    for yi, i, q in zip(y, e, p):
        rechts = max(i, q, 0) + sp2 * 0.04
        a2.text(rechts, yi, T(f"{zahl(i / 1000, 1)} Tsd. (Plan {zahl(q / 1000, 1)})", f"{zahl(i / 1000, 1)}k (plan {zahl(q / 1000, 1)})"), va="center", ha="left",
                fontsize=9, fontweight="bold", color=FARBE["pos_text"] if i >= q else FARBE["neg_text"])
    a2.axvline(0, color=FARBE["grau"], lw=1)
    a2.set_xlim(lo - sp2 * 0.08, hi + sp2 * 0.95)
    a2.xaxis.set_major_formatter(TSD)
    a2.set_title(T("EBIT: Ist gegen Plan ($)", "EBIT: actual vs. plan ($)"))
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


def benchmark_punkte(bm: pd.DataFrame, eigen: str, namen: dict[str, str], eigen_name: str):
    """Je Kennzahl eine Zeile: Branche (gestrichelt), andere Mandanten (grau), eigener Wert (groß, farbig).

    bm: Ergebnis von logik.benchmark (Spalten je Mandant). eigen: Spalte des eigenen Werts
    ('gesamt' für die Gesamtfirma). namen: Spalte -> angezeigter Name der Vergleichspunkte.
    """
    n = len(bm)
    fig, axes = plt.subplots(n, 1, figsize=(10, 1.55 * n + 0.6))
    for ax, (_, r) in zip(np.atleast_1d(axes), bm.iterrows()):
        einh = T(" Tage", " days") if r.einheit == "Tage" else T(" %", "%")
        fmt = lambda v: zahl(v, 1) + einh
        andere = {namen[c]: r[c] for c in namen}
        werte = list(andere.values()) + [r.branche, r[eigen]]
        lo, hi = min(werte), max(werte)
        sp = max(hi - lo, 1e-9)
        ax.set_xlim(lo - sp * 0.18, hi + sp * 0.18)
        ax.set_ylim(-1.25, 1.15)
        gleich = abs(r[eigen] - r.branche) < 0.05          # in der Anzeige gleich (eine Nachkommastelle)
        besser = (r[eigen] >= r.branche) if r.hoch_gut else (r[eigen] <= r.branche)
        farbe = FARBE["gelb"] if gleich else FARBE["gut"] if besser else FARBE["schlecht"]
        textfarbe = "#A84F0F" if gleich else FARBE["pos_text"] if besser else FARBE["neg_text"]
        ax.axhline(0, color="#C3CEDC", lw=1, zorder=0)
        ax.plot([r.branche, r.branche], [-0.28, 0.8], color=CI["navy"], ls="--", lw=1.4, zorder=1)
        ax.scatter(list(andere.values()), [0] * len(andere), s=55, color="#A9B8CC", edgecolor=CI["navy"],
                   lw=0.6, zorder=2)
        ax.scatter([r[eigen]], [0], s=190, color=farbe, edgecolor=CI["navy"], lw=0.8, zorder=3)
        # eigener Wert oben
        ax.text(r[eigen], 0.42, f"{eigen_name}: {fmt(r[eigen])}", ha="center", va="bottom", fontsize=9.5,
                fontweight="bold", color=textfarbe, bbox=_bbox(), zorder=5)
        # unten: Branche + andere, entzerrt
        unten = [(T("Branche ", "Industry ") + fmt(r.branche), r.branche, True)] + [(f"{k}: {fmt(v)}", v, False) for k, v in andere.items()]
        breite = (ax.get_xlim()[1] - ax.get_xlim()[0])
        pos = _entzerren([u[1] for u in unten], breite * 0.2)
        x0, x1 = ax.get_xlim()
        rand = breite * 0.1
        pos = [min(max(p, x0 + rand), x1 - rand) for p in pos]
        pos = _entzerren(pos, breite * 0.2)
        for (txt, x, ist_branche), px in zip(unten, pos):
            ax.annotate(txt, (x, -0.12 if not ist_branche else -0.1), xytext=(px, -0.75), ha="center", va="top",
                        fontsize=8.5, color=CI["navy"] if ist_branche else FARBE["grau"],
                        fontweight="bold" if ist_branche else "normal",
                        arrowprops=dict(arrowstyle="-", color="#A9B8CC", lw=0.7))
        richtung = T("höher = besser", "higher = better") if r.hoch_gut else T("niedriger = besser", "lower = better")
        ax.set_title(f"{r.titel}  ({richtung})", fontsize=10.5)
        ax.set_yticks([])
        ax.spines[["left"]].set_visible(False)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 5, 10]))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: zahl(v, 0 if abs(v - round(v)) < 1e-9 else 1)))
        ax.tick_params(axis="x", labelsize=8.5)
    fig.tight_layout(h_pad=1.0)
    return fig


# ------------------------------------------------------------- Datenaufbereitung
PASTELL = {"R": "#A8D8C0", "A": "#F2B8C0", "H": "#FBD7A8"}
PASTELL_RAND = {"R": "#4F9C78", "A": "#B5606D", "H": "#C08A3E"}


def bereinigung_regeln(t: pd.DataFrame, zeilen: int, texte: dict[str, str]):
    """Drei Felder untereinander: vereinheitlichte Werte, ausgeschlossene Zeilen, Hinweise.

    t: Spalten regel, anzahl · zeilen: gelesene Zeilen (für Anteile) · texte: Regel -> Beschriftung
    """
    gruppen = [("R", T("Werte vereinheitlicht", "Values standardised")),
               ("A", T("Zeilen ausgeschlossen", "Rows excluded")),
               ("H", T("Hinweise (Zeilen bleiben drin)", "Notes (rows are kept)"))]
    teile = [(g, titel, t[t.regel.str.startswith(g)].sort_values("anzahl")) for g, titel in gruppen]
    teile = [x for x in teile if len(x[2])]
    hoehen = [len(x[2]) + 1.2 for x in teile]
    fig, achsen = plt.subplots(len(teile), 1, figsize=(10, 0.42 * sum(hoehen) + 0.6),
                               gridspec_kw={"height_ratios": hoehen}, squeeze=False)
    for ax, (g, titel, d) in zip(achsen[:, 0], teile):
        y = np.arange(len(d))
        ax.barh(y, d.anzahl, color=PASTELL[g], edgecolor=PASTELL_RAND[g], height=0.62)
        ax.set_yticks(y, [texte[r] for r in d.regel])
        ax.set_title(titel, fontsize=11)
        top = d.anzahl.max()
        ax.set_xlim(0, top * 1.42)
        for yi, n in zip(y, d.anzahl):
            if g in ("R", "H"):          # Werte (eine Zeile kann mehrere haben)
                text = T(f"{zahl(n)} Werte", f"{zahl(n)} values")
            else:
                text = T(f"{zahl(n)} von {zahl(zeilen)} Zeilen ({proz(n / zeilen, False, 2)})",
                         f"{zahl(n)} of {zahl(zeilen)} rows ({proz(n / zeilen, False, 2)})")
            ax.text(n + top * 0.015, yi, text, va="center", fontsize=9, color=FARBE["text"])
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)
    fig.tight_layout(h_pad=1.0)
    return fig
