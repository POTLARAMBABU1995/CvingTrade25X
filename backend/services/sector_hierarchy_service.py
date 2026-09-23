from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any

from cache import TTLCache
from db import get_oracle_connection

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = max(900, int(str(os.getenv('SECTOR_HIERARCHY_CACHE_TTL_SECONDS', '1800')).strip() or '1800'))
_cache = TTLCache(ttl_seconds=_CACHE_TTL_SECONDS, max_items=512)

_SQL_ACTIVE_BASE_CTE = """
WITH normalized_active AS (
    SELECT
        PARENT_SECTOR,
        INDUSTRY_SECTOR,
        SUB_SECTOR,
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL,
        EXCHANGE,
        EFFECTIVE_DATE,
        CASE
            WHEN UPPER(INDUSTRY_SECTOR) LIKE '%PHARMA%' OR UPPER(SUB_SECTOR) LIKE '%PHARMA%' THEN 100
            ELSE 0
        END AS BUCKET_PRIORITY,
        CASE WHEN UPPER(EXCHANGE) = 'NSE' THEN 10 ELSE 0 END AS EXCHANGE_PRIORITY
    FROM VW_NSE_SECTOR_HIERARCHY_ACTIVE
    WHERE SYMBOL IS NOT NULL
),
active_data AS (
    SELECT
        PARENT_SECTOR,
        INDUSTRY_SECTOR,
        SUB_SECTOR,
        SYMBOL,
        EXCHANGE
    FROM (
        SELECT
            normalized_active.*,
            ROW_NUMBER() OVER (
                PARTITION BY PARENT_SECTOR, SYMBOL
                ORDER BY BUCKET_PRIORITY DESC, EXCHANGE_PRIORITY DESC, EFFECTIVE_DATE DESC NULLS LAST, INDUSTRY_SECTOR, SUB_SECTOR, EXCHANGE
            ) AS RN
        FROM normalized_active
        WHERE SYMBOL IS NOT NULL
    )
    WHERE RN = 1
)
"""

_SQL_PARENTS = _SQL_ACTIVE_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM active_data
GROUP BY PARENT_SECTOR
ORDER BY PARENT_SECTOR
"""

_SQL_INDUSTRIES = _SQL_ACTIVE_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM active_data
WHERE PARENT_SECTOR = :parent_sector
GROUP BY PARENT_SECTOR, INDUSTRY_SECTOR
ORDER BY INDUSTRY_SECTOR
"""

_SQL_SUB_SECTORS = _SQL_ACTIVE_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM active_data
WHERE PARENT_SECTOR = :parent_sector
  AND INDUSTRY_SECTOR = :industry_sector
GROUP BY PARENT_SECTOR, INDUSTRY_SECTOR, SUB_SECTOR
ORDER BY SUB_SECTOR
"""

_SQL_STOCKS = _SQL_ACTIVE_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    SYMBOL,
    EXCHANGE
FROM active_data
WHERE (:parent_sector IS NULL OR PARENT_SECTOR = :parent_sector)
  AND (:industry_sector IS NULL OR INDUSTRY_SECTOR = :industry_sector)
  AND (:sub_sector IS NULL OR SUB_SECTOR = :sub_sector)
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR, SYMBOL
"""

_SQL_TOTAL_BY_PARENT = _SQL_ACTIVE_BASE_CTE + """
SELECT COUNT(DISTINCT SYMBOL) AS TOTAL_STOCKS
FROM active_data
WHERE PARENT_SECTOR = :parent_sector
"""

_SQL_SUMMARY_ROWS = _SQL_ACTIVE_BASE_CTE + """
SELECT
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM active_data
WHERE PARENT_SECTOR = :parent_sector
GROUP BY INDUSTRY_SECTOR, SUB_SECTOR
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR
"""

_SQL_TREE_ROWS = _SQL_ACTIVE_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    SYMBOL,
    EXCHANGE
