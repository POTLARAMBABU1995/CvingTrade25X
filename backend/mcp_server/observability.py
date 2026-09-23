"""Allowlisted JSON audit records with rotation and no raw exceptions."""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SafeJsonFormatter(logging.Formatter):
  def format(self, record):
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "level": record.levelname, "logger": record.name}
    payload["event"] = getattr(record, "event", record.msg if isinstance(record.msg, str)
                               and record.msg.startswith("mcp.") else "service_event")
    for key in ("request_id", "tool_name", "status", "duration_ms", "transport", "rows_returned"):
      value = getattr(record, key, None)
      if value is not None:
        payload[key] = str(value)[:160] if isinstance(value, str) else value
    if record.exc_info:
      payload["exception_type"] = record.exc_info[0].__name__
    return json.dumps(payload, ensure_ascii=True)


def configure_logging(level):
  directory = Path(__file__).resolve().parents[2] / "runtime" / "logs"
  directory.mkdir(parents=True, exist_ok=True)
  size = max(65536, min(int(os.getenv("CVING_MCP_LOG_MAX_BYTES", "10485760")), 104857600))
  copies = max(1, min(int(os.getenv("CVING_MCP_LOG_BACKUPS", "5")), 20))
  handler = RotatingFileHandler(directory / "mcp.log", maxBytes=size, backupCount=copies, encoding="utf-8")
  handler.setFormatter(SafeJsonFormatter())
  root = logging.getLogger()
  root.handlers.clear()
  root.addHandler(handler)
  root.setLevel(getattr(logging, level, logging.INFO))
