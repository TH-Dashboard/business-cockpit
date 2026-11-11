-- Plan-Ist je Region seit Jahresbeginn, sortiert nach Abweichung (schlechteste zuerst)
-- Plan vs. actual per region year-to-date, worst first
-- Parameter: :stichtag
WITH ist AS (
    SELECT region, SUM(umsatz) AS umsatz, SUM(db1) AS db1
    FROM fakt_umsatz
    WHERE date(monat) BETWEEN date(:stichtag, 'start of year') AND date(:stichtag)
    GROUP BY region
),
plan AS (
    SELECT region, SUM(umsatz_plan) AS umsatz_plan, SUM(db1_plan) AS db1_plan
    FROM fakt_plan
    WHERE date(monat) BETWEEN date(:stichtag, 'start of year') AND date(:stichtag)
    GROUP BY region
)
SELECT
    i.region,
    i.umsatz,
    ROUND(p.umsatz_plan, 2)                              AS umsatz_plan,
    ROUND(100.0 * (i.umsatz / p.umsatz_plan - 1), 1)     AS abw_proz,
    i.db1,
    ROUND(p.db1_plan, 2)                                 AS db1_plan,
    RANK() OVER (ORDER BY i.umsatz / p.umsatz_plan)      AS rang
FROM ist i
JOIN plan p USING (region)
ORDER BY abw_proz;
