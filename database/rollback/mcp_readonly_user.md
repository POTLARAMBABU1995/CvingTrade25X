# MCP account rollback
No database change is applied by the application installer. To undo a reviewed
account rollout, stop MCP and restore the prior ignored MCP credential configuration
from your secure backup, then restart and validate. A DBA must explicitly approve
any account lock, revocation or removal; no destructive rollback SQL is automated.
