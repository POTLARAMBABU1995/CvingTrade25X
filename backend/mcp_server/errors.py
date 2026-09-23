from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class McpServiceError(Exception):
  code: str
  message: str
  retryable: bool = False

  def __str__(self) -> str:
    return self.message

  def to_payload(self) -> dict[str, object]:
    return {
      "error": {
        "code": self.code,
        "message": self.message,
        "retryable": self.retryable,
      }
    }
