from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import nifty500_sync_service as sync_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize and deduplicate the FYERS NIFTY500 CSV.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    symbols = sync_service._read_symbols_from_path(path)
    canonical = sync_service._dedupe_symbols(symbols)
    before = path.read_text(encoding="utf-8-sig") if path.exists() else ""

    if args.dry_run:
        print(f"path={path}")
        print(f"input_rows={len(symbols)} canonical_rows={len(canonical)}")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.pre_canonical_{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    sync_service._write_existing_symbols(path, canonical)
    after = path.read_text(encoding="utf-8-sig")
    print(f"path={path}")
    print(f"backup={backup}")
    print(f"changed={int(before != after)} canonical_rows={len(canonical)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

