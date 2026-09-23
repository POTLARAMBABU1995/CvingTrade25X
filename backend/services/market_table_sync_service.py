from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any, Dict, List

from db import get_oracle_connection
import services.nse_mcap_service as nse_mcap_svc
import services.nse_ffmc_service as nse_ffmc_svc
import services.nse_delivery_service as nse_delivery_svc
from services.sector_cache_service import sector_cache_service

logger = logging.getLogger(__name__)

# Cache of last sync status and sync execution time
_LAST_SYNC_TIME: str | None = None

def get_latest_dates() -> Dict[str, dt.date | None]:
    """Retrieve the latest trade date from each table."""
    conn = get_oracle_connection()
    dates: Dict[str, dt.date | None] = {
        'dev': None,
        'mcap': None,
        'ffmc': None,
        'delivery': None
    }
    try:
        with conn.cursor() as cur:
            # DEV
            cur.execute("SELECT MAX(TRADING_DATE) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV")
            row = cur.fetchone()
            if row and row[0]:
                dates['dev'] = row[0].date() if isinstance(row[0], dt.datetime) else row[0]

            # MCAP
            cur.execute("SELECT MAX(TRADE_DATE) FROM CVING_NSE_MARKET_CAP_HIST WHERE FETCH_STATUS = 'SUCCESS'")
            row = cur.fetchone()
            if row and row[0]:
                dates['mcap'] = row[0].date() if isinstance(row[0], dt.datetime) else row[0]

            # FFMC
            cur.execute("SELECT MAX(TRADE_DATE) FROM CVING_NSE_FFMC_HIST WHERE FETCH_STATUS = 'SUCCESS'")
            row = cur.fetchone()
            if row and row[0]:
                dates['ffmc'] = row[0].date() if isinstance(row[0], dt.datetime) else row[0]

            # DELIVERY
            cur.execute("SELECT MAX(TRADE_DATE) FROM CVING_NSE_DELIVERY_HIST WHERE FETCH_STATUS = 'SUCCESS'")
            row = cur.fetchone()
            if row and row[0]:
                dates['delivery'] = row[0].date() if isinstance(row[0], dt.datetime) else row[0]
    except Exception:
        logger.exception("Failed to get latest dates from market tables")
    finally:
        conn.close()
    return dates

def get_missing_symbols(dev_date: dt.date) -> Dict[str, List[str]]:
    """Identify symbols present in DEV but missing in MCAP/FFMC/DELIVERY for the same date."""
    conn = get_oracle_connection()
    missing: Dict[str, List[str]] = {
        'mcap': [],
        'ffmc': [],
        'delivery': []
    }
    try:
        with conn.cursor() as cur:
            # Missing MCAP
            cur.execute("""
                SELECT DISTINCT d.SYMBOL
                FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
                LEFT JOIN CVING_NSE_MARKET_CAP_HIST m
                  ON UPPER(TRIM(d.SYMBOL)) = UPPER(TRIM(m.SYMBOL))
                 AND d.TRADING_DATE = m.TRADE_DATE
                 AND m.FETCH_STATUS = 'SUCCESS'
                WHERE d.TRADING_DATE = :trading_date
                  AND m.SYMBOL IS NULL
                  AND d.SYMBOL IS NOT NULL
            """, {'trading_date': dev_date})
            missing['mcap'] = [row[0] for row in cur.fetchall() if row[0]]

            # Missing FFMC
            cur.execute("""
                SELECT DISTINCT d.SYMBOL
                FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
                LEFT JOIN CVING_NSE_FFMC_HIST f
                  ON UPPER(TRIM(d.SYMBOL)) = UPPER(TRIM(f.SYMBOL))
                 AND d.TRADING_DATE = f.TRADE_DATE
                 AND f.FETCH_STATUS = 'SUCCESS'
                WHERE d.TRADING_DATE = :trading_date
                  AND f.SYMBOL IS NULL
                  AND d.SYMBOL IS NOT NULL
            """, {'trading_date': dev_date})
            missing['ffmc'] = [row[0] for row in cur.fetchall() if row[0]]

            # Missing DELIVERY
            cur.execute("""
                SELECT DISTINCT d.SYMBOL
                FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
                LEFT JOIN CVING_NSE_DELIVERY_HIST dl
                  ON UPPER(TRIM(d.SYMBOL)) = UPPER(TRIM(dl.SYMBOL))
                 AND d.TRADING_DATE = dl.TRADE_DATE
                 AND dl.FETCH_STATUS = 'SUCCESS'
                WHERE d.TRADING_DATE = :trading_date
                  AND dl.SYMBOL IS NULL
                  AND d.SYMBOL IS NOT NULL
            """, {'trading_date': dev_date})
            missing['delivery'] = [row[0] for row in cur.fetchall() if row[0]]
    except Exception:
        logger.exception("Failed to query missing symbols")
    finally:
        conn.close()
    return missing

