import argparse
import hashlib
from datetime import datetime
from typing import Dict, List

from batch.common.db import execute_many, fetch_all
from batch.common.math_indicators import atr, detect_pivots, fib_retracement
from batch.common.sr_levels_sql import get_sr_levels_merge_sql

LOOKBACK_BARS = 1500
PIVOT_LEFT = 2
PIVOT_RIGHT = 2
ATR_TOLERANCE_MULT = 0.5  # cluster tolerance vs ATR

PIVOT_MERGE = """
MERGE INTO PIVOTS dst
USING (
  SELECT :pivot_id AS PIVOT_ID,
         :symbol AS SYMBOL,
         :tf AS TF,
         :bar_date AS BAR_DATE,
         :pivot_type AS PIVOT_TYPE,
         :price AS PRICE,
         :left_bars AS LEFT_BARS,
         :right_bars AS RIGHT_BARS,
         :strength AS STRENGTH,
         :confidence AS CONFIDENCE
  FROM dual
) src
ON (dst.PIVOT_ID = src.PIVOT_ID)
WHEN MATCHED THEN UPDATE SET
  dst.PRICE = src.PRICE,
  dst.STRENGTH = src.STRENGTH,
  dst.CONFIDENCE = src.CONFIDENCE,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  PIVOT_ID, SYMBOL, TF, BAR_DATE, PIVOT_TYPE, PRICE, LEFT_BARS, RIGHT_BARS, STRENGTH, CONFIDENCE
) VALUES (
  src.PIVOT_ID, src.SYMBOL, src.TF, src.BAR_DATE, src.PIVOT_TYPE, src.PRICE, src.LEFT_BARS, src.RIGHT_BARS, src.STRENGTH, src.CONFIDENCE
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
          SELECT BAR_DATE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE
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


def _resolve_sr_levels(price_low: float, price_high: float) -> float:
    if price_low == price_high:
        return price_low
    return round((price_low + price_high) / 2.0, 6)


def compute_levels(symbol: str, tf: str, rows: List[Dict[str, object]], level_merge_sql: str) -> None:
    highs = [float(r['high_price']) for r in rows]
    lows = [float(r['low_price']) for r in rows]
    closes = [float(r['close_price']) for r in rows]
    atr_values = atr(highs, lows, closes, 14)
    avg_atr = next((v for v in reversed(atr_values) if v), None) or 1.0
    tolerance = avg_atr * ATR_TOLERANCE_MULT

    pivots = detect_pivots(highs, lows, PIVOT_LEFT, PIVOT_RIGHT)
    pivot_payload = []
    pivot_prices = []
    pivot_dates = []
    pivot_types = []

    for pivot in pivots:
        idx = pivot['index']
        bar_date = rows[idx]['bar_date']
        p_type = pivot['type']
        price = float(pivot['price'])
        pivot_prices.append(price)
        pivot_dates.append(bar_date)
        pivot_types.append(p_type)
        pivot_id = _hash_id(f"{symbol}:{tf}:{bar_date}:{p_type}:{price}")
        pivot_payload.append({
            'pivot_id': pivot_id,
            'symbol': symbol,
            'tf': tf,
            'bar_date': bar_date,
            'pivot_type': p_type,
            'price': price,
            'left_bars': PIVOT_LEFT,
            'right_bars': PIVOT_RIGHT,
            'strength': 1.0,
            'confidence': 0.8,
        })
    execute_many(PIVOT_MERGE, pivot_payload)

    clusters: List[Dict[str, object]] = []
    for price, bar_date in sorted(zip(pivot_prices, pivot_dates), key=lambda x: x[0]):
        if not clusters:
            clusters.append({'prices': [price], 'dates': [bar_date]})
            continue
        last_cluster = clusters[-1]
        cluster_center = sum(last_cluster['prices']) / len(last_cluster['prices'])
        if abs(price - cluster_center) <= tolerance:
            last_cluster['prices'].append(price)
            last_cluster['dates'].append(bar_date)
        else:
            clusters.append({'prices': [price], 'dates': [bar_date]})

    level_payload = []
    for cluster in clusters:
        prices = cluster['prices']
        price_low = min(prices)
        price_high = max(prices)
        sr_levels = _resolve_sr_levels(price_low, price_high)
        level_payload.append({
            'level_id': _hash_id(f"{symbol}:{tf}:SR:{sr_levels}"),
            'symbol': symbol,
            'tf': tf,
            'level_type': 'SR',
            'sr_levels': sr_levels,
        })

    last_low_idx = None
    last_high_idx = None
    for i in range(len(pivot_types) - 1, -1, -1):
        if pivot_types[i] == 'LOW' and last_low_idx is None:
            last_low_idx = i
        if pivot_types[i] == 'HIGH' and last_high_idx is None:
            last_high_idx = i
        if last_low_idx is not None and last_high_idx is not None:
            break
    if last_low_idx is not None and last_high_idx is not None:
        low_price = pivot_prices[last_low_idx]
        high_price = pivot_prices[last_high_idx]
        if high_price != low_price:
            levels = fib_retracement(low_price, high_price)
            for ratio, level_price in levels.items():
                level_payload.append({
                    'level_id': _hash_id(f"{symbol}:{tf}:FIB:{ratio}:{level_price}"),
                    'symbol': symbol,
                    'tf': tf,
                    'level_type': 'FIB',
                    'sr_levels': level_price,
                })

    execute_many(level_merge_sql, level_payload)


def main() -> None:
    parser = argparse.ArgumentParser(description='Detect pivots and support/resistance levels')
    parser.add_argument('--symbol', dest='symbol', required=False)
    parser.add_argument('--tf', dest='tf', default='1D')
    args = parser.parse_args()

    level_merge_sql = get_sr_levels_merge_sql()
    symbols = [args.symbol] if args.symbol else get_symbols()
    for symbol in symbols:
        rows = fetch_recent_bars(symbol)
        if rows:
            compute_levels(symbol, args.tf, rows, level_merge_sql)


if __name__ == '__main__':
    main()



