from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from backend.mcp_server.config import McpSettings
from backend.mcp_server.database_guard import (
  validate_read_only_sql,
  ReadOnlyCursor,
  ReadOnlyPool,
  pool_options,
)
from backend.mcp_server.observability import SafeJsonFormatter
from backend.mcp_server.security import McpHttpSecurityMiddleware
from backend.mcp_server.server import build_server
from backend.mcp_server.service import McpPriceActionService


def settings(**kw):
  return replace(
    McpSettings.from_env(),
    auth_mode="bearer",
    bearer_token="a" * 32,
    host="127.0.0.1",
    port=1729,
    path="/mcp",
    profile="local-http",
    **kw,
  )


@pytest.mark.parametrize(
  "sql",
  [
    "DELETE FROM t",
    "DROP TABLE t",
    "UPDATE t SET x=1",
    "INSERT INTO t VALUES(1)",
    "SELECT 1 FROM dual; SELECT 2 FROM dual",
    "BEGIN NULL; END;",
    "WITH FUNCTION f RETURN NUMBER IS BEGIN RETURN 1; END; SELECT f FROM dual",
    "SELECT UTL_HTTP.REQUEST(:url) FROM dual",
    "SELECT DBMS_SQL.OPEN_CURSOR FROM dual",
    "SELECT seq.NEXTVAL FROM dual",
    "SELECT * FROM t FOR UPDATE",
    "SELECT * FROM t@remote",
    "SELECT 1 FROM dual /* unfinished",
    'SELECT "UTL_HTTP"."REQUEST"(:url) FROM dual',
  ],
)
def test_reject_write_and_side_effect_sql(sql):
  with pytest.raises(ValueError):
    validate_read_only_sql(sql)


@pytest.mark.parametrize(
  "sql",
  [
    "SELECT 'DELETE; DROP' FROM dual",
    "-- comment\n SELECT 1 FROM dual",
    "WITH x AS (SELECT 1 n FROM dual) SELECT n FROM x",
    "SELECT symbol FROM stocks WHERE symbol=:symbol",
    "SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual",
  ],
)
def test_allow_existing_selects(sql):
  validate_read_only_sql(sql)


def test_row_limit_is_failure_not_partial_success():
  cursor = SimpleNamespace(fetchmany=lambda size: list(range(size)))
  with pytest.raises(ValueError):
    ReadOnlyCursor(cursor, 2).fetchall()


def test_pool_limit_configuration(monkeypatch):
  monkeypatch.setenv("CVING_MCP_DB_POOL_MIN", "0")
  monkeypatch.setenv("CVING_MCP_DB_POOL_MAX", "3")
  options = pool_options(SimpleNamespace(POOL_GETMODE_TIMEDWAIT=1))
  assert options["max"] == 3 and options["wait_timeout"] == 5000
  monkeypatch.setenv("CVING_MCP_DB_POOL_MIN", "4")
  with pytest.raises(ValueError):
    pool_options(SimpleNamespace(POOL_GETMODE_TIMEDWAIT=1))


def test_readonly_pool_rolls_back_and_closes():
  calls = []

  class Cursor:
    def __enter__(self):
      return self

    def __exit__(self, *args):
      pass

    def execute(self, sql):
      calls.append(sql)

  conn = SimpleNamespace(
    rollback=lambda: calls.append("rollback"),
    close=lambda: calls.append("close"),
    cursor=Cursor,
  )
  pool = ReadOnlyPool(SimpleNamespace(acquire=lambda: conn), 1000, 500)
  with pool.acquire():
    pass
  assert conn.call_timeout == 1000
  assert calls == ["rollback", "SET TRANSACTION READ ONLY", "rollback", "close"]


def test_bind_cannot_be_overridden_for_remote():
  with pytest.raises(ValueError):
    replace(settings(), host="0.0.0.0", allow_remote=True).validate_http_security()


