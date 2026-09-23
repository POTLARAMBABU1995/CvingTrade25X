from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
IST = ZoneInfo("Asia/Kolkata")


def _relative_path(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve(strict=False))
    except ValueError as exc:
        raise ValueError(f"Path is outside project root: {path}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_folder(version: str, timestamp: datetime) -> Path:
    safe_version = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in version.strip()) or "v0"
    stamp = timestamp.strftime("%Y-%m-%d_%H%M%S")
    candidate = BACKUP_ROOT / f"{stamp}_{safe_version}"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        next_candidate = BACKUP_ROOT / f"{stamp}_{safe_version}_{suffix}"
        if not next_candidate.exists():
            return next_candidate
        suffix += 1


def create_backup(files: list[str], version: str, reason: str, changed_by: str) -> dict[str, object]:
    timestamp = datetime.now(IST)
    folder = _backup_folder(version, timestamp)
    folder.mkdir(parents=True, exist_ok=False)

    manifest_files: list[dict[str, str]] = []
    for raw_file in files:
        source = (PROJECT_ROOT / raw_file).resolve(strict=False)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Cannot back up missing file: {raw_file}")
        relative = _relative_path(source)
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append(
            {
                "source": relative.as_posix(),
                "backup": _relative_path(target).as_posix(),
                "sha256_before": _sha256(source),
            }
        )

    manifest = {
        "version": version,
        "timestamp": timestamp.isoformat(),
        "changed_by": changed_by,
        "reason": reason,
        "files": manifest_files,
    }
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        **manifest,
        "backup_folder": _relative_path(folder).as_posix(),
        "manifest": _relative_path(manifest_path).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create timestamped backups before repository edits.")
    parser.add_argument("files", nargs="+", help="Project-relative files to back up.")
    parser.add_argument("--version", default="v1", help="Change version label.")
    parser.add_argument("--reason", default="pre-change backup", help="Reason recorded in manifest.")
    parser.add_argument("--changed-by", default="codex-agent", help="Actor recorded in manifest.")
    args = parser.parse_args()

    result = create_backup(
        files=args.files,
        version=args.version,
        reason=args.reason,
        changed_by=args.changed_by,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
