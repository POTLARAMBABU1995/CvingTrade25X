from __future__ import annotations

import json
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


EXPECTED_TOOLS = {
  "health_check",
  "readiness_check",
  "list_symbols",
  "get_symbol_info",
  "get_latest_price",
  "get_ohlcv",
  "get_swing_points",
  "get_market_structure",
  "get_support_resistance",
  "get_price_zones",
  "get_breakout_status",
  "get_momentum",
  "analyze_symbol",
  "analyze_multi_timeframe",
  "explain_level",
  "scan_price_action",
}
_SECRET_MARKERS = (
  "password=",
  "oracle://",
  ":1521/",
  "oracle_user",
  "oracle_password",
  "authorization: bearer",
  "oauth_client_secret",
)


def _tls_report(host: str, port: int) -> dict[str, object]:
  context = ssl.create_default_context()
  with socket.create_connection((host, port), timeout=10) as raw:
    with context.wrap_socket(raw, server_hostname=host) as secured:
      certificate = secured.getpeercert()
      expires = datetime.strptime(certificate["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
      return {
        "status": "PASS",
        "expires_at": expires.isoformat(),
        "days_remaining": (expires - datetime.now(timezone.utc)).days,
        "tls_version": secured.version(),
      }


def _result_payload(result: Any) -> object:
  if result.structured_content is not None:
    return result.structured_content
  return [getattr(item, "text", str(item)) for item in result.content]


def _safe_error(exc: BaseException, token: str) -> str:
  message = f"{type(exc).__name__}: {exc}"
  if token:
    message = message.replace(token, "[REDACTED]")
  return message[:500]


def _has_secret_leak(payload: object, token: str) -> bool:
  serialized = json.dumps(payload, default=str).lower()
  if token and token.lower() in serialized:
    return True
  return any(marker in serialized for marker in _SECRET_MARKERS)


async def validate_endpoint(
  *,
  url: str,
  auth_mode: str,
  token_env: str,
  symbol: str | None,
  run_analysis: bool,
  remote: bool,
  check_local_security: bool = False,
) -> tuple[int, dict[str, object]]:
  parsed = urlparse(url)
  if remote and (parsed.scheme != "https" or not parsed.hostname):
    return 1, {"status": "FAIL", "error_code": "REMOTE_MCP_UNREACHABLE", "error": "Remote URL must use HTTPS"}
  if not remote and (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}):
    return 1, {"status": "FAIL", "error_code": "LOCAL_MCP_UNAVAILABLE", "error": "Local URL must use loopback HTTP"}
  token = os.getenv(token_env, "").strip()
  if auth_mode in {"bearer", "oauth", "oauth-server"} and not token:
    return 1, {
      "status": "FAIL",
      "error_code": "REMOTE_MCP_AUTH_FAILED" if remote else "LOCAL_MCP_UNHEALTHY",
      "error": f"{token_env} is required for {auth_mode} validation",
    }

  report: dict[str, object] = {
    "url": url,
    "authentication": auth_mode,
    "checks": {},
  }
  checks: dict[str, object] = report["checks"]  # type: ignore[assignment]
  if remote:
    try:
      addresses = sorted({item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)})
      checks["https"] = "PASS"
      checks["dns"] = {"status": "PASS", "addresses": addresses}
      checks["tls"] = _tls_report(parsed.hostname, parsed.port or 443)
      checks["quick_tunnel"] = "PASS" if parsed.hostname.endswith(".trycloudflare.com") else "NOT APPLICABLE"
    except (OSError, ValueError, ssl.SSLError) as exc:
      checks["https"] = "FAIL"
      checks["tls"] = {"status": "FAIL", "error": _safe_error(exc, token)}

  headers = {"Authorization": f"Bearer {token}"} if token else {}
  observed_payloads: list[object] = []
  try:
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=False) as http_client:
      started = time.perf_counter()
      async with Client(streamable_http_client(url, http_client=http_client)) as client:
        checks["initialize"] = "PASS"
        checks["protocol_version"] = str(client.protocol_version)
        listed = await client.list_tools()
        names = sorted(tool.name for tool in listed.tools)
        missing = sorted(EXPECTED_TOOLS - set(names))
        checks["tools_list"] = {"status": "PASS" if not missing else "FAIL", "tools": names, "missing": missing}
        health = await client.call_tool("health_check", {})
        health_payload = _result_payload(health)
        observed_payloads.append(health_payload)
        checks["health"] = {"status": "PASS" if not health.is_error else "FAIL", "result": health_payload}
        if symbol:
          sample = await client.call_tool("get_latest_price", {"symbol": symbol})
          sample_name = "get_latest_price"
        else:
          sample = await client.call_tool("list_symbols", {"limit": 1})
          sample_name = "list_symbols"
        sample_payload = _result_payload(sample)
        observed_payloads.append(sample_payload)
        checks["sample_tool"] = {
          "status": "PASS" if not sample.is_error else "FAIL",
          "tool": sample_name,
          "result": sample_payload,
        }
        if run_analysis and symbol:
          analysis = await client.call_tool("analyze_symbol", {"symbol": symbol})
          analysis_payload = _result_payload(analysis)
          observed_payloads.append(analysis_payload)
          checks["analyze_symbol"] = {
            "status": "PASS" if not analysis.is_error else "FAIL",
            "result": analysis_payload,
          }
        checks["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
  except Exception as exc:  # MCP/httpx expose several transport-specific exception classes.
    checks.setdefault("initialize", "FAIL")
    checks["mcp_error"] = _safe_error(exc, token)

  if auth_mode in {"bearer", "oauth", "oauth-server"}:
    try:
      async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as anonymous:
        missing_response = await anonymous.post(
          url,
          json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        invalid_response = await anonymous.post(
          url,
          headers={"Authorization": "Bearer invalid-cving-token"},
          json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
      checks["auth"] = {
        "status": "PASS" if missing_response.status_code == 401 and invalid_response.status_code == 401 else "FAIL",
        "missing_token_status": missing_response.status_code,
        "invalid_token_status": invalid_response.status_code,
      }
      observed_payloads.extend((missing_response.text[:1000], invalid_response.text[:1000]))
    except Exception as exc:
      checks["auth"] = {"status": "FAIL", "error": _safe_error(exc, token)}
  else:
    checks["auth"] = {"status": "PASS", "mode": "none"}

  if check_local_security:
    try:
      async with httpx.AsyncClient(timeout=10.0) as raw:
        invalid_host = await raw.post(url, headers={"Host": "attacker.invalid"}, json={})
        invalid_origin = await raw.post(url, headers={"Origin": "https://attacker.invalid"}, json={})
      checks["host_origin"] = {
        "status": "PASS" if invalid_host.status_code in {403, 421} and invalid_origin.status_code == 403 else "FAIL",
        "invalid_host_status": invalid_host.status_code,
        "invalid_origin_status": invalid_origin.status_code,
      }
    except Exception as exc:
      checks["host_origin"] = {"status": "FAIL", "error": _safe_error(exc, token)}

  response_bytes = len(json.dumps(observed_payloads, default=str).encode("utf-8"))
  max_response_bytes = int(os.getenv("CVING_MCP_MAX_RESPONSE_BYTES", "1048576"))
  checks["response_limit"] = {
    "status": "PASS" if response_bytes <= max_response_bytes else "FAIL",
    "observed_bytes": response_bytes,
    "configured_max_bytes": max_response_bytes,
  }
  checks["secret_leak"] = "FAIL" if _has_secret_leak(observed_payloads, token) else "PASS"

  required = ["initialize", "tools_list", "health", "sample_tool", "auth", "response_limit"]
  if remote:
    required.extend(["https", "tls"])
  if check_local_security:
    required.append("host_origin")

  def passed(name: str) -> bool:
    value = checks.get(name)
    return value == "PASS" or (isinstance(value, dict) and value.get("status") == "PASS")

  success = all(passed(name) for name in required) and checks.get("secret_leak") == "PASS"
  report["status"] = "PASS" if success else "FAIL"
  if remote:
    report["summary"] = {
      "HTTPS": checks.get("https", "FAIL"),
      "TLS": checks.get("tls", {"status": "FAIL"}),
      "MCP INITIALIZE": checks.get("initialize", "FAIL"),
      "TOOLS/LIST": checks.get("tools_list", {"status": "FAIL"}),
      "HEALTH": checks.get("health", {"status": "FAIL"}),
      "AUTH": checks.get("auth", {"status": "FAIL"}),
      "SAMPLE TOOL": checks.get("sample_tool", {"status": "FAIL"}),
      "QUICK TUNNEL": checks.get("quick_tunnel", "NOT APPLICABLE"),
    }
  return (0 if success else 1), report


def print_report(report: dict[str, object]) -> None:
  print(json.dumps(report, indent=2, default=str))
