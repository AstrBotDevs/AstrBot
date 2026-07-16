"""Import smoke tests for astrbot.core.star.command_management."""
from astrbot.core.star.command_management import (
    CommandDescriptor,
    sync_command_configs,
    toggle_command,
    rename_command,
    update_command_permission,
    list_commands,
    list_command_conflicts,
)


def test_command_descriptor_class():
    """CommandDescriptor is importable and is a dataclass."""
    assert isinstance(CommandDescriptor, type)


def test_sync_command_configs_is_async():
    """sync_command_configs is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(sync_command_configs)


def test_toggle_command_is_async():
    """toggle_command is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(toggle_command)


def test_rename_command_is_async():
    """rename_command is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(rename_command)


def test_update_command_permission_is_async():
    """update_command_permission is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(update_command_permission)


def test_list_commands_is_async():
    """list_commands is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(list_commands)


def test_list_command_conflicts_is_async():
    """list_command_conflicts is an async callable."""
    import asyncio
    assert asyncio.iscoroutinefunction(list_command_conflicts)
