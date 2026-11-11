"""Maßnahmen-Tracking: eigene kleine SQLite-Datei neben der App (die Datenbank mit den Unicorn-Daten bleibt unverändert)."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import date
from pathlib import Path

import pandas as pd

PFAD = Path(os.environ.get("COCKPIT_MASSNAHMEN", Path(__file__).resolve().parent / "massnahmen.sqlite"))
STATUS = ["offen", "in Arbeit", "erledigt", "verworfen"]
SPALTEN = ["titel", "bereich", "verantwortlich", "faellig", "status", "effekt", "notiz", "quelle", "angelegt"]
# Externer Modus: Maßnahmen gehören zu einem Mandanten. None = interner Modus (Gesamtfirma).
# Die App ruft bei jedem Durchlauf setze(mandant, sitzung) auf. Die Werte gelten je Thread; Streamlit
# rechnet jede Sitzung in einem eigenen Thread, gleichzeitige Nutzer stören sich also nicht.
# sitzung: dict aus st.session_state (Online-Demo) -> Maßnahmen nur in dieser Sitzung, nichts in der Datei.
_ctx = threading.local()


def setze(mandant: str | None, sitzung: dict | None = None) -> None:
    _ctx.aktiv, _ctx.sitzung = mandant, sitzung


def _aktiv() -> str | None:
    return getattr(_ctx, "aktiv", None)


def _sitzung() -> dict | None:
    return getattr(_ctx, "sitzung", None)


def _leer() -> pd.DataFrame:
    return pd.DataFrame({"id": pd.Series(dtype="int64"), **{c: pd.Series(dtype="object") for c in SPALTEN}})

_SQL = """create table if not exists massnahmen (
    id integer primary key autoincrement,
    titel text not null, bereich text, verantwortlich text, faellig date,
    status text default 'offen', effekt real default 0, notiz text, quelle text, angelegt date)"""


def _con():
    con = sqlite3.connect(PFAD)
    con.execute(_SQL)
    if "mandant" not in [r[1] for r in con.execute("pragma table_info(massnahmen)")]:
        con.execute("alter table massnahmen add column mandant text")   # Schritt 3: bestehende Zeilen = intern
    return con


def laden() -> pd.DataFrame:
    sz = _sitzung()
    if sz is not None:
        t = sz.get(_aktiv(), _leer()).copy()
        t["effekt"] = pd.to_numeric(t.effekt, errors="coerce").fillna(0.0)
    else:
        with _con() as con:
            t = pd.read_sql("select * from massnahmen where mandant is ? order by id", con, params=(_aktiv(),))
        t = t.drop(columns=["mandant"])
    t["faellig"] = pd.to_datetime(t.faellig).dt.date
    t["angelegt"] = pd.to_datetime(t.angelegt).dt.date
    return t


def anlegen(titel: str, bereich: str = "", effekt: float = 0.0, notiz: str = "", quelle: str = "",
            verantwortlich: str = "", faellig: date | None = None) -> None:
    sz = _sitzung()
    if sz is not None:
        t = sz.get(_aktiv(), _leer())
        neu = {"id": int(t.id.max()) + 1 if len(t) else 1, "titel": titel, "bereich": bereich,
               "verantwortlich": verantwortlich, "faellig": faellig.isoformat() if faellig else None,
               "status": "offen", "effekt": float(effekt), "notiz": notiz, "quelle": quelle,
               "angelegt": date.today().isoformat()}
        sz[_aktiv()] = pd.concat([t, pd.DataFrame([neu])], ignore_index=True)
        return
    with _con() as con:
        con.execute("insert into massnahmen (titel, bereich, verantwortlich, faellig, status, effekt, notiz, quelle, angelegt, mandant) "
                    "values (?, ?, ?, ?, 'offen', ?, ?, ?, ?, ?)",
                    (titel, bereich, verantwortlich, faellig.isoformat() if faellig else None, float(effekt),
                     notiz, quelle, date.today().isoformat(), _aktiv()))


def speichern(t: pd.DataFrame) -> None:
    """Ersetzt die Tabelle durch den bearbeiteten Stand (Zeilen ohne Titel fallen weg)."""
    t = t[t.titel.fillna("").str.strip() != ""].copy()
    t["status"] = t.status.where(t.status.isin(STATUS), "offen")
    t["angelegt"] = t.angelegt.fillna(date.today())
    t["effekt"] = pd.to_numeric(t.effekt, errors="coerce").fillna(0.0)
    for c in ("faellig", "angelegt"):
        t[c] = pd.to_datetime(t[c]).dt.strftime("%Y-%m-%d")
    sz = _sitzung()
    if sz is not None:
        t = t.reset_index(drop=True)
        t["id"] = range(1, len(t) + 1)
        sz[_aktiv()] = t[["id"] + SPALTEN]
        return
    with _con() as con:
        con.execute("delete from massnahmen where mandant is ?", (_aktiv(),))
        rows = [r + [_aktiv()] for r in t[SPALTEN].astype(object).where(t[SPALTEN].notna(), None).values.tolist()]
        sp = SPALTEN + ["mandant"]
        con.executemany(f"insert into massnahmen ({', '.join(sp)}) values ({', '.join('?' * len(sp))})", rows)


def kennzahlen(t: pd.DataFrame, heute: date | None = None) -> dict:
    heute = heute or date.today()
    aktiv = t[t.status.isin(["offen", "in Arbeit"])]
    ueber = aktiv[aktiv.faellig.notna() & (aktiv.faellig < heute)]
    return {"aktiv": len(aktiv), "ueberfaellig": len(ueber), "erledigt": int((t.status == "erledigt").sum()),
            "effekt_aktiv": aktiv.effekt.sum(), "effekt_erledigt": t.loc[t.status == "erledigt", "effekt"].sum()}
