# Unternehmer-Cockpit · Datengrundlage (Unicorn)

Stand: 11.11.2026 · Erzeugt mit `gen_data.py` (Seed 42, reproduzierbar)

## Herkunft

| Ebene | Quelle | Status |
|---|---|---|
| Umsatz, Rabatt, Menge, DB I je Position | Unicorn-Datenbank (Neon), Export `cockpit_export_positionen.csv` | **echt** |
| Aufteilung Wareneinsatz / Versandkosten | Annahme Versandsatz je Versandart | simuliert |
| Plan (Umsatz, DB I) 2016–2019 | aus Vorjahres-Ist + Wachstumsziel | simuliert |
| Fixkosten Plan/Ist 2015–2019 | Annahme | simuliert |
| Rechnungen, Zahlungsziele, Zahlungseingänge | Annahme je Segment + Kundenverhalten | simuliert |
| Kontostand je Tag | aus allen Zahlungsströmen | simuliert |

## Abgleich mit der korrigierten Analyse (06.11.2026)

Der Export stimmt exakt: 9.997 Positionen, 5.013 Aufträge, 793 Kunden, Umsatz 2.307.249 $, DB I 289.956 $. Auch Jahre (497.371 / 470.425 / 607.904 / 731.549 $), Regionen 2017–2018, Rabattstufen und Kategorien stimmen. `gen_data.py` bricht ab, wenn Zeilenzahl, Umsatz oder Gewinn abweichen.

## Tabellen

| Tabelle | Zeilen | Inhalt |
|---|---|---|
| `fakt_umsatz` | 9.997 | eine Zeile je Position; `umsatz`, `db1` echt; `listenumsatz`, `rabattbetrag` daraus berechnet; `wareneinsatz`, `versandkosten` simuliert, Summe = Umsatz − DB I |
| `fakt_plan` | 576 | Monat × Region × Kategorie, `umsatz_plan`, `db1_plan`, Jahre 2016–2019 |
| `fakt_fixkosten` | 240 | Monat × Kostenart (Personal, Miete, Marketing, IT & Verwaltung), `plan`, `ist` (2019 nur Plan) |
| `fakt_rechnungen` | 5.013 | eine Rechnung je Auftrag; Rechnungsdatum = Versanddatum; Ziel, fällig, bezahlt, Status |
| `fakt_liquiditaet_tag` | 1.461 | Ein- und Auszahlungen je Tag, Kontostand 01.01.2015–31.12.2018 |
| `dim_kunde` | 793 | Kunde, Segment, Hauptregion, simuliertes Zahlungsverhalten |
| `dim_produkt` | 1.850 | Produkt, Kategorie, Subkategorie |

Alle Tabellen liegen als CSV und gemeinsam in `unicorn_cockpit.sqlite`.

## Annahmen im Detail

**DB I:** `order_profits` wird als Deckungsbeitrag I gelesen, also Umsatz minus Wareneinsatz und Versand. Darüber liegen die Fixkosten.

**Versandkosten** in % vom Umsatz: Same Day 6 %, First Class 4 %, Second Class 3 %, Standard 2 %. Sie sind gedeckelt, sodass der Wareneinsatz nie negativ wird.

**Plan:** Erstellt jeweils Ende des Vorjahres. Jahresplan = Vorjahres-Umsatz je Region × Kategorie × (1 + Wachstumsziel). Die Verteilung auf Monate folgt der bisherigen Saison der Kategorie. Plan-Marge = Vorjahresmarge + Verbesserungsziel (Furniture +1,5 Pp., sonst +0,5 Pp.).

| Wachstumsziel | West | East | Central | South |
|---|---|---|---|---|
| 2016 | 10 % | 8 % | 6 % | 6 % |
| 2017 | 12 % | 10 % | 8 % | 10 % |
| 2018 | 20 % | 15 % | 8 % | 15 % |
| 2019 | 15 % | 12 % | 5 % | 12 % |

**Fixkosten:** Inhabergeführter Online-Händler, Unternehmerlohn nicht enthalten. Jahresbudget 45 / 48 / 56 / 64 / 70 Tsd. $ (2015–2019). Aufteilung: Personal 62 %, Miete 14 %, Marketing 12 % (saisonal, Schwerpunkt Herbst), IT & Verwaltung 12 %. Ist = Plan ± Zufallsabweichung (σ 4 %).

**Zahlungen:** Consumer zahlen per Karte bei Bestellung. Home Office hat 14 Tage Ziel, Corporate 30 Tage. Jeder Geschäftskunde hat ein festes Zahlungsverhalten: 70 % pünktlich, 20 % mäßig (5–20 Tage Verzug), 10 % langsam (20–60 Tage). 0,5 % der Geschäftsrechnungen fallen aus („uneinbringlich“). Wareneinsatz wird am Auftragstag gezahlt, Versand am Versandtag. Miete wird am 1., Marketing und IT am 15. und Personal am 28. des Monats bezahlt. Dazu kommt eine Privatentnahme von 1.000 $ am Monatsende. Der Anfangsbestand beträgt 60.000 $.

## Eingebaute Signale (für Abweichungsanalyse und Frühwarnung)

1. **Umsatz über Plan, DB I unter Plan (2018):** Umsatz +4,8 % über Plan, DB I 92.943 $ statt 99.166 $. Ursache in den echten Daten sind die Rabatte über 20 %.
2. **Central verfehlt 2018 den Plan** um −7,6 %, South liegt +15,8 % darüber.
3. **Marketing überzieht ab September 2018** um rund 25 %.
4. **Personalkosten steigen ab Juli 2018** um rund 8 % (Aushilfe).
5. **Große Corporate-Kunden in Central zahlen ab Juli 2018** 30–60 Tage später.
6. **Liquiditätsengpass April 2015:** Tiefpunkt 2.360 $ am 16.04.2015.

Die Signale 3–6 sind simuliert. Signal 1 kommt aus den echten Daten, Signal 2 aus echten Daten gegen einen simulierten Plan.

## Grenzen

- Plan, Kosten und Zahlungen sind erfunden, aber in sich stimmig. Für Aussagen über das echte Unicorn-Geschäft gelten nur die echten Spalten.
- Keine Umsatzsteuer, keine Lagerhaltung, keine Ertragsteuern.
- Beträge in US-Dollar wie in der Quelle.
