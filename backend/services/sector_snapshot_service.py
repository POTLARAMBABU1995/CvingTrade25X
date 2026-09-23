import logging
import json
import time
from datetime import date, datetime
from typing import Any

from db import get_oracle_connection

logger = logging.getLogger(__name__)


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != '':
            return value
    return None

def get_latest_ltc_date_fast() -> date | None:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # Assume NSE_NIFTY500_DAILY_RAW_DATA_DEV or NSE_EOD_HISTORY is the source.
            # Using FACT_OHLCV or similar table.
            # Usually latest date is best queried from FACT_OHLCV or STOCK_EOD_HISTORY
            # We will use the same query logic as _latest_raw_trading_date
            cursor.execute("SELECT MAX(TRADING_DATE) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV")
            row = cursor.fetchone()
            if row and row[0]:
                if isinstance(row[0], datetime):
                    return row[0].date()
                return row[0]
            return None
    except Exception:
        logger.exception("Failed to get latest LTC date for snapshot")
        return None
    finally:
        conn.close()

def read_sector_rotation_snapshot(ltc_date: date) -> list[dict[str, Any]] | None:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT PAYLOAD_JSON 
                FROM NSE_SECTOR_ROTATION_SNAPSHOT 
                WHERE LTC_DATE = :ltc_date
                ORDER BY SCORE DESC, SECTOR
            """, {'ltc_date': ltc_date})
            rows = cursor.fetchall()
            if not rows:
                return None
            
            payloads = []
            for row in rows:
                if row[0]:
                    try:
                        payload = json.loads(row[0].read() if hasattr(row[0], 'read') else row[0])
                        payloads.append(payload)
                    except Exception:
                        pass
            return payloads if payloads else None
    except Exception:
        logger.exception("Failed to read sector rotation snapshot")
        return None
    finally:
        conn.close()

def write_sector_rotation_snapshot(ltc_date: date, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
        
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # Delete existing for idempotency
            cursor.execute("DELETE FROM NSE_SECTOR_ROTATION_SNAPSHOT WHERE LTC_DATE = :ltc_date", {'ltc_date': ltc_date})
            
            for row in rows:
                sector = row.get('sectorCode') or row.get('sector')
                if not sector:
                    continue
                
                payload_json = json.dumps(row)
                cursor.execute("""
                    INSERT INTO NSE_SECTOR_ROTATION_SNAPSHOT (
                        LTC_DATE, SECTOR, RSI55, RSI50, SMA20, SMA50, SMA100, SCORE, PAYLOAD_JSON
                    ) VALUES (
                        :ltc_date, :sector, :rsi55, :rsi50, :sma20, :sma50, :sma100, :score, :payload_json
                    )
                """, {
                    'ltc_date': ltc_date,
                    'sector': sector,
                    'rsi55': row.get('rsi55Pct'),
                    'rsi50': row.get('rsi50Pct'),
                    'sma20': row.get('sma20Pct'),
                    'sma50': row.get('sma50Pct'),
                    'sma100': row.get('sma100Pct'),
                    'score': row.get('rotationScore', row.get('score')),
                    'payload_json': payload_json
                })
            
            cursor.execute("""
                INSERT INTO NSE_SECTOR_CACHE_AUDIT_LOG (
                    SNAPSHOT_TYPE, LTC_DATE, REFRESH_STATUS, ROW_COUNT, DURATION_MS
                ) VALUES (
                    'ROTATION_BREADTH', :ltc_date, 'SUCCESS', :row_count, 0
                )
            """, {'ltc_date': ltc_date, 'row_count': len(rows)})
            
            conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Failed to write sector rotation snapshot")
    finally:
        conn.close()

def read_sector_wise_snapshot(sector: str, ltc_date: date) -> list[dict[str, Any]] | None:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT PAYLOAD_JSON 
                FROM NSE_SECTOR_WISE_STOCKS_SNAPSHOT 
                WHERE LTC_DATE = :ltc_date AND SECTOR = :sector
            """, {'ltc_date': ltc_date, 'sector': sector})
            rows = cursor.fetchall()
            if not rows:
                return None
            
            payloads = []
            for row in rows:
                if row[0]:
                    try:
                        payload = json.loads(row[0].read() if hasattr(row[0], 'read') else row[0])
                        payloads.append(payload)
                    except Exception:
                        pass
            return payloads if payloads else None
    except Exception:
        logger.exception(f"Failed to read sector wise snapshot for {sector}")
        return None
    finally:
        conn.close()

