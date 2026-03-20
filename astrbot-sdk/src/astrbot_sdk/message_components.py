"""Backward-compatible message component exports.

The SDK internals now live under ``astrbot_sdk.message.*``. Keep this module as a
thin compatibility layer so existing plugin imports and generated docs continue to
work during the package layout migration.
"""

from .message.components import *  # noqa: F401,F403
from .message.components import __all__ as _message_components_all

__all__ = list(_message_components_all)
