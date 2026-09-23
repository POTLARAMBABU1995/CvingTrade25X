--------------------------------------------------------
--  Backup generated - 2026-03-29 15:48:55
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: TRIGGER
--  Source object name: TRG_STOCK_EOD_HISTORY_NORM

CREATE OR REPLACE NONEDITIONABLE TRIGGER "TRG_STOCK_EOD_HISTORY_NORM"
BEFORE INSERT OR UPDATE OF symbol ON stock_eod_history
FOR EACH ROW
BEGIN
  :NEW.symbol := normalize_symbol(:NEW.symbol);
END;

/
ALTER TRIGGER "TRG_STOCK_EOD_HISTORY_NORM" ENABLE;
