--------------------------------------------------------
--  Backup generated - 2026-03-29 15:09:27
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: VW_CVING_NSE_DELIVERY_LATEST

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "VW_CVING_NSE_DELIVERY_LATEST" ("ID", "TRADE_DATE", "SYMBOL", "SOURCE_NAME", "SERIES", "SECURITY_NAME", "PREV_CLOSE", "CLOSE_PRICE", "TOTAL_TRADED_QTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIVERY_QTY", "DELIVERY_PCT", "RESPONSE_PAYLOAD", "FETCH_STATUS", "ERROR_MESSAGE", "FETCH_TS", "CREATED_BY", "UPDATED_TS") AS
  SELECT id, trade_date, symbol, source_name, series, security_name,
		 prev_close, close_price, total_traded_qty, turnover_lacs,
		 no_of_trades, delivery_qty, delivery_pct, response_payload,
		 fetch_status, error_message, fetch_ts, created_by, updated_ts
	  FROM (
	    SELECT t.*, ROW_NUMBER() OVER (
	      PARTITION BY t.symbol, t.source_name
	      ORDER BY t.trade_date DESC, t.fetch_ts DESC, t.updated_ts DESC
	    ) rn
	    FROM CVING_NSE_DELIVERY_HIST t
	  )
	  WHERE rn = 1;