def test_audit_does_not_serialize_exception_or_arguments():
  record = logging.LogRecord(
    "test", logging.ERROR, "", 1, "Database password=%s", ("sensitive",), None
  )
  record.request_id = "trace1"
  result = SafeJsonFormatter().format(record)
  assert "sensitive" not in result and "password" not in result
  assert json.loads(result)["request_id"] == "trace1"


def test_timeout_returns_safe_504_and_releases_capacity():
  messages = []

  async def app(*args):
    await asyncio.sleep(0.2)

  async def send(message):
    messages.append(message)

  async def receive():
    return {"type": "http.request", "body": b""}

  middleware = McpHttpSecurityMiddleware(app, settings(request_timeout_seconds=0.01))
  asyncio.run(
    middleware(
      {
        "type": "http",
        "path": "/mcp",
        "method": "POST",
        "headers": [(b"host", b"127.0.0.1:1729")],
      },
      receive,
      send,
    )
  )
  assert messages[0]["status"] == 504 and middleware._active == 0


def test_rate_limit_and_bounded_identity_memory():
  middleware = McpHttpSecurityMiddleware(None, settings(rate_limit_per_minute=1))
  assert middleware._within_rate_limit("one")
  assert not middleware._within_rate_limit("one")
  for n in range(2200):
    middleware._within_rate_limit(str(n))
  assert len(middleware._request_times) == 2048


def test_forwarded_host_does_not_authorize_origin():
  middleware = McpHttpSecurityMiddleware(None, settings())
  assert not middleware._origin_allowed(
    "https://evil.example",
    {"host": "127.0.0.1:1729", "x-forwarded-host": "evil.example"},
  )


def test_health_redacted_and_auth_enforced(monkeypatch):
  service = McpPriceActionService(settings())
  monkeypatch.setattr(
    service,
    "readiness_check",
    lambda: {"ready": True, "database": {"name": "SECRET_DB", "version": "secret"}},
  )
  server = build_server(service)
  app = server.streamable_http_app(stateless_http=True, json_response=True)
  with TestClient(app, base_url="http://127.0.0.1:1729") as client:
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["database"] == "reachable"
    assert "SECRET_DB" not in health.text and "secret" not in health.text
    assert client.post("/mcp", json={}).status_code == 401
    assert (
      client.post(
        "/mcp", json={}, headers={"Authorization": "Bearer wrong"}
      ).status_code
      == 401
    )
    response = client.post(
      "/mcp",
      headers={
        "Authorization": "Bearer " + "a" * 32,
        "Accept": "application/json, text/event-stream",
      },
      json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
          "protocolVersion": "2025-03-26",
          "capabilities": {},
          "clientInfo": {"name": "test", "version": "1"},
        },
      },
    )
    assert response.status_code == 200


def test_existing_input_schemas_unchanged():
  from pathlib import Path
  from mcp import Client

  expected = json.loads(
    (Path(__file__).parent / "fixtures" / "mcp_tool_contract.json").read_text(
      encoding="utf-8"
    )
  )

  async def inspect():
    service = McpPriceActionService(replace(settings(), auth_mode="none"))
    async with Client(build_server(service)) as client:
      result = await client.list_tools()
      return {tool.name: tool.input_schema for tool in result.tools}

  assert asyncio.run(inspect()) == expected


def test_http_capacity_rejects_second_request():
  async def run():
    entered, release = asyncio.Event(), asyncio.Event()

    async def app(scope, receive, send):
      entered.set()
      await release.wait()

    async def receive():
      return {"type": "http.request", "body": b""}

    first, second = [], []

    async def send_first(message):
      first.append(message)

    async def send_second(message):
      second.append(message)

    middleware = McpHttpSecurityMiddleware(app, settings(max_concurrent_requests=1))
    scope = {"type": "http", "path": "/mcp", "headers": [(b"host", b"127.0.0.1:1729")]}
    task = asyncio.create_task(middleware(scope, receive, send_first))
    await entered.wait()
    await middleware(scope, receive, send_second)
    release.set()
    await task
    assert second[0]["status"] == 503
    assert middleware._active == 0

  asyncio.run(run())
