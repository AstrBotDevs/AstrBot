"""Recommended plugin categories that plugins may declare in ``metadata.yaml``.

A category is an optional, free-form hint. The values below are the ones the
plugin market, the WebUI and the runtime know how to label and order, and a
plugin may declare something else: the declared value is normalized to a slug
either way, so one typo or one niche category cannot block a plugin from loading,
installing or updating. Display code derives labels from the slug and falls back
to the words of the slug itself.
"""

from __future__ import annotations

import re

RECOMMENDED_PLUGIN_CATEGORIES: tuple[str, ...] = (
    "utility",
    "ai_context",
    "entertainment",
    "game",
    "media",
    "productivity",
    "integration",
    "platform_adapter",
    "provider_adapter",
    "other",
)
"""Recommended ``metadata.yaml`` ``category`` values, in display order."""


def normalize_plugin_category(value: object) -> str | None:
    """Normalize the optional category declared by plugin metadata.

    Any value is accepted. A value outside ``RECOMMENDED_PLUGIN_CATEGORIES`` is
    kept as declared instead of being rejected or rewritten, because the
    vocabulary is a recommendation for plugin authors rather than a constraint
    the runtime enforces.

    Args:
        value: Raw ``category`` value read from ``metadata.yaml``.

    Returns:
        The normalized slug, or ``None`` when the plugin declares no category or
        declares something that is not a string.
    """
    if not isinstance(value, str):
        return None

    # Collapse separator runs so that "AI - Context", "ai-context" and
    # "ai_context" reach the WebUI as one slug.
    slug = re.sub(r"[\s-]+", "_", value.strip().lower())
    return slug or None
