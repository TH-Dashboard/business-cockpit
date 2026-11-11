-- Kontostand am Stichtag und Tiefpunkt seit Jahresbeginn
-- Bank balance at the cut-off date and lowest balance year-to-date
-- Parameter: :stichtag
WITH jahr AS (
    SELECT date(datum) AS datum, kontostand
    FROM fakt_liquiditaet_tag
    WHERE date(datum) BETWEEN date(:stichtag, 'start of year') AND date(:stichtag)
)
SELECT
    (SELECT ROUND(kontostand, 2) FROM jahr ORDER BY datum DESC LIMIT 1)  AS kontostand,
    (SELECT ROUND(kontostand, 2) FROM jahr ORDER BY kontostand LIMIT 1)  AS tiefpunkt,
    (SELECT datum FROM jahr ORDER BY kontostand LIMIT 1)                 AS tiefpunkt_am;
