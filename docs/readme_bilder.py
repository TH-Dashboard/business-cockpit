"""Erzeugt die Diagramm-Bilder der README (docs/*_de.png, docs/*_en.png) mit den Farben der App.

Aufruf:  python docs/readme_bilder.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import diagramme as D  # noqa: E402
import logik as L  # noqa: E402
import sprache as S  # noqa: E402


def main() -> None:
    d = L.lade_daten()
    s = L.stichtage(d)[-1]
    for sp in S.SPRACHEN:
        S.setze(sp)
        T = S.T
        bilder = {
            "umsatz": D.monate_ist_plan(L.plan_ist_monate(d, s)),
            "wasserfall": D.db_wasserfall(L.db_zerlegung(d, s)),
            "liquiditaet": D.liquiditaet(L.liquiditaet_prognose(d, s), s),
            "benchmark": D.benchmark_punkte(L.benchmark(d, s), "gesamt",
                                            {m: f"Region {m}" for m in L.mandanten(d)},
                                            T("Unicorn gesamt", "Unicorn total")),
        }
        for name, fig in bilder.items():
            ziel = HIER / f"{name}_{sp}.png"
            fig.savefig(ziel, dpi=100, facecolor="white")
            print(ziel.name)


if __name__ == "__main__":
    main()
