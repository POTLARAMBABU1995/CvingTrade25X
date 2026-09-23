# Strategy Auth Smoke Check

This workflow probes the React strategy routes and their protected strategy APIs with the same centralized session-token flow used by the app.

## What It Checks

- `GET /app/strategy/bhramhastra`
- `GET /api/bhramhastra?timeframe=<timeframe>`
- `GET /api/bhramhastra/last-ltc-date`
- `GET /app/strategy/bhramhaputra`
- `GET /api/bhramhaputra?tf=<timeframe>`
- `GET /api/bhramhaputra/last-ltc-date`

The script logs in through `POST /api/auth/login` unless you pass an existing session token. It then validates `GET /api/auth/session` and sends both `Authorization: Bearer <token>` and `X-Session-Token: <token>` on the protected probes.

## Rerun Command

From Windows PowerShell:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_SMOKE_IDENTIFIER = '<client-id-or-email-or-mobile>'
$env:CVING_SMOKE_PASSWORD = '<password>'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_strategy_auth.ps1 -BaseUrl http://127.0.0.1:5055
```

If you already have a valid session token:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_SESSION_TOKEN = '<session-token>'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_strategy_auth.ps1 -BaseUrl http://127.0.0.1:5055
```

Use `-Timeframe weekly`, `-Timeframe monthly`, or `-Timeframe yearly` to probe another timeframe. Use `-Refresh` only when you intentionally want to trigger the backend refresh path.

## Output Interpretation

- Any `401` means the probe did not reach the strategy business logic. Fix the session first.
- `Stale`, `Refreshing`, and `StaleReasons` come from the real strategy API payload and are the fields to use for stale-status debugging.
- `RequestId` maps the smoke-check row to backend logs.

The script logs out sessions it creates by default. Add `-KeepSession` if you want to keep the newly created session alive after the check.
