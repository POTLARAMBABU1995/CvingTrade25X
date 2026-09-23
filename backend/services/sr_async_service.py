from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from oracledb import AsyncCursor

from ..cache import HybridCache, LocalTTLCache
from ..config import settings
from ..oracle_pool import oracle_pool

logger = logging.getLogger(__name__)


_CACHE_KEY_TEMPLATE = "sr:{tf}:{tol}:{page}:{size}:{search}"
_TRADING_DAYS_LOOKBACK = max(0, settings.sr_trading_days_lookback)


def _serialize_rows(columns: List[str], rows: List[Tuple[Any, ...]]) -> List[Dict[str, Any]]:
    return [dict(zip(columns, row)) for row in rows]


class SRLevelsService:
    def __init__(self, cache: HybridCache) -> None:
        self._cache = cache

    @staticmethod
    def _build_query(search: str | None, include_cutoff: bool) -> str:
        base_query = """
            SELECT
                symbol,
                price,
                trading_date AS "tradingDate",
                ltc_date AS "ltcDate",
                trading_days AS "tradingDays",
                support_display AS "supportDisplay",
                resistance_display AS "resistanceDisplay",
                score,
                trend_direction AS "trendDirection"
            FROM sr_levels_mv
            WHERE timeframe = :timeframe
              AND tolerance = :tolerance
        """
        if search:
            base_query += " AND symbol LIKE :search "
        if include_cutoff:
            base_query += " AND trading_date >= :cutoff_date "
        base_query += " ORDER BY score DESC NULLS LAST, symbol ASC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
        return base_query

    @staticmethod
    def _build_count_query(search: str | None, include_cutoff: bool) -> str:
        query = "SELECT COUNT(*) FROM sr_levels_mv WHERE timeframe = :timeframe AND tolerance = :tolerance"
        if search:
            query += " AND symbol LIKE :search"
        if include_cutoff:
            query += " AND trading_date >= :cutoff_date"
        return query

    @staticmethod
    async def _determine_cutoff_date(conn, timeframe: str):
        if _TRADING_DAYS_LOOKBACK <= 0:
            return None
        lookup_sql = f"""
            SELECT MIN(trading_date) FROM (
                SELECT DISTINCT trading_date
                FROM sr_levels_mv
                WHERE timeframe = :timeframe
                ORDER BY trading_date DESC
                FETCH FIRST {_TRADING_DAYS_LOOKBACK} ROWS ONLY
            )
        """
        async with conn.cursor() as cursor:
            await cursor.execute(lookup_sql, {"timeframe": timeframe})
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None

    async def fetch_page(
        self,
        *,
        timeframe: str,
        tolerance: float,
        page: int,
        page_size: int,
        search: str | None = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        page = max(page, 1)
        page_size = max(1, min(page_size, settings.max_page_size))
        search_term = f"{search.upper()}%" if search else None
        cache_key = _CACHE_KEY_TEMPLATE.format(
            tf=timeframe,
            tol=f"{tolerance:.4f}",
            page=page,
            size=page_size,
            search=search_term or "",
        )
        cached = None
        if not force_refresh:
            cached = await self._cache.get(cache_key)
        if cached:
            payload = json.loads(cached)
            payload['cached'] = True
            payload['refreshing'] = False
            return payload

        offset = (page - 1) * page_size
        conn = await oracle_pool.acquire()
        try:
            cutoff_date = await self._determine_cutoff_date(conn, timeframe)

            cursor: AsyncCursor
            async with conn.cursor() as cursor:
                cursor.arraysize = settings.oracle_arraysize
                bind_params = {
                    "timeframe": timeframe,
                    "tolerance": tolerance,
                    "offset": offset,
                    "limit": page_size,
                }
                if search_term:
                    bind_params["search"] = search_term
                if cutoff_date:
                    bind_params["cutoff_date"] = cutoff_date

                await cursor.execute(self._build_query(search, bool(cutoff_date)), bind_params)
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
            async with conn.cursor() as cursor:
                count_params = {
                    "timeframe": timeframe,
                    "tolerance": tolerance,
                    **({"search": search_term} if search_term else {}),
                }
                if cutoff_date:
                    count_params["cutoff_date"] = cutoff_date
                await cursor.execute(self._build_count_query(search, bool(cutoff_date)), count_params)
                total_rows = (await cursor.fetchone())[0]
        finally:
            await oracle_pool.release(conn)

        payload: Dict[str, Any] = {
            "rows": _serialize_rows(columns, rows),
            "meta": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "timeframe": timeframe,
                "tolerance": tolerance,
            },
        }
        await self._cache.set(cache_key, json.dumps(payload), settings.cache_ttl_seconds)
        response = dict(payload)
        response['cached'] = False
        response['refreshing'] = False
        return response


local_cache = LocalTTLCache(settings.cache_ttl_seconds, settings.cache_max_items)

try:
    import redis.asyncio as aioredis  # type: ignore

    _redis_client = None
    if settings.redis_url:
        _redis_client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        logger.info("Redis cache enabled for SR levels at %s", settings.redis_url)
except ImportError:
    logger.warning("redis package missing - falling back to in-process cache")
    _redis_client = None

sr_levels_service = SRLevelsService(HybridCache(_redis_client, local_cache))
