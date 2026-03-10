"""Constants for subagent configuration and error classification.

This module centralizes default values and configuration constants
for the subagent orchestration system.
"""

import asyncio
from typing import Literal

# ============================================================================
# Error Classifier Defaults
# ============================================================================

DEFAULT_FATAL_EXCEPTION_NAMES: list[str] = [
    "ValueError",
    "PermissionError",
    "KeyError",
]

DEFAULT_TRANSIENT_EXCEPTION_NAMES: list[str] = [
    "asyncio.TimeoutError",
    "TimeoutError",
    "ConnectionError",
    "ConnectionResetError",
]


def _resolve_default_exception_types(
    names: list[str],
) -> tuple[type[Exception], ...]:
    resolved: list[type[Exception]] = []
    for name in names:
        exc_type = EXCEPTION_ALLOWLIST[name]
        if exc_type not in resolved:
            resolved.append(exc_type)
    return tuple(resolved)


# Default error classification for unclassified exceptions
ErrorClass = Literal["fatal", "transient", "retryable"]
DEFAULT_ERROR_CLASS: ErrorClass = "transient"

# ============================================================================
# Subagent Runtime Defaults
# ============================================================================

DEFAULT_MAX_CONCURRENT_TASKS: int = 8
DEFAULT_MAX_ATTEMPTS: int = 3
DEFAULT_BASE_DELAY_MS: int = 500
DEFAULT_MAX_DELAY_MS: int = 30000
DEFAULT_JITTER_RATIO: float = 0.1

# Limits for runtime parameters
MIN_CONCURRENT_TASKS: int = 1
MAX_CONCURRENT_TASKS: int = 64
MIN_ATTEMPTS: int = 1
MIN_BASE_DELAY_MS: int = 100

# ============================================================================
# Subagent Worker Defaults
# ============================================================================

DEFAULT_POLL_INTERVAL: float = 1.0
DEFAULT_BATCH_SIZE: int = 8
DEFAULT_ERROR_RETRY_MAX_INTERVAL: float = 30.0
MIN_POLL_INTERVAL: float = 0.1
MIN_BATCH_SIZE: int = 1

# ============================================================================
# Handoff Execution Limits
# ============================================================================

# Maximum nested depth for subagent handoffs
MAX_NESTED_DEPTH_LIMIT: int = 8
MIN_NESTED_DEPTH_LIMIT: int = 1
DEFAULT_MAX_NESTED_HANDOFF_DEPTH: int = 2

# Default max steps for subagent execution
DEFAULT_MAX_STEPS: int = 30
DEFAULT_AGENT_MAX_STEPS: int = 200

# ============================================================================
# Allowed Exception Types for Configuration
# ============================================================================

EXCEPTION_ALLOWLIST: dict[str, type[Exception]] = {
    "ValueError": ValueError,
    "PermissionError": PermissionError,
    "KeyError": KeyError,
    "TimeoutError": TimeoutError,
    "ConnectionError": ConnectionError,
    "ConnectionResetError": ConnectionResetError,
    "asyncio.TimeoutError": asyncio.TimeoutError,
}

DEFAULT_FATAL_EXCEPTIONS: tuple[type[Exception], ...] = (
    _resolve_default_exception_types(DEFAULT_FATAL_EXCEPTION_NAMES)
)
DEFAULT_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    _resolve_default_exception_types(DEFAULT_TRANSIENT_EXCEPTION_NAMES)
)
