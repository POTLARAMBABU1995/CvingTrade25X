# CVING_MCP security boundary

HTTP is restricted to 127.0.0.1:1729/mcp. Anonymous HTTP, including the old public
no-auth testing override, is rejected. Bearer and existing OAuth modes remain;
stdio remains a local transport. The original sixteen tool names and parameters
are unchanged. No arbitrary SQL tool or live-trading capability is added.

Controls: constant-time existing bearer verification, explicit Origin policy,
validated Host, no forwarded-host Origin bypass, safe errors, no-store/nosniff,
server-generated request IDs, 60 requests/minute per token plus transport peer
by default, and at most 2048 stored rate identities. Since Cloudflare connects
from loopback, the peer budget is a conservative aggregate ceiling across remote
clients. Increase CVING_MCP_RATE_LIMIT_PER_MINUTE only after capacity review.
Do not use wildcard CORS. Explicit browser origins can be configured through
CVING_MCP_ALLOWED_ORIGINS. /docs, /redoc, /openapi.json, /admin and /debug are denied.

CVING_MCP_MAX_CONCURRENT_REQUESTS bounds HTTP and executing tool workers. Worker
slots remain held after request cancellation until the synchronous work exits.
HTTP deadlines default to 45 seconds; tool deadlines to 30 seconds; Oracle calls
to 15 seconds, pool acquisition to 5 seconds. Python cannot forcibly cancel a
running synchronous operation; driver timeouts and retained worker slots bound
that residual work. The MCP-only pool is bounded by DB_POOL_MIN/MAX (0/6 default),
and legacy module aliases share the same pool in the CLI process.

The existing pool is wrapped only when launched by the MCP CLI. Each checkout
starts SET TRANSACTION READ ONLY and rolls back on release. Cursor operations
lex SQL comments/literals, reject DML/DDL, PL/SQL, multiple statements, database
links, sequences and DBMS_/UTL_ packages. Direct connection fallback is disabled
in MCP mode. These checks are defense in depth, not a full SQL parser or substitute
for Oracle grants. Shared predefined service SQL remains the only source of SQL.

CVING_MCP_MAX_ROWS defaults to 5000 fetched rows per query; exceeding it fails
rather than returning a misleading partial analysis. Existing per-tool result
limits remain unchanged. A cold price-action full-universe calculation can
exceed this limit. Populate its existing application snapshot through the normal
application workflow before requesting scans; MCP reports RESOURCE_LIMIT safely.
No new default-rows parameter changes existing tool signatures.

## Least privilege and secrets
Live inspection found that the current Oracle account is not least-privilege.
No grants were changed. database/create_mcp_readonly_user.sql is deliberately
non-executing (EXIT before DDL) and needs DBA review of schema and dependencies.
Use its paired validation script; rollback guidance is under database/rollback.
Set optional CVING_MCP_ORACLE_USER/PASSWORD only after the account is provisioned.
Oracle PUBLIC grants and callable functions must also be reviewed by the DBA.

.env, runtime/secrets, runtime/cloudflare, PEM/KEY/token files and diagnostic
outputs are ignored by Git. Restrict .env, named-tunnel config/credentials and the
project used by elevated tasks to the intended Windows user, Administrators and
SYSTEM using Windows ACLs. Do not put real credentials in examples or logs.
Ignore rules do not remove secrets already tracked in an enclosing repository;
Git status was unavailable in the restricted validation session.

Built-in OAuth stores clients/tokens in memory; clients may need to reconnect and
reauthorize after restart. Stable DNS does not make these sessions persistent.
For enterprise multi-user identity, use the already supported external OAuth IdP.
