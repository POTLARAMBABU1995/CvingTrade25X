from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import oracledb


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = Path(__file__).resolve().parent
GENERATED_DIR = MIGRATION_DIR / "_generated"
REPORT_PATH = MIGRATION_DIR / "restore_report.json"
EXPORT_ROOT = Path(os.getenv("CVING_EXPORT_ROOT", r"E:\DB_BACKUP_SAFETY\EXPORT"))
SQLPLUS_EXE = Path(os.getenv("ORACLE_SQLPLUS_EXE", r"E:\SOFTWARES\WINDOWS.X64_193000_db_home\bin\sqlplus.exe"))
SQLLDR_EXE = Path(os.getenv("ORACLE_SQLLDR_EXE", r"E:\SOFTWARES\WINDOWS.X64_193000_db_home\bin\sqlldr.exe"))

CUSTOM_TABLES = {
    "REGISTRATIONS",
    "LOGIN_ACTIVITY",
    "AUTH_SESSIONS",
    "AUTH_QUICK_MPIN",
    "GAINERS_TOP25",
    "LOOSERS_TOP25",
    "VOLUME_MOVERS_TOP25",
    "DIM_SYMBOLS",
    "FACT_OHLCV",
    "MV_NSE_SECTOR_UI_SNAPSHOT",
}
CUSTOM_PROCEDURES = {
    "PR_SYNC_DIM_SYMBOLS_FROM_DEV",
    "PR_MERGE_FACT_OHLCV_FROM_DEV",
    "PR_SYNC_FACT_OHLCV_FROM_DEV",
    "PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES",
    "PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING",
    "PR_SYNC_SECTOR_REFERENCE_DATA",
}
CUSTOM_VIEWS = {
    "VW_SYMBOL_CAP_BUCKET",
    "VW_NSE_CANONICAL_SECTOR_STAGE",
}
SPECIAL_LOAD_TARGETS = {
    "MV_NSE_SECTOR_UI_SNAPSHOT": "MV_NSE_SECTOR_UI_SNAPSHOT_SRC",
}
SKIP_EXPORT_DIRS = {
    "ACT_TYPES_BKP",
    "BATCH_DETAILS_STAGE_BKP",
    "BATCH_HEADER_STAGE_BKP",
    "VIEW_SCHEDULER_JOB_ARGS_BKP",
    "VIEW_SCHEDULER_PROGRAM_ARGS_BKP",
    "INDEX_OL$HNT_NUM_BKP",
    "INDEX_REDO_DB_IDX_BKP",
    "INDEX_REDO_LOG_IDX_BKP",
    "INDEX_SYS_C_SNAP$_66PK_NSE_NIFTY500_RAW_BKP",
}
INDEX_SKIP_TABLES = CUSTOM_TABLES | {"MV_NSE_SECTOR_UI_SNAPSHOT_SRC"}
TABLE_SKIP_PREFIXES = ("MLOG$_", "MVIEW_LOG_", "MV_")
DATA_SKIP_PREFIXES = ("MLOG$_", "MVIEW_LOG_")
INDEX_DIR_PREFIX = "INDEX_"
VIEW_DIR_PREFIX = "VIEW_"
PROCEDURE_DIR_PREFIX = "PROCEDURE_"
PACKAGE_DIR_PREFIX = "PACKAGE_"
TRIGGER_DIR_PREFIX = "TRIGGER_"


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


load_env()


@dataclass(frozen=True)
class OracleConfig:
    user: str
    password: str
    host: str
    port: str
    service_name: str
    dsn: str

    @property
    def sqlplus_connect(self) -> str:
        return f'{self.user}/"{self.password}"@//{self.host}:{self.port}/{self.service_name}'


