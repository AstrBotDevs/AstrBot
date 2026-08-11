"""Stable OneBot plugin exceptions."""

from astrbot.core.platform.contracts.onebot import (
    OneBotActionRejected,
    OneBotActionTimeout,
    OneBotActionUnavailable,
    OneBotActionValidationError,
    OneBotCapabilityUnavailable,
    OneBotError,
    OneBotTransportError,
)

__all__ = [
    "OneBotError",
    "OneBotCapabilityUnavailable",
    "OneBotActionUnavailable",
    "OneBotActionValidationError",
    "OneBotActionRejected",
    "OneBotTransportError",
    "OneBotActionTimeout",
]
