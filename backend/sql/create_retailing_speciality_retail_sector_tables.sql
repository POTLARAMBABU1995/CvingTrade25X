PROMPT Creating Retailing Speciality Retail sector tables

CREATE TABLE NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING (
    SYMBOL VARCHAR2(64 CHAR) NOT NULL,
    SECTOR VARCHAR2(128 CHAR),
    INDUSTRY VARCHAR2(128 CHAR),
    COMPANY_NAME VARCHAR2(256 CHAR),
    ACTIVE_FLAG VARCHAR2(1 CHAR) DEFAULT 'Y',
    UPDATED_DATE DATE DEFAULT SYSDATE,
    CREATED_DATE DATE DEFAULT SYSDATE
);

CREATE UNIQUE INDEX IDX_NSE_RET_SPEC_RET_SYM ON NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING(SYMBOL);

BEGIN
    MERGE INTO NSE_SECTOR_MASTER tgt
    USING (
        SELECT 'RETAILING_SPECIALITY_RETAIL' AS sector_code, 'Retailing Speciality Retail' AS sector_name, 'NIFTY_RETAILING_SPECIALITY_RETAIL' AS index_code FROM dual
    ) src
    ON (tgt.sector_code = src.sector_code)
    WHEN MATCHED THEN UPDATE SET
        tgt.sector_name = src.sector_name,
        tgt.index_code = src.index_code
    WHEN NOT MATCHED THEN INSERT (sector_code, sector_name, index_code)
    VALUES (src.sector_code, src.sector_name, src.index_code);
    COMMIT;
END;
/
