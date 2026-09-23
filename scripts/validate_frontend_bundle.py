"""Fail closed when a production React bundle is missing core Tailwind utilities."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SELECTORS = (
    ".flex{",
    ".grid{",
    ".h-4{",
    ".w-4{",
    ".h-8{",
    ".w-8{",
    ".inline-flex{",
    ".min-h-screen{",
)


def _stylesheet_paths(index_html: str, dist_dir: Path) -> list[Path]:
    hrefs = re.findall(
        r'<link\b[^>]*\brel=["\']stylesheet["\'][^>]*\bhref=["\']([^"\']+)["\']',
        index_html,
        flags=re.IGNORECASE,
    )
    if not hrefs:
        raise ValueError("frontend bundle index.html does not reference a stylesheet")

    resolved_dist = dist_dir.resolve()
    paths: list[Path] = []
    for href in hrefs:
        relative = href.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        candidate = (resolved_dist / relative).resolve()
        if resolved_dist not in candidate.parents:
            raise ValueError(f"stylesheet path escapes dist directory: {href}")
        paths.append(candidate)
    return paths


def validate_bundle(dist_dir: Path) -> list[Path]:
    index_path = dist_dir / "index.html"
    if not index_path.is_file():
        raise ValueError(f"frontend bundle index is missing: {index_path}")

    stylesheets = _stylesheet_paths(index_path.read_text(encoding="utf-8"), dist_dir)
    css_parts: list[str] = []
    for stylesheet in stylesheets:
        if not stylesheet.is_file():
            raise ValueError(f"referenced stylesheet is missing: {stylesheet}")
        css_parts.append(stylesheet.read_text(encoding="utf-8"))

    css = "\n".join(css_parts)
    missing = [selector for selector in REQUIRED_SELECTORS if selector not in css]
    if missing:
        raise ValueError(
            "production stylesheet is missing required Tailwind utilities: "
            + ", ".join(missing)
            + ". Refusing to publish a visually broken bundle."
        )
    return stylesheets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("frontend/dist"))
    args = parser.parse_args()
    try:
        stylesheets = validate_bundle(args.dist_dir)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"[frontend-bundle-guard] FAIL: {error}", file=sys.stderr)
        return 1

    total_bytes = sum(path.stat().st_size for path in stylesheets)
    print(
        "[frontend-bundle-guard] PASS: "
        f"{len(stylesheets)} stylesheet(s), {total_bytes} bytes, core Tailwind utilities present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
