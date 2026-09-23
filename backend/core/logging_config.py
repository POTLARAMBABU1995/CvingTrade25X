from __future__ import annotations

import logging
from typing import Any


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_enterprise_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
    logging.getLogger().addFilter(RequestIdFilter())



class RequestIdAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("request_id", self.extra.get("request_id", "-"))
        return msg, kwargs


def get_request_logger(name: str, request_id: str | None = None) -> RequestIdAdapter:
    return RequestIdAdapter(logging.getLogger(name), {"request_id": request_id or "-"})
