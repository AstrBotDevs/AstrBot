"""Stable command identifiers independent of Python method names."""

BUILTIN_COMMANDS_MODULE = "astrbot.builtin_stars.builtin_commands.main"


def compute_command_id(plugin_name: str, original_command: str) -> str:
    """Return the stable command ID for one declared command path.

    Args:
        plugin_name: Plugin name that owns the handler.
        original_command: Space-separated original command path.

    Returns:
        `{plugin_name}:{original_command}` with spaces replaced by dots.
    """

    fragment = (original_command or "").replace(" ", ".")
    return f"{plugin_name}:{fragment}"


def take_alter_cmd_entry(plugin_cfg: dict, command_id: str) -> dict | None:
    """Return alter_cmd config stored under ``command_id``.

    Args:
        plugin_cfg: Per-plugin alter_cmd mapping.
        command_id: Stable command identifier.

    Returns:
        The stored config dict, or None when absent.
    """

    command = plugin_cfg.get(command_id)
    return command if isinstance(command, dict) else None
