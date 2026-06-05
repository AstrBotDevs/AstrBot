from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any

DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS = 600.0


def _coerce_timeout(value: Any, default: float) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(timeout) or timeout < 0:
        return default
    return timeout


def resolve_sandbox_timeout(
    config: Mapping[str, Any],
    key: str,
    *,
    aliases: tuple[str, ...] = (),
    default: float,
) -> float:
    for candidate in (key, *aliases):
        if candidate in config:
            return _coerce_timeout(config.get(candidate), default)
    return default


def lease_is_active(
    controller_session_id: str | None,
    lease_expires_at: float | None,
    *,
    now: float | None = None,
) -> bool:
    if not controller_session_id:
        return False
    if lease_expires_at is None:
        return True
    current_time = time.time() if now is None else now
    return float(lease_expires_at) > current_time


def lease_expires_at_from_timeout(
    timeout: float | int | None,
    *,
    now: float | None = None,
) -> float | None:
    if timeout is None:
        return None
    current_time = time.time() if now is None else now
    normalized = _coerce_timeout(timeout, DEFAULT_SANDBOX_LEASE_TIMEOUT_SECONDS)
    if normalized <= 0:
        return None
    return current_time + normalized


def expires_at_from_timeout(
    timeout: float | int | None,
    *,
    now: float | None = None,
) -> float | None:
    return lease_expires_at_from_timeout(timeout, now=now)


def idle_cleanup_at_from_record(
    *,
    last_used_at: float | None,
    idle_timeout: float | int | None,
    now: float | None = None,
) -> float | None:
    if last_used_at is None:
        return None
    current_timeout = _coerce_timeout(idle_timeout, 0.0)
    if current_timeout <= 0:
        return None
    candidate = float(last_used_at) + current_timeout
    return candidate


def get_provider_sandbox_config(context: Any, session_id: str) -> dict[str, Any]:
    if context is None:
        return {}
    get_config = getattr(context, "get_config", None)
    if not callable(get_config):
        return {}
    config = get_config(umo=session_id)
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    return sandbox_cfg if isinstance(sandbox_cfg, dict) else {}
