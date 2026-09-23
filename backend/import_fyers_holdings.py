from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services import fyers_holdings_service as fyers_holdings_svc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import FYERS holdings CSV into Oracle.")
    parser.add_argument("--file", required=True, help="Absolute or relative path to the FYERS holdings CSV file.")
    parser.add_argument(
        "--replace-missing",
        dest="replace_missing",
        action="store_true",
        default=True,
        help="Delete current holdings that are not present in the imported CSV.",
    )
    parser.add_argument(
        "--no-replace-missing",
        dest="replace_missing",
        action="store_false",
        help="Keep current holdings that are missing from the imported CSV.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    csv_path = Path(args.file).expanduser()
    try:
        payload = fyers_holdings_svc.import_holdings(
            {
                "filePath": str(csv_path),
                "replaceMissing": bool(args.replace_missing),
            }
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
