"""Namespaced bridge for ``astrbot.api.provider``."""

from __future__ import annotations

from ..._api_bridge import export_public_api

__all__ = export_public_api("astrbot.api.provider", globals())
