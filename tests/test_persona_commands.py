from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands


def test_persona_commands_imported():
    assert PersonaCommands is not None


def test_persona_commands_class():
    assert issubclass(PersonaCommands, object)
    assert hasattr(PersonaCommands, "persona")
    assert hasattr(PersonaCommands, "_build_tree_output")
