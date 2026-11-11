-- Umsatzanteil und DB I je Rabattstufe, seit Jahresbeginn bis Stichtag
-- Revenue share and contribution margin I per discount level, year-to-date
-- Parameter: :stichtag
SELECT
    rabattstufe,
    COUNT(*)                                                       AS positionen,
    SUM(umsatz)                                                    AS umsatz,
    ROUND(100.0 * SUM(umsatz) / SUM(SUM(umsatz)) OVER (), 1)       AS umsatzanteil_proz,
    SUM(db1)                                                       AS db1,
    ROUND(100.0 * SUM(db1) / SUM(umsatz), 1)                       AS marge_proz
FROM fakt_umsatz
WHERE date(monat) BETWEEN date(:stichtag, 'start of year') AND date(:stichtag)
GROUP BY rabattstufe
ORDER BY CASE rabattstufe WHEN '0 %' THEN 1 WHEN '1–20 %' THEN 2 ELSE 3 END;
