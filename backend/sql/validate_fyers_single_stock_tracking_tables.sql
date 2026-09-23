-- Validation queries for FYERS single-stock tracking tables.

SELECT table_name
FROM user_tables
WHERE table_name IN ('FYERS_REUSE_SYMBOLS', 'FYERS_SUCCESS_SYMBOLS')
ORDER BY table_name;

SELECT index_name, table_name
FROM user_indexes
WHERE table_name IN ('FYERS_REUSE_SYMBOLS', 'FYERS_SUCCESS_SYMBOLS')
ORDER BY table_name, index_name;

SELECT constraint_name, table_name, constraint_type, status
FROM user_constraints
WHERE table_name IN ('FYERS_REUSE_SYMBOLS', 'FYERS_SUCCESS_SYMBOLS')
ORDER BY table_name, constraint_name;

SELECT status, COUNT(*) AS row_count
FROM FYERS_REUSE_SYMBOLS
GROUP BY status
ORDER BY status;

SELECT status, COUNT(*) AS row_count
FROM FYERS_SUCCESS_SYMBOLS
GROUP BY status
ORDER BY status;
