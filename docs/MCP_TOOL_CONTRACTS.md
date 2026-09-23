# CvingTrade25X MCP Tool Contracts

The MCP is a read-only adapter. It does not add Flask endpoints, expose arbitrary SQL, or create a second market-data pipeline.

| MCP tool | Existing owner reused | MCP-only addition |
| --- | --- | --- |
| `health_check` | `backend.db_pool.pool` | Sanitized readiness envelope |
| `readiness_check` | `health_check` owner | Fail-closed deployment readiness and active profile |
| `list_symbols` | `marketdata_service.list_symbols` | Bound and sanitize output |
| `get_symbol_info` | `chart_service.fetch_ohlcv_payload` | Availability and DQ summary |
| `get_latest_price` | `chart_service.fetch_ohlcv_payload` | MCP response envelope |
| `get_ohlcv` | `/api/bars` owner: `chart_service.fetch_ohlcv_payload` | Limits and DQ metadata |
| `get_swing_points` | `technical_utils.detect_swing_pivots` | HH/HL/LH/LL labels |
| `get_market_structure` | Existing swing primitives | MCP evidence envelope |
| `get_support_resistance` | `technical_utils.calculate_support_resistance` | Zone/touch/rejection evidence |
| `get_price_zones` | Existing S/R owner | Demand/supply projection |
| `get_breakout_status` | `technical_utils.detect_resistance_breakout` | Breakdown and retest envelope |
| `get_momentum` | Existing OHLCV source | Pure price/volume composite |
| `analyze_symbol` | Existing chart and technical services | One-fetch composite response |
| `analyze_multi_timeframe` | Existing 1D plus existing weekly/monthly aggregation | Confluence/conflict summary |
| `explain_level` | Existing OHLCV, swing, and S/R owners | Evidence for a caller-supplied positive price level |
| `scan_price_action` | `price_action_service.fetch_price_action_page` and `/api/technicals/price-action` | MCP bounds and filters |

Every tool is annotated read-only and idempotent. The server has no `execute_sql`, mutation, brokerage, or order-placement tool.

Authorization is default-deny by scope: market lookup, analysis, scan, and admin health. `CVING_MCP_ALLOWED_TOOLS`, exchange policy, and optional symbol allow/deny lists can further reduce data egress without adding provider-specific tools.

## Stable data boundary for RAG and agents

Future RAG, AI-agent, or other reasoning clients should consume the structured tool outputs. Database values stay factual evidence and are marked by the `trust_boundary` field as data, never instructions. A future client may index evidence and reason codes, but must not receive Oracle credentials or unrestricted SQL access.

Schema evolution must be additive. Keep `meta`, `data_quality`, source provenance, evidence, and engine version in stored RAG documents so an answer can be reproduced.
