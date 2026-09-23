PROMPT Rolling back Restaurants, Hospitality Hotels & Resorts, Tourism & Travel Sectors

SET DEFINE OFF;
SET SERVEROUTPUT ON;

BEGIN
  DBMS_OUTPUT.PUT_LINE('NOTE: Staging tables were NOT dropped to prevent accidental data loss. Drop them manually if required.');
  
  DELETE FROM NSE_SECTOR_MASTER WHERE SECTOR_CODE IN ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL');
  DBMS_OUTPUT.PUT_LINE('Removed sector master registrations.');
  
  DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE IN ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL');
  DBMS_OUTPUT.PUT_LINE('Removed symbol sector mappings.');
  
  COMMIT;
END;
/
EXIT;
