import sys
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

CONFLICTS = [
    {"symbol": "ADANIPORTS", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "AEGISLOG", "tableName": "NSE_NIFTY_OIL_AND_GAS_STAGING"},
    {"symbol": "AEGISVOPAK", "tableName": "NSE_NIFTY_OIL_AND_GAS_STAGING"},
    {"symbol": "ASHOKA", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "BEML", "tableName": "NSE_NIFTY_CAPITAL_GOODS_STAGING"},
    {"symbol": "BLACKBUCK", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "BLUEDART", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "CONCOR", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "DBL", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "DELHIVERY", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "GESHIP", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "GMRAIRPORT", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "GPPL", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "HGINFRA", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "INDIGO", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "IRB", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "IRCON", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "JSWINFRA", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "JWL", "tableName": "NSE_NIFTY_CAPITAL_GOODS_STAGING"},
    {"symbol": "KNRCON", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "PNCINFRA", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "RITES", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "RVNL", "tableName": "NSE_NIFTY_CONSTRUCTION_STAGING"},
    {"symbol": "SCI", "tableName": "NSE_NIFTY_SERVICES_STAGING"},
    {"symbol": "TEXRAIL", "tableName": "NSE_NIFTY_CAPITAL_GOODS_STAGING"},
    {"symbol": "TITAGARH", "tableName": "NSE_NIFTY_CAPITAL_GOODS_STAGING"},
    {"symbol": "TVSSCS", "tableName": "NSE_NIFTY_SERVICES_STAGING"}
]

def resolve_conflicts():
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Backup the rows
            cursor.execute('''
                DECLARE
                    l_count NUMBER;
                BEGIN
                    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'BACKUP_CONFLICT_SYMBOLS';
                    IF l_count = 0 THEN
                        EXECUTE IMMEDIATE 'CREATE TABLE BACKUP_CONFLICT_SYMBOLS (TABLE_NAME VARCHAR2(100), SYMBOL VARCHAR2(100))';
                    END IF;
                END;
            ''')
            
            for conflict in CONFLICTS:
                sym = conflict['symbol']
                tbl = conflict['tableName']
                cursor.execute(
                    "INSERT INTO BACKUP_CONFLICT_SYMBOLS (TABLE_NAME, SYMBOL) VALUES (:tbl, :sym)",
                    {'tbl': tbl, 'sym': sym}
                )
                cursor.execute(
                    f"DELETE FROM {tbl} WHERE SYMBOL = :sym",
                    {'sym': sym}
                )
                print(f"Deleted {sym} from {tbl}")
                
        conn.commit()
        print("Conflicts resolved successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error resolving conflicts: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    resolve_conflicts()
