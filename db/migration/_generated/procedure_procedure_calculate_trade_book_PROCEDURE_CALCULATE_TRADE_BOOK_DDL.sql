--------------------------------------------------------
--  Backup generated - 2026-03-29 15:49:39
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: CALCULATE_TRADE_BOOK

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "CALCULATE_TRADE_BOOK" (
    p_trade_date_buy IN DATE,
    p_trade_time_buy IN TIMESTAMP,
    p_trade_date_sell IN DATE,
    p_trade_time_sell IN TIMESTAMP,
    p_segment IN VARCHAR2,
    p_symbol IN VARCHAR2,
    p_trade_type_buy IN VARCHAR2,
    p_trade_type_sell IN VARCHAR2,
    p_quantity IN NUMBER,
    p_trade_price_buy IN NUMBER,
    p_trade_price_sell IN NUMBER,
    p_process_status IN CHAR
)
IS
    v_entry_price NUMBER;
    v_exit_price NUMBER;
    v_stop_loss NUMBER;
    v_profit NUMBER;
    v_percentage NUMBER;
    v_entry_date DATE;
    v_exit_date DATE;
    v_trading_days NUMBER;
    v_quantity NUMBER;
    v_invested NUMBER;
    v_net_profit NUMBER;
    v_dp_charges NUMBER := 12.5; -- Default value
    v_gain_loss NUMBER;
    v_trade_status CHAR;

BEGIN
    -- Check if both buy and sell orders exist
    IF p_trade_type_buy = 'BUY' AND p_trade_type_sell = 'SELL' THEN
	-- Calculate entry and exit prices
	v_entry_price := p_trade_price_buy;
	v_exit_price := p_trade_price_sell;
	v_stop_loss := v_entry_price - v_exit_price;
	v_profit := v_exit_price - v_entry_price;
	v_percentage := (v_profit / v_entry_price) * 100;
	v_entry_date := p_trade_date_buy;
	v_exit_date := p_trade_date_sell;
	v_trading_days := v_exit_date - v_entry_date;
	v_quantity := p_quantity;
	v_invested := p_quantity * v_entry_price;
	v_net_profit := ((v_exit_price - v_entry_price) * p_quantity) / 100;
	v_gain_loss := (v_net_profit - v_dp_charges);
	v_trade_status := 'Y'; -- Both buy and sell orders present

	-- Check if the total quantity matches
	IF p_quantity = v_quantity THEN
	    -- Insert the record into the table
	    INSERT INTO TRADE_BOOK_BUY_SELL_FYRES (
		TRADE_DATE,
		TRADE_TIME,
		SEGMENT,
		SYMBOL,
		TRADE_TYPE,
		QUANTITY,
		TRADE_PRICE,
		TRADE_VALUE,
		PROCESS_STATUS
	    ) VALUES (
		CASE
		    WHEN p_trade_type_sell = 'SELL' THEN v_exit_date
		    ELSE v_entry_date
		END,
		CASE
		    WHEN p_trade_type_sell = 'SELL' THEN p_trade_time_sell
		    ELSE p_trade_time_buy
		END,
		p_segment,
		p_symbol,
		p_trade_type_buy, -- Since both buy and sell exist, using buy type
		v_quantity, -- Using the calculated quantity
		v_entry_price,
		v_invested,
		v_trade_status
	    );
	ELSE
	    -- Handle the case where the total quantity doesn't match, you can add custom logic here
	    NULL;
	END IF;
    ELSIF p_trade_type_buy = 'BUY' THEN
	-- Handle case with only the buy order
	v_trade_status := 'N';
    ELSE
	-- Handle other cases or invalid trade types as needed
	NULL;
    END IF;
END;
/
