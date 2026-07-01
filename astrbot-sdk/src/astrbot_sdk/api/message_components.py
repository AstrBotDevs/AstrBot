"""Namespaced bridge for ``astrbot.api.message_components``."""

from __future__ import annotations

from .._api_bridge import export_public_api

__all__ = export_public_api("astrbot.api.message_components", globals())
