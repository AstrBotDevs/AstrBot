from __future__ import annotations

from typing import Literal, Protocol

from .constants import (
    DEFAULT_ERROR_CLASS,
    DEFAULT_FATAL_EXCEPTION_NAMES,
    DEFAULT_FATAL_EXCEPTIONS,
    DEFAULT_TRANSIENT_EXCEPTION_NAMES,
    DEFAULT_TRANSIENT_EXCEPTIONS,
    EXCEPTION_ALLOWLIST,
)
from .models import SubagentErrorClassifierConfig

ErrorClass = Literal["fatal", "transient", "retryable"]


class ErrorClassifier(Protocol):
    def classify(self, exc: Exception) -> ErrorClass: ...


class DefaultErrorClassifier:
    def __init__(
        self,
        *,
        fatal_types: tuple[type[Exception], ...] | None = None,
        transient_types: tuple[type[Exception], ...] | None = None,
        default_class: ErrorClass = DEFAULT_ERROR_CLASS,
    ) -> None:
        self.fatal_types = fatal_types or DEFAULT_FATAL_EXCEPTIONS
        self.transient_types = transient_types or DEFAULT_TRANSIENT_EXCEPTIONS
        self.default_class: ErrorClass = (
            default_class
            if default_class in {"fatal", "transient", "retryable"}
            else DEFAULT_ERROR_CLASS
        )

    def classify(self, exc: Exception) -> ErrorClass:
        if isinstance(exc, self.fatal_types):
            return "fatal"
        if isinstance(exc, self.transient_types):
            return "transient"
        return self.default_class


def get_error_classifier_defaults() -> dict[str, str | list[str]]:
    """Return default configuration for error classifier.

    This function provides serializable default values for configuration.
    """
    return {
        "fatal_exceptions": DEFAULT_FATAL_EXCEPTION_NAMES,
        "transient_exceptions": DEFAULT_TRANSIENT_EXCEPTION_NAMES,
        "default_class": DEFAULT_ERROR_CLASS,
    }


def build_error_classifier_from_config(
    cfg: SubagentErrorClassifierConfig | None,
) -> tuple[ErrorClassifier, list[str]]:
    config = cfg or SubagentErrorClassifierConfig()
    diagnostics: list[str] = []

    if config.type != "default":
        diagnostics.append(
            f"Unsupported error_classifier.type '{config.type}', fallback to 'default'."
        )

    fatal_types = _resolve_exception_types(
        config.fatal_exceptions, "error_classifier.fatal_exceptions", diagnostics
    )
    transient_types = _resolve_exception_types(
        config.transient_exceptions,
        "error_classifier.transient_exceptions",
        diagnostics,
    )

    classifier = DefaultErrorClassifier(
        fatal_types=fatal_types,
        transient_types=transient_types,
        default_class=config.default_class,
    )
    return classifier, diagnostics


def _resolve_exception_types(
    names: list[str],
    field_name: str,
    diagnostics: list[str],
) -> tuple[type[Exception], ...]:
    resolved: list[type[Exception]] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        exc_type = EXCEPTION_ALLOWLIST.get(name)
        if exc_type is None:
            diagnostics.append(f"{field_name}: unsupported exception '{name}' ignored.")
            continue
        if exc_type not in resolved:
            resolved.append(exc_type)
    return tuple(resolved)
