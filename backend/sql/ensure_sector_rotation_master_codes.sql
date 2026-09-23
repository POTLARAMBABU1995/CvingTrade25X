PROMPT Ensuring Sector Rotation master codes for new sectors
SET DEFINE OFF;

MERGE INTO nse_sector_master tgt
USING (
    SELECT 'CAPITAL_GOODS' AS sector_code, 'Capital Goods' AS sector_name, 'NIFTY_CAPITAL_GOODS' AS index_code, 22 AS display_order FROM dual
    UNION ALL
    SELECT 'CONSTRUCTION', 'Construction', 'NIFTY_CONSTRUCTION', 23 FROM dual
    UNION ALL
    SELECT 'POWER', 'Power', 'NIFTY_POWER', 24 FROM dual
    UNION ALL
    SELECT 'SERVICES', 'Services', 'NIFTY_SERVICES', 25 FROM dual
    UNION ALL
    SELECT 'TELECOM', 'Telecom', 'NIFTY_TELECOMMUNICATION', 26 FROM dual
    UNION ALL
    SELECT 'UTILITIES', 'Utilities', 'NIFTY_UTILITIES', 27 FROM dual
) src
ON (tgt.sector_code = src.sector_code)
WHEN MATCHED THEN UPDATE SET
    tgt.sector_name = src.sector_name,
    tgt.index_code = src.index_code,
    tgt.display_order = src.display_order
WHEN NOT MATCHED THEN
    INSERT (sector_code, sector_name, index_code, display_order)
    VALUES (src.sector_code, src.sector_name, src.index_code, src.display_order);

COMMIT;

PROMPT Sector master codes ensured.