FROM active_data
WHERE PARENT_SECTOR = :parent_sector
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR, SYMBOL
"""

_SQL_FB_BASE_CTE = """
WITH staged_union AS (
    SELECT
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL,
        'Healthcare' AS PARENT_SECTOR,
        'Healthcare & Hospitals' AS INDUSTRY_SECTOR,
        'Healthcare Segment' AS SUB_SECTOR,
        'NSE' AS EXCHANGE,
        10 AS SOURCE_PRIORITY
    FROM NSE_NIFTY_HEALTHCARE_INDEX_STAGING
    WHERE SYMBOL IS NOT NULL
    UNION ALL
    SELECT
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL,
        'Healthcare' AS PARENT_SECTOR,
        'Healthcare & Hospitals' AS INDUSTRY_SECTOR,
        'Healthcare Segment' AS SUB_SECTOR,
        'NSE' AS EXCHANGE,
        20 AS SOURCE_PRIORITY
    FROM NSE_NIFTY500_HEALTHCARE_STAGING
    WHERE SYMBOL IS NOT NULL
    UNION ALL
    SELECT
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL,
        'Healthcare' AS PARENT_SECTOR,
        'Healthcare & Hospitals' AS INDUSTRY_SECTOR,
        'Healthcare Segment' AS SUB_SECTOR,
        'NSE' AS EXCHANGE,
        30 AS SOURCE_PRIORITY
    FROM NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING
    WHERE SYMBOL IS NOT NULL
    UNION ALL
    SELECT
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL,
        'Healthcare' AS PARENT_SECTOR,
        'Pharmaceuticals' AS INDUSTRY_SECTOR,
        'Pharma Segment' AS SUB_SECTOR,
        'NSE' AS EXCHANGE,
        100 AS SOURCE_PRIORITY
    FROM NSE_NIFTY_PHARMA_STAGING
    WHERE SYMBOL IS NOT NULL
),
ranked_union AS (
    SELECT
        s.SYMBOL,
        s.PARENT_SECTOR,
        s.INDUSTRY_SECTOR,
        s.SUB_SECTOR,
        s.EXCHANGE,
        ROW_NUMBER() OVER (PARTITION BY s.SYMBOL ORDER BY s.SOURCE_PRIORITY DESC) AS RN
    FROM staged_union s
),
raw_symbols AS (
    SELECT DISTINCT
        REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
    WHERE SYMBOL IS NOT NULL
),
fallback_data AS (
    SELECT
        r.PARENT_SECTOR,
        r.INDUSTRY_SECTOR,
        r.SUB_SECTOR,
        r.SYMBOL,
        r.EXCHANGE
    FROM ranked_union r
    JOIN raw_symbols rs
      ON rs.SYMBOL = r.SYMBOL
    WHERE r.RN = 1
)
"""

_SQL_FB_PARENTS = _SQL_FB_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM fallback_data
GROUP BY PARENT_SECTOR
ORDER BY PARENT_SECTOR
"""

_SQL_FB_INDUSTRIES = _SQL_FB_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM fallback_data
WHERE PARENT_SECTOR = :parent_sector
GROUP BY PARENT_SECTOR, INDUSTRY_SECTOR
ORDER BY INDUSTRY_SECTOR
"""

_SQL_FB_SUB_SECTORS = _SQL_FB_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM fallback_data
WHERE PARENT_SECTOR = :parent_sector
  AND INDUSTRY_SECTOR = :industry_sector
GROUP BY PARENT_SECTOR, INDUSTRY_SECTOR, SUB_SECTOR
ORDER BY SUB_SECTOR
"""

_SQL_FB_STOCKS = _SQL_FB_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    SYMBOL,
    EXCHANGE
