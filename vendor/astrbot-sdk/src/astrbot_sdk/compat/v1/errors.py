"""Errors raised by the legacy compat layer."""

from __future__ import annotations

from ...errors import AstrBotSDKError


class IsolationUnsupportedError(AstrBotSDKError):
    """A legacy API cannot work inside the isolated Runner.

    The message names the unsupported API and, when known, the alternative.
    Plugins needing it must run in-process.
    """
