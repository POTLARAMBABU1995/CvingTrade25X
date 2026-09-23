PROMPT Validating Auto Mobile rename and Auto Ancillaries sector staging table
SET DEFINE OFF;
SET SERVEROUTPUT ON;

PROMPT [1] Table and index presence
SELECT object_type, object_name
FROM user_objects
WHERE object_name IN (
    'NSE_NIFTY_AUTO_ANCILLARIES_STAGING',
    'UK_NIFTY_AUTO_ANC_SYM'
)
ORDER BY object_type, object_name;

PROMPT [2] Sector master rows
SELECT sector_code, sector_name, index_code, display_order
FROM NSE_SECTOR_MASTER
WHERE sector_code IN ('AUTO', 'AUTO_ANCILLARIES')
ORDER BY sector_code;

PROMPT [3] Auto Ancillaries staging row count
SELECT COUNT(*) AS auto_ancillaries_count
FROM NSE_NIFTY_AUTO_ANCILLARIES_STAGING;

PROMPT [4] Auto staging overlap with Auto Ancillaries source list, expected 0
SELECT COUNT(*) AS auto_overlap_count
FROM NSE_NIFTY_AUTO_STAGING
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ACGL', 'ALICON', 'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASAL', 'ASKAUTOLTD', 'AUTOAXLES',
    'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD', 'CEATLTD', 'CIEINDIA', 'CRAFTSMAN',
    'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'GNA', 'HBLENGINE', 'JAMNAAUTO', 'JBMA',
    'JKTYRE', 'JTEKTINDIA'
);

PROMPT [5] Auto Mobile CSV symbols present in Auto staging
SELECT COUNT(*) AS auto_mobile_symbol_count
FROM NSE_NIFTY_AUTO_STAGING
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ASHOKLEY', 'ATHERENERG', 'ATULAUTO', 'BAJAJ-AUTO', 'EICHERMOT', 'ESCORTS', 'FORCEMOT',
    'HEROMOTOCO', 'HINDMOTORS', 'HYUNDAI', 'M&M', 'MARUTI', 'OLAELEC', 'OLECTRA', 'SMLMAH',
    'TMCV', 'TMPV', 'TVSMOTOR'
);

PROMPT [6] Auto Ancillaries symbol map count
SELECT sector_code, COUNT(*) AS symbol_count
FROM NSE_SYMBOL_SECTOR_MAP
WHERE sector_code IN ('AUTO', 'AUTO_ANCILLARIES')
GROUP BY sector_code
ORDER BY sector_code;

PROMPT [7] Auto Ancillaries symbols mapped to unexpected sectors, expected no rows
SELECT symbol, sector_code
FROM NSE_SYMBOL_SECTOR_MAP
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ACGL', 'ALICON', 'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASAL', 'ASKAUTOLTD', 'AUTOAXLES',
    'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD', 'CEATLTD', 'CIEINDIA', 'CRAFTSMAN',
    'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'GNA', 'HBLENGINE', 'JAMNAAUTO', 'JBMA',
    'JKTYRE', 'JTEKTINDIA'
)
  AND UPPER(TRIM(SECTOR_CODE)) <> 'AUTO_ANCILLARIES'
ORDER BY symbol;

PROMPT [8] Duplicate symbols inside Auto Ancillaries staging, expected no rows
SELECT UPPER(TRIM(SYMBOL)) AS symbol, COUNT(*) AS duplicate_count
FROM NSE_NIFTY_AUTO_ANCILLARIES_STAGING
GROUP BY UPPER(TRIM(SYMBOL))
HAVING COUNT(*) > 1
ORDER BY symbol;
