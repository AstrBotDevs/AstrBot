from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiError(Exception):
    message: str
    status_code: int = 400
    data: Any = None


def ok(data: Any = None, message: str | None = None) -> dict[str, Any]:
    return {"status": "ok", "message": message, "data": {} if data is None else data}


def error(message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if data is not None:
        payload["data"] = data
    return payload