FROM fallback_data
WHERE (:parent_sector IS NULL OR PARENT_SECTOR = :parent_sector)
  AND (:industry_sector IS NULL OR INDUSTRY_SECTOR = :industry_sector)
  AND (:sub_sector IS NULL OR SUB_SECTOR = :sub_sector)
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR, SYMBOL
"""

_SQL_FB_TOTAL_BY_PARENT = _SQL_FB_BASE_CTE + """
SELECT COUNT(DISTINCT SYMBOL) AS TOTAL_STOCKS
FROM fallback_data
WHERE PARENT_SECTOR = :parent_sector
"""

_SQL_FB_SUMMARY_ROWS = _SQL_FB_BASE_CTE + """
SELECT
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    COUNT(DISTINCT SYMBOL) AS STOCK_COUNT
FROM fallback_data
WHERE PARENT_SECTOR = :parent_sector
GROUP BY INDUSTRY_SECTOR, SUB_SECTOR
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR
"""

_SQL_FB_TREE_ROWS = _SQL_FB_BASE_CTE + """
SELECT
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    SYMBOL,
    EXCHANGE
FROM fallback_data
WHERE PARENT_SECTOR = :parent_sector
ORDER BY INDUSTRY_SECTOR, SUB_SECTOR, SYMBOL
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str | None) -> str:
    return ' '.join(str(value or '').strip().split())


def _cache_get(cache_key: str, refresh: bool) -> tuple[dict[str, Any] | None, bool]:
    if refresh:
        return None, False
    cached_payload = _cache.get(cache_key)
    if isinstance(cached_payload, dict):
        return cached_payload, True
    return None, False


def _cache_set(cache_key: str, data: Any) -> dict[str, Any]:
    payload = {
        'generatedAt': _now_iso(),
        'data': data,
    }
    _cache.set(cache_key, payload)
    return payload


def _fetch_rows(sql: str, binds: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, binds or {})
            description = cursor.description or []
            keys = [str(item[0]).lower() for item in description if item and item[0]]
            out: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                out.append({keys[index]: row[index] for index in range(len(keys))})
            return out
    finally:
        conn.close()


def _fetch_single_value(sql: str, binds: dict[str, Any]) -> int:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, binds)
            row = cursor.fetchone()
            if not row:
                return 0
            return int(row[0] or 0)
    finally:
        conn.close()


def _is_missing_hierarchy_object_error(exc: Exception) -> bool:
    text = str(exc or '')
    return ('ORA-00942' in text) or ('ORA-04063' in text)


