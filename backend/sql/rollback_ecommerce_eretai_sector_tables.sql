PROMPT Rolling back E-Commerce E-Retai sector tables

DELETE FROM NSE_SECTOR_MASTER WHERE sector_code = 'ECOMMERCE_ERETAI';
DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE sector_code = 'ECOMMERCE_ERETAI';
-- DROP TABLE NSE_NIFTY_ECOMMERCE_ERETAI_STAGING;

COMMIT;

PROMPT Rollback complete. Note: DROP TABLE is commented out per safety standards.
