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


def ausfuehren(name: str, stichtag, pfad: Path | str | None = None, db: bytes | None = None) -> pd.DataFrame:
    """Führt die Abfrage gegen die SQLite-Datenbank aus (Parameter :stichtag).

    db: eine Datenbank im Speicher (siehe als_sqlite), z. B. die aufbereitete Datei statt der SQLite-Datei."""
    con = sqlite3.connect(":memory:" if db else (pfad or L.DB_PFAD))
    try:
        if db:
            con.deserialize(db)
        return pd.read_sql(text(name), con, params={"stichtag": pd.Timestamp(stichtag).strftime("%Y-%m-%d")})
    finally:
        con.close()


def als_sqlite(tabellen: dict[str, pd.DataFrame]) -> bytes:
    """Tabellen in eine SQLite-Datenbank im Speicher schreiben, so wie gen_data.py die Datei anlegt."""
    con = sqlite3.connect(":memory:")
    try:
        for n, t in tabellen.items():
            t.to_sql(n, con, index=False)
        return con.serialize()
    finally:
        con.close()
