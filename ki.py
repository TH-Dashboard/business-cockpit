"""KI-Fragefeld: beantwortet Fragen zu den Cockpit-Zahlen über die Claude-API.

Die KI bekommt nur einen Faktenzettel mit verdichteten Kennzahlen (keine Rohdaten).
Schlüssel: Umgebungsvariable ANTHROPIC_API_KEY. Modell: COCKPIT_MODELL (Standard claude-sonnet-5-5).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pandas as pd

import logik as L
import sprache as S
from sprache import T

MODELL = os.environ.get("COCKPIT_MODELL", "claude-sonnet-5-5")
URL = "https://api.anthropic.com/v1/messages"

SYSTEM_DE = """Du bist der Controlling-Assistent im Unternehmer-Cockpit von Unicorn (Online-Händler, Werte in US-Dollar).
Antworte auf Deutsch, kurz und konkret, für eine Unternehmerin ohne Controlling-Ausbildung.
Regeln:
- Nutze ausschließlich die Zahlen aus dem Faktenzettel. Erfinde keine Werte. Wenn etwas nicht drinsteht, sag das und nenne, welche Daten fehlen.
- Schreibe Zahlen mit Dezimalkomma und Tausenderpunkt (1.234,5 $).
- Nenne bei jeder Aussage die Zahl, auf die sie sich stützt.
- Wenn du etwas empfiehlst, kennzeichne es als Vorschlag und nenne den erwarteten Effekt, soweit er sich aus den Zahlen ableiten lässt.
- Plan, Fixkosten, Zahlungsziele und Kontostand sind simuliert; Umsatz und DB I sind echt. Weise darauf hin, wenn es für die Antwort wichtig ist."""

SYSTEM_EN = """You are the controlling assistant in the Business Cockpit of Unicorn (online retailer, values in US dollars).
The fact sheet is written in German (DB I = contribution margin I, Umsatz = revenue, Fixkosten = fixed costs,
Kontostand = bank balance, Forderungen = receivables). Answer in English, briefly and concretely, for a business
owner without controlling training.
Rules:
- Use only the numbers from the fact sheet. Never invent values. If something is missing, say so and name the missing data.
- Write numbers in English format ($1,234.5).
- Back every statement with the number it relies on.
- Mark recommendations as suggestions and state the expected effect where the numbers allow it.
- Plan, fixed costs, payment terms and bank balance are simulated; revenue and contribution margin are real sample data. Mention this when it matters."""


def system() -> str:
    return SYSTEM_EN if S.en() else SYSTEM_DE


def _tab(df: pd.DataFrame) -> str:
    return df.to_csv(sep=";", index=False, decimal=",", float_format="%.1f")


def faktenzettel(d: L.Daten, s: pd.Timestamp, massnahmen: pd.DataFrame | None = None) -> str:
    k = L.kennzahlen(d, s)
    prog = L.liquiditaet_prognose(d, s)
    firma = f"Firma: {d.name}."
    if d.mandant:
        firma += (f" Mandant im externen Modus (Region {d.mandant}). Fixkosten, Privatentnahme und Anfangskasse "
                  "sind per Umlage nach Planumsatz von der Gesamtfirma verteilt.")
    z = [firma, f"Stichtag: {L.datum(s)}. Zeitraum der Kennzahlen: 01.01.–{L.datum(s)} (Jahr bis Stichtag).", "",
         "KENNZAHLEN",
         f"Umsatz {L.geld(k['umsatz'])}, Plan {L.geld(k['umsatz_plan'])} ({L.proz(k['umsatz_abw'])}), Vorjahr {L.geld(k['umsatz_vj'])} ({L.proz(k['umsatz_vj_abw'])})",
         f"DB I {L.geld(k['db1'])}, Plan {L.geld(k['db1_plan'])} ({L.proz(k['db1_abw'])}), Marge {L.proz(k['marge'], False)} (Plan {L.proz(k['marge_plan'], False)})",
         f"Fixkosten {L.geld(k['fix'])}, Plan {L.geld(k['fix_plan'])}",
         f"EBIT {L.geld(k['ebit'])}, Plan {L.geld(k['ebit_plan'])}",
         f"Kontostand {L.geld(k['kontostand'])}; Prognose 13 Wochen: tiefster Stand {L.geld(prog['minimum'])} am "
         f"{L.datum(prog['minimum_tag'])}, Ende {L.geld(prog['ende'])}, Puffer {L.geld(prog['puffer'])}, offene Forderungen {L.geld(prog['op_summe'])}",
         "", "DB-I-ABWEICHUNG ZERLEGT (Plan -> Ist)"]
    zer = L.db_zerlegung(d, s)
    z.append(f"Plan {L.geld(zer['plan'])}; Mengeneffekt {L.geld(zer['menge'])}; Mixeffekt {L.geld(zer['mix'])}; "
             f"Preis-/Rabatteffekt {L.geld(zer['preis'])}; Ist {L.geld(zer['ist'])}")
    t = L.plan_ist_monate(d, s)
    z += ["", "MONATE (umsatz; umsatz_plan; db1; db1_plan)",
          _tab(pd.DataFrame({"monat": t.monat.dt.strftime("%m/%Y"), "umsatz": t.umsatz, "umsatz_plan": t.umsatz_plan,
                             "db1": t.db1, "db1_plan": t.db1_plan}))]
    for dim in ("region", "kategorie"):
        r = L.plan_ist_nach(d, s, dim)
        r["abw_proz"] = (r.abw_proz * 100).round(1)
        z += ["", f"NACH {dim.upper()} (abw_proz in %)", _tab(r[[dim, "umsatz", "umsatz_plan", "abw_proz", "db1", "db1_plan"]])]
    rp = L.rabatt_profil(d, s)
    rp["anteil"] = (rp.anteil * 100).round(1)
    z += ["", "RABATTSTUFEN (anteil = Umsatzanteil in %)", _tab(rp[["zeitraum", "rabattstufe", "umsatz", "db1", "anteil", "n"]])]
    fx = L.fix_plan_ist(d, s)
    fx["abw_proz"] = (fx.abw_proz * 100).round(1)
    z += ["", "FIXKOSTEN JAHR BIS STICHTAG", _tab(fx)]
    sk = L.saeumige_kunden(d, s).head(10)
    if not sk.empty:
        z += ["", "SÄUMIGE KUNDEN (Top 10, offen in $, max_tage = Tage überfällig)",
              _tab(sk[["kunde", "segment", "region", "offen", "rechnungen", "max_tage"]])]
    z += ["", "SIGNALE DER FRÜHWARNUNG"] + [f"[{x.stufe}] {x.titel}: {x.text}" for x in L.signale(d, s)]
    if massnahmen is not None and len(massnahmen):
        m = massnahmen[massnahmen.status.isin(["offen", "in Arbeit"])]
        if len(m):
            z += ["", "LAUFENDE MASSNAHMEN"] + [f"- {r.titel} ({r.status}, fällig {'–' if pd.isna(r.faellig) else r.faellig}, Effekt {L.geld(r.effekt)})"
                                                for r in m.itertuples()]
    return "\n".join(z)


class KIFehler(Exception):
    pass


def schluessel() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def frage(text: str, fakten: str, verlauf: list[dict] | None = None, timeout: int = 60) -> str:
    key = schluessel()
    if not key:
        raise KIFehler(T("Kein API-Schlüssel: Setze die Umgebungsvariable ANTHROPIC_API_KEY und starte die App neu.",
                         "No API key: set the environment variable ANTHROPIC_API_KEY and restart the app."))
    nachrichten = list(verlauf or []) + [{"role": "user", "content": text}]
    body = {"model": MODELL, "max_tokens": 1200,
            "system": [{"type": "text", "text": system()},
                       {"type": "text", "text": "FAKTENZETTEL\n" + fakten}],
            "messages": nachrichten}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            antwort = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise KIFehler(T(f"Die KI-Schnittstelle meldet Fehler {e.code}: {detail}", f"The AI API returned error {e.code}: {detail}")) from e
    except urllib.error.URLError as e:
        raise KIFehler(T(f"Keine Verbindung zur KI-Schnittstelle: {e.reason}", f"No connection to the AI API: {e.reason}")) from e
    return "".join(b.get("text", "") for b in antwort.get("content", []) if b.get("type") == "text").strip()


# ---------------------------------------------------------------- Beispielantworten ohne KI
# Für die Online-Demo ohne API-Schlüssel: Antworten werden regelbasiert aus denselben Zahlen erzeugt
# (keine KI). Sie zeigen, welche Art Antwort das Fragefeld liefert, und stimmen für jeden Mandanten und Stichtag.
def beispiel_antwort(nr: int, d: L.Daten, s: pd.Timestamp) -> str:
    k = L.kennzahlen(d, s)
    if nr == 0:
        zer = L.db_zerlegung(d, s)
        rp = L.rabatt_profil(d, s)
        h = rp[(rp.rabattstufe == "> 20 %") & (rp.zeitraum == "Ist")]
        db_h = float(h.db1.iloc[0]) if len(h) else 0.0
        an_h = float(h.anteil.iloc[0]) if len(h) else 0.0
        return T(
            f"Umsatz {L.geld(k['umsatz'])} ({L.proz(k['umsatz_abw'])} gegen Plan), DB I {L.geld(k['db1'])} "
            f"({L.proz(k['db1_abw'])}). Zerlegt man die DB-I-Abweichung, kommt der Mengeneffekt auf {L.geld(zer['menge'])}, "
            f"der Mix auf {L.geld(zer['mix'])} und der Preis-/Rabatteffekt auf {L.geld(zer['preis'])}.\n\n"
            f"Der Haupttreiber sind Aufträge mit mehr als 20 % Rabatt: Sie bringen {L.proz(an_h, False)} des Umsatzes, "
            f"aber {L.geld(db_h)} DB I.\n\n**Vorschlag:** Rabatte über 20 % prüfen; die Wirkung eines Deckels "
            f"rechnest du unter „Was wäre wenn?“ durch.",
            f"Revenue {L.geld(k['umsatz'])} ({L.proz(k['umsatz_abw'])} vs. plan), contribution margin {L.geld(k['db1'])} "
            f"({L.proz(k['db1_abw'])}). Breaking down the gap: volume effect {L.geld(zer['menge'])}, "
            f"mix {L.geld(zer['mix'])}, price/discount effect {L.geld(zer['preis'])}.\n\n"
            f"The main driver is orders with more than 20% discount: they bring {L.proz(an_h, False)} of revenue "
            f"but {L.geld(db_h)} of contribution margin.\n\n**Suggestion:** review discounts above 20%; model the "
            f"effect of a cap under “What if?”.")
    if nr == 1:
        reg = L.plan_ist_nach(d, s, "region")
        w = reg.iloc[0]
        if len(reg) == 1:
            return T(f"Dieser Mandant ist eine Region ({w.region}): Umsatz {L.proz(w.abw_proz)} gegen Plan, "
                     f"DB-I-Abweichung {L.geld(w.db1_abw)}. Den Vergleich mit anderen zeigt der Benchmark.",
                     f"This client is a single region ({w.region}): revenue {L.proz(w.abw_proz)} vs. plan, "
                     f"contribution margin gap {L.geld(w.db1_abw)}. The Benchmark page compares it with others.")
        return T(f"Zuerst **{w.region}**: {L.proz(w.abw_proz)} gegen Plan, also {L.geld(abs(w.abw))} weniger Umsatz "
                 f"und {L.geld(abs(w.db1_abw))} DB-I-Lücke. Am besten läuft {reg.iloc[-1].region} "
                 f"({L.proz(reg.iloc[-1].abw_proz)}).",
                 f"Start with **{w.region}**: {L.proz(w.abw_proz)} vs. plan, i.e. {L.geld(abs(w.abw))} less revenue "
                 f"and a {L.geld(abs(w.db1_abw))} contribution margin gap. Best performer is {reg.iloc[-1].region} "
                 f"({L.proz(reg.iloc[-1].abw_proz)}).")
    prog = L.liquiditaet_prognose(d, s)
    reicht = prog["minimum"] >= prog["puffer"]
    if prog["minimum_tag"] == s:
        verlauf_de = "fällt er nicht unter den heutigen Stand"
        verlauf_en = "it does not fall below today's level"
    else:
        verlauf_de = f"sinkt er bis auf {L.geld(prog['minimum'])} ({L.datum(prog['minimum_tag'])})"
        verlauf_en = f"it falls to {L.geld(prog['minimum'])} ({L.datum(prog['minimum_tag'])})"
    return T(
        f"Kontostand heute {L.geld(prog['start'])}. In den nächsten 13 Wochen {verlauf_de} "
        f"und liegt am Ende bei {L.geld(prog['ende'])}. Der Puffer beträgt "
        f"{L.geld(prog['puffer'])}, das Geld reicht also " + ("mit Puffer." if reicht else
        "nicht mit Puffer" + (" – das Konto rutscht ins Minus." if prog["minimum"] < 0 else ".")),
        f"Balance today {L.geld(prog['start'])}. Over the next 13 weeks {verlauf_en} "
        f"and ends at {L.geld(prog['ende'])}. The buffer is {L.geld(prog['puffer'])}, "
        "so the cash " + ("lasts with buffer." if reicht else
        "does not keep the buffer" + (" – the account goes overdrawn." if prog["minimum"] < 0 else ".")))
