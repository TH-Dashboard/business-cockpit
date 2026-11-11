-- Kunden, die heute später zahlen als früher: Ø Verzug der letzten 6 Monate gegen die 12 Monate davor
-- Customers paying later than before: average delay of the last 6 months vs. the 12 months before
-- Basis: bezahlte Rechnungen mit Zahlungsziel, zeitlich eingeordnet nach Fälligkeit. Parameter: :stichtag
WITH rechnungen AS (
    SELECT kunde_id, verzug_tage,
           CASE WHEN date(faellig_am) > date(:stichtag, '-6 months') THEN 'jetzt' ELSE 'vorher' END AS zeitraum
    FROM fakt_rechnungen
    WHERE status = 'bezahlt'
      AND date(bezahlt_am) <= date(:stichtag)
      AND zahlungsziel_tage > 0
      AND date(faellig_am) > date(:stichtag, '-18 months')
),
je_kunde AS (
    SELECT kunde_id,
           AVG(CASE WHEN zeitraum = 'vorher' THEN verzug_tage END) AS verzug_vorher,
           AVG(CASE WHEN zeitraum = 'jetzt'  THEN verzug_tage END) AS verzug_jetzt,
           SUM(zeitraum = 'jetzt')                                 AS n_jetzt,
           SUM(zeitraum = 'vorher')                                AS n_vorher
    FROM rechnungen
    GROUP BY kunde_id
    HAVING n_jetzt >= 1 AND n_vorher >= 1 AND n_jetzt + n_vorher >= 3
)
SELECT k.kunde_id, k.kunde, k.segment, k.hauptregion,
       ROUND(j.verzug_vorher, 1)                  AS verzug_vorher_tage,
       ROUND(j.verzug_jetzt, 1)                   AS verzug_jetzt_tage,
       ROUND(j.verzug_jetzt - j.verzug_vorher, 1) AS zunahme_tage
FROM je_kunde j
JOIN dim_kunde k USING (kunde_id)
ORDER BY j.verzug_jetzt - j.verzug_vorher DESC, k.kunde_id
LIMIT 10;
