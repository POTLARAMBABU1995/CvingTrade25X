SET DEFINE OFF;
SET SERVEROUTPUT ON;

PROMPT Normalizing tablespaces and recompiling objects...

BEGIN
  FOR rec IN (
    SELECT table_name
    FROM user_tables
    WHERE temporary = 'N'
      AND secondary = 'N'
      AND table_name NOT LIKE 'BIN$%'
  ) LOOP
    BEGIN
      EXECUTE IMMEDIATE 'ALTER TABLE "' || rec.table_name || '" MOVE TABLESPACE CVING_DATA';
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;
  END LOOP;
END;
/

BEGIN
  FOR rec IN (
    SELECT table_name, column_name
    FROM user_lobs
    WHERE table_name NOT LIKE 'BIN$%'
  ) LOOP
    BEGIN
      EXECUTE IMMEDIATE
        'ALTER TABLE "' || rec.table_name || '" MOVE LOB ("' || rec.column_name || '") STORE AS (TABLESPACE CVING_DATA)';
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;
  END LOOP;
END;
/

BEGIN
  FOR rec IN (
    SELECT index_name
    FROM user_indexes
    WHERE temporary = 'N'
      AND index_type NOT LIKE 'LOB%'
      AND index_name NOT LIKE 'BIN$%'
  ) LOOP
    BEGIN
      EXECUTE IMMEDIATE 'ALTER INDEX "' || rec.index_name || '" REBUILD TABLESPACE CVING_INDEX';
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;
  END LOOP;
END;
/

BEGIN
  FOR rec IN (
    SELECT object_name, object_type
    FROM user_objects
    WHERE status = 'INVALID'
      AND object_type IN ('VIEW', 'MATERIALIZED VIEW', 'PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'TRIGGER')
  ) LOOP
    BEGIN
      IF rec.object_type = 'PACKAGE' THEN
        EXECUTE IMMEDIATE 'ALTER PACKAGE "' || rec.object_name || '" COMPILE';
        EXECUTE IMMEDIATE 'ALTER PACKAGE "' || rec.object_name || '" COMPILE BODY';
      ELSIF rec.object_type = 'PACKAGE BODY' THEN
        EXECUTE IMMEDIATE 'ALTER PACKAGE "' || rec.object_name || '" COMPILE BODY';
      ELSIF rec.object_type = 'MATERIALIZED VIEW' THEN
        EXECUTE IMMEDIATE 'ALTER MATERIALIZED VIEW "' || rec.object_name || '" COMPILE';
      ELSIF rec.object_type = 'VIEW' THEN
        EXECUTE IMMEDIATE 'ALTER VIEW "' || rec.object_name || '" COMPILE';
      ELSIF rec.object_type = 'PROCEDURE' THEN
        EXECUTE IMMEDIATE 'ALTER PROCEDURE "' || rec.object_name || '" COMPILE';
      ELSIF rec.object_type = 'FUNCTION' THEN
        EXECUTE IMMEDIATE 'ALTER FUNCTION "' || rec.object_name || '" COMPILE';
      ELSIF rec.object_type = 'TRIGGER' THEN
        EXECUTE IMMEDIATE 'ALTER TRIGGER "' || rec.object_name || '" COMPILE';
      END IF;
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;
  END LOOP;
END;
/

BEGIN
  DBMS_STATS.GATHER_SCHEMA_STATS(USER, options => 'GATHER AUTO', cascade => TRUE);
EXCEPTION
  WHEN OTHERS THEN
    NULL;
END;
/

PROMPT Tablespace normalization and recompilation complete.
