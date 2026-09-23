from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "runtime" / "reports" / "enterprise-validation-report.json"
SECURITY_FINDINGS_PATH = PROJECT_ROOT / "runtime" / "reports" / "security-findings.json"
MANDATORY_DOCS = [
    "AGENTS.md",
    "MEMORY.md",
    "README.md",
    "CHANGELOG.md",
    "docs/api-catalog.md",
]
EXCLUDED_SCAN_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "runtime/backups",
    "runtime/reports",
    "backend/cache",
}
SECRET_PATTERNS = [
    re.compile(r"\bpassword\s*=\s*['\"]?[^'\"\s#]+['\"]?", re.IGNORECASE),
    re.compile(r"\btoken\s*=\s*['\"]?[^'\"\s#]+['\"]?", re.IGNORECASE),
    re.compile(r"\bsecret\s*=\s*['\"]?[^'\"\s#]+['\"]?", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*=\s*['\"]?[^'\"\s#]+['\"]?", re.IGNORECASE),
    re.compile(r"authorization\s*[:=]\s*['\"]?[^'\"\s#]+['\"]?", re.IGNORECASE),
]


@dataclass
class CheckResult:
    name: str
    status: str
    command: str = ""
    exit_code: int | None = None
    details: str = ""
    required: bool = False


@dataclass
class ValidationReport:
    status: str = "passed"
    checks: list[CheckResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        if result.required and result.status == "failed":
            self.failures.append(result.name)
            self.status = "failed"


def _run(command: list[str], *, cwd: Path = PROJECT_ROOT, required: bool = False, name: str) -> CheckResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    except FileNotFoundError:
        return CheckResult(name=name, status="skipped", command=" ".join(command), details="Command not found.", required=required)
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=name,
            status="failed" if required else "skipped",
            command=" ".join(command),
            details=f"Timed out after {exc.timeout}s.",
            required=required,
        )
    stdout = completed.stdout.strip() if completed.stdout else ""
    stderr = completed.stderr.strip() if completed.stderr else ""
    output = "\n".join(part for part in [stdout, stderr] if part)
    return CheckResult(
        name=name,
        status="passed" if completed.returncode == 0 else "failed",
        command=" ".join(command),
        exit_code=completed.returncode,
        details=output[-4000:],
        required=required,
    )


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _npm_script_exists(package_json: Path, script_name: str) -> bool:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return False
    scripts = payload.get("scripts")
    return isinstance(scripts, dict) and script_name in scripts


def _path_excluded(path: Path) -> bool:
    relative = path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    parts = relative.split("/")
    if any(part in EXCLUDED_SCAN_DIRS for part in parts):
        return True
    return any(relative == item or relative.startswith(f"{item}/") for item in EXCLUDED_SCAN_DIRS)


def _secret_scan() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".sql", ".ps1", ".bat", ".cmd", ".json", ".env"}
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or _path_excluded(path) or path.suffix.lower() not in suffixes:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(stripped):
                    findings.append(
                        {
                            "file": path.relative_to(PROJECT_ROOT).as_posix(),
                            "line": line_number,
                            "pattern": pattern.pattern,
                            "snippet": pattern.sub("[REDACTED]", stripped)[:220],
                        }
                    )
                    break
    report = {
        "status": "review_required" if findings else "passed",
        "finding_count": len(findings),
        "findings": findings,
    }
    SECURITY_FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECURITY_FINDINGS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def validate_docs(report: ValidationReport) -> None:
    missing = [path for path in MANDATORY_DOCS if not (PROJECT_ROOT / path).exists()]
    report.add(
        CheckResult(
            name="mandatory-docs",
            status="failed" if missing else "passed",
            details="Missing: " + ", ".join(missing) if missing else "All mandatory docs exist.",
            required=True,
        )
    )


def validate_api(report: ValidationReport) -> None:
    report.add(_run([sys.executable, "scripts/scan_api_duplicates.py"], name="api-duplicate-scan", required=True))


def validate_backend(report: ValidationReport) -> None:
    tests_exist = (PROJECT_ROOT / "backend" / "tests").exists() or (PROJECT_ROOT / "tests").exists()
    if tests_exist:
        report.add(_run([sys.executable, "-m", "pytest", "backend/tests"], name="backend-pytest", required=True))
    else:
        report.add(CheckResult(name="backend-pytest", status="skipped", details="No backend tests found."))

    if _module_available("pytest_cov") or _module_available("pytest_cov.plugin"):
        report.add(_run([sys.executable, "-m", "pytest", "backend/tests", "--cov=backend", "--cov-report=term-missing"], name="backend-coverage", required=False))
    else:
        report.add(CheckResult(name="backend-coverage", status="skipped", details="pytest-cov is not installed."))

    if shutil.which("ruff"):
        report.add(_run(["ruff", "check", "backend", "scripts"], name="ruff", required=False))
    else:
        report.add(CheckResult(name="ruff", status="skipped", details="ruff is not installed."))

    if _module_available("bandit"):
        report.add(_run([sys.executable, "-m", "bandit", "-q", "-r", "backend", "scripts"], name="bandit", required=False))
    else:
        report.add(CheckResult(name="bandit", status="skipped", details="bandit is not installed."))

    if shutil.which("pip-audit"):
        report.add(_run(["pip-audit"], name="pip-audit", required=False))
    else:
        report.add(CheckResult(name="pip-audit", status="skipped", details="pip-audit is not installed."))


def validate_frontend(report: ValidationReport) -> None:
    frontend = PROJECT_ROOT / "frontend"
    package_json = frontend / "package.json"
    if not package_json.exists():
        report.add(CheckResult(name="frontend-package", status="skipped", details="frontend/package.json not found."))
        return

    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
    if _npm_script_exists(package_json, "lint"):
        report.add(_run([npm_cmd, "run", "lint"], cwd=frontend, name="frontend-lint", required=True))
    else:
        report.add(CheckResult(name="frontend-lint", status="skipped", details="No lint script in frontend/package.json."))
    if _npm_script_exists(package_json, "test"):
        report.add(_run([npm_cmd, "run", "test"], cwd=frontend, name="frontend-test", required=True))
    if _npm_script_exists(package_json, "build"):
        report.add(_run([npm_cmd, "run", "build"], cwd=frontend, name="frontend-build", required=True))


def validate_security(report: ValidationReport) -> None:
    gitignore = PROJECT_ROOT / ".gitignore"
    ignore_text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
    required_rules = [".env", ".env.*", "!.env.example"]
    missing_rules = [rule for rule in required_rules if rule not in ignore_text.splitlines()]
    report.add(
        CheckResult(
            name="sensitive-file-ignore-rules",
            status="failed" if missing_rules else "passed",
            details="Missing: " + ", ".join(missing_rules) if missing_rules else ".env rules are present.",
            required=True,
        )
    )
    findings = _secret_scan()
    report.add(
        CheckResult(
            name="secret-pattern-scan",
            status="passed",
            details=f"{findings['finding_count']} potential finding(s) written to runtime/reports/security-findings.json.",
            required=False,
        )
    )


def main() -> int:
    report = ValidationReport()
    validate_docs(report)
    validate_api(report)
    validate_backend(report)
    validate_frontend(report)
    validate_security(report)

    payload = {
        "status": report.status,
        "failures": report.failures,
        "checks": [result.__dict__ for result in report.checks],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
