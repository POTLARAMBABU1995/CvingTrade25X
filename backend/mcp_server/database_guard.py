"""MCP-process-only guard for the existing Oracle pool; never a remote SQL tool."""
from __future__ import annotations

import os
import re


class McpQueryLimitError(ValueError):
  pass


def validate_read_only_sql(sql: str) -> None:
  # Lex strings/comments before examining tokens: forbidden words inside literals
  # are data, while malformed quotes/comments and chained statements fail closed.
  tokens: list[str] = []
  i = 0
  while i < len(sql):
    if sql[i].isspace():
      i += 1
    elif sql.startswith("--", i):
      end = sql.find("\n", i + 2)
      i = len(sql) if end < 0 else end + 1
    elif sql.startswith("/*", i):
      end = sql.find("*/", i + 2)
      if end < 0:
        raise ValueError("Unterminated SQL comment")
      i = end + 2
    elif sql[i] in "'\"":
      quote = sql[i]
      i += 1
      while i < len(sql):
        if sql[i] == quote:
          i += 1
          if i < len(sql) and sql[i] == quote:
            i += 1
            continue
          break
        i += 1
      else:
        raise ValueError("Unterminated SQL literal")
      if quote == '"':
        raise ValueError("Quoted SQL identifiers are not enabled for MCP")
    elif sql[i] in ";@":
      raise ValueError("SQL chaining and database links are not allowed")
    else:
      match = re.match(r"[A-Za-z_][A-Za-z0-9_$#]*", sql[i:])
      if match:
        tokens.append(match.group().upper())
        i += len(match.group())
      else:
        i += 1
  forbidden = {
    "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE",
    "MERGE", "GRANT", "REVOKE", "BEGIN", "DECLARE", "EXECUTE", "CALL",
    "COMMIT", "ROLLBACK", "SAVEPOINT", "LOCK", "INTO", "PROCEDURE",
    "FUNCTION", "JAVA", "NEXTVAL", "SHUTDOWN", "AUTONOMOUS_TRANSACTION",
  }
  if not tokens or tokens[0] not in {"SELECT", "WITH"} or "SELECT" not in tokens:
    raise ValueError("Only read-only SELECT statements are permitted")
  if any(t in forbidden or t.startswith(("DBMS_", "UTL_")) for t in tokens):
    raise ValueError("SQL operation is not permitted by MCP read policy")


class ReadOnlyCursor:
  def __init__(self, cursor, max_rows: int):
    self._cursor = cursor
    if not 1 <= max_rows <= 50000:
      raise ValueError("MCP row limit must be between 1 and 50000")
    self._max_rows = max_rows
    self._rows = 0

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self._cursor.close()

  def __getattr__(self, name):
    if name in {"description", "rowcount", "arraysize", "fetchvars"}:
      return getattr(self._cursor, name)
    raise AttributeError(name)

  def execute(self, sql, *args, **kwargs):
    validate_read_only_sql(sql)
    self._rows = 0
    self._cursor.execute(sql, *args, **kwargs)
    return self

  def _count(self, rows):
    self._rows += len(rows)
    if self._rows > self._max_rows:
      raise McpQueryLimitError("MCP query row limit exceeded; narrow the request")
    return rows

  def fetchone(self):
    row = self._cursor.fetchone()
    if row is not None:
      self._count([row])
    return row

  def fetchmany(self, size=None):
    size = min(size or self._cursor.arraysize, self._max_rows - self._rows + 1)
    return self._count(self._cursor.fetchmany(size))

  def fetchall(self):
    return self._count(self._cursor.fetchmany(self._max_rows - self._rows + 1))

  def __iter__(self):
    while True:
      row = self.fetchone()
      if row is None:
        return
      yield row


class ReadOnlyConnection:
  def __init__(self, connection, timeout_ms, max_rows):
    self._connection = connection
    self._max_rows = max_rows
    connection.call_timeout = timeout_ms
    connection.rollback()
    with connection.cursor() as cursor:
      cursor.execute("SET TRANSACTION READ ONLY")

  def __enter__(self):
    return self

  def __exit__(self, *args):
    self.close()

  def close(self):
    try:
      self._connection.rollback()
    finally:
      self._connection.close()

  @property
  def version(self):
    return self._connection.version

  def cursor(self):
    return ReadOnlyCursor(self._connection.cursor(), self._max_rows)


class ReadOnlyPool:
  def __init__(self, pool, timeout_ms, max_rows):
    self._pool = pool
    self._timeout_ms = timeout_ms
    self._max_rows = max_rows

  def acquire(self):
    connection = self._pool.acquire()
    try:
      return ReadOnlyConnection(connection, self._timeout_ms, self._max_rows)
    except BaseException:
      connection.close()
      raise

  def close(self, **kwargs):
    self._pool.close(**kwargs)


def pool_options(driver) -> dict:
  minimum = int(os.getenv("CVING_MCP_DB_POOL_MIN", "0"))
  maximum = int(os.getenv("CVING_MCP_DB_POOL_MAX", "6"))
  if not 0 <= minimum <= maximum <= 32 or maximum < 1:
    raise ValueError("MCP pool requires 0 <= min <= max <= 32 and max >= 1")
  return dict(min=minimum, max=maximum, getmode=driver.POOL_GETMODE_TIMEDWAIT,
              wait_timeout=5000, tcp_connect_timeout=5)
