from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.t2i import T2ICommand


def test_t2i_command_imported():
    assert T2ICommand is not None


def test_t2i_command_class():
    assert issubclass(T2ICommand, object)
    assert hasattr(T2ICommand, "t2i")
