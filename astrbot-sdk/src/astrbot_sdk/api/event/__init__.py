"""Namespaced bridge for ``astrbot.api.event``."""

from __future__ import annotations

from ..._api_bridge import export_public_api
from . import filter as filter

__all__ = [*export_public_api("astrbot.api.event", globals()), "filter"]
