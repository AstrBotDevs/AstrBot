"""Backward-compatible message result exports.

The SDK internals now live under ``astrbot_sdk.message.*``. Keep this module as a
thin compatibility layer so existing plugin imports and generated docs continue to
work during the package layout migration.
"""

from .message.result import *  # noqa: F401,F403
from .message.result import __all__ as _message_result_all

__all__ = list(_message_result_all)
