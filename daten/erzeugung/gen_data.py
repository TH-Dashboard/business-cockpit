"""
Unternehmer-Cockpit · Datengrundlage aus dem Unicorn-Projekt
=============================================================
Eingang : cockpit_export_positionen.csv  (Beekeeper-Export, 9.997 Positionen, ECHT)
Ausgang : out/*.csv + out/unicorn_cockpit.sqlite

ECHT       = unverändert aus der Unicorn-Datenbank
SIMULIERT  = für Übungszwecke ergänzt, Annahmen siehe daten_dokumentation.md
Die Rechenschritte stehen in aufbau.py (dieselben nutzt die App nach dem Hochladen und Bereinigen).
Reproduzierbar über SEED.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import aufbau  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "raw.csv")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "out")
OUT.mkdir(exist_ok=True)

roh = pd.read_csv(SRC, parse_dates=["order_date", "shipping_date"])
assert len(roh) == 9997 and roh.order_sales.sum() == 2_307_249 and roh.order_profits.sum() == 289_956

tabellen = aufbau.erzeuge_tabellen(roh, seed=aufbau.SEED)
con = sqlite3.connect(OUT / "unicorn_cockpit.sqlite")
for name, t in tabellen.items():
    t.to_csv(OUT / f"{name}.csv", index=False)
    t.to_sql(name, con, if_exists="replace", index=False)
con.close()
for name, t in tabellen.items():
    print(f"{name:24s} {len(t):>6} Zeilen")
