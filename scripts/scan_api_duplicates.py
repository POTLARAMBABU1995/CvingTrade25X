from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = PROJECT_ROOT / "backend" / "routes"
APP_FILE = PROJECT_ROOT / "backend" / "app.py"
FRONTEND_DIRS = (
    PROJECT_ROOT / "frontend" / "src" / "api",
    PROJECT_ROOT / "frontend" / "src" / "services",
)
REPORT_PATH = PROJECT_ROOT / "runtime" / "reports" / "api-duplicate-report.json"

ROUTE_DECORATOR_RE = re.compile(
    r"@(?P<object>[\w.]+)\.(?P<kind>route|get|post|put|delete|patch)\((?P<args>.*)\)",
    re.IGNORECASE,
)
BLUEPRINT_RE = re.compile(r"Blueprint\([^)]*url_prefix\s*=\s*(?P<prefix>['\"][^'\"]+['\"])", re.DOTALL)
STRING_RE = re.compile(r"(['\"])(?P<value>/[^'\"]*)\1")
METHODS_RE = re.compile(r"methods\s*=\s*\[(?P<methods>[^\]]*)\]", re.IGNORECASE)
FRONTEND_ENDPOINT_RE = re.compile(r"['\"](?P<path>/api/[^'\"]+)['\"]")


@dataclass(frozen=True)
class RouteEntry:
    method: str
    path: str
    route_file: str
    function: str
    line: int
    frontend_callers: tuple[str, ...] = ()


def _project_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix()


def _join_paths(prefix: str, path: str) -> str:
    clean_prefix = str(prefix or "").strip()
    clean_path = str(path or "").strip()
    if not clean_prefix:
        return clean_path or "/"
    if not clean_path:
        return clean_prefix
    return f"{clean_prefix.rstrip('/')}/{clean_path.lstrip('/')}"


def _parse_methods(kind: str, args: str) -> list[str]:
    lowered = kind.lower()
    if lowered in {"get", "post", "put", "delete", "patch"}:
        return [lowered.upper()]
    match = METHODS_RE.search(args)
    if not match:
        return ["GET"]
    methods = re.findall(r"['\"]([A-Za-z]+)['\"]", match.group("methods"))
    return sorted({method.upper() for method in methods}) or ["GET"]


def _next_function_name(lines: list[str], start_index: int) -> str:
    for index in range(start_index + 1, min(start_index + 8, len(lines))):
        stripped = lines[index].strip()
        if stripped.startswith("def "):
            return stripped.split("def ", 1)[1].split("(", 1)[0].strip()
    return "<unknown>"


def _blueprint_prefix(text: str) -> str:
    match = BLUEPRINT_RE.search(text)
    if not match:
        return ""
    try:
        return ast.literal_eval(match.group("prefix"))
    except Exception:
        return ""


def _scan_frontend_callers() -> dict[str, set[str]]:
    callers: dict[str, set[str]] = defaultdict(set)
    for directory in FRONTEND_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for match in FRONTEND_ENDPOINT_RE.finditer(text):
                callers[match.group("path")].add(_project_path(path))
    return callers


def _scan_route_file(path: Path, frontend_callers: dict[str, set[str]]) -> list[RouteEntry]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    prefix = _blueprint_prefix(text)
    lines = text.splitlines()
    routes: list[RouteEntry] = []
    for index, line in enumerate(lines):
        match = ROUTE_DECORATOR_RE.search(line.strip())
        if not match:
            continue
        string_match = STRING_RE.search(match.group("args"))
        if not string_match:
            continue
        route_path = _join_paths(prefix, string_match.group("value"))
        methods = _parse_methods(match.group("kind"), match.group("args"))
        function = _next_function_name(lines, index)
        callers = tuple(sorted(frontend_callers.get(route_path, set())))
        for method in methods:
            routes.append(
                RouteEntry(
                    method=method,
                    path=route_path,
                    route_file=_project_path(path),
                    function=function,
                    line=index + 1,
                    frontend_callers=callers,
                )
            )
    return routes


