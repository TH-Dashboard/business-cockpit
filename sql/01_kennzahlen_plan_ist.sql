-- Kennzahlen seit Jahresbeginn (YTD) bis Stichtag: Umsatz, DB I, Fixkosten, EBIT – jeweils Ist und Plan
-- Key figures year-to-date: revenue, contribution margin I, fixed costs, EBIT – actual and plan
-- Parameter: :stichtag (z. B. '2018-12-31')
WITH zeitraum AS (
    SELECT date(:stichtag, 'start of year') AS von, date(:stichtag) AS bis
),
ist AS (
    SELECT SUM(umsatz) AS umsatz, SUM(db1) AS db1
    FROM fakt_umsatz, zeitraum
    WHERE date(monat) BETWEEN von AND bis
),
plan AS (
    SELECT SUM(umsatz_plan) AS umsatz_plan, SUM(db1_plan) AS db1_plan
    FROM fakt_plan, zeitraum
    WHERE date(monat) BETWEEN von AND bis
),
fix AS (
    SELECT SUM(ist) AS fix, SUM(plan) AS fix_plan
    FROM fakt_fixkosten, zeitraum
    WHERE date(monat) BETWEEN von AND bis
)
SELECT
    ist.umsatz,
    ROUND(plan.umsatz_plan, 2)                            AS umsatz_plan,
    ROUND(100.0 * (ist.umsatz / plan.umsatz_plan - 1), 1)  AS umsatz_abw_proz,
    ist.db1,
    ROUND(plan.db1_plan, 2)                               AS db1_plan,
    ROUND(100.0 * (ist.db1 / plan.db1_plan - 1), 1)        AS db1_abw_proz,
    ROUND(fix.fix, 2)                                     AS fixkosten,
    ROUND(ist.db1 - fix.fix, 2)                           AS ebit,
    ROUND(plan.db1_plan - fix.fix_plan, 2)                AS ebit_plan
FROM ist, plan, fix;
