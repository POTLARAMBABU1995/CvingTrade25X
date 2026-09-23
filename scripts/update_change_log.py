from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
IST = ZoneInfo("Asia/Kolkata")


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def append_changelog_entry(
    *,
    version: str,
    summary: str,
    files_changed: list[str],
    before_logic: str,
    after_logic: str,
    validation: str,
    security_review: str,
    rollback: str,
    timestamp: str | None = None,
) -> None:
    resolved_timestamp = timestamp or datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    if not CHANGELOG_PATH.exists():
        CHANGELOG_PATH.write_text("# Changelog\n\n", encoding="utf-8")

    files_block = "\n".join(f"- `{item}`" for item in files_changed) if files_changed else "- None"
    entry = f"""## {version} - {resolved_timestamp}

### Summary

{summary}

### Files Changed

{files_block}

### Before Logic

{before_logic}

### After Logic

{after_logic}

### Validation

{validation}

### Security Review

{security_review}

### Rollback

{rollback}

"""
    with CHANGELOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a versioned technical changelog entry.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--files-changed", default="", help="Semicolon-separated file list.")
    parser.add_argument("--before-logic", required=True)
    parser.add_argument("--after-logic", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--security-review", default="Security review not recorded.")
    parser.add_argument("--rollback", required=True)
    parser.add_argument("--timestamp", default="")
    args = parser.parse_args()

    append_changelog_entry(
        version=args.version,
        summary=args.summary,
        files_changed=_split_values(args.files_changed),
        before_logic=args.before_logic,
        after_logic=args.after_logic,
        validation=args.validation,
        security_review=args.security_review,
        rollback=args.rollback,
        timestamp=args.timestamp or None,
    )
    print(f"Updated {CHANGELOG_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
