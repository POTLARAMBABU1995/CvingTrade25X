-- Validate FYERS holdings schema objects and basic row counts.

SELECT table_name
FROM user_tables
WHERE table_name IN (
    'FYERS_HOLDINGS_IMPORTS',
    'FYERS_HOLDINGS_CURRENT',
    'FYERS_HOLDINGS_AUDIT'
)
ORDER BY table_name;

SELECT index_name, table_name, uniqueness
FROM user_indexes
WHERE index_name IN (
    'FYERS_HOLDINGS_CURR_UK1',
    'FYERS_HOLDINGS_CURR_IDX1',
    'FYERS_HOLDINGS_AUDIT_IDX1'
)
ORDER BY index_name;

SELECT
    (SELECT COUNT(*) FROM FYERS_HOLDINGS_IMPORTS) AS import_count,
    (SELECT COUNT(*) FROM FYERS_HOLDINGS_CURRENT) AS current_count,
    (SELECT COUNT(*) FROM FYERS_HOLDINGS_AUDIT) AS audit_count
FROM dual;

SELECT CLIENT_ID, COUNT(*) AS holding_count
FROM FYERS_HOLDINGS_CURRENT
GROUP BY CLIENT_ID
ORDER BY CLIENT_ID;
