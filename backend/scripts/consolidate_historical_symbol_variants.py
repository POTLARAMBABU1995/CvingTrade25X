from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
  sys.path.insert(0, str(BACKEND_ROOT))

from db_pool import pool  # noqa: E402


TABLES = (
  "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
  "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
)

# Keep the current canonical identity and fold alternate historical series into it.
# GRETEX has only SM/ST rows today, so both are folded into the canonical base symbol.
VARIANT_GROUPS: dict[str, tuple[str, ...]] = {
  "AGRITECH": ("AGRITECH-BE",),
  "BLISSGVS": ("BLISSGVS-BE",),
  "DBREALTY": ("DBREALTY-BE",),
  "GRETEX": ("GRETEX-SM", "GRETEX-ST"),
  "JAIBALAJI": ("JAIBALAJI-BE",),
  "LIKHITHA": ("LIKHITHA-BE",),
  "LTM": ("LTIM",),
  "MENONBE": ("MENONBE-BE",),
  "MTARTECH": ("MTARTECH-BE",),
  "NOVAAGRI": ("NOVAAGRI-BE",),
  "ONMOBILE": ("ONMOBILE-BE",),
  "PAVNAIND": ("PAVNAIND-BE",),
  "PFOCUS": ("PFOCUS-BE",),
  "PPAP": ("PPAP-BE",),
  "PRADPME": ("PRADPME-BE",),
  "PREMIERPOL": ("PREMIERPOL-BE",),
  "QPOWER": ("QPOWER-BE",),
  "STERTOOLS": ("STERTOOLS-BE",),
  "SUNDRMBRAK": ("SUNDRMBRAK-BE",),
  "TRIVENI": ("TRIVENI-BE",),
  "VELJAN": ("VELJAN-BE",),
  "VIKRAMSOLR": ("VIKRAMSOLR-BE",),
}


def _json_value(value: Any) -> Any:
  if isinstance(value, (date, datetime)):
    return value.isoformat()
  if isinstance(value, Decimal):
    return str(value)
  raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _symbol_binds(symbols: list[str], prefix: str) -> tuple[str, dict[str, str]]:
  binds = {f"{prefix}{index}": symbol for index, symbol in enumerate(symbols)}
  return ", ".join(f":{name}" for name in binds), binds


def _table_columns(cursor: Any, table: str) -> list[str]:
  cursor.execute(
    """
    SELECT column_name
    FROM user_tab_columns
    WHERE table_name = :table_name
    ORDER BY column_id
    """,
    {"table_name": table},
  )
  columns = [str(row[0]) for row in cursor.fetchall()]
  if not columns or "SYMBOL" not in columns or "TRADING_DATE" not in columns:
    raise RuntimeError(f"Unexpected table contract for {table}.")
  return columns


def _group_stats(cursor: Any, table: str, target: str, sources: tuple[str, ...]) -> dict[str, int]:
  symbols = [target, *sources]
  in_sql, binds = _symbol_binds(symbols, "group_symbol_")
  cursor.execute(
    f"""
    SELECT COUNT(*) AS row_count,
           COUNT(DISTINCT TRUNC(trading_date)) AS trading_day_count
    FROM {table}
    WHERE symbol IN ({in_sql})
    """,
    binds,
  )
  row_count, trading_day_count = cursor.fetchone()
  return {
    "rowCount": int(row_count or 0),
    "tradingDayCount": int(trading_day_count or 0),
  }


def _export_table_rows(cursor: Any, table: str, backup_dir: Path) -> dict[str, Any]:
  columns = _table_columns(cursor, table)
  symbols = sorted({symbol for target, sources in VARIANT_GROUPS.items() for symbol in (target, *sources)})
  in_sql, binds = _symbol_binds(symbols, "backup_symbol_")
  cursor.execute(
    f"SELECT {', '.join(columns)} FROM {table} WHERE symbol IN ({in_sql}) ORDER BY symbol, trading_date",
    binds,
  )
  rows = cursor.fetchall()
  output_path = backup_dir / f"{table}.csv"
  with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(columns)
    writer.writerows(rows)
  return {
    "columns": columns,
    "path": str(output_path),
    "rowCount": len(rows),
  }


