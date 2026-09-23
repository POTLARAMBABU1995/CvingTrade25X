# DevSecOps Standards

## Security Baseline

- No hardcoded passwords, tokens, cookies, API keys, Oracle credentials, or session values.
- No secrets in logs, screenshots, docs, changelog entries, or runtime reports.
- Use bind variables for Oracle SQL.
- Validate request payloads before using them.
- Protect authenticated routes through the centralized session flow in `backend/app.py`.
- Frontend calls must use `frontend/src/api/client.ts` so request IDs and auth headers remain consistent.

## Secret Review

Run:

```powershell
python scripts\enterprise_validate.py
```

The validation script writes potential findings to `runtime/reports/security-findings.json`. Findings are review items; do not delete or rotate secrets automatically without owner approval.

## SonarQube Standard

Use `sonar-project.properties` as the local configuration template.

Release gate:
- No blocker quality issues.
- No critical quality issues.
- Duplication must remain controlled.
- Coverage target is greater than or equal to 99 percent for critical changed modules.
- Legacy modules that cannot immediately reach 99 percent must document the gap and enforce the target on new/modified critical code.

## Checkmarx Standard

Checkmarx SAST is required before production release when available in the release pipeline.

Release gate:
- No high or critical security vulnerabilities.
- No untriaged SQL injection, authentication, authorization, XSS, secret exposure, insecure deserialization, or path traversal findings.
- Security scan failures block release until resolved or formally risk-accepted.

## Dependency Review

Use:

```powershell
pip-audit
```

Optional tools are skipped by `scripts/enterprise_validate.py` when not installed, but release candidates should install the development/security dependencies from `requirements.txt`.

## Logging Standard

Allowed:
- Request ID.
- Route and method.
- Status code and duration.
- Safe counts and symbols where business-approved.

Disallowed:
- Full tokens.
- Passwords or MPINs.
- Cookies.
- Raw authorization headers.
- Oracle passwords or DSNs with credentials.
- Aadhaar/PAN values or other sensitive identity data.
