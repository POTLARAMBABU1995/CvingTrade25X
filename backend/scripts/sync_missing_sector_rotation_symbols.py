"""Synchronize validated missing Sector Rotation symbols from staging into the canonical map.

The source CSV must contain SYMBOL and SECTOR columns.  ``--dry-run`` is the
default; ``--apply`` makes only idempotent MERGE/insert changes for the supplied
symbols and never deletes existing sector mappings.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import get_oracle_connection


REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_SNAPSHOT_PATH = REPO_ROOT / "backend" / "runtime" / "snapshots" / "sector_rotation_tables.json"
OVERVIEW_SNAPSHOT_PATH = REPO_ROOT / "runtime" / "snapshots" / "sector_overview_latest.json"
DEV_TABLE = "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
UTILITIES_TABLE = "NSE_NIFTY_UTILITIES_STAGING"
SPECIAL_STAGING_ASSIGNMENTS = {"GUJENERGY": "UTILITIES"}
MASTER_CODE_OVERRIDES = {"ELECTRONICS_SERVICES_CONSUMER_DURABLES": "ELEC_SERVICES_CONS_DURABLES"}
SAFE_SQL_NAME = re.compile(r"^[A-Z][A-Z0-9_$#]*$")

# The CSV's source classifications determine the preferred staging table.  A
# candidate is never assigned to a table it does not already occupy, except for
# the explicitly validated GUJENERGY Utilities backfill above.
SECTOR_PREFERENCES: dict[str, tuple[str, ...]] = {
    "AEROSPACE & PRECISION ENGINEERING": ("DEFENCE_AEROSPACE_DEFENSE", "ENGINEERING", "CAPITAL_GOODS"),
    "BANKS": ("PRIVATE_BANK", "PSU_BANK", "FINANCIAL_SERVICES"),
    "BUILDING MATERIALS": ("CONSTRUCTION_MATERIALS", "CEMENT_CEMENT_PRODUCTS"),
    "CAPITAL MARKETS & ASSET MANAGEMENT": ("CAPITAL_MARKETS", "ASSET_MANAGEMENT_COMPANY", "STOCKBROKING_AND_ALLIED", "FINANCIAL_SERVICES"),
    "CHEMICALS, ENZYMES & BIOTECH": ("BIOTECHNOLOGY", "CHEMICALS", "SPECIALTY_CHEMICALS"),
    "CONSUMER DURABLES & HOME PRODUCTS": ("CONSUMER_DURABLES", "CONSUMER_ELECTRONICS", "HOUSEHOLD_PERSONAL_PRODUCTS"),
    "DIVERSIFIED / OTHER": ("DIVERSIFIED",),
    "DIVERSIFIED INDUSTRIALS": ("INDUSTRIAL_MANUFACTURING", "INDUSTRIAL_PRODUCTS", "ENGINEERING", "CAPITAL_GOODS"),
    "ELECTRONICS & EMS": ("ELECTRONICS_SERVICES_CONSUMER_DURABLES", "CONSUMER_ELECTRONICS"),
    "FINANCIAL HOLDINGS & DIVERSIFIED FINANCE": ("FINANCIAL_SERVICES",),
    "FINTECH & DIGITAL PAYMENTS": ("FINTECH", "FINANCIAL_SERVICES"),
    "FMCG & PERSONAL CARE": ("FMCG", "HOUSEHOLD_PERSONAL_PRODUCTS"),
    "FOOTWEAR": ("FOOTWEAR", "LEATHER_LEATHER_PRODUCTS", "CONSUMER_DURABLES"),
    "HEALTHCARE & HOSPITALS": ("HEALTHCARE_INDEX", "NIFTY500_HEALTHCARE", "MIDSMALL_HEALTHCARE"),
    "INSURANCE": ("INSURANCE", "FINANCIAL_SERVICES"),
    "IT & SOFTWARE SERVICES": ("IT", "SOFTWARE_PRODUCTS_SERVICES", "IT_ENABLED_SERVICES", "MIDSMALL_IT_TELECOM"),
    "JEWELLERY & WATCHES": ("JEWELLERY_WATCHES", "GEMS", "CONSUMER_DURABLES"),
    "MEDICAL EQUIPMENT & DIAGNOSTICS": ("MEDICAL_EQUIPMENT_SUPPLIES", "HEALTHCARE_INDEX"),
    "METALS & MINING": ("METALS_MINING", "IRON_STEEL", "METAL", "MINING", "NON_FERROUS_METALS"),
    "NBFC & HOUSING FINANCE": ("NBFC", "HOUSING_FINANCE_COMPANY", "FINANCIAL_SERVICES"),
    "OIL, GAS & ENERGY": ("OIL_AND_GAS", "PETROLEUM_PRODUCTS_REFINERIES", "LPG_CNG_PNG_LNG_SUPPLIER", "UTILITIES"),
    "PAPER & PACKAGING": ("PAPER_PACKAGING",),
    "PHARMACEUTICALS & LIFE SCIENCES": ("PHARMA", "HEALTHCARE_INDEX", "NIFTY500_HEALTHCARE"),
    "RETAIL & DISTRIBUTION": ("RETAILING_SPECIALITY_RETAIL", "ECOMMERCE_ERETAI", "CONSUMER_SERVICES"),
    "TELECOM & DIGITAL COMMUNICATIONS": ("TELECOMMUNICATION", "MIDSMALL_IT_TELECOM"),
    "TEXTILES & APPAREL": ("TEXTILES_APPARELS",),
    "TRADING & COMMERCE": ("COMMODITIES_TRADING", "SERVICES"),
}
FALLBACK_SECTOR_PREFERENCE = (
    "FINANCIAL_SERVICES", "HEALTHCARE_INDEX", "IT", "CONSUMER_DURABLES",
    "METALS_MINING", "OIL_AND_GAS", "TEXTILES_APPARELS", "DIVERSIFIED",
    "INDUSTRIAL_MANUFACTURING", "UTILITIES", "SERVICES",
)


def _normalize(value: Any) -> str:
    return str(value or "").strip().upper()


def _load_candidates(csv_path: Path) -> dict[str, str]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"SYMBOL", "SECTOR"}
        if not reader.fieldnames or not required.issubset({_normalize(name) for name in reader.fieldnames}):
            raise ValueError("CSV must contain SYMBOL and SECTOR headers.")
        candidates: dict[str, str] = {}
        for row in reader:
            symbol = _normalize(row.get("SYMBOL"))
            sector = _normalize(row.get("SECTOR"))
            if not symbol or not sector:
                raise ValueError("Every CSV row must have SYMBOL and SECTOR values.")
            if symbol in candidates and candidates[symbol] != sector:
                raise ValueError(f"Conflicting source sectors for {symbol}: {candidates[symbol]} / {sector}")
            candidates[symbol] = sector
    return candidates


def _load_staging_tables() -> dict[str, dict[str, str]]:
    payload = json.loads(TABLE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    tables: dict[str, dict[str, str]] = {}
    for item in payload.get("tables", []):
        code = _normalize(item.get("sectorCode"))
        table = _normalize(item.get("tableName"))
        if code and table and SAFE_SQL_NAME.fullmatch(table):
            tables[code] = {"table": table, "name": str(item.get("sectorName") or code).strip()}
    return tables


def _load_visible_rotation_symbols() -> set[str]:
    payload = json.loads(OVERVIEW_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {
        _normalize(row.get("stock") or row.get("symbol"))
        for row in payload.get("rows", [])
        if _normalize(row.get("stock") or row.get("symbol"))
    }


def _binds(symbols: list[str]) -> tuple[str, dict[str, str]]:
    return ", ".join(f":symbol_{index}" for index in range(len(symbols))), {
        f"symbol_{index}": symbol for index, symbol in enumerate(symbols)
    }


def _read_staging_memberships(cursor: Any, symbols: list[str], tables: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    placeholders, binds = _binds(symbols)
    memberships: dict[str, set[str]] = defaultdict(set)
    for code, metadata in tables.items():
        table = metadata["table"]
        cursor.execute(
            f"SELECT DISTINCT UPPER(TRIM(symbol)) FROM {table} "
            f"WHERE UPPER(TRIM(symbol)) IN ({placeholders})",
            binds,
        )
        for row in cursor.fetchall():
            memberships[_normalize(row[0])].add(code)
    return memberships


def _read_dev_symbols(cursor: Any, symbols: list[str]) -> set[str]:
    placeholders, binds = _binds(symbols)
    cursor.execute(
        f"SELECT DISTINCT UPPER(TRIM(symbol)) FROM {DEV_TABLE} "
        f"WHERE UPPER(TRIM(symbol)) IN ({placeholders})",
        binds,
    )
    return {_normalize(row[0]) for row in cursor.fetchall()}


def _read_existing_map(cursor: Any, symbols: list[str]) -> dict[str, str]:
    placeholders, binds = _binds(symbols)
    cursor.execute(
        f"SELECT UPPER(TRIM(symbol)), UPPER(TRIM(sector_code)) FROM NSE_SYMBOL_SECTOR_MAP "
        f"WHERE UPPER(TRIM(symbol)) IN ({placeholders})",
        binds,
    )
    return {_normalize(symbol): _normalize(code) for symbol, code in cursor.fetchall()}


def _choose_sector(symbol: str, source_sector: str, memberships: set[str]) -> str:
    if symbol in SPECIAL_STAGING_ASSIGNMENTS:
        return SPECIAL_STAGING_ASSIGNMENTS[symbol]
    for preferred in SECTOR_PREFERENCES.get(source_sector, ()):
        if preferred in memberships:
            return MASTER_CODE_OVERRIDES.get(preferred, preferred)
    for preferred in FALLBACK_SECTOR_PREFERENCE:
        if preferred in memberships:
            return MASTER_CODE_OVERRIDES.get(preferred, preferred)
    if len(memberships) == 1:
        return MASTER_CODE_OVERRIDES.get(next(iter(memberships)), next(iter(memberships)))
    raise ValueError(
        f"No unambiguous respected staging assignment for {symbol} ({source_sector}); "
        f"staging={sorted(memberships)}"
    )


def _ensure_gujenergy_staging(cursor: Any) -> None:
    cursor.execute(
        f"MERGE INTO {UTILITIES_TABLE} target USING (SELECT 'GUJENERGY' symbol FROM dual) source "
        "ON (UPPER(TRIM(target.symbol)) = source.symbol) "
        "WHEN NOT MATCHED THEN INSERT (SYMBOL, SECTOR) VALUES (source.symbol, 'Utilities')"
    )


def _missing_master_codes(cursor: Any, sector_codes: set[str]) -> set[str]:
    if not sector_codes:
        return set()
    placeholders, binds = _binds(sorted(sector_codes))
    cursor.execute(
        f"SELECT UPPER(TRIM(sector_code)) FROM NSE_SECTOR_MASTER WHERE UPPER(TRIM(sector_code)) IN ({placeholders})",
        binds,
    )
    existing = {_normalize(row[0]) for row in cursor.fetchall()}
    return sector_codes - existing


def _ensure_sector_master(cursor: Any, missing_codes: set[str], tables: dict[str, dict[str, str]]) -> int:
    inserted = 0
    for position, code in enumerate(sorted(missing_codes), start=1):
        metadata = tables.get(code)
        if not metadata:
            raise ValueError(f"No registered staging metadata for sector code {code}")
        cursor.execute(
            "INSERT INTO NSE_SECTOR_MASTER (SECTOR_CODE, SECTOR_NAME, INDEX_CODE, DISPLAY_ORDER) "
            "VALUES (:sector_code, :sector_name, :index_code, :display_order)",
            {
                "sector_code": code,
                "sector_name": metadata["name"],
                "index_code": code,
                "display_order": 900 + position,
            },
        )
        inserted += 1
    return inserted


def _merge_map(cursor: Any, assignments: dict[str, str]) -> int:
    changed = 0
    for symbol, sector_code in assignments.items():
        cursor.execute(
            "MERGE INTO NSE_SYMBOL_SECTOR_MAP target "
            "USING (SELECT :symbol symbol, :sector_code sector_code FROM dual) source "
            "ON (UPPER(TRIM(target.symbol)) = source.symbol) "
            "WHEN MATCHED THEN UPDATE SET target.sector_code = source.sector_code "
            "WHERE NVL(target.sector_code, '~') <> source.sector_code "
            "WHEN NOT MATCHED THEN INSERT (SYMBOL, SECTOR_CODE) VALUES (source.symbol, source.sector_code)",
            {"symbol": symbol, "sector_code": sector_code},
        )
        changed += int(cursor.rowcount or 0)
    return changed


def run(csv_path: Path, *, apply: bool) -> dict[str, Any]:
    source_candidates = _load_candidates(csv_path)
    visible_symbols = _load_visible_rotation_symbols()
    candidates = {
        symbol: source_sector
        for symbol, source_sector in source_candidates.items()
        if symbol not in visible_symbols
    }
    symbols = sorted(candidates)
    tables = _load_staging_tables()
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            memberships = _read_staging_memberships(cursor, symbols, tables)
            if apply and "GUJENERGY" in candidates and not memberships.get("GUJENERGY"):
                _ensure_gujenergy_staging(cursor)
                memberships["GUJENERGY"].add("UTILITIES")
            dev_symbols = _read_dev_symbols(cursor, symbols)
            missing_dev = sorted(set(symbols) - dev_symbols)
            if missing_dev:
                raise ValueError(f"DEV-table validation failed for: {', '.join(missing_dev)}")
            assignments = {
                symbol: _choose_sector(symbol, candidates[symbol], memberships.get(symbol, set()))
                for symbol in symbols
            }
            existing = _read_existing_map(cursor, symbols)
            missing_master_codes = _missing_master_codes(cursor, set(assignments.values()))
            master_inserts = _ensure_sector_master(cursor, missing_master_codes, tables) if apply else 0
            changed = _merge_map(cursor, assignments) if apply else 0
        if apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    inserts = sorted(symbol for symbol in assignments if symbol not in existing)
    updates = sorted(symbol for symbol in assignments if existing.get(symbol) and existing[symbol] != assignments[symbol])
    unchanged = sorted(symbol for symbol in assignments if existing.get(symbol) == assignments[symbol])
    return {
        "ok": True,
        "dryRun": not apply,
        "sourceCandidateCount": len(source_candidates),
        "alreadyVisibleExcludedCount": len(source_candidates) - len(symbols),
        "candidateCount": len(symbols),
        "stagingTableCount": len(tables),
        "insertCount": len(inserts),
        "updateCount": len(updates),
        "unchangedCount": len(unchanged),
        "changedRowCount": changed,
        "masterInsertCount": len(missing_master_codes),
        "masterRowsInserted": master_inserts,
        "gujenergyUtilitiesBackfill": apply and "GUJENERGY" in candidates,
        "assignmentsBySector": {code: sum(1 for value in assignments.values() if value == code) for code in sorted(set(assignments.values()))},
        "inserts": inserts,
        "updates": updates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Validated MCAP-filtered CSV with SYMBOL and SECTOR columns.")
    parser.add_argument("--apply", action="store_true", help="Commit staging/map MERGE operations; default is dry-run.")
    args = parser.parse_args()
    print(json.dumps(run(args.csv, apply=args.apply), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