def _safe_fetch_rows(sql: str, binds: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        return _fetch_rows(sql, binds)
    except Exception as exc:
        if _is_missing_hierarchy_object_error(exc):
            logger.warning(
                '[SECTOR_HIERARCHY_MISSING_OBJECT] action=query_rows sql_ref=VW_NSE_SECTOR_HIERARCHY_ACTIVE details=%s',
                exc,
            )
            return []
        raise


def _safe_fetch_single_value(sql: str, binds: dict[str, Any]) -> int:
    try:
        return _fetch_single_value(sql, binds)
    except Exception as exc:
        if _is_missing_hierarchy_object_error(exc):
            logger.warning(
                '[SECTOR_HIERARCHY_MISSING_OBJECT] action=query_single sql_ref=VW_NSE_SECTOR_HIERARCHY_ACTIVE details=%s',
                exc,
            )
            return 0
        raise


def _safe_fetch_rows_with_fallback(
    primary_sql: str,
    primary_binds: dict[str, Any] | None,
    fallback_sql: str,
    fallback_binds: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    try:
        rows = _fetch_rows(primary_sql, primary_binds)
        return rows, False
    except Exception as exc:
        if not _is_missing_hierarchy_object_error(exc):
            raise
        logger.warning(
            '[SECTOR_HIERARCHY_FALLBACK] action=query_rows reason=primary_missing details=%s',
            exc,
        )
        try:
            rows = _fetch_rows(fallback_sql, fallback_binds or primary_binds or {})
            return rows, True
        except Exception as fallback_exc:
            logger.exception(
                '[SECTOR_HIERARCHY_FALLBACK_ERROR] action=query_rows details=%s',
                fallback_exc,
            )
            return [], True


def _safe_fetch_single_with_fallback(
    primary_sql: str,
    primary_binds: dict[str, Any],
    fallback_sql: str,
    fallback_binds: dict[str, Any] | None = None,
) -> tuple[int, bool]:
    try:
        value = _fetch_single_value(primary_sql, primary_binds)
        return value, False
    except Exception as exc:
        if not _is_missing_hierarchy_object_error(exc):
            raise
        logger.warning(
            '[SECTOR_HIERARCHY_FALLBACK] action=query_single reason=primary_missing details=%s',
            exc,
        )
        try:
            value = _fetch_single_value(fallback_sql, fallback_binds or primary_binds)
            return value, True
        except Exception as fallback_exc:
            logger.exception(
                '[SECTOR_HIERARCHY_FALLBACK_ERROR] action=query_single details=%s',
                fallback_exc,
            )
            return 0, True


def _with_metadata(cache_key: str, cached: bool, generated_at: str, data: Any) -> dict[str, Any]:
    return {
        'data': data,
        'metadata': {
            'cacheKey': cache_key,
            'cached': cached,
            'generatedAt': generated_at,
        },
    }


def _enrich_stock_rows_with_marketcap(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not stocks:
        return stocks
    try:
        from services import nse_mcap_service as nse_mcap_svc
    except Exception:
        return stocks
    try:
        enriched = nse_mcap_svc.enrich_rows_with_marketcap_index(stocks, symbol_keys=('symbol', 'SYMBOL'))
        return enriched if isinstance(enriched, list) else stocks
    except Exception:
        logger.exception('[SECTOR_HIERARCHY_ENRICHMENT_ERROR] endpoint=stocks reason=marketcap_enrichment_failed')
        return stocks


def _first_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ''):
            return value
    return None


def get_parents(*, refresh: bool) -> dict[str, Any]:
    endpoint = 'parents'
    started_at = time.perf_counter()
    cache_key = 'sectorHierarchy:parents:v2'

    cached_payload, cache_hit = _cache_get(cache_key, refresh)
    if cached_payload:
        data = [
            {
                'parentSector': str(row.get('parentSector') or ''),
                'stockCount': int(row.get('stockCount') or 0),
            }
            for row in cached_payload.get('data', [])
        ]
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        result['metadata']['totalParents'] = len(data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector= industrySector= subSector= rows=%s cached=true durationMs=%s',
            endpoint,
            len(data),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    rows, fallback_used = _safe_fetch_rows_with_fallback(_SQL_PARENTS, None, _SQL_FB_PARENTS)
    data = [
        {
            'parentSector': str(row.get('parent_sector') or ''),
            'stockCount': int(row.get('stock_count') or 0),
        }
        for row in rows
    ]
    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, cache_hit, str(stored['generatedAt']), data)
    result['metadata']['totalParents'] = len(data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector= industrySector= subSector= rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        len(data),
        str(fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def get_industries(*, parent_sector: str, refresh: bool) -> dict[str, Any]:
    endpoint = 'industries'
    started_at = time.perf_counter()
    normalized_parent = _normalize_text(parent_sector)
    cache_key = f'sectorHierarchy:industries:{normalized_parent}:v2'

    cached_payload, _ = _cache_get(cache_key, refresh)
    if cached_payload:
        data = list(cached_payload.get('data', []))
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=true durationMs=%s',
            endpoint,
            normalized_parent,
            len(data),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    rows, fallback_used = _safe_fetch_rows_with_fallback(
        _SQL_INDUSTRIES,
        {'parent_sector': normalized_parent},
        _SQL_FB_INDUSTRIES,
    )
    data = [
        {
            'parentSector': str(row.get('parent_sector') or normalized_parent),
            'industrySector': str(row.get('industry_sector') or ''),
            'stockCount': int(row.get('stock_count') or 0),
        }
        for row in rows
    ]
    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, False, str(stored['generatedAt']), data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        normalized_parent,
        len(data),
        str(fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def get_sub_sectors(*, parent_sector: str, industry_sector: str, refresh: bool) -> dict[str, Any]:
    endpoint = 'sub-sectors'
    started_at = time.perf_counter()
    normalized_parent = _normalize_text(parent_sector)
    normalized_industry = _normalize_text(industry_sector)
    cache_key = f'sectorHierarchy:subSectors:{normalized_parent}:{normalized_industry}:v2'

    cached_payload, _ = _cache_get(cache_key, refresh)
    if cached_payload:
        data = list(cached_payload.get('data', []))
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector=%s subSector= rows=%s cached=true durationMs=%s',
            endpoint,
            normalized_parent,
            normalized_industry,
            len(data),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    rows, fallback_used = _safe_fetch_rows_with_fallback(
        _SQL_SUB_SECTORS,
        {
            'parent_sector': normalized_parent,
            'industry_sector': normalized_industry,
        },
        _SQL_FB_SUB_SECTORS,
    )
    data = [
        {
            'parentSector': str(row.get('parent_sector') or normalized_parent),
            'industrySector': str(row.get('industry_sector') or normalized_industry),
            'subSector': str(row.get('sub_sector') or ''),
            'stockCount': int(row.get('stock_count') or 0),
        }
        for row in rows
    ]
    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, False, str(stored['generatedAt']), data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector=%s subSector= rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        normalized_parent,
        normalized_industry,
        len(data),
        str(fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def get_stocks(
    *,
    parent_sector: str | None,
    industry_sector: str | None,
    sub_sector: str | None,
    refresh: bool,
) -> dict[str, Any]:
    endpoint = 'stocks'
    started_at = time.perf_counter()
    normalized_parent = _normalize_text(parent_sector)
    normalized_industry = _normalize_text(industry_sector)
    normalized_sub = _normalize_text(sub_sector)

    cache_key = f'sectorHierarchy:stocks:{normalized_parent}:{normalized_industry}:{normalized_sub}:v3'
    cached_payload, _ = _cache_get(cache_key, refresh)
    if cached_payload:
        data = dict(cached_payload.get('data', {}))
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector=%s subSector=%s rows=%s cached=true durationMs=%s',
            endpoint,
            normalized_parent,
            normalized_industry,
            normalized_sub,
            int(data.get('totalStocks') or 0),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    rows, fallback_used = _safe_fetch_rows_with_fallback(
        _SQL_STOCKS,
        {
            'parent_sector': normalized_parent or None,
            'industry_sector': normalized_industry or None,
            'sub_sector': normalized_sub or None,
        },
        _SQL_FB_STOCKS,
    )
    base_stocks = [
        {
            'parentSector': str(row.get('parent_sector') or ''),
            'industrySector': str(row.get('industry_sector') or ''),
            'subSector': str(row.get('sub_sector') or ''),
            'symbol': str(row.get('symbol') or ''),
            'exchange': str(row.get('exchange') or 'NSE'),
        }
        for row in rows
    ]
    enriched_rows = _enrich_stock_rows_with_marketcap(base_stocks)
    stocks = [
        {
            **row,
            'index': _first_value(row, 'index', 'INDEX', 'index_value', 'INDEX_VALUE', 'market_cap_index', 'MARKET_CAP_INDEX'),
            'mcap': _first_value(row, 'mcap', 'MCAP', 'totalMcap', 'TOTAL_MCAP', 'TOTAL_MCAP_CR'),
            'mcapRank': _first_value(row, 'mcapRank', 'MCAP_RANK', 'mcap_rank', 'market_cap_rank', 'MARKET_CAP_RANK'),
        }
        for row in enriched_rows
    ]
    data = {
        'parentSector': normalized_parent or None,
        'industrySector': normalized_industry or None,
        'subSector': normalized_sub or None,
        'totalStocks': len(stocks),
        'stocks': stocks,
    }
    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, False, str(stored['generatedAt']), data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector=%s subSector=%s rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        normalized_parent,
        normalized_industry,
        normalized_sub,
        len(stocks),
        str(fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def get_summary(*, parent_sector: str, refresh: bool) -> dict[str, Any]:
    endpoint = 'summary'
    started_at = time.perf_counter()
    normalized_parent = _normalize_text(parent_sector)
    cache_key = f'sectorHierarchy:summary:{normalized_parent}:v2'

    cached_payload, _ = _cache_get(cache_key, refresh)
    if cached_payload:
        data = dict(cached_payload.get('data', {}))
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=true durationMs=%s',
            endpoint,
            normalized_parent,
            int(data.get('totalStocks') or 0),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    total_stocks, total_fallback_used = _safe_fetch_single_with_fallback(
        _SQL_TOTAL_BY_PARENT,
        {'parent_sector': normalized_parent},
        _SQL_FB_TOTAL_BY_PARENT,
    )
    rows, rows_fallback_used = _safe_fetch_rows_with_fallback(
        _SQL_SUMMARY_ROWS,
        {'parent_sector': normalized_parent},
        _SQL_FB_SUMMARY_ROWS,
    )

    industries_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        industry = str(row.get('industry_sector') or '')
        sub_sector = str(row.get('sub_sector') or '')
        stock_count = int(row.get('stock_count') or 0)
        industry_entry = industries_map.setdefault(
            industry,
            {
                'industrySector': industry,
                'stockCount': 0,
                'subSectors': [],
            },
        )
        industry_entry['stockCount'] += stock_count
        industry_entry['subSectors'].append(
            {
                'subSector': sub_sector,
                'stockCount': stock_count,
            }
        )

    data = {
        'parentSector': normalized_parent,
        'totalStocks': total_stocks,
        'industries': list(industries_map.values()),
    }

    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, False, str(stored['generatedAt']), data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        normalized_parent,
        total_stocks,
        str(total_fallback_used or rows_fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def get_tree(*, parent_sector: str, refresh: bool) -> dict[str, Any]:
    endpoint = 'tree'
    started_at = time.perf_counter()
    normalized_parent = _normalize_text(parent_sector)
    cache_key = f'sectorHierarchy:tree:{normalized_parent}:v2'

    cached_payload, _ = _cache_get(cache_key, refresh)
    if cached_payload:
        data = dict(cached_payload.get('data', {}))
        result = _with_metadata(cache_key, True, str(cached_payload.get('generatedAt') or _now_iso()), data)
        logger.info(
            '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=true durationMs=%s',
            endpoint,
            normalized_parent,
            int(data.get('totalStocks') or 0),
            int((time.perf_counter() - started_at) * 1000),
        )
        return result

    rows, fallback_used = _safe_fetch_rows_with_fallback(
        _SQL_TREE_ROWS,
        {'parent_sector': normalized_parent},
        _SQL_FB_TREE_ROWS,
    )

    industries_map: dict[str, dict[str, Any]] = {}
    total_stocks = 0
    for row in rows:
        industry = str(row.get('industry_sector') or '')
        sub_sector = str(row.get('sub_sector') or '')
        symbol = str(row.get('symbol') or '')
        exchange = str(row.get('exchange') or 'NSE')

        industry_entry = industries_map.setdefault(
            industry,
            {
                'industrySector': industry,
                'stockCount': 0,
                'subSectors': {},
            },
        )
        sub_entry = industry_entry['subSectors'].setdefault(
            sub_sector,
            {
                'subSector': sub_sector,
                'stockCount': 0,
                'stocks': [],
            },
        )
        sub_entry['stocks'].append({'symbol': symbol, 'exchange': exchange})
        sub_entry['stockCount'] += 1
        industry_entry['stockCount'] += 1
        total_stocks += 1

    industries: list[dict[str, Any]] = []
    for industry_entry in industries_map.values():
        sub_sector_map = industry_entry.pop('subSectors')
        industry_entry['subSectors'] = list(sub_sector_map.values())
        industries.append(industry_entry)

    data = {
        'parentSector': normalized_parent,
        'totalStocks': total_stocks,
        'industries': industries,
    }
    stored = _cache_set(cache_key, data)
    result = _with_metadata(cache_key, False, str(stored['generatedAt']), data)
    logger.info(
        '[SECTOR_HIERARCHY_OK] endpoint=%s parentSector=%s industrySector= subSector= rows=%s cached=false fallback=%s durationMs=%s',
        endpoint,
        normalized_parent,
        total_stocks,
        str(fallback_used).lower(),
        int((time.perf_counter() - started_at) * 1000),
    )
    return result


def clear_cache() -> None:
    _cache.clear()
