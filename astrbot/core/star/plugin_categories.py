"""Canonical plugin categories that plugins declare in ``metadata.yaml``.

Plugins declare a stable, machine-readable slug instead of a localized label so
the plugin market index, the WebUI and the runtime all filter on the same
values. Adding a category is a code change here; labels are derived from the
slug wherever it is displayed.
"""

from __future__ import annotations

import re

from astrbot.core import logger

PLUGIN_CATEGORY_SLUGS: tuple[str, ...] = (
    "ai_tools",
    "ai_image",
    "ai_speech",
    "ai_agent",
    "ai_context",
    "long_term_memory",
    "knowledge_base",
    "tools",
    "productivity",
    "utilities",
    "integrations",
    "platform_adapter",
    "media_processing",
    "automation",
    "security",
    "entertainment",
    "group_games",
    "game_integration",
    "other",
)
"""Supported ``metadata.yaml`` ``category`` values, in display order."""

DEFAULT_PLUGIN_CATEGORY = "other"
"""Category used when a plugin declares an unsupported category."""


def normalize_plugin_category(value: object, *, warn: bool = True) -> str | None:
    """Normalize the category declared by plugin metadata.

    Unsupported values never block loading or installation: they are reported in
    the log and mapped to ``DEFAULT_PLUGIN_CATEGORY`` so that a typo in
    ``metadata.yaml`` cannot make a plugin uninstallable.

    Args:
        value: Raw ``category`` value read from ``metadata.yaml``.
        warn: Whether to report an unsupported value. Callers that already
            validated the same metadata can pass ``False`` to avoid a duplicate
            warning while still getting the normalized value.

    Returns:
        The declared slug when it is supported, ``None`` when the plugin does
        not declare a category, otherwise ``DEFAULT_PLUGIN_CATEGORY``.
    """
    if value is None:
        return None

    if isinstance(value, str):
        # Collapse separator runs so that "AI - Tools" matches what the WebUI
        # derives from the same declaration instead of falling back to "other".
        slug = re.sub(r"[\s-]+", "_", value.strip().lower())
        if slug in PLUGIN_CATEGORY_SLUGS:
            return slug
        if not slug:
            return None

    if not warn:
        return DEFAULT_PLUGIN_CATEGORY

    logger.warning(
        f"Unsupported plugin category {value!r}; falling back to "
        f"{DEFAULT_PLUGIN_CATEGORY!r}."
    )
    return DEFAULT_PLUGIN_CATEGORY
