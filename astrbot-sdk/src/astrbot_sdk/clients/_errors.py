from __future__ import annotations

from ..errors import AstrBotError


def client_call_label(
    client_name: str,
    method_name: str,
    details: str | None = None,
) -> str:
    label = f"{client_name}.{method_name}"
    if details:
        return f"{label} ({details})"
    return label


def wrap_client_exception(
    *,
    client_name: str,
    method_name: str,
    exc: Exception,
    details: str | None = None,
) -> Exception:
    message = f"{client_call_label(client_name, method_name, details)} failed: {exc}"
    if isinstance(exc, AstrBotError):
        return AstrBotError(
            code=exc.code,
            message=message,
            hint=exc.hint,
            retryable=exc.retryable,
            docs_url=exc.docs_url,
            details=exc.details,
        )
    try:
        rebuilt = exc.__class__(message)
    except Exception:
        return RuntimeError(message)
    if isinstance(rebuilt, Exception):
        return rebuilt
    return RuntimeError(message)


__all__ = ["client_call_label", "wrap_client_exception"]
