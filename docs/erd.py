"""Erzeugt docs/datenmodell_de.png und docs/datenmodell_en.png aus dem Schema der SQLite-Datenbank (Graphviz)."""
import sqlite3
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import logik as L  # noqa: E402

ECHT, SIM, DIM = "#0F2A4A", "#D5DCE6", "#F1F3F6"   # Navy-Design: echt dunkel, simuliert hell, Dimension grau
KOPF_TEXT = {ECHT: ("white", "#C3CDDA")}          # Titel- und Untertitelfarbe im dunklen Kopf
TAB = {   # Tabelle: (Farbe, Text DE, Text EN, gezeigte Spalten)
    "fakt_umsatz": (ECHT, "eine Zeile je Auftragsposition · echt", "one row per order line · real",
                    ["position_id", "auftrag_id", "monat", "region", "kategorie", "kunde_id", "produkt_id",
                     "rabattstufe", "umsatz", "db1", "wareneinsatz*", "versandkosten*"]),
    "dim_kunde": (DIM, "Kunden · Zahlungsverhalten simuliert", "customers · payment behaviour simulated",
                  ["kunde_id", "kunde", "segment", "hauptregion", "zahlungsverhalten_sim*"]),
    "dim_produkt": (DIM, "Produkte · echt", "products · real", ["produkt_id", "produkt", "kategorie", "subkategorie"]),
    "fakt_plan": (SIM, "Plan je Monat × Region × Kategorie · Join über diese drei", "plan per month × region × category · joined on these three",
                  ["monat", "region", "kategorie", "umsatz_plan", "db1_plan"]),
    "fakt_fixkosten": (SIM, "Fixkosten je Monat × Kostenart · Join über Monat", "fixed costs per month × cost type · joined on month",
                       ["monat", "kostenart", "plan", "ist"]),
    "fakt_rechnungen": (SIM, "eine Rechnung je Auftrag", "one invoice per order",
                        ["auftrag_id", "kunde_id", "rechnungsdatum", "betrag", "faellig_am", "bezahlt_am", "status"]),
    "fakt_liquiditaet_tag": (SIM, "Kontostand je Tag, aus allen Zahlungen", "daily bank balance from all payments",
                             ["datum", "einzahlungen", "auszahlungen_fix", "kontostand"]),
}
KANTEN = [   # (von, Spalte, nach, Spalte, Beschriftung DE, EN, gestrichelt = logische Verknüpfung)
    ("fakt_umsatz", "kunde_id", "dim_kunde", "kunde_id", "n : 1", "n : 1", False),
    ("fakt_umsatz", "produkt_id", "dim_produkt", "produkt_id", "n : 1", "n : 1", False),
    ("fakt_rechnungen", "auftrag_id", "fakt_umsatz", "auftrag_id", "1 : n", "1 : n", False),
    ("fakt_rechnungen", "kunde_id", "dim_kunde", "kunde_id", "n : 1", "n : 1", False),
    ("fakt_plan", "monat", "fakt_umsatz", "monat", "Monat + Region + Kategorie", "month + region + category", True),
    ("fakt_fixkosten", "monat", "fakt_umsatz", "monat", "Monat", "month", True),
]


def dot(sprache: str, zeilen: dict) -> str:
    en = sprache == "en"
    out = ['digraph G {', 'graph [rankdir=LR, bgcolor="white", pad=0.3, nodesep=0.35, ranksep=1.1, '
           'fontname="Helvetica", fontsize=12, fontcolor="#0F2A4A", labelloc=t, labeljust=l, label=<'
           + ("<b>Data model · Unicorn cockpit (SQLite)</b><br/><font point-size='10' color='#4B5A6E'>"
              "navy = real sample data · light blue = simulated · grey = dimension · * simulated column · "
              "dashed = join on shared keys, no ID</font>" if en else
              "<b>Datenmodell · Unicorn-Cockpit (SQLite)</b><br/><font point-size='10' color='#4B5A6E'>"
              "Navy = echte Beispieldaten · hellblau = simuliert · grau = Dimension · * simulierte Spalte · "
              "gestrichelt = Verknüpfung über gemeinsame Schlüssel, keine ID</font>") + '>];',
           'node [shape=plain, fontname="Helvetica", fontsize=10, fontcolor="#0F2A4A"];',
           'edge [color="#4B5A6E", fontname="Helvetica", fontsize=9, fontcolor="#4B5A6E", arrowsize=0.7];']
    for t, (farbe, de, en_txt, spalten) in TAB.items():
        kopf, unter = KOPF_TEXT.get(farbe, ("#0F2A4A", "#4B5A6E"))
        n = f"{zeilen[t]:,}".replace(",", "." if not en else ",")
        z = "".join(f'<tr><td port="{c.rstrip("*")}" align="left" bgcolor="white">{c}</td></tr>' for c in spalten)
        out.append(f'{t} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="4" color="#9AA6B6">'
                   f'<tr><td bgcolor="{farbe}" align="left"><font color="{kopf}"><b>{t}</b></font></td></tr>'
                   f'<tr><td bgcolor="{farbe}" align="left"><font point-size="8.5" color="{unter}">'
                   f'{en_txt if en else de} · {n} {"rows" if en else "Zeilen"}</font></td></tr>{z}</table>>];')
    for a, ca, b, cb, de, en_txt, gestr in KANTEN:
        if gestr:
            out.append(f'{a}:{ca} -> {b}:{cb} [style=dashed, arrowhead=none];')
        else:
            kt, kh = (en_txt if en else de).split(" : ")
            if (a, b) == ("fakt_rechnungen", "dim_kunde"):
                kh = ""          # die „1“ am Kunden steht schon an der Kante von fakt_umsatz
            out.append(f'{a}:{ca} -> {b}:{cb} [taillabel="{kt}", headlabel="{kh}", labeldistance=1.6, labelangle=25];')
    out.append('{rank=same; fakt_plan; fakt_fixkosten; fakt_rechnungen}')
    out.append('{rank=same; dim_kunde; dim_produkt}')
    out.append('}')
    return "\n".join(out)


if __name__ == "__main__":
    with sqlite3.connect(L.DB_PFAD) as con:
        zeilen = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TAB}
    for sp in ("de", "en"):
        subprocess.run(["dot", "-Tpng", "-Gdpi=130", "-o", str(HIER / f"datenmodell_{sp}.png")],
                       input=dot(sp, zeilen).encode(), check=True)
    print("ok")
