from __future__ import annotations

from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands


def test_provider_commands_imported():
    assert ProviderCommands is not None


def test_provider_commands_class():
    assert issubclass(ProviderCommands, object)
    assert hasattr(ProviderCommands, "provider")
    assert hasattr(ProviderCommands, "model_ls")
    assert hasattr(ProviderCommands, "_build_provider_display_data")
    assert hasattr(ProviderCommands, "_test_provider_capability")
