-- Enterprise Quant Engine V2 Additive Tables

-- 1. Sector Rotation V2 Audit Log
BEGIN
   EXECUTE IMMEDIATE 'CREATE TABLE SECTOR_ROTATION_V2_AUDIT_LOG (
        id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        run_date DATE NOT NULL,
        status VARCHAR2(50) NOT NULL,
        message CLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- 2. Stock Trend Snapshot V2
BEGIN
   EXECUTE IMMEDIATE 'CREATE TABLE NSE_STOCK_TREND_SNAP_V2 (
        symbol VARCHAR2(100) NOT NULL,
        trade_date DATE NOT NULL,
        sector_id VARCHAR2(100),
        close_price NUMBER(18,6),
        trend_score NUMBER(18,6),
        trend_label VARCHAR2(100),
        breakout_status VARCHAR2(100),
        rs_vs_sector NUMBER(18,6),
        rs_vs_benchmark NUMBER(18,6),
        confidence VARCHAR2(50),
        data_quality_status VARCHAR2(50),
        reason_codes VARCHAR2(500),
        PRIMARY KEY (symbol, trade_date)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- 3. Sector Rotation Snapshot V2
BEGIN
   EXECUTE IMMEDIATE 'CREATE TABLE NSE_SECTOR_ROTATION_SNAP_V2 (
        sector_code VARCHAR2(100) NOT NULL,
        trade_date DATE NOT NULL,
        sector_name VARCHAR2(255),
        rotation_phase VARCHAR2(50),
        rotation_score NUMBER(18,6),
        momentum_score NUMBER(18,6),
        breadth_score NUMBER(18,6),
        money_flow_score NUMBER(18,6),
        risk_score NUMBER(18,6),
        trend_score NUMBER(18,6),
        confidence VARCHAR2(50),
        reason_codes VARCHAR2(500),
        coverage_percent NUMBER(5,2),
        data_quality_status VARCHAR2(50),
        rs_ratio NUMBER(18,6),
        rs_momentum NUMBER(18,6),
        money_flow_signal VARCHAR2(100),
        alpha_annualized NUMBER(18,6),
        beta NUMBER(18,6),
        breadth_conflict_signal VARCHAR2(100),
        total_symbols NUMBER,
        confirmed_stocks NUMBER,
        PRIMARY KEY (sector_code, trade_date)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
