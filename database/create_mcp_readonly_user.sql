-- REVIEW TEMPLATE ONLY. No SQL below runs until a DBA removes EXIT.
-- No existing account, grant, table or data is modified by this template.
SET ECHO OFF
SET VERIFY OFF
PROMPT Review schema names, password policy and exact MCP dependencies first.
EXIT
-- Replace placeholders offline. Never place real passwords in version control.
CREATE USER CVING_MCP_RO IDENTIFIED BY "<SET_SECURE_PASSWORD>";
GRANT CREATE SESSION TO CVING_MCP_RO;
-- Replace APP_OWNER with the existing schema. Grant only verified read sources.
GRANT SELECT ON APP_OWNER.NSE_NIFTY500_DAILY_RAW_DATA_DEV TO CVING_MCP_RO;
GRANT SELECT ON APP_OWNER.STOCK_EOD_HISTORY TO CVING_MCP_RO;
-- If configured as SUMMARY_SOURCES, separately review V_STOCK_EOD_HISTORY.
-- Configure CVING_MCP_ORACLE_USER/PASSWORD in ignored .env and ORACLE_SCHEMA
-- to the existing owning schema. Verify all 16 tools before enabling remote use.
-- Do not grant DBA, RESOURCE, ANY privileges, DML or procedure execution.
