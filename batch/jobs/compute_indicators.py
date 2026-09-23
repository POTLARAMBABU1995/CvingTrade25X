import argparse
from typing import Dict, List

from batch.common.db import execute_many, fetch_all
from batch.common.math_indicators import atr, ema, macd, pivot_points, rsi

LOOKBACK_BARS = 500

MERGE_SQL = """
MERGE INTO INDICATORS_D dst
USING (
  SELECT :symbol AS SYMBOL,
         :bar_date AS BAR_DATE,
         :rsi14 AS RSI14,
         :ema20 AS EMA20,
         :ema50 AS EMA50,
         :ema200 AS EMA200,
         :atr14 AS ATR14,
         :macd_line AS MACD_LINE,
         :macd_signal AS MACD_SIGNAL,
         :macd_hist AS MACD_HIST,
         :pivot_p AS PIVOT_P,
         :pivot_r1 AS PIVOT_R1,
         :pivot_r2 AS PIVOT_R2,
         :pivot_r3 AS PIVOT_R3,
         :pivot_s1 AS PIVOT_S1,
         :pivot_s2 AS PIVOT_S2,
         :pivot_s3 AS PIVOT_S3
  FROM dual
) src
ON (dst.SYMBOL = src.SYMBOL AND dst.BAR_DATE = src.BAR_DATE)
WHEN MATCHED THEN UPDATE SET
  dst.RSI14 = src.RSI14,
  dst.EMA20 = src.EMA20,
  dst.EMA50 = src.EMA50,
  dst.EMA200 = src.EMA200,
  dst.ATR14 = src.ATR14,
  dst.MACD_LINE = src.MACD_LINE,
  dst.MACD_SIGNAL = src.MACD_SIGNAL,
  dst.MACD_HIST = src.MACD_HIST,
  dst.PIVOT_P = src.PIVOT_P,
  dst.PIVOT_R1 = src.PIVOT_R1,
  dst.PIVOT_R2 = src.PIVOT_R2,
  dst.PIVOT_R3 = src.PIVOT_R3,
  dst.PIVOT_S1 = src.PIVOT_S1,
  dst.PIVOT_S2 = src.PIVOT_S2,
  dst.PIVOT_S3 = src.PIVOT_S3,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  SYMBOL, BAR_DATE, RSI14, EMA20, EMA50, EMA200, ATR14,
  MACD_LINE, MACD_SIGNAL, MACD_HIST,
  PIVOT_P, PIVOT_R1, PIVOT_R2, PIVOT_R3, PIVOT_S1, PIVOT_S2, PIVOT_S3
) VALUES (
  src.SYMBOL, src.BAR_DATE, src.RSI14, src.EMA20, src.EMA50, src.EMA200, src.ATR14,
  src.MACD_LINE, src.MACD_SIGNAL, src.MACD_HIST,
  src.PIVOT_P, src.PIVOT_R1, src.PIVOT_R2, src.PIVOT_R3, src.PIVOT_S1, src.PIVOT_S2, src.PIVOT_S3
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
          SELECT BAR_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
          FROM OHLCV_D
          WHERE SYMBOL = :symbol
          ORDER BY BAR_DATE DESC
        ) WHERE ROWNUM <= :limit
    """
    rows = fetch_all(sql, {'symbol': symbol, 'limit': LOOKBACK_BARS})
    rows.reverse()
    return rows


def compute_for_symbol(symbol: str) -> int:
    rows = fetch_recent_bars(symbol)
    if not rows:
        return 0
    highs = [float(r['high_price']) for r in rows]
    lows = [float(r['low_price']) for r in rows]
    closes = [float(r['close_price']) for r in rows]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)
    macd_pack = macd(closes)
    pivots = pivot_points(highs, lows, closes)

    payload = []
    for idx, row in enumerate(rows):
        pivot = pivots[idx] or {}
        payload.append({
            'symbol': symbol,
            'bar_date': row['bar_date'],
            'rsi14': rsi14[idx],
            'ema20': ema20[idx],
            'ema50': ema50[idx],
            'ema200': ema200[idx],
            'atr14': atr14[idx],
            'macd_line': macd_pack['macd'][idx],
            'macd_signal': macd_pack['signal'][idx],
            'macd_hist': macd_pack['hist'][idx],
            'pivot_p': pivot.get('p'),
            'pivot_r1': pivot.get('r1'),
            'pivot_r2': pivot.get('r2'),
            'pivot_r3': pivot.get('r3'),
            'pivot_s1': pivot.get('s1'),
            'pivot_s2': pivot.get('s2'),
            'pivot_s3': pivot.get('s3'),
        })
    return execute_many(MERGE_SQL, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description='Compute daily indicators')
    parser.add_argument('--symbol', dest='symbol', required=False)
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else get_symbols()
    for symbol in symbols:
        compute_for_symbol(symbol)


if __name__ == '__main__':
    main()