def get_sync_status() -> Dict[str, Any]:
    """Retrieve detailed validation output for database sync status."""
    global _LAST_SYNC_TIME
    dates = get_latest_dates()
    dev_date = dates['dev']

    if not dev_date:
        return {
            'dev_ltc_date': None,
            'mcap_ltc_date': None,
            'ffmc_ltc_date': None,
            'delivery_ltc_date': None,
            'is_fully_synced': False,
            'missing_mcap_count': 0,
            'missing_ffmc_count': 0,
            'missing_delivery_count': 0,
            'stale_tables': [],
            'missing_symbols': {'mcap': [], 'ffmc': [], 'delivery': []},
            'last_sync_time': _LAST_SYNC_TIME or dt.datetime.now().isoformat(),
            'message': 'No data available in DEV table'
        }

    missing = get_missing_symbols(dev_date)
    missing_mcap = len(missing['mcap'])
    missing_ffmc = len(missing['ffmc'])
    missing_del = len(missing['delivery'])

    stale_tables: List[str] = []
    if not dates['mcap'] or dates['mcap'] < dev_date:
        stale_tables.append('MCAP')
    if not dates['ffmc'] or dates['ffmc'] < dev_date:
        stale_tables.append('FFMC')
    if not dates['delivery'] or dates['delivery'] < dev_date:
        stale_tables.append('DELIVERY')

    is_fully_synced = (
        len(stale_tables) == 0 and 
        missing_mcap == 0 and 
        missing_ffmc == 0 and 
        missing_del == 0
    )

    message = "All tables fully synchronized." if is_fully_synced else "Sync pending / stale tables detected."

    return {
        'dev_ltc_date': dev_date.isoformat(),
        'mcap_ltc_date': dates['mcap'].isoformat() if dates['mcap'] else None,
        'ffmc_ltc_date': dates['ffmc'].isoformat() if dates['ffmc'] else None,
        'delivery_ltc_date': dates['delivery'].isoformat() if dates['delivery'] else None,
        'is_fully_synced': is_fully_synced,
        'missing_mcap_count': missing_mcap,
        'missing_ffmc_count': missing_ffmc,
        'missing_delivery_count': missing_del,
        'stale_tables': stale_tables,
        'missing_symbols': missing,
        'last_sync_time': _LAST_SYNC_TIME or dt.datetime.now().isoformat(),
        'message': message
    }

def clear_and_refresh_sector_caches():
    """Clear all sector in-memory caches and trigger Oracle MV refreshes."""
    logger.info("Clearing sector caches and refreshing materialized views...")
    sector_cache_service.clear_sector_cache()
    
    # Invalidate other caches in routes/sector_rotation
    try:
        from routes.sector_rotation import warm_sector_rotation_cache
        # Also clears standard in-memory caches
    except ImportError:
        pass

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C'); END;")
                logger.info("Refreshed MV_NSE_SECTOR_UI_SNAPSHOT")
            except Exception:
                logger.exception("Failed MV refresh for MV_NSE_SECTOR_UI_SNAPSHOT")
            try:
                cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_BREADTH', 'C'); END;")
                logger.info("Refreshed MV_NSE_SECTOR_BREADTH")
            except Exception:
                logger.exception("Failed MV refresh for MV_NSE_SECTOR_BREADTH")
        conn.commit()
    except Exception:
        logger.exception("Failed to execute DB materialized view refreshes")
    finally:
        conn.close()

def sync_latest_market_tables() -> Dict[str, Any]:
    """Manually trigger synchronization of missing rows to the latest DEV date."""
    global _LAST_SYNC_TIME
    status = get_sync_status()
    dev_date_str = status['dev_ltc_date']
    if not dev_date_str:
        return {'ok': False, 'message': 'No date found in DEV table to sync'}

    dev_date = dt.date.fromisoformat(dev_date_str)
    summary = {
        'mcap': {'processed': False, 'status': 'ALREADY_EXISTS'},
        'ffmc': {'processed': False, 'status': 'ALREADY_EXISTS'},
        'delivery': {'processed': False, 'status': 'ALREADY_EXISTS'}
    }

    # MCAP Sync
    if 'MCAP' in status['stale_tables'] or status['missing_mcap_count'] > 0:
        logger.info(f"Syncing MCAP table for date {dev_date_str}")
        try:
            res = nse_mcap_svc.run_mcap_pipeline_for_trade_date(dev_date, force=True, eq_only=True)
            summary['mcap'] = {'processed': True, 'status': res.get('status', 'SUCCESS'), 'details': res}
        except Exception as e:
            logger.exception("MCAP sync pipeline execution failed")
            summary['mcap'] = {'processed': True, 'status': 'FAILED', 'error': str(e)}

    # FFMC Sync
    if 'FFMC' in status['stale_tables'] or status['missing_ffmc_count'] > 0:
        logger.info(f"Syncing FFMC table for date {dev_date_str}")
        try:
            res = nse_ffmc_svc.run_pipeline({"tradeDate": dev_date_str, "force": True, "eqOnly": True})
            summary['ffmc'] = {'processed': True, 'status': res.get('status', 'SUCCESS'), 'details': res}
        except Exception as e:
            logger.exception("FFMC sync pipeline execution failed")
            summary['ffmc'] = {'processed': True, 'status': 'FAILED', 'error': str(e)}

    # DELIVERY Sync
    if 'DELIVERY' in status['stale_tables'] or status['missing_delivery_count'] > 0:
        logger.info(f"Syncing DELIVERY table for date {dev_date_str}")
        try:
            res = nse_delivery_svc.run_pipeline({"tradeDate": dev_date_str, "force": True, "eqOnly": True})
            summary['delivery'] = {'processed': True, 'status': res.get('status', 'SUCCESS'), 'details': res}
        except Exception as e:
            logger.exception("DELIVERY sync pipeline execution failed")
            summary['delivery'] = {'processed': True, 'status': 'FAILED', 'error': str(e)}

    # Clear cache and refresh MVs
    clear_and_refresh_sector_caches()
    
    _LAST_SYNC_TIME = dt.datetime.now().isoformat()
    
    # Get final status after sync
    final_status = get_sync_status()

    return {
        'ok': True,
        'summary': summary,
        'final_status': final_status,
        'message': 'Sync process completed.'
    }
