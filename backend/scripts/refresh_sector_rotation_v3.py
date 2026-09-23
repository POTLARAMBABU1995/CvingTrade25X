from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.sector_rotation_v3_refresh_service import refresh_sector_rotation_v3_snapshot


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and atomically publish a Sector Rotation V3 snapshot.")
    parser.add_argument("--trade-date", help="Optional common as-of date in YYYY-MM-DD format.")
    parser.add_argument("--force-reference-sync", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        result = refresh_sector_rotation_v3_snapshot(
            _parse_date(args.trade_date),
            force_reference_sync=args.force_reference_sync,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
