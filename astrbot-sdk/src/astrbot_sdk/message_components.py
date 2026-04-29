"""Backward-compatible alias for ``astrbot_sdk.message.components``.

This module intentionally aliases the implementation module instead of re-exporting
names one by one so private helpers keep working with existing monkeypatch sites.
"""

from __future__ import annotations

import sys

from .message import components as _components_module

sys.modules[__name__] = _components_module
