-- Forderungslaufzeit (DSO) = offene Forderungen am Stichtag / Umsatz der letzten 12 Monate · 365
-- Days sales outstanding = open receivables at the cut-off date / revenue of the last 12 months · 365
-- Offen: Rechnung gestellt, aber am Stichtag noch nicht bezahlt; uneinbringliche Rechnungen zählen nicht.
-- Parameter: :stichtag
WITH offen AS (
    SELECT SUM(betrag) AS forderungen
    FROM fakt_rechnungen
    WHERE date(rechnungsdatum) <= date(:stichtag)
      AND (bezahlt_am IS NULL OR date(bezahlt_am) > date(:stichtag))
      AND status <> 'uneinbringlich'
),
umsatz_12m AS (
    SELECT SUM(umsatz) AS umsatz
    FROM fakt_umsatz
    WHERE date(monat) > date(:stichtag, '-12 months')
      AND date(monat) <= date(:stichtag)
)
SELECT
    offen.forderungen,
    umsatz_12m.umsatz                                         AS umsatz_12_monate,
    ROUND(offen.forderungen * 365.0 / umsatz_12m.umsatz, 1)   AS forderungslaufzeit_tage
FROM offen, umsatz_12m;
