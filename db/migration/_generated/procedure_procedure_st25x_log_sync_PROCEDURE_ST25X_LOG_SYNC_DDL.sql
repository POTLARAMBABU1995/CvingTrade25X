--------------------------------------------------------
--  Backup generated - 2026-03-29 15:02:58
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: ST25X_LOG_SYNC

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "ST25X_LOG_SYNC" (
    p_s2d NUMBER,
    p_s2o NUMBER,
    p_d2s NUMBER,
    p_status VARCHAR2,
    p_error VARCHAR2 DEFAULT NULL
)
IS
BEGIN
    INSERT INTO ST25X_SYNC_LOG (
	STOCK_TO_DEV_INSERTED,
	STOCK_TO_ORACLE_INSERTED,
	DEV_TO_STOCK_INSERTED,
	STATUS,
	ERROR_MESSAGE
    ) VALUES (
	p_s2d, p_s2o, p_d2s, p_status, p_error
    );
    COMMIT;
END;
/
