import argparse
from datetime import date, datetime, timedelta

from batch.common.db import execute

MERGE_WEEK = """
MERGE INTO OHLCV_W dst
USING (
  SELECT SYMBOL,
         TRUNC(BAR_DATE, 'IW') AS BAR_DATE,
         MIN(LOW_PRICE) AS LOW_PRICE,
         MAX(HIGH_PRICE) AS HIGH_PRICE,
         SUM(VOLUME) AS VOLUME,
         MIN(OPEN_PRICE) KEEP (DENSE_RANK FIRST ORDER BY BAR_DATE) AS OPEN_PRICE,
         MAX(CLOSE_PRICE) KEEP (DENSE_RANK LAST ORDER BY BAR_DATE) AS CLOSE_PRICE
  FROM OHLCV_D
  WHERE BAR_DATE BETWEEN :from_date AND :to_date
  GROUP BY SYMBOL, TRUNC(BAR_DATE, 'IW')
) src
ON (dst.SYMBOL = src.SYMBOL AND dst.BAR_DATE = src.BAR_DATE)
WHEN MATCHED THEN UPDATE SET
  dst.OPEN_PRICE = src.OPEN_PRICE,
  dst.HIGH_PRICE = src.HIGH_PRICE,
  dst.LOW_PRICE = src.LOW_PRICE,
  dst.CLOSE_PRICE = src.CLOSE_PRICE,
  dst.VOLUME = src.VOLUME,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  SYMBOL, BAR_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
) VALUES (
  src.SYMBOL, src.BAR_DATE, src.OPEN_PRICE, src.HIGH_PRICE, src.LOW_PRICE, src.CLOSE_PRICE, src.VOLUME
)
"""

MERGE_MONTH = """
MERGE INTO OHLCV_M dst
USING (
  SELECT SYMBOL,
         TRUNC(BAR_DATE, 'MM') AS BAR_DATE,
         MIN(LOW_PRICE) AS LOW_PRICE,
         MAX(HIGH_PRICE) AS HIGH_PRICE,
         SUM(VOLUME) AS VOLUME,
         MIN(OPEN_PRICE) KEEP (DENSE_RANK FIRST ORDER BY BAR_DATE) AS OPEN_PRICE,
         MAX(CLOSE_PRICE) KEEP (DENSE_RANK LAST ORDER BY BAR_DATE) AS CLOSE_PRICE
  FROM OHLCV_D
  WHERE BAR_DATE BETWEEN :from_date AND :to_date
  GROUP BY SYMBOL, TRUNC(BAR_DATE, 'MM')
) src
ON (dst.SYMBOL = src.SYMBOL AND dst.BAR_DATE = src.BAR_DATE)
WHEN MATCHED THEN UPDATE SET
  dst.OPEN_PRICE = src.OPEN_PRICE,
  dst.HIGH_PRICE = src.HIGH_PRICE,
  dst.LOW_PRICE = src.LOW_PRICE,
  dst.CLOSE_PRICE = src.CLOSE_PRICE,
  dst.VOLUME = src.VOLUME,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  SYMBOL, BAR_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
) VALUES (
  src.SYMBOL, src.BAR_DATE, src.OPEN_PRICE, src.HIGH_PRICE, src.LOW_PRICE, src.CLOSE_PRICE, src.VOLUME
)
"""

MERGE_YEAR = """
MERGE INTO OHLCV_Y dst
USING (
  SELECT SYMBOL,
         TRUNC(BAR_DATE, 'YYYY') AS BAR_DATE,
         MIN(LOW_PRICE) AS LOW_PRICE,
         MAX(HIGH_PRICE) AS HIGH_PRICE,
         SUM(VOLUME) AS VOLUME,
         MIN(OPEN_PRICE) KEEP (DENSE_RANK FIRST ORDER BY BAR_DATE) AS OPEN_PRICE,
         MAX(CLOSE_PRICE) KEEP (DENSE_RANK LAST ORDER BY BAR_DATE) AS CLOSE_PRICE
  FROM OHLCV_D
  WHERE BAR_DATE BETWEEN :from_date AND :to_date
  GROUP BY SYMBOL, TRUNC(BAR_DATE, 'YYYY')
) src
ON (dst.SYMBOL = src.SYMBOL AND dst.BAR_DATE = src.BAR_DATE)
WHEN MATCHED THEN UPDATE SET
  dst.OPEN_PRICE = src.OPEN_PRICE,
  dst.HIGH_PRICE = src.HIGH_PRICE,
  dst.LOW_PRICE = src.LOW_PRICE,
  dst.CLOSE_PRICE = src.CLOSE_PRICE,
  dst.VOLUME = src.VOLUME,
  dst.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  SYMBOL, BAR_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
) VALUES (
  src.SYMBOL, src.BAR_DATE, src.OPEN_PRICE, src.HIGH_PRICE, src.LOW_PRICE, src.CLOSE_PRICE, src.VOLUME
)
"""


def parse_date(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def main() -> None:
    parser = argparse.ArgumentParser(description='Aggregate OHLCV timeframes')
    parser.add_argument('--from', dest='from_date', required=False)
    parser.add_argument('--to', dest='to_date', required=False)
    args = parser.parse_args()

    to_date = parse_date(args.to_date) if args.to_date else date.today()
    from_date = parse_date(args.from_date) if args.from_date else to_date - timedelta(days=400)

    params = {'from_date': from_date, 'to_date': to_date}
    execute(MERGE_WEEK, params)
    execute(MERGE_MONTH, params)
    execute(MERGE_YEAR, params)


if __name__ == '__main__':
    main()
