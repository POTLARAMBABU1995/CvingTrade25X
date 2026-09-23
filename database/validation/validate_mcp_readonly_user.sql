-- Read-only: run as the proposed MCP account. Do not print account credentials.
SELECT privilege FROM session_privs ORDER BY privilege;
SELECT role FROM session_roles ORDER BY role;
SELECT owner, table_name, privilege FROM user_tab_privs_recd ORDER BY owner, table_name;
-- Expected system privilege: CREATE SESSION only; no write roles or grants.
-- DBA must also review inherited PUBLIC privileges and executable functions.
