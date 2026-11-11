"""Die wichtigsten Kennzahlen als lesbare SQL-Abfragen (Ordner sql/).

Die App rechnet mit pandas (logik.py). Die SQL-Dateien rechnen dieselben Zahlen direkt in der SQLite-Datenbank;
tests/test_cockpit.py prüft, dass beide Wege übereinstimmen. In der App zeigt „SQL anzeigen“ Abfrage und Ergebnis.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

import logik as L

ORDNER = Path(__file__).resolve().parent / "sql"


def dateien() -> list[Path]:
    return sorted(ORDNER.glob("*.sql"))


def text(name: str) -> str:
    """SQL-Text einer Abfrage, z. B. text("01_kennzahlen_plan_ist")."""
    return (ORDNER / f"{name}.sql").read_text(encoding="utf-8")


def ausfuehren(name: str, stichtag, pfad: Path | str | None = None) -> pd.DataFrame:
    """Führt die Abfrage gegen die SQLite-Datenbank aus (Parameter :stichtag)."""
    with sqlite3.connect(pfad or L.DB_PFAD) as con:
        return pd.read_sql(text(name), con, params={"stichtag": pd.Timestamp(stichtag).strftime("%Y-%m-%d")})
