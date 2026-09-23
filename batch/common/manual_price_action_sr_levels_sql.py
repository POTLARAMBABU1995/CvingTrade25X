from __future__ import annotations

from functools import lru_cache

from batch.common.db import fetch_all

TABLE_NAME = 'PRICE_ACTION_SR_LEVELS_MANUALLY'
VALUE_COLUMN = 'SR_LEVEL'
_ROUND_SENTINEL = '-999999999999'


@lru_cache(maxsize=1)
def resolve_manual_sr_levels_table_name() -> str:
    rows = fetch_all(
        """
        SELECT table_name
        FROM user_tables
        WHERE table_name = :table_name
        """,
        {'table_name': TABLE_NAME},
    )
    names = [str(row['table_name']).upper() for row in rows]
    if TABLE_NAME in names:
        return TABLE_NAME
    raise RuntimeError(f'{TABLE_NAME} table is not available in the current Oracle schema')


def get_manual_sr_levels_value_column() -> str:
    return VALUE_COLUMN


def build_manual_sr_levels_merge_sql() -> str:
    table_name = resolve_manual_sr_levels_table_name()
    return f"""
MERGE INTO {table_name} dst
USING (
  SELECT :level_id AS LEVEL_ID,
         :symbol AS SYMBOL,
         :tf AS TF,
         :level_type AS LEVEL_TYPE,
         :sr_levels AS LEVEL_VALUE
  FROM dual
) src
ON (
  dst.SYMBOL = src.SYMBOL
  AND NVL(dst.TF, '~') = src.TF
  AND NVL(dst.LEVEL_TYPE, '~') = src.LEVEL_TYPE
  AND NVL(ROUND(dst.{VALUE_COLUMN}, 6), {_ROUND_SENTINEL}) = ROUND(src.LEVEL_VALUE, 6)
)
WHEN MATCHED THEN UPDATE SET
  dst.UPDATED_AT = SYSDATE
WHEN NOT MATCHED THEN INSERT (
  LEVEL_ID, SYMBOL, TF, LEVEL_TYPE, {VALUE_COLUMN}
) VALUES (
  src.LEVEL_ID, src.SYMBOL, src.TF, src.LEVEL_TYPE, src.LEVEL_VALUE
)
""".strip()


def build_manual_sr_levels_presence_sql(value_column: str) -> str:
    table_name = resolve_manual_sr_levels_table_name()
    return f"""
SELECT ROUND({value_column}, 6) AS LEVEL_VALUE
FROM {table_name}
WHERE SYMBOL = :symbol
  AND TF = :tf
  AND LEVEL_TYPE = :level_type
""".strip()


def build_manual_sr_levels_delete_sql() -> str:
    table_name = resolve_manual_sr_levels_table_name()
    return f"""
DELETE FROM {table_name}
WHERE SYMBOL = :symbol
  AND TF = :tf
  AND LEVEL_TYPE = :level_type
  AND ROUND({VALUE_COLUMN}, 6) = ROUND(:sr_levels, 6)
""".strip()
