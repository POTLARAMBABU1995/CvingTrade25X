SET DEFINE OFF
SET SERVEROUTPUT ON SIZE UNLIMITED
SET FEEDBACK ON
SET ECHO OFF
SET TERMOUT ON
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
CONNECT CVING_APP/"Rambabu@1260"@//127.0.0.1:1521/cvingpdb.local
@C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\db\migration\_generated\storage_normalization_cving_app_storage_normalization.sql
EXIT
