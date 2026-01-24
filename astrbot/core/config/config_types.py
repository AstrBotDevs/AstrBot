"""Configuration type constants for AstrBot.

This module defines shared constants for configuration item types,
ensuring consistency between validation, default values, and UI rendering.
"""

from __future__ import annotations

from enum import Enum


class ConfigType(str, Enum):
    """Enumeration of all supported configuration item types."""

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    TEXT = "text"
    LIST = "list"
    OBJECT = "object"
    TEMPLATE_LIST = "template_list"
    PALETTE = "palette"
    PALETTE_RGB = "palette_rgb"
    PALETTE_HSV = "palette_hsv"


# Types that expect string values
STRING_LIKE_TYPES: frozenset[str] = frozenset(
    {
        ConfigType.STRING,
        ConfigType.TEXT,
        ConfigType.PALETTE,
        ConfigType.PALETTE_RGB,
        ConfigType.PALETTE_HSV,
    }
)

# Palette types specifically
PALETTE_TYPES: frozenset[str] = frozenset(
    {
        ConfigType.PALETTE,
        ConfigType.PALETTE_RGB,
        ConfigType.PALETTE_HSV,
    }
)

# Default values for each config type
# For palette types, empty string is valid (means no color selected)
DEFAULT_VALUE_MAP: dict[str, int | float | bool | str | list | dict] = {
    ConfigType.INT: 0,
    ConfigType.FLOAT: 0.0,
    ConfigType.BOOL: False,
    ConfigType.STRING: "",
    ConfigType.TEXT: "",
    ConfigType.LIST: [],
    ConfigType.OBJECT: {},
    ConfigType.TEMPLATE_LIST: [],
    ConfigType.PALETTE: "",
    ConfigType.PALETTE_RGB: "",
    ConfigType.PALETTE_HSV: "",
}


def get_default_value(config_type: str) -> int | float | bool | str | list | dict:
    """Get the default value for a configuration type.

    Args:
        config_type: The configuration type string

    Returns:
        The default value for the given type, or empty string if unknown

    """
    return DEFAULT_VALUE_MAP.get(config_type, "")


def is_string_like_type(config_type: str) -> bool:
    """Check if a configuration type expects string values.

    Args:
        config_type: The configuration type string

    Returns:
        True if the type expects string values

    """
    return config_type in STRING_LIKE_TYPES


def is_palette_type(config_type: str) -> bool:
    """Check if a configuration type is a palette type.

    Args:
        config_type: The configuration type string

    Returns:
        True if the type is a palette type

    """
    return config_type in PALETTE_TYPES
