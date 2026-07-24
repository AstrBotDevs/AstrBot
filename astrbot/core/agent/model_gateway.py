"""Bounded model invocation contracts for the Agent runtime.

Provider implementations remain AstrBot-compatible. This module supplies a
small, provider-independent result/error vocabulary for supervisors and
observability without storing hidden reasoning content.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from astrbot.core.exceptions import EmptyModelOutputError


class ModelErrorCode(StrEnum):
    """Stable model failure categories exposed to the run supervisor."""

    TIMEOUT = "MODEL_TIMEOUT"
    RATE_LIMITED = "MODEL_RATE_LIMITED"
    AUTH_FAILED = "MODEL_AUTH_FAILED"
    INVALID_MODEL = "MODEL_INVALID_MODEL"
    EMPTY_OUTPUT = "MODEL_EMPTY_OUTPUT"
    UNAVAILABLE = "MODEL_PROVIDER_UNAVAILABLE"
    NETWORK = "MODEL_NETWORK_ERROR"
    CANCELLED = "MODEL_CANCELLED"


@dataclass(slots=True)
class ModelOutcome:
    """Normalized non-streaming model result."""

    status: str
    response: Any | None = None
    error_code: ModelErrorCode | None = None
    diagnostics: str = ""
    provider_id: str = ""
    elapsed_ms: int = 0


@dataclass(slots=True)
class StreamEvent:
    """Provider-independent stream lifecycle event."""

    kind: str
    payload: Any | None = None
    provider_id: str = ""
    error_code: ModelErrorCode | None = None


class ModelGateway:
    """Execute one provider request under a bounded timeout.

    The gateway intentionally does not retry authentication, quota, or model
    errors. A caller may invoke a separately approved fallback provider once.
    """

    @staticmethod
    def _diagnostic_text(error: Exception) -> str:
        """Build a bounded, non-secret description of a provider failure.

        Args:
            error: Provider exception raised by the model adapter.

        Returns:
            A short diagnostic string containing status/code and provider text.
        """

        parts: list[str] = []
        code = getattr(error, "code", None)
        status = getattr(error, "status", None)
        message = getattr(error, "message", None)
        response_json = getattr(error, "response_json", None)
        if code is not None:
            parts.append(f"code={code}")
        if status is not None and status != code:
            parts.append(f"status={status}")
        if message:
            parts.append(str(message))
        if response_json and not message:
            parts.append(str(response_json))
        if not parts:
            parts.append(str(error))
        # Provider error payloads occasionally echo request metadata. Keep the
        # audit message small and remove common credential-bearing fields.
        detail = " ".join(parts)
        for marker in ("api_key", "apikey", "access_token", "authorization"):
            if marker in detail.lower():
                detail = detail[: detail.lower().find(marker)] + marker + "=<redacted>"
                break
        return detail[:500]

    @staticmethod
    def _classify_error(error: Exception) -> ModelErrorCode:
        """Map provider error text to a stable, non-sensitive error category."""

        detail = str(error).lower()
        if any(
            marker in detail
            for marker in ("429", "rate limit", "resource_exhausted", "quota")
        ):
            return ModelErrorCode.RATE_LIMITED
        if any(
            marker in detail
            for marker in ("401", "403", "unauthorized", "forbidden", "api key")
        ):
            return ModelErrorCode.AUTH_FAILED
        if any(
            marker in detail
            for marker in ("model not found", "invalid model", "unknown model")
        ):
            return ModelErrorCode.INVALID_MODEL
        if any(
            marker in detail
            for marker in (
                "connection",
                "network",
                "dns",
                "connect timeout",
                "disconnected",
                "connection reset",
                "connection aborted",
            )
        ):
            return ModelErrorCode.NETWORK
        return ModelErrorCode.UNAVAILABLE

    @staticmethod
    async def complete(
        request: Callable[[], Awaitable[Any]],
        *,
        timeout: float,
        provider_id: str = "",
    ) -> ModelOutcome:
        """Run a model request and normalize timeout/cancellation failures.

        Args:
            request: Zero-argument coroutine factory.
            timeout: Hard request deadline in seconds.
            provider_id: Provider identifier for diagnostics.

        Returns:
            A bounded :class:`ModelOutcome`.
        """

        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            response = await asyncio.wait_for(request(), timeout=max(0.1, timeout))
        except asyncio.TimeoutError:
            return ModelOutcome(
                status="failed",
                error_code=ModelErrorCode.TIMEOUT,
                diagnostics="model request exceeded its deadline",
                provider_id=provider_id,
                elapsed_ms=int((loop.time() - started) * 1000),
            )
        except asyncio.CancelledError:
            raise
        except EmptyModelOutputError:
            # The runner owns its single bounded empty-output retry/fallback
            # policy; preserve this typed signal instead of hiding it here.
            raise
        except Exception as exc:  # noqa: BLE001
            error_code = ModelGateway._classify_error(exc)
            return ModelOutcome(
                status="failed",
                error_code=error_code,
                diagnostics=ModelGateway._diagnostic_text(exc),
                provider_id=provider_id,
                elapsed_ms=int((loop.time() - started) * 1000),
            )
        return ModelOutcome(
            status="success" if response is not None else "empty",
            response=response,
            error_code=None if response is not None else ModelErrorCode.EMPTY_OUTPUT,
            provider_id=provider_id,
            elapsed_ms=int((loop.time() - started) * 1000),
        )

    @staticmethod
    async def stream(
        request: Callable[[], AsyncIterator[Any]],
        *,
        timeout: float,
        provider_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Wrap a provider stream with START/DELTA/END/ERROR semantics."""

        yield StreamEvent(kind="START", provider_id=provider_id)
        iterator = request()
        try:
            async with asyncio.timeout(max(0.1, timeout)):
                async for item in iterator:
                    yield StreamEvent(
                        kind="DELTA", payload=item, provider_id=provider_id
                    )
            yield StreamEvent(kind="END", provider_id=provider_id)
        except asyncio.TimeoutError:
            yield StreamEvent(
                kind="ERROR",
                provider_id=provider_id,
                error_code=ModelErrorCode.TIMEOUT,
            )
        except asyncio.CancelledError:
            yield StreamEvent(
                kind="CANCEL",
                provider_id=provider_id,
                error_code=ModelErrorCode.CANCELLED,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            yield StreamEvent(
                kind="ERROR",
                provider_id=provider_id,
                error_code=ModelGateway._classify_error(exc),
            )
