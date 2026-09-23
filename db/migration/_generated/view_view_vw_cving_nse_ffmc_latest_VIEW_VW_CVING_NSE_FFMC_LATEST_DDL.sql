--------------------------------------------------------
--  Backup generated - 2026-03-29 15:09:42
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: VW_CVING_NSE_FFMC_LATEST

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "VW_CVING_NSE_FFMC_LATEST" ("ID", "TRADE_DATE", "SYMBOL", "SOURCE_NAME", "SERIES", "SECURITY_NAME", "RAW_TOTAL_MCAP", "RAW_TOTAL_MCAP_UNIT", "TOTAL_MCAP_CR", "RAW_FFMC", "RAW_FFMC_UNIT", "FFMC_CR", "RESPONSE_PAYLOAD", "FETCH_STATUS", "ERROR_MESSAGE", "FETCH_TS", "CREATED_BY", "UPDATED_TS") AS
  SELECT id, trade_date, symbol, source_name, series, security_name,
		 raw_total_mcap, raw_total_mcap_unit, total_mcap_cr,
		 raw_ffmc, raw_ffmc_unit, ffmc_cr, response_payload,
		 fetch_status, error_message, fetch_ts, created_by, updated_ts
	  FROM (
	    SELECT t.*, ROW_NUMBER() OVER (
	      PARTITION BY t.symbol, t.source_name
	      ORDER BY t.trade_date DESC, t.fetch_ts DESC, t.updated_ts DESC
	    ) rn
	    FROM CVING_NSE_FFMC_HIST t
	  )
	  WHERE rn = 1;
