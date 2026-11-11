"""Zweisprachigkeit (Deutsch/Englisch).

Texte stehen direkt im Code als Paar:  T("Überblick", "Overview").
Die aktive Sprache gilt je Thread; Streamlit rechnet jede Sitzung in einem eigenen Thread,
gleichzeitige Nutzer mit unterschiedlicher Sprache stören sich also nicht.
Zahlenformat: Deutsch 1.234,5 · Englisch 1,234.5 (siehe logik.zahl).
"""
from __future__ import annotations

import threading

SPRACHEN = {"de": "Deutsch", "en": "English"}
_ctx = threading.local()


def setze(sprache: str) -> None:
    _ctx.sprache = sprache if sprache in SPRACHEN else "de"


def aktiv() -> str:
    return getattr(_ctx, "sprache", "de")


def en() -> bool:
    return aktiv() == "en"


def T(de: str, en_: str) -> str:
    """Gibt den Text in der aktiven Sprache zurück."""
    return en_ if en() else de


# Wiederkehrende Begriffe aus den Daten (Spaltenwerte bleiben deutsch, angezeigt wird übersetzt)
BEGRIFFE = {
    "grün": "green", "gelb": "amber", "rot": "red",
    "offen": "open", "in Arbeit": "in progress", "erledigt": "done", "verworfen": "dropped",
    "bezahlt": "paid", "uneinbringlich": "written off",
    "Personal": "Staff", "Miete": "Rent", "Marketing": "Marketing", "IT & Verwaltung": "IT & admin",
    "Umsatz": "Revenue", "Marge": "Margin", "Region": "Region", "Fixkosten": "Fixed costs",
    "Forderungen": "Receivables", "Liquidität": "Liquidity", "Szenario": "Scenario",
}


def B(wort) -> str:
    """Übersetzt einen Begriff aus den Daten, wenn Englisch aktiv ist."""
    if wort is None:
        return ""
    return BEGRIFFE.get(str(wort), str(wort)) if en() else str(wort)
