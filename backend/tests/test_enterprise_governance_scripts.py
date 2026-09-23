from __future__ import annotations

import json
from pathlib import Path

from scripts import backup_before_change, enterprise_validate, scan_api_duplicates


def test_backup_before_change_creates_manifest(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    project_root.mkdir()
    source = project_root / "README.md"
    source.write_text("before", encoding="utf-8")
    monkeypatch.setattr(backup_before_change, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(backup_before_change, "BACKUP_ROOT", project_root / "runtime" / "backups")

    result = backup_before_change.create_backup(
        files=["README.md"],
        version="v-test",
        reason="unit test",
        changed_by="pytest",
    )

    manifest_path = project_root / result["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "v-test"
    assert manifest["files"][0]["source"] == "README.md"
    assert (project_root / manifest["files"][0]["backup"]).read_text(encoding="utf-8") == "before"


def test_scan_api_duplicates_detects_exact_duplicate(tmp_path, monkeypatch):
    routes_dir = tmp_path / "backend" / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "sample.py").write_text(
        """from flask import Blueprint
bp = Blueprint("sample", __name__, url_prefix="/api/sample")

@bp.get("/items")
def first():
    return {}

@bp.route("/items", methods=["GET"])
def second():
    return {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(scan_api_duplicates, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scan_api_duplicates, "ROUTES_DIR", routes_dir)
    monkeypatch.setattr(scan_api_duplicates, "APP_FILE", tmp_path / "backend" / "app.py")
    monkeypatch.setattr(scan_api_duplicates, "FRONTEND_DIRS", ())
    monkeypatch.setattr(scan_api_duplicates, "REPORT_PATH", tmp_path / "runtime" / "reports" / "api-duplicate-report.json")

    routes = scan_api_duplicates.scan_routes()
    duplicates = scan_api_duplicates.find_exact_duplicates(routes)

    assert len(routes) == 2
    assert duplicates[0]["method"] == "GET"
    assert duplicates[0]["path"] == "/api/sample/items"


def test_enterprise_validate_detects_npm_scripts(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text('{"scripts":{"build":"vite build"}}', encoding="utf-8")

    assert enterprise_validate._npm_script_exists(package_json, "build") is True
    assert enterprise_validate._npm_script_exists(package_json, "lint") is False
