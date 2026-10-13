SELECT fecha, curva, plazo, valor
FROM datamart.view_zero_curve_end_of_day
WHERE curva IN ('CLF ICPUF 0D COL CLP ICP 0D', 'CLP ICP 0D DG', 'USD SOFR 1D COL CLP ICP 0D', 'EUR ESTR 1D COL CLP ICP 0D')
AND fecha >= '2026-01-01'


SELECT DISTINCT fecha, curva, 'ACT365', 'COM'
FROM datamart.view_zero_curve_end_of_day
WHERE curva IN ('CLF ICPUF 0D COL CLP ICP 0D', 'CLP ICP 0D DG', 'USD SOFR 1D COL CLP ICP 0D', 'EUR ESTR 1D COL CLP ICP 0D')
AND fecha >= '2026-01-01'