def get_oracle_config() -> OracleConfig:
    user = os.getenv("ORACLE_USER", "CVING_APP").strip()
    password = os.getenv("ORACLE_PASSWORD", "").strip()
    host = os.getenv("ORACLE_HOST", "127.0.0.1").strip()
    port = os.getenv("ORACLE_PORT", "1521").strip()
    service_name = (os.getenv("ORACLE_SERVICE_NAME") or os.getenv("ORACLE_SERVICE") or "cvingpdb.local").strip()
    dsn = (os.getenv("ORACLE_DSN") or f"{host}:{port}/{service_name}").strip()
    if not password:
        raise RuntimeError("ORACLE_PASSWORD is required. Set it in .env or the environment.")
    return OracleConfig(
        user=user,
        password=password,
        host=host,
        port=port,
        service_name=service_name,
        dsn=dsn,
    )


def get_connection(config: OracleConfig):
    return oracledb.connect(user=config.user, password=config.password, dsn=config.dsn)


def ensure_tools() -> None:
    missing = [str(path) for path in (SQLPLUS_EXE, SQLLDR_EXE) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Oracle client tools: {', '.join(missing)}")
    if not EXPORT_ROOT.exists():
        raise FileNotFoundError(f"Export root not found: {EXPORT_ROOT}")


def object_name_from_dir(folder: Path) -> str:
    return folder.name[:-4] if folder.name.endswith("_BKP") else folder.name


def remap_sql(text: str) -> str:
    out = text.replace("\ufeff", "")
    out = re.sub(r'"SYSTEM"\.', "", out, flags=re.IGNORECASE)
    out = re.sub(r"\bSYSTEM\.", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+SHARING\s*=\s*(?:METADATA|DATA|EXTENDED\s+DATA|NONE)\b", "", out, flags=re.IGNORECASE)
    out = re.sub(r'TABLESPACE\s+"?SYSTEM"?', "TABLESPACE CVING_DATA", out, flags=re.IGNORECASE)
    out = re.sub(r'TABLESPACE\s+"?CVING_APP"?', "TABLESPACE CVING_DATA", out, flags=re.IGNORECASE)
    out = re.sub(r'TABLESPACE\s+"?USERS"?', "TABLESPACE CVING_DATA", out, flags=re.IGNORECASE)
    return out


def wrap_sqlplus_statement(statement: str, allowed_sqlcodes: tuple[int, ...]) -> str:
    statement_text = statement.strip().rstrip(";")
    codes = ", ".join(str(code) for code in allowed_sqlcodes)
    return "\n".join(
        [
            "BEGIN",
            f"  EXECUTE IMMEDIATE q'~{statement_text}~';",
            "EXCEPTION",
            "  WHEN OTHERS THEN",
            f"    IF SQLCODE NOT IN ({codes}) THEN",
            "      RAISE;",
            "    END IF;",
            "END;",
            "/",
            "",
        ]
    )


def remap_table_ddl_sql(text: str) -> str:
    remapped = remap_sql(text)
    statement_parts: list[str] = []
    current_lines: list[str] = []

    for line in remapped.splitlines():
        current_lines.append(line)
        if line.strip().endswith(";"):
            statement_parts.append("\n".join(current_lines))
            current_lines = []

    if current_lines:
        statement_parts.append("\n".join(current_lines))

    wrapped_parts: list[str] = []
    for part in statement_parts:
        sql_lines = [line for line in part.splitlines() if line.strip() and not line.strip().startswith("--")]
        stripped = "\n".join(sql_lines).strip()
        upper = stripped.upper()
        if not stripped:
            continue
        if upper.startswith("CREATE TABLE "):
            wrapped_parts.append(wrap_sqlplus_statement(stripped, (-955,)))
            continue
        if upper.startswith("CREATE UNIQUE INDEX ") or upper.startswith("CREATE INDEX "):
            wrapped_parts.append(wrap_sqlplus_statement(stripped, (-955, -1408)))
            continue
        if " MODIFY " in upper and " NOT NULL ENABLE" in upper and upper.startswith("ALTER TABLE "):
            wrapped_parts.append(wrap_sqlplus_statement(stripped, (-1442,)))
            continue
        if upper.startswith("ALTER TABLE "):
            if " ADD PRIMARY KEY " in upper or " ADD CONSTRAINT " in upper:
                wrapped_parts.append(wrap_sqlplus_statement(stripped, (-2260, -2261, -2264, -2275)))
                continue
        wrapped_parts.append(stripped)

    return "\n".join(wrapped_parts)


def reset_generated_dir() -> None:
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def write_processed_sql(src: Path, prefix: str, processed_text: str) -> Path:
    target = GENERATED_DIR / f"{prefix}_{src.stem}.sql"
    target.write_text(processed_text, encoding="utf-8")
    return target


def sqlplus_wrapper(sql_file: Path, config: OracleConfig, wrapper_name: str) -> Path:
    wrapper = GENERATED_DIR / wrapper_name
    wrapper.write_text(
        "\n".join(
            [
                "SET DEFINE OFF",
                "SET SERVEROUTPUT ON SIZE UNLIMITED",
                "SET FEEDBACK ON",
                "SET ECHO OFF",
                "SET TERMOUT ON",
                "WHENEVER SQLERROR EXIT FAILURE ROLLBACK",
                f"CONNECT {config.sqlplus_connect}",
                f"@{sql_file}",
                "EXIT",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return wrapper


def run_sqlplus(sql_file: Path, config: OracleConfig, label: str) -> str:
    wrapper = sqlplus_wrapper(sql_file, config, f"wrapper_{sql_file.stem}.sql")
    completed = subprocess.run(
        [str(SQLPLUS_EXE), "-S", "/nolog", f"@{wrapper}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    if completed.returncode != 0:
        raise RuntimeError(f"{label} failed.\n{output.strip()}")
    return output


def execute_sql_file(src: Path, config: OracleConfig, prefix: str, preprocess: bool = True) -> str:
    sql_text = src.read_text(encoding="utf-8", errors="replace")
    processed = remap_sql(sql_text) if preprocess else sql_text
    processed_path = write_processed_sql(src, prefix, processed)
    return run_sqlplus(processed_path, config, prefix)


def execute_table_ddl_file(src: Path, config: OracleConfig, prefix: str) -> str:
    sql_text = src.read_text(encoding="utf-8", errors="replace")
    processed_path = write_processed_sql(src, prefix, remap_table_ddl_sql(sql_text))
    return run_sqlplus(processed_path, config, prefix)


def table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = :table_name",
            {"table_name": table_name.upper()},
        )
        return int((cur.fetchone() or [0])[0] or 0) > 0


def sequence_exists(conn, sequence_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :sequence_name",
            {"sequence_name": sequence_name.upper()},
        )
        return int((cur.fetchone() or [0])[0] or 0) > 0


def get_row_count(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{table_name.upper()}"')
        return int((cur.fetchone() or [0])[0] or 0)


def get_virtual_columns(conn, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM user_tab_cols
            WHERE table_name = :table_name
              AND virtual_column = 'YES'
            """,
            {"table_name": table_name.upper()},
        )
        return {str(row[0]).upper() for row in cur.fetchall()}


def index_target_table(index_file: Path) -> str | None:
    text = index_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'\bON\s+(?:"?[A-Z0-9_$#]+"\.)?"?([A-Z0-9_$#]+)"?\s*\(', text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def trigger_target_table(trigger_file: Path) -> str | None:
    text = trigger_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'\bON\s+(?:"?[A-Z0-9_$#]+"\.)?"?([A-Z0-9_$#]+)"?\b', text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def iter_backup_dirs() -> Iterable[Path]:
    return sorted(path for path in EXPORT_ROOT.iterdir() if path.is_dir())


def is_generic_table_dir(folder: Path) -> bool:
    name = folder.name
    object_name = object_name_from_dir(folder)
    if name in SKIP_EXPORT_DIRS:
        return False
    if name.startswith((INDEX_DIR_PREFIX, VIEW_DIR_PREFIX, PROCEDURE_DIR_PREFIX, PACKAGE_DIR_PREFIX, TRIGGER_DIR_PREFIX)):
        return False
    if object_name in CUSTOM_TABLES or object_name in SPECIAL_LOAD_TARGETS:
        return False
    if object_name.startswith(TABLE_SKIP_PREFIXES):
        return False
    return True


def is_data_load_dir(folder: Path) -> bool:
    object_name = object_name_from_dir(folder)
    if folder.name in SKIP_EXPORT_DIRS:
        return False
    if folder.name.startswith((INDEX_DIR_PREFIX, VIEW_DIR_PREFIX, PROCEDURE_DIR_PREFIX, PACKAGE_DIR_PREFIX, TRIGGER_DIR_PREFIX)):
        return False
    if object_name.startswith(DATA_SKIP_PREFIXES):
        return False
    return True


def iter_sql_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.glob("*.sql"))


def first_control_file(folder: Path) -> Path | None:
    controls = sorted(folder.glob("*.ctl"))
    return controls[0] if controls else None


def write_control_file(src: Path, target_table: str, virtual_columns: set[str] | None = None) -> Path:
    text = src.read_text(encoding="utf-8", errors="replace")
    remapped = re.sub(
        r'INTO TABLE\s+"?SYSTEM"?\."?[A-Z0-9_$#]+"?',
        f'INTO TABLE "{target_table.upper()}"',
        text,
        flags=re.IGNORECASE,
    )
    remapped = re.sub(
        r'INTO TABLE\s+"?[A-Z0-9_$#]+"?\."?[A-Z0-9_$#]+"?',
        f'INTO TABLE "{target_table.upper()}"',
        remapped,
        flags=re.IGNORECASE,
    )
    remapped = re.sub(
        r"INFILE\s+'([^']+)'",
        lambda match: f"INFILE '{(src.parent / Path(match.group(1)).name)}'",
        remapped,
        flags=re.IGNORECASE,
    )
    remapped = re.sub(
        r'\b(TIMESTAMP|DATE)\s+""([^"]+)""',
        lambda match: f'{match.group(1)} "{match.group(2)}"',
        remapped,
        flags=re.IGNORECASE,
    )
    if virtual_columns:
        filtered_lines = []
        for line in remapped.splitlines():
            column_match = re.match(r'\s*"([A-Z0-9_$#]+)"\s+', line, flags=re.IGNORECASE)
            if column_match and column_match.group(1).upper() in virtual_columns:
                continue
            filtered_lines.append(line)
        for index in range(len(filtered_lines) - 1, -1, -1):
            if re.match(r'\s*"([A-Z0-9_$#]+)"\s+', filtered_lines[index], flags=re.IGNORECASE):
                filtered_lines[index] = re.sub(r',\s*$', "", filtered_lines[index])
                break
        remapped = "\n".join(filtered_lines)
        if not re.search(r'\)\s*$', remapped):
            remapped = remapped.rstrip() + "\n)"
    out_path = GENERATED_DIR / f"ctl_{src.stem}_{target_table.upper()}.ctl"
    out_path.write_text(remapped, encoding="utf-8")
    return out_path


def run_sqlldr(control_file: Path, config: OracleConfig, target_table: str) -> str:
    log_path = GENERATED_DIR / f"{target_table.lower()}_load.log"
    bad_path = GENERATED_DIR / f"{target_table.lower()}_load.bad"
    discard_path = GENERATED_DIR / f"{target_table.lower()}_load.dis"
    userid = f'userid={config.sqlplus_connect}'
    completed = subprocess.run(
        [
            str(SQLLDR_EXE),
            userid,
            f"control={control_file}",
            f"log={log_path}",
            f"bad={bad_path}",
            f"discard={discard_path}",
            "direct=true",
            "rows=50000",
            "bindsize=10485760",
            "readsize=10485760",
            "errors=1000000",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    if completed.returncode not in (0, 2):
        raise RuntimeError(f"SQL*Loader failed for {target_table}.\n{output.strip()}")
    return (log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else output)


def ensure_fyers_holdings_tables(config: OracleConfig, report: dict[str, list[dict[str, object]]]) -> None:
    script = REPO_ROOT / "backend" / "sql" / "create_fyers_holdings_tables.sql"
    with get_connection(config) as conn:
        if table_exists(conn, "FYERS_HOLDINGS_IMPORTS"):
            report["skipped"].append({"stage": "custom", "object": "FYERS_HOLDINGS_*", "reason": "already present"})
            return
    execute_sql_file(script, config, "custom_fyers_holdings", preprocess=False)
    report["executed_sql"].append({"stage": "custom", "path": str(script)})


def build_report_skeleton(config: OracleConfig) -> dict[str, object]:
    return {
        "connection": {
            "user": config.user,
            "host": config.host,
            "port": config.port,
            "service_name": config.service_name,
            "dsn": config.dsn,
        },
        "executed_sql": [],
        "loaded_tables": [],
        "skipped": [],
        "errors": [],
    }


def restore() -> int:
    config = get_oracle_config()
    ensure_tools()
    reset_generated_dir()
    report: dict[str, object] = build_report_skeleton(config)

    pre_sql = MIGRATION_DIR / "cving_app_runtime_pre.sql"
    post_sql = MIGRATION_DIR / "cving_app_runtime_post.sql"
    storage_sql = MIGRATION_DIR / "cving_app_storage_normalization.sql"
    repo_fact_sql = REPO_ROOT / "backend" / "sql" / "create_fact_ohlcv_sync_procedures.sql"
    repo_sector_sql = REPO_ROOT / "backend" / "sql" / "create_sector_reference_sync_procedures.sql"

    execute_sql_file(pre_sql, config, "runtime_pre", preprocess=False)
    report["executed_sql"].append({"stage": "custom-pre", "path": str(pre_sql)})

    restored_tables: set[str] = set(CUSTOM_TABLES | {"MV_NSE_SECTOR_UI_SNAPSHOT_SRC"})

    with get_connection(config) as conn:
        for folder in iter_backup_dirs():
            object_name = object_name_from_dir(folder)
            if not is_generic_table_dir(folder):
                continue
            sql_files = iter_sql_files(folder)
            if not sql_files:
                report["skipped"].append({"stage": "table-ddl", "object": object_name, "reason": "no ddl file"})
                continue
            for sql_file in sql_files:
                execute_table_ddl_file(sql_file, config, f"table_{object_name.lower()}")
                report["executed_sql"].append({"stage": "table-ddl", "object": object_name, "path": str(sql_file)})
            restored_tables.add(object_name)

    with get_connection(config) as conn:
        for folder in iter_backup_dirs():
            object_name = object_name_from_dir(folder)
            if not is_data_load_dir(folder):
                continue
            target_table = SPECIAL_LOAD_TARGETS.get(object_name, object_name)
            control_file = first_control_file(folder)
            if control_file is None:
                report["skipped"].append({"stage": "data-load", "object": object_name, "reason": "no control file"})
                continue
            if not table_exists(conn, target_table):
                report["skipped"].append({"stage": "data-load", "object": object_name, "reason": f"target table {target_table} missing"})
                continue
            current_count = get_row_count(conn, target_table)
            if current_count > 0:
                report["skipped"].append({"stage": "data-load", "object": object_name, "reason": f"target table {target_table} already has {current_count} rows"})
                continue
            generated_ctl = write_control_file(control_file, target_table, get_virtual_columns(conn, target_table))
            run_sqlldr(generated_ctl, config, target_table)
            loaded_count = get_row_count(conn, target_table)
            report["loaded_tables"].append(
                {"source_object": object_name, "target_table": target_table, "row_count": loaded_count, "control_file": str(control_file)}
            )

    execute_sql_file(post_sql, config, "runtime_post", preprocess=False)
    report["executed_sql"].append({"stage": "custom-post", "path": str(post_sql)})

    for folder in iter_backup_dirs():
        object_name = object_name_from_dir(folder)
        if folder.name in SKIP_EXPORT_DIRS or not folder.name.startswith(VIEW_DIR_PREFIX):
            continue
        if object_name in CUSTOM_VIEWS:
            report["skipped"].append({"stage": "view-ddl", "object": object_name, "reason": "created from repo SQL"})
            continue
        for sql_file in iter_sql_files(folder):
            execute_sql_file(sql_file, config, f"view_{object_name.lower()}")
            report["executed_sql"].append({"stage": "view-ddl", "object": object_name, "path": str(sql_file)})

    for folder in iter_backup_dirs():
        object_name = object_name_from_dir(folder)
        if folder.name in SKIP_EXPORT_DIRS or not folder.name.startswith(PACKAGE_DIR_PREFIX):
            continue
        for sql_file in iter_sql_files(folder):
            execute_sql_file(sql_file, config, f"package_{object_name.lower()}")
            report["executed_sql"].append({"stage": "package-ddl", "object": object_name, "path": str(sql_file)})

    for folder in iter_backup_dirs():
        object_name = object_name_from_dir(folder)
        if folder.name in SKIP_EXPORT_DIRS or not folder.name.startswith(PROCEDURE_DIR_PREFIX):
            continue
        if object_name in CUSTOM_PROCEDURES:
            report["skipped"].append({"stage": "procedure-ddl", "object": object_name, "reason": "created from repo SQL"})
            continue
        for sql_file in iter_sql_files(folder):
            execute_sql_file(sql_file, config, f"procedure_{object_name.lower()}")
            report["executed_sql"].append({"stage": "procedure-ddl", "object": object_name, "path": str(sql_file)})

    execute_sql_file(repo_fact_sql, config, "repo_fact_procedures", preprocess=False)
    report["executed_sql"].append({"stage": "repo-procedure", "path": str(repo_fact_sql)})

    execute_sql_file(repo_sector_sql, config, "repo_sector_procedures", preprocess=False)
    report["executed_sql"].append({"stage": "repo-procedure", "path": str(repo_sector_sql)})

    with get_connection(config) as conn:
        for folder in iter_backup_dirs():
            object_name = object_name_from_dir(folder)
            if folder.name in SKIP_EXPORT_DIRS or not folder.name.startswith(TRIGGER_DIR_PREFIX):
                continue
            sql_files = iter_sql_files(folder)
            if not sql_files:
                continue
            target_table = trigger_target_table(sql_files[0])
            if not target_table or not table_exists(conn, target_table):
                report["skipped"].append({"stage": "trigger-ddl", "object": object_name, "reason": f"target table {target_table or 'UNKNOWN'} missing"})
                continue
            for sql_file in sql_files:
                execute_sql_file(sql_file, config, f"trigger_{object_name.lower()}")
                report["executed_sql"].append({"stage": "trigger-ddl", "object": object_name, "path": str(sql_file)})

    for folder in iter_backup_dirs():
        object_name = object_name_from_dir(folder)
        if folder.name in SKIP_EXPORT_DIRS or not folder.name.startswith(INDEX_DIR_PREFIX):
            continue
        sql_files = iter_sql_files(folder)
        if not sql_files:
            continue
        target_table = index_target_table(sql_files[0])
        if not target_table or target_table in INDEX_SKIP_TABLES or target_table not in restored_tables:
            report["skipped"].append({"stage": "index-ddl", "object": object_name, "reason": f"target table {target_table or 'UNKNOWN'} not eligible"})
            continue
        try:
            for sql_file in sql_files:
                execute_sql_file(sql_file, config, f"index_{object_name.lower()}")
                report["executed_sql"].append({"stage": "index-ddl", "object": object_name, "path": str(sql_file)})
        except RuntimeError as exc:
            message = str(exc)
            if any(token in message for token in ("ORA-00955", "ORA-01408", "ORA-02261", "ORA-02260")):
                report["skipped"].append({"stage": "index-ddl", "object": object_name, "reason": "duplicate or equivalent index/constraint"})
                continue
            raise

    ensure_fyers_holdings_tables(config, report)  # type: ignore[arg-type]

    execute_sql_file(storage_sql, config, "storage_normalization", preprocess=False)
    report["executed_sql"].append({"stage": "storage-normalization", "path": str(storage_sql)})

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Restore completed. Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(restore())
    except Exception as exc:
        error_report = {
            "status": "failed",
            "error": str(exc),
        }
        REPORT_PATH.write_text(json.dumps(error_report, indent=2), encoding="utf-8")
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
