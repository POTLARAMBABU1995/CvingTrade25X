# Versioning And Backup Standard

## Versioning

Every change must append a `CHANGELOG.md` entry:

```text
## vN - YYYY-MM-DD HH:mm:ss IST
```

Include summary, changed files, before logic, after logic, validation, security review, and rollback notes.

## Backup Before Change

Before editing an existing file:

```powershell
python scripts\backup_before_change.py <file1> <file2> --version vN --reason "reason"
```

Backups are stored under:

```text
runtime/backups/<timestamp>_<version>/
```

Each backup includes `manifest.json` with source path, backup path, timestamp, changed_by, reason, version, and SHA-256 before hash.

Newly created files do not require backup, but they must be listed in `CHANGELOG.md`.

## Lifecycle

Dev:
- Feature branch.
- Local backup.
- Unit tests.
- Lint/typecheck where available.
- Local enterprise validation.

QA:
- Merge candidate.
- Integration tests.
- API duplicate scan.
- Oracle validation scripts for data changes.

UAT:
- Business testing.
- Production-like masked data.
- Release notes.

Pre-Prod:
- Deployment rehearsal.
- Rollback validation.
- Performance sanity testing.
- Production-like config.

Prod:
- Tagged release.
- Approved deployment.
- No manual file changes.
- No manual DB changes.
- Post-deployment validation.
- Monitoring and rollback plan.

## Rollback

Preferred:

```powershell
git restore <file>
```

Backup restore:

```powershell
Copy-Item runtime\backups\<folder>\<file> <file> -Force
```

DB rollback:
- Use paired scripts in `database/rollback`.
- Validate with paired scripts in `database/validation`.
- Do not execute destructive DB rollback without explicit approval.
