"""Stable command identifiers independent of Python method names."""

BUILTIN_COMMANDS_MODULE = "astrbot.builtin_stars.builtin_commands.main"

BUILTIN_HANDLER_FULL_NAME_MIGRATION: dict[str, str] = {
    f"{BUILTIN_COMMANDS_MODULE}_sid": "builtin_commands:session.info",
    f"{BUILTIN_COMMANDS_MODULE}_name": "builtin_commands:session.name",
    f"{BUILTIN_COMMANDS_MODULE}_reset": "builtin_commands:conversation.reset",
    f"{BUILTIN_COMMANDS_MODULE}_new_conv": "builtin_commands:conversation.create",
    f"{BUILTIN_COMMANDS_MODULE}_stats": "builtin_commands:conversation.stats",
    f"{BUILTIN_COMMANDS_MODULE}_history": "builtin_commands:conversation.history",
    f"{BUILTIN_COMMANDS_MODULE}_convs": "builtin_commands:conversation.list",
    f"{BUILTIN_COMMANDS_MODULE}_groupnew": "builtin_commands:conversation.create-for",
    f"{BUILTIN_COMMANDS_MODULE}_switch": "builtin_commands:conversation.switch",
    f"{BUILTIN_COMMANDS_MODULE}_rename": "builtin_commands:conversation.rename",
    f"{BUILTIN_COMMANDS_MODULE}_delete": "builtin_commands:conversation.delete",
    f"{BUILTIN_COMMANDS_MODULE}_stop": "builtin_commands:task.stop",
    f"{BUILTIN_COMMANDS_MODULE}_op": "builtin_commands:admin.grant",
    f"{BUILTIN_COMMANDS_MODULE}_deop": "builtin_commands:admin.revoke",
    f"{BUILTIN_COMMANDS_MODULE}_persona_view": "builtin_commands:persona.show",
    f"{BUILTIN_COMMANDS_MODULE}_plugin_ls": "builtin_commands:plugin.list",
    f"{BUILTIN_COMMANDS_MODULE}_plugin_off": "builtin_commands:plugin.disable",
    f"{BUILTIN_COMMANDS_MODULE}_plugin_on": "builtin_commands:plugin.enable",
    f"{BUILTIN_COMMANDS_MODULE}_plugin_get": "builtin_commands:plugin.install",
    f"{BUILTIN_COMMANDS_MODULE}_plugin_help": "builtin_commands:plugin.show",
    f"{BUILTIN_COMMANDS_MODULE}_set_variable": "builtin_commands:variable.set",
    f"{BUILTIN_COMMANDS_MODULE}_unset_variable": "builtin_commands:variable.unset",
    f"{BUILTIN_COMMANDS_MODULE}_flow_on": "builtin_commands:flow.enable",
    f"{BUILTIN_COMMANDS_MODULE}_flow_off": "builtin_commands:flow.disable",
}


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


def legacy_alter_cmd_keys(
    command_id: str, handler_name: str | None = None
) -> tuple[str, ...]:
    """Return non-command_id keys that may still store alter_cmd for one handler.

    Args:
        command_id: Stable command identifier.
        handler_name: Current Python method name, if known.

    Returns:
        Current handler_name plus fossil builtin method names mapped to
        ``command_id``. ``command_id`` itself is never included.
    """

    keys: list[str] = []
    seen: set[str] = {command_id}
    if handler_name and handler_name not in seen:
        keys.append(handler_name)
        seen.add(handler_name)
    prefix = f"{BUILTIN_COMMANDS_MODULE}_"
    for full_name, mapped_id in BUILTIN_HANDLER_FULL_NAME_MIGRATION.items():
        if mapped_id != command_id or not full_name.startswith(prefix):
            continue
        legacy_name = full_name.removeprefix(prefix)
        if legacy_name not in seen:
            keys.append(legacy_name)
            seen.add(legacy_name)
    return tuple(keys)


def take_alter_cmd_entry(
    plugin_cfg: dict,
    command_id: str,
    handler_name: str | None = None,
) -> dict | None:
    """Claim alter_cmd config for ``command_id``, migrating legacy keys.

    Lookup order is ``command_id``, the current handler_name, then fossil
    builtin method names. Legacy keys are always popped when a dict is
    claimed. If nothing is found, leftover legacy keys are still removed.

    Args:
        plugin_cfg: Per-plugin alter_cmd mapping, mutated in place.
        command_id: Stable command identifier.
        handler_name: Current Python method name, if known.

    Returns:
        The stored config dict after migration, or None when absent.
    """

    legacy_keys = legacy_alter_cmd_keys(command_id, handler_name)
    command = plugin_cfg.get(command_id)
    if not isinstance(command, dict):
        command = None
        for key in legacy_keys:
            found = plugin_cfg.get(key)
            if isinstance(found, dict):
                command = found
                break
    for key in legacy_keys:
        plugin_cfg.pop(key, None)
    if command is None:
        return None
    plugin_cfg[command_id] = command
    return command
