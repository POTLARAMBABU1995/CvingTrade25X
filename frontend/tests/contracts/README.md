# API Contract Snapshots

This folder is reserved for page-level API response snapshots during migration.

## Rules

- Save snapshots before and after each page migration.
- Keep backend field names exactly as returned by the API.
- Add TypeScript wire DTOs that match the snapshot without renaming fields.
- Perform any normalization only in adapter functions.
- Do not delete the legacy snapshot until the React page is approved for cutover.

## Suggested layout

```text
tests/contracts/
  dashboard/
    movers.before.json
    movers.after.json
  market-cap/
    latest.before.json
    latest.after.json
```
