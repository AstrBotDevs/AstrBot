from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.admin import AdminCommands


def test_admin_commands_imported():
    assert AdminCommands is not None


def test_admin_commands_class():
    assert issubclass(AdminCommands, object)
    assert hasattr(AdminCommands, "op")
    assert hasattr(AdminCommands, "deop")
    assert hasattr(AdminCommands, "wl")
    assert hasattr(AdminCommands, "dwl")
    assert hasattr(AdminCommands, "update_dashboard")
