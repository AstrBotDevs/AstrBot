from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.tts import TTSCommand


def test_tts_command_imported():
    assert TTSCommand is not None


def test_tts_command_class():
    assert issubclass(TTSCommand, object)
    assert hasattr(TTSCommand, "tts")
