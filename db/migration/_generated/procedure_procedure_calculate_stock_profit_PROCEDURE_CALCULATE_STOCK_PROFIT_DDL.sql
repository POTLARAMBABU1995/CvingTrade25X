--------------------------------------------------------
--  Backup generated - 2026-03-29 15:49:33
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: CALCULATE_STOCK_PROFIT

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "CALCULATE_STOCK_PROFIT" (
    p_stock_name IN VARCHAR2,
    p_entry_price NUMBER,
    p_exit_target_price NUMBER,
    p_stop_loss NUMBER,
    p_profit NUMBER,
    p_percentage NUMBER,
    p_entry_date DATE,
    p_exit_date DATE,
    p_quantity NUMBER,
    p_invested NUMBER,
    p_net_profit OUT NUMBER,
    p_dp_charges OUT NUMBER,
    p_profit_or_loss OUT VARCHAR2,
    p_trade OUT VARCHAR2,
    p_period OUT NUMBER
)
AS
BEGIN
    -- Calculate the net profit
    p_net_profit := p_quantity * (p_exit_target_price - p_entry_price);
    -- Calculate the DP charges
    p_dp_charges := p_net_profit * 0.03;
    -- Check if the trade was a profit or a loss
    IF p_net_profit > 0 THEN
	p_profit_or_loss := 'PROFIT';
	p_trade := 'LONG';
    ELSE
	p_profit_or_loss := 'LOSS';
	p_trade := 'SHORT';
    END IF;
    -- Calculate the period of the trade
    p_period := p_exit_date - p_entry_date;
END;
/
