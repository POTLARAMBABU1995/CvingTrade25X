import argparse
import hashlib
import json
from typing import Dict, List, Optional

from batch.common.db import execute_many, fetch_all
from batch.common.math_indicators import atr
from batch.common.pattern_rules import (
    detect_breakout_from_consolidation,
    detect_bull_flag,
    detect_double_bottom,
    detect_zones,
)

LOOKBACK_BARS = 600

PATTERN_MERGE = """
MERGE INTO PATTERNS dst
USING (
  SELECT :pattern_id AS PATTERN_ID,
         :symbol AS SYMBOL,
         :tf AS TF,
         :pattern_type AS PATTERN_TYPE,
         :t1_date AS T1_DATE,
         :t2_date AS T2_DATE,
         :breakout_date AS BREAKOUT_DATE,
         :price_low AS PRICE_LOW,
         :price_high AS PRICE_HIGH,
         :score AS SCORE,
         :confidence AS CONFIDENCE,
         :details_json AS DETAILS_JSON
  FROM dual
) src
ON (dst.PATTERN_ID = src.PATTERN_ID)
WHEN MATCHED THEN UPDATE SET
  dst.T2_DATE = src.T2_DATE,
  dst.BREAKOUT_DATE = src.BREAKOUT_DATE,
  dst.PRICE_LOW = src.PRICE_LOW,
  dst.PRICE_HIGH = src.PRICE_HIGH,
  dst.SCORE = src.SCORE,
  dst.CONFIDENCE = src.CONFIDENCE,
  dst.DETAILS_JSON = src.DETAILS_JSON,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  PATTERN_ID, SYMBOL, TF, PATTERN_TYPE, T1_DATE, T2_DATE, BREAKOUT_DATE,
  PRICE_LOW, PRICE_HIGH, SCORE, CONFIDENCE, DETAILS_JSON
) VALUES (
  src.PATTERN_ID, src.SYMBOL, src.TF, src.PATTERN_TYPE, src.T1_DATE, src.T2_DATE, src.BREAKOUT_DATE,
  src.PRICE_LOW, src.PRICE_HIGH, src.SCORE, src.CONFIDENCE, src.DETAILS_JSON
)
"""

ZONE_MERGE = """
MERGE INTO ZONES dst
USING (
  SELECT :zone_id AS ZONE_ID,
         :symbol AS SYMBOL,
         :tf AS TF,
         :zone_type AS ZONE_TYPE,
         :t1_date AS T1_DATE,
         :t2_date AS T2_DATE,
         :price_low AS PRICE_LOW,
         :price_high AS PRICE_HIGH,
         :score AS SCORE,
         :confidence AS CONFIDENCE,
         :details_json AS DETAILS_JSON
  FROM dual
) src
ON (dst.ZONE_ID = src.ZONE_ID)
WHEN MATCHED THEN UPDATE SET
  dst.T2_DATE = src.T2_DATE,
  dst.PRICE_LOW = src.PRICE_LOW,
  dst.PRICE_HIGH = src.PRICE_HIGH,
  dst.SCORE = src.SCORE,
  dst.CONFIDENCE = src.CONFIDENCE,
  dst.DETAILS_JSON = src.DETAILS_JSON,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  ZONE_ID, SYMBOL, TF, ZONE_TYPE, T1_DATE, T2_DATE, PRICE_LOW, PRICE_HIGH, SCORE, CONFIDENCE, DETAILS_JSON
) VALUES (
  src.ZONE_ID, src.SYMBOL, src.TF, src.ZONE_TYPE, src.T1_DATE, src.T2_DATE, src.PRICE_LOW, src.PRICE_HIGH, src.SCORE, src.CONFIDENCE, src.DETAILS_JSON
)
"""


def get_symbols() -> List[str]:
    rows = fetch_all("SELECT SYMBOL FROM SYMBOLS WHERE IS_ACTIVE = 'Y'")
    if rows:
        return [row['symbol'] for row in rows]
    rows = fetch_all('SELECT DISTINCT SYMBOL FROM OHLCV_D')
    return [row['symbol'] for row in rows]


def fetch_recent_bars(symbol: str) -> List[Dict[str, object]]:
    sql = """
        SELECT * FROM (
          SELECT BAR_DATE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
          FROM OHLCV_D
          WHERE SYMBOL = :symbol
          ORDER BY BAR_DATE DESC
        ) WHERE ROWNUM <= :limit
    """
    rows = fetch_all(sql, {'symbol': symbol, 'limit': LOOKBACK_BARS})
    rows.reverse()
    return rows


def _hash_id(value: str) -> str:
    return hashlib.md5(value.encode('utf-8')).hexdigest()


def build_patterns(symbol: str, tf: str, rows: List[Dict[str, object]]) -> None:
    dates = [r['bar_date'] for r in rows]
    highs = [float(r['high_price']) for r in rows]
    lows = [float(r['low_price']) for r in rows]
    closes = [float(r['close_price']) for r in rows]
    volumes = [float(r['volume']) for r in rows]
    atr_values = atr(highs, lows, closes, 14)

    patterns = []
    patterns.extend(detect_breakout_from_consolidation(dates, highs, lows, closes, volumes, atr_values))
    patterns.extend(detect_bull_flag(dates, highs, lows, closes, volumes, atr_values))
    patterns.extend(detect_double_bottom(dates, highs, lows, closes, volumes))

    payload = []
    for pattern in patterns:
        t1 = dates[pattern['t1_index']]
        t2 = dates[pattern['t2_index']]
        breakout = dates[pattern['breakout_index']]
        pattern_id = _hash_id(f"{symbol}:{tf}:{pattern['pattern_type']}:{t1}:{t2}")
        payload.append({
            'pattern_id': pattern_id,
            'symbol': symbol,
            'tf': tf,
            'pattern_type': pattern['pattern_type'],
            't1_date': t1,
            't2_date': t2,
            'breakout_date': breakout,
            'price_low': pattern['price_low'],
            'price_high': pattern['price_high'],
            'score': pattern['score'],
            'confidence': pattern['confidence'],
            'details_json': json.dumps({'rule': 'v1'}, ensure_ascii=True),
        })
    execute_many(PATTERN_MERGE, payload)

    zones = detect_zones(dates, highs, lows, closes, volumes, atr_values)
    zone_payload = []
    for zone in zones:
        t1 = dates[zone['t1_index']]
        t2 = dates[zone['t2_index']]
        zone_id = _hash_id(f"{symbol}:{tf}:{zone['zone_type']}:{t1}:{t2}")
        zone_payload.append({
            'zone_id': zone_id,
            'symbol': symbol,
            'tf': tf,
            'zone_type': zone['zone_type'],
            't1_date': t1,
            't2_date': t2,
            'price_low': zone['price_low'],
            'price_high': zone['price_high'],
            'score': zone['score'],
            'confidence': zone['confidence'],
            'details_json': json.dumps({'rule': 'v1'}, ensure_ascii=True),
        })
    execute_many(ZONE_MERGE, zone_payload)


def main() -> None:
    parser = argparse.ArgumentParser(description='Detect chart patterns and zones')
    parser.add_argument('--symbol', dest='symbol', required=False)
    parser.add_argument('--tf', dest='tf', default='1D')
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else get_symbols()
    for symbol in symbols:
        rows = fetch_recent_bars(symbol)
        if rows:
            build_patterns(symbol, args.tf, rows)


if __name__ == '__main__':
    main()
