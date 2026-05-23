"""Backward-compatible alias for ``astrbot_sdk.message.result``.

Use a module alias so callers patching helper functions on the legacy module path
still affect ``MessageBuilder`` and other implementation globals.
"""

from __future__ import annotations

import sys

from .message import result as _result_module

sys.modules[__name__] = _result_module
