import logging
from typing import Tuple, Optional
from db import get_oracle_connection

logger = logging.getLogger(__name__)

def resolve_sector_key(input_sector_or_slug: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves an incoming slug or sector name to a canonical sector ID and Name.
    e.g. 'alcohol-breweries' -> (sector_id, 'Alcohol Breweries')
    """
    if not input_sector_or_slug:
        return None, None
        
    normalized = str(input_sector_or_slug).strip().lower()
    if not normalized:
        return None, None
        
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Direct hit in alias map
            cursor.execute("""
                SELECT COALESCE(a.canonical_sector_id, m.sector_code), a.canonical_sector_name
                FROM NSE_SECTOR_ALIAS_MAP a
                LEFT JOIN NSE_SECTOR_MASTER m ON LOWER(m.sector_name) = LOWER(a.canonical_sector_name)
                WHERE a.alias_key = :1 AND a.active_flag = 1
            """, [normalized])
            row = cursor.fetchone()
            if row and row[1]:
                return row[0], row[1]
                
            # 2. Case-insensitive hit in master
            cursor.execute("""
                SELECT sector_code, sector_name 
                FROM NSE_SECTOR_MASTER 
                WHERE LOWER(sector_name) = :val OR LOWER(sector_code) = :val
            """, {"val": normalized})
            row = cursor.fetchone()
            if row:
                return row[0], row[1]
                
            # 3. Dashes to spaces match in master
            with_spaces = normalized.replace('-', ' ')
            cursor.execute("""
                SELECT sector_code, sector_name 
                FROM NSE_SECTOR_MASTER 
                WHERE LOWER(sector_name) = :val OR LOWER(sector_code) = :val
            """, {"val": with_spaces})
            row = cursor.fetchone()
            if row:
                return row[0], row[1]
                
            # Fallback
            logger.warning(f"Could not resolve canonical sector for input: {input_sector_or_slug}")
            return None, None
    except Exception as e:
        logger.exception(f"Error resolving sector key for {input_sector_or_slug}: {e}")
        return None, None
    finally:
        conn.close()
