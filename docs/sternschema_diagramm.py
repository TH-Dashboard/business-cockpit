"""Erzeugt docs/sternschema_de.svg und docs/sternschema_en.svg aus sternschema.py (Graphviz)."""
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import logik as L  # noqa: E402
import quelle as Q  # noqa: E402
import sternschema as S  # noqa: E402

FAKT, DIM, DATUM = "#DCEBFF", "#E3F2E8", "#FDE6D2"
ZAHLEN = {"fakt_umsatz": ["umsatz", "db1", "menge", "…"], "fakt_plan": ["umsatz_plan", "db1_plan"],
          "fakt_fixkosten": ["plan", "ist"], "fakt_rechnungen": ["betrag", "verzug_tage", "status"],
          "fakt_liquiditaet_tag": ["einzahlungen", "kontostand", "…"]}
INFO = {"dim_datum": ["jahr", "quartal", "monatsname", "…"], "dim_kunde": ["kunde", "segment"],
        "dim_produkt": ["produkt", "subkategorie"], "dim_ort": ["stadt", "bundesstaat"]}


def dot(sprache: str, stern: dict) -> str:
    en = sprache == "en"
    titel = ("<b>Star schema for Power BI · Unicorn cockpit</b><br/><font point-size='10' color='#556F8E'>"
             "blue = fact table · green = dimension · orange = date table · solid = active relationship "
             "(n : 1, filters from right to left) · dashed = inactive (USERELATIONSHIP)</font>" if en else
             "<b>Sternschema für Power BI · Unicorn-Cockpit</b><br/><font point-size='10' color='#556F8E'>"
             "blau = Faktentabelle · grün = Dimension · orange = Datumstabelle · durchgezogen = aktive Beziehung "
             "(n : 1, filtert von rechts nach links) · gestrichelt = inaktiv (USERELATIONSHIP)</font>")
    out = ['digraph G {', 'graph [rankdir=LR, bgcolor="white", pad=0.3, nodesep=0.3, ranksep=1.4, '
           'fontname="Helvetica", fontsize=12, fontcolor="#0A2342", labelloc=t, labeljust=l, label=<' + titel + '>];',
           'node [shape=plain, fontname="Helvetica", fontsize=10, fontcolor="#0A2342"];',
           'edge [color="#556F8E", fontname="Helvetica", fontsize=9, fontcolor="#556F8E", arrowsize=0.7];']
    schluessel = {}
    for vt, vs, zt, zs, *_ in S.BEZIEHUNGEN:
        schluessel.setdefault(vt, []).append(vs)
        schluessel.setdefault(zt, []).append(zs)
    for t, df in stern.items():
        farbe = DATUM if t == "dim_datum" else FAKT if t.startswith("fakt_") else DIM
        spalten = list(dict.fromkeys(schluessel.get(t, []))) + ZAHLEN.get(t, []) + INFO.get(t, [])
        n = f"{len(df):,}".replace(",", "." if not en else ",")
        z = "".join(f'<tr><td port="{c}" align="left" bgcolor="white">'
                    + (f"<b>{c}</b>" if c in schluessel.get(t, []) else c) + "</td></tr>" for c in spalten)
        out.append(f'{t} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3" color="#8FA3BC">'
                   f'<tr><td bgcolor="{farbe}" align="left"><b>{t}</b></td></tr>'
                   f'<tr><td bgcolor="{farbe}" align="left"><font point-size="8.5" color="#556F8E">'
                   f'{n} {"rows" if en else "Zeilen"}</font></td></tr>{z}</table>>];')
    beschriftet = set()                  # die „1“ nur einmal je Zielspalte, sonst liegen die Ziffern übereinander
    for vt, vs, zt, zs, aktiv, _ in S.BEZIEHUNGEN:
        stil = "" if aktiv else ', style=dashed, color="#B5C2D3"'
        eins = "" if (zt, zs) in beschriftet else "1"
        beschriftet.add((zt, zs))
        out.append(f'{vt}:{vs} -> {zt}:{zs} [taillabel="n", headlabel="{eins}", labeldistance=1.5{stil}];')
    out.append("{rank=same; " + "; ".join(t for t in stern if t.startswith("fakt_")) + "}")
    out.append("{rank=same; dim_datum; dim_kunde; dim_produkt; dim_ort; dim_kostenart}")
    out.append("{rank=same; dim_kategorie; dim_region}")
    out.append("}")
    return "\n".join(out)


if __name__ == "__main__":
    stern = S.baue_stern(Q.lade_sqlite(L.DB_PFAD))
    for sp in ("de", "en"):
        subprocess.run(["dot", "-Tsvg", "-o", str(HIER / f"sternschema_{sp}.svg")],
                       input=dot(sp, stern).encode(), check=True)
    print("ok")
