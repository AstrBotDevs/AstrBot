"""Backward-compatible message session exports.

The canonical implementation moved to ``astrbot_sdk.message.session``. Preserve the
legacy import path to avoid breaking existing plugins.
"""

from .message.session import MessageSession

__all__ = ["MessageSession"]