def scan_routes() -> list[RouteEntry]:
    frontend_callers = _scan_frontend_callers()
    routes: list[RouteEntry] = []
    files: list[Path] = []
    if ROUTES_DIR.exists():
        files.extend(sorted(ROUTES_DIR.glob("*.py")))
    if APP_FILE.exists():
        files.append(APP_FILE)

    for path in files:
        routes.extend(_scan_route_file(path, frontend_callers))
    return routes


def _normalized_path(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", path.lower())


def find_exact_duplicates(routes: Iterable[RouteEntry]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[RouteEntry]] = defaultdict(list)
    for route in routes:
        grouped[(route.method, route.path)].append(route)
    duplicates: list[dict[str, object]] = []
    for (method, path), entries in sorted(grouped.items()):
        if len(entries) > 1:
            duplicates.append(
                {
                    "method": method,
                    "path": path,
                    "locations": [asdict(entry) for entry in entries],
                }
            )
    return duplicates


def find_similar_paths(routes: Iterable[RouteEntry]) -> list[dict[str, object]]:
    unique = sorted({route.path for route in routes})
    similar: list[dict[str, object]] = []
    for left_index, left in enumerate(unique):
        left_norm = _normalized_path(left)
        if len(left_norm) < 10:
            continue
        for right in unique[left_index + 1:]:
            right_norm = _normalized_path(right)
            if len(right_norm) < 10:
                continue
            ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
            if ratio >= 0.92 and left != right:
                similar.append({"left": left, "right": right, "similarity": round(ratio, 4)})
    return similar[:250]


def write_report(routes: list[RouteEntry]) -> dict[str, object]:
    exact_duplicates = find_exact_duplicates(routes)
    similar_paths = find_similar_paths(routes)
    report = {
        "status": "failed" if exact_duplicates else "passed",
        "route_count": len(routes),
        "exact_duplicate_count": len(exact_duplicates),
        "similar_path_count": len(similar_paths),
        "exact_duplicates": exact_duplicates,
        "similar_paths": similar_paths,
        "routes": [asdict(route) for route in routes],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def write_catalog(routes: list[RouteEntry], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# API Catalog",
        "",
        "Generated from `backend/routes` and frontend API usage. No new endpoint may be added without updating this catalog.",
        "",
        "| Method | Path | Route File | Handler | Frontend Caller | Auth Required | Request Parameters | Response Shape | Status | Duplicate Risk | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    duplicate_keys = {(item["method"], item["path"]) for item in find_exact_duplicates(routes)}
    for route in sorted(routes, key=lambda item: (item.path, item.method, item.route_file, item.line)):
        callers = ", ".join(route.frontend_callers) if route.frontend_callers else "Not found in scanned frontend services"
        auth_required = "Review route exemptions in `backend/app.py`"
        duplicate_risk = "Exact duplicate" if (route.method, route.path) in duplicate_keys else "None detected"
        lines.append(
            "| {method} | `{path}` | `{route_file}:{line}` | `{function}` | {callers} | {auth_required} | Inspect route/service | Inspect route/service | Active | {duplicate_risk} | Generated scanner entry |".format(
                method=route.method,
                path=route.path,
                route_file=route.route_file,
                line=route.line,
                function=route.function,
                callers=callers.replace("|", "/"),
                auth_required=auth_required,
                duplicate_risk=duplicate_risk,
            )
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Flask route files for duplicate API endpoints.")
    parser.add_argument("--write-catalog", help="Optional project-relative markdown catalog output path.")
    args = parser.parse_args()

    routes = scan_routes()
    report = write_report(routes)
    if args.write_catalog:
        write_catalog(routes, PROJECT_ROOT / args.write_catalog)

    print(
        "API duplicate scan: {status}; routes={routes}; exact_duplicates={duplicates}; similar_paths={similar}".format(
            status=report["status"],
            routes=report["route_count"],
            duplicates=report["exact_duplicate_count"],
            similar=report["similar_path_count"],
        )
    )
    print(f"Report: {_project_path(REPORT_PATH)}")
    if args.write_catalog:
        print(f"Catalog: {args.write_catalog}")
    return 1 if report["exact_duplicate_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