def write_sector_wise_snapshot(sector: str, ltc_date: date, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    snapshot_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(_first_present(row, 'symbol', 'stock') or '').strip().upper()
        if not symbol:
            continue
        snapshot_rows.append({
            'ltc_date': ltc_date,
            'sector': sector,
            'symbol': symbol,
            'idx_code': _first_present(row, 'indexCode', 'index', 'INDEX', 'index_value', 'INDEX_VALUE'),
            'mcap': _first_present(row, 'mcapCr', 'totalMcap', 'mcap', 'MCAP'),
            'mcap_rank': _first_present(row, 'mcapRank', 'mcap_rank', 'MCAP_RANK', 'rank'),
            'price': _first_present(row, 'close', 'price'),
            'ath': row.get('ath'),
            'gap': _first_present(row, 'gapPct', 'gap_pct'),
            'wh52': _first_present(row, 'wh52', 'high52w', 'high_52w'),
            'wl52': _first_present(row, 'wl52', 'low52w', 'low_52w'),
            'ema20': _first_present(row, 'ema20Flag', 'ema20_flag'),
            'ema50': _first_present(row, 'ema50Flag', 'ema50_flag'),
            'ema100': _first_present(row, 'ema100Flag', 'ema100_flag'),
            'ema200': _first_present(row, 'ema200Flag', 'ema200_flag'),
            'trend': _first_present(row, 'trend', 'trendDirection'),
            'score': _first_present(row, 'score', 'masterScore'),
            'payload_json': json.dumps(row, ensure_ascii=True, default=str),
        })

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM NSE_SECTOR_WISE_STOCKS_SNAPSHOT WHERE LTC_DATE = :ltc_date AND SECTOR = :sector", 
                           {'ltc_date': ltc_date, 'sector': sector})

            if snapshot_rows:
                cursor.executemany("""
                    INSERT INTO NSE_SECTOR_WISE_STOCKS_SNAPSHOT (
                        LTC_DATE, SECTOR, SYMBOL, IDX_CODE, MCAP, MCAP_RANK, PRICE, ATH, GAP, WH52, WL52, 
                        EMA20_FLAG, EMA50_FLAG, EMA100_FLAG, EMA200_FLAG, TREND, SCORE, PAYLOAD_JSON
                    ) VALUES (
                        :ltc_date, :sector, :symbol, :idx_code, :mcap, :mcap_rank, :price, :ath, :gap, :wh52, :wl52,
                        :ema20, :ema50, :ema100, :ema200, :trend, :score, :payload_json
                    )
                """, snapshot_rows)

            cursor.execute("""
                INSERT INTO NSE_SECTOR_CACHE_AUDIT_LOG (
                    SNAPSHOT_TYPE, LTC_DATE, REFRESH_STATUS, ROW_COUNT, DURATION_MS
                ) VALUES (
                    'SECTOR_WISE_' || :sector, :ltc_date, 'SUCCESS', :row_count, 0
                )
            """, {'sector': sector, 'ltc_date': ltc_date, 'row_count': len(snapshot_rows)})

            conn.commit()
            logger.info(
                'sector_wise_oracle_snapshot_written sector=%s ltc_date=%s rows=%s',
                sector,
                ltc_date,
                len(snapshot_rows),
            )
    except Exception:
        conn.rollback()
        logger.exception(f"Failed to write sector wise snapshot for {sector}")
    finally:
        conn.close()
