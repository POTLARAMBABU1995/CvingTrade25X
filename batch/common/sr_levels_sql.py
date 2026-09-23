from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, Mapping, Set

from batch.common.db import fetch_all

PRIMARY_TABLE_NAME = 'SR_LEVELS'
LEGACY_TABLE_NAME = 'SR_LEVELS'
MODERN_VALUE_COLUMN = 'SR_LEVELS'
MINIMAL_VALUE_COLUMN = 'SR_LEVEL'
LEGACY_AUX_COLUMNS = (
    'PRICE_LOW',
    'PRICE_HIGH',
    'STRENGTH',
    'TOUCHES',
    'LAST_TOUCH_DATE',
)
_ROUND_SENTINEL = '-999999999999'


@lru_cache(maxsize=1)
def resolve_sr_levels_table_name() -> str:
    return 'SR_LEVELS'


def fetch_sr_levels_metadata() -> Dict[str, Dict[str, str | bool | None]]:
    table_name = resolve_sr_levels_table_name()
    rows = fetch_all(
        """
        SELECT column_name, data_type, nullable, data_default
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {'table_name': table_name},
    )
    metadata: Dict[str, Dict[str, str | bool | None]] = {}
    for row in rows:
        name = str(row['column_name']).upper()
        metadata[name] = {
            'data_type': row.get('data_type'),
            'nullable': str(row.get('nullable') or '').upper() == 'Y',
            'data_default': row.get('data_default'),
        }
    return metadata


def fetch_sr_levels_columns() -> Set[str]:
    return set(fetch_sr_levels_metadata())


def _normalize_column_names(columns_or_metadata: Iterable[str] | Mapping[str, object]) -> Set[str]:
    if isinstance(columns_or_metadata, Mapping):
        return {str(column).upper() for column in columns_or_metadata.keys()}
    return {str(column).upper() for column in columns_or_metadata}


def resolve_sr_value_column(columns_or_metadata: Iterable[str] | Mapping[str, object]) -> str:
    column_set = _normalize_column_names(columns_or_metadata)
    if MINIMAL_VALUE_COLUMN in column_set:
        return MINIMAL_VALUE_COLUMN
    if MODERN_VALUE_COLUMN in column_set:
        return MODERN_VALUE_COLUMN
    raise RuntimeError(
        f'{PRIMARY_TABLE_NAME} table must expose either {MINIMAL_VALUE_COLUMN} or {MODERN_VALUE_COLUMN}'
    )


def get_sr_levels_value_column() -> str:
    return resolve_sr_value_column(fetch_sr_levels_columns())


def _render_modern_sr_levels_sql(table_name: str) -> str:
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
  AND NVL(ROUND(dst.{MODERN_VALUE_COLUMN}, 6), {_ROUND_SENTINEL}) = ROUND(src.LEVEL_VALUE, 6)
)
WHEN MATCHED THEN UPDATE SET
  dst.UPDATED_AT = SYSDATE
WHEN NOT MATCHED THEN INSERT (
  LEVEL_ID, SYMBOL, TF, LEVEL_TYPE, {MODERN_VALUE_COLUMN}
) VALUES (
  src.LEVEL_ID, src.SYMBOL, src.TF, src.LEVEL_TYPE, src.LEVEL_VALUE
)
""".strip()


def _render_minimal_sr_level_sql(table_name: str) -> str:
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
  AND NVL(ROUND(dst.{MINIMAL_VALUE_COLUMN}, 6), {_ROUND_SENTINEL}) = ROUND(src.LEVEL_VALUE, 6)
)
WHEN MATCHED THEN UPDATE SET
  dst.UPDATED_AT = SYSDATE
WHEN NOT MATCHED THEN INSERT (
  LEVEL_ID, SYMBOL, TF, LEVEL_TYPE, {MINIMAL_VALUE_COLUMN}
) VALUES (
  src.LEVEL_ID, src.SYMBOL, src.TF, src.LEVEL_TYPE, src.LEVEL_VALUE
)
""".strip()


def _render_legacy_sr_level_sql(
    table_name: str,
    columns_or_metadata: Iterable[str] | Mapping[str, object],
) -> str:
    column_set = _normalize_column_names(columns_or_metadata)
    update_clauses = []
    insert_columns = ['LEVEL_ID', 'SYMBOL', 'TF', 'LEVEL_TYPE']
    insert_values = ['src.LEVEL_ID', 'src.SYMBOL', 'src.TF', 'src.LEVEL_TYPE']

    if 'PRICE_LOW' in column_set:
        update_clauses.append('  dst.PRICE_LOW = src.LEVEL_VALUE')
        insert_columns.append('PRICE_LOW')
        insert_values.append('src.LEVEL_VALUE')
    if 'PRICE_HIGH' in column_set:
        update_clauses.append('  dst.PRICE_HIGH = src.LEVEL_VALUE')
        insert_columns.append('PRICE_HIGH')
        insert_values.append('src.LEVEL_VALUE')
    if 'STRENGTH' in column_set:
        update_clauses.append('  dst.STRENGTH = COALESCE(dst.STRENGTH, 1)')
        insert_columns.append('STRENGTH')
        insert_values.append('1')
    if 'TOUCHES' in column_set:
        update_clauses.append('  dst.TOUCHES = COALESCE(dst.TOUCHES, 1)')
        insert_columns.append('TOUCHES')
        insert_values.append('1')
    if 'LAST_TOUCH_DATE' in column_set:
        update_clauses.append('  dst.LAST_TOUCH_DATE = COALESCE(dst.LAST_TOUCH_DATE, SYSDATE)')
        insert_columns.append('LAST_TOUCH_DATE')
        insert_values.append('SYSDATE')

    insert_columns.append(MINIMAL_VALUE_COLUMN)
    insert_values.append('src.LEVEL_VALUE')
    update_clauses.append('  dst.UPDATED_AT = SYSDATE')

    update_sql = ',\n'.join(update_clauses)
    insert_sql = ', '.join(insert_columns)
    values_sql = ', '.join(insert_values)

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
  AND NVL(ROUND(dst.{MINIMAL_VALUE_COLUMN}, 6), {_ROUND_SENTINEL}) = ROUND(src.LEVEL_VALUE, 6)
)
WHEN MATCHED THEN UPDATE SET
{update_sql}
WHEN NOT MATCHED THEN INSERT (
  {insert_sql}
) VALUES (
  {values_sql}
)
""".strip()


def build_sr_levels_merge_sql(columns_or_metadata: Iterable[str] | Mapping[str, object]) -> str:
    column_set = _normalize_column_names(columns_or_metadata)
    value_column = resolve_sr_value_column(column_set)
    table_name = resolve_sr_levels_table_name()

    if value_column == MODERN_VALUE_COLUMN:
        return _render_modern_sr_levels_sql(table_name)

    if any(column in column_set for column in LEGACY_AUX_COLUMNS):
        return _render_legacy_sr_level_sql(table_name, column_set)

    return _render_minimal_sr_level_sql(table_name)


def get_sr_levels_merge_sql() -> str:
    metadata = fetch_sr_levels_metadata()
    if not metadata:
        raise RuntimeError(f'{PRIMARY_TABLE_NAME} table not found in current Oracle schema')
    return build_sr_levels_merge_sql(metadata)


def build_sr_levels_presence_sql(value_column: str) -> str:
    table_name = resolve_sr_levels_table_name()
    return f"""
SELECT ROUND({value_column}, 6) AS LEVEL_VALUE
FROM {table_name}
WHERE SYMBOL = :symbol
  AND TF = :tf
  AND LEVEL_TYPE = :level_type
""".strip()

