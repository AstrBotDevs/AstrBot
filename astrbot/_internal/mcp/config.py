"""MCP configuration management."""

import json
import os

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

DEFAULT_MCP_CONFIG = {"mcpServers": {}}


def get_mcp_config_path() -> str:
    """Get the path to the MCP configuration file."""
    data_dir = get_astrbot_data_path()
    return os.path.join(data_dir, "mcp_server.json")


def load_mcp_config() -> dict:
    """Load MCP configuration from file.

    Returns:
        MCP configuration dict. If file doesn't exist, returns default config.

    """
    config_path = get_mcp_config_path()
    if not os.path.exists(config_path):
        # Create default config if not exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_MCP_CONFIG, f, ensure_ascii=False, indent=4)
        return DEFAULT_MCP_CONFIG

    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_MCP_CONFIG


def save_mcp_config(config: dict) -> bool:
    """Save MCP configuration to file.

    Args:
        config: MCP configuration dict to save.

    Returns:
        True if successful, False otherwise.

    """
    config_path = get_mcp_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False