def _consolidate_group(
  cursor: Any,
  table: str,
  target: str,
  sources: tuple[str, ...],
) -> dict[str, Any]:
  before = _group_stats(cursor, table, target, sources)
  operations: list[dict[str, Any]] = []

  for source in sources:
    cursor.execute(
      f"""
      DELETE FROM {table} source_row
      WHERE source_row.symbol = :source_symbol
        AND EXISTS (
          SELECT 1
          FROM {table} target_row
          WHERE target_row.symbol = :target_symbol
            AND TRUNC(target_row.trading_date) = TRUNC(source_row.trading_date)
        )
      """,
      {"source_symbol": source, "target_symbol": target},
    )
    deleted_overlap_rows = int(cursor.rowcount or 0)

    cursor.execute(
      f"UPDATE {table} SET symbol = :target_symbol WHERE symbol = :source_symbol",
      {"target_symbol": target, "source_symbol": source},
    )
    renamed_rows = int(cursor.rowcount or 0)
    operations.append({
      "source": source,
      "deletedOverlapRows": deleted_overlap_rows,
      "renamedRows": renamed_rows,
    })

  after = _group_stats(cursor, table, target, sources)
  if after["rowCount"] != before["tradingDayCount"]:
    raise RuntimeError(
      f"{table} {target}: expected {before['tradingDayCount']} consolidated rows, "
      f"found {after['rowCount']}."
    )

  source_in_sql, source_binds = _symbol_binds(list(sources), "remaining_source_")
  cursor.execute(
    f"SELECT COUNT(*) FROM {table} WHERE symbol IN ({source_in_sql})",
    source_binds,
  )
  remaining_source_rows = int(cursor.fetchone()[0] or 0)
  if remaining_source_rows:
    raise RuntimeError(f"{table} {target}: {remaining_source_rows} variant rows remain.")

  return {
    "target": target,
    "sources": list(sources),
    "before": before,
    "after": after,
    "operations": operations,
  }


def _preview(cursor: Any) -> dict[str, Any]:
  preview: dict[str, Any] = {}
  for table in TABLES:
    groups = []
    for target, sources in VARIANT_GROUPS.items():
      groups.append({
        "target": target,
        "sources": list(sources),
        **_group_stats(cursor, table, target, sources),
      })
    preview[table] = groups
  return preview


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Consolidate duplicate historical symbol variants without losing unique trading dates."
  )
  parser.add_argument("--apply", action="store_true", help="Commit the consolidation. Default is read-only.")
  parser.add_argument(
    "--backup-dir",
    default="",
    help="Backup directory used only with --apply. Defaults under runtime/backups.",
  )
  args = parser.parse_args()

  with pool.acquire() as connection, connection.cursor() as cursor:
    preview = _preview(cursor)
    if not args.apply:
      print(json.dumps({"apply": False, "groups": len(VARIANT_GROUPS), "preview": preview}, indent=2))
      return 0

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_dir = (
      Path(args.backup_dir).expanduser().resolve()
      if args.backup_dir
      else PROJECT_ROOT / "runtime" / "backups" / f"{stamp}_v143-historical-symbol-variants"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
      "createdAt": datetime.now().astimezone().isoformat(),
      "groups": {target: list(sources) for target, sources in VARIANT_GROUPS.items()},
      "preview": preview,
      "tables": {},
      "status": "backup-created",
    }
    for table in TABLES:
      manifest["tables"][table] = _export_table_rows(cursor, table, backup_dir)
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=_json_value), encoding="utf-8")

    try:
      results: dict[str, Any] = {}
      for table in TABLES:
        results[table] = [
          _consolidate_group(cursor, table, target, sources)
          for target, sources in VARIANT_GROUPS.items()
        ]
      connection.commit()
    except Exception:
      connection.rollback()
      manifest["status"] = "rolled-back-on-error"
      manifest_path.write_text(json.dumps(manifest, indent=2, default=_json_value), encoding="utf-8")
      raise

    manifest["status"] = "committed"
    manifest["results"] = results
    manifest["completedAt"] = datetime.now().astimezone().isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, default=_json_value), encoding="utf-8")
    print(json.dumps({"apply": True, "backupDir": str(backup_dir), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
  raise SystemExit(main())
