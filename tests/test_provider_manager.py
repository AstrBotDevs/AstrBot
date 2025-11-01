"""Tests for ProviderManager dynamic config properties."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.manager import ProviderManager


@pytest.fixture
def provider_manager_fixture(tmp_path):
    """Provides a ProviderManager instance for testing dynamic config properties."""
    # Create temporary database
    temp_db_path = tmp_path / "test_db.db"
    db = SQLiteDatabase(str(temp_db_path))

    # Create mock config manager with initial config
    acm = MagicMock(spec=AstrBotConfigManager)
    config = AstrBotConfig()
    config["provider"] = [
        {"id": "provider1", "type": "openai_chat_completion", "enable": True}
    ]
    config["provider_settings"] = {"default_provider_id": "provider1"}
    config["provider_stt_settings"] = {"provider_id": "stt1"}
    config["provider_tts_settings"] = {"provider_id": "tts1"}
    acm.confs = {"default": config}

    # Create mock persona manager
    persona_mgr = MagicMock(spec=PersonaManager)
    persona_mgr.default_persona = "default_persona"
    persona_mgr.persona_v3_config = []
    persona_mgr.personas_v3 = []
    persona_mgr.selected_default_persona_v3 = None

    # Create ProviderManager instance
    manager = ProviderManager(acm, db, persona_mgr)
    return manager, acm, config


def test_providers_config_is_dynamic(provider_manager_fixture):
    """Test that providers_config property dynamically reflects config changes."""
    manager, acm, config = provider_manager_fixture

    # Initial state
    assert len(manager.providers_config) == 1
    assert manager.providers_config[0]["id"] == "provider1"

    # Modify the config by adding a new provider
    config["provider"].append(
        {"id": "provider2", "type": "openai_chat_completion", "enable": True}
    )

    # Verify the property reflects the change
    assert len(manager.providers_config) == 2
    assert manager.providers_config[1]["id"] == "provider2"


def test_provider_settings_is_dynamic(provider_manager_fixture):
    """Test that provider_settings property dynamically reflects config changes."""
    manager, acm, config = provider_manager_fixture

    # Initial state
    assert manager.provider_settings["default_provider_id"] == "provider1"

    # Modify the config
    config["provider_settings"]["default_provider_id"] = "provider2"

    # Verify the property reflects the change
    assert manager.provider_settings["default_provider_id"] == "provider2"


def test_provider_stt_settings_is_dynamic(provider_manager_fixture):
    """Test that provider_stt_settings property dynamically reflects config changes."""
    manager, acm, config = provider_manager_fixture

    # Initial state
    assert manager.provider_stt_settings["provider_id"] == "stt1"

    # Modify the config
    config["provider_stt_settings"]["provider_id"] = "stt2"

    # Verify the property reflects the change
    assert manager.provider_stt_settings["provider_id"] == "stt2"


def test_provider_tts_settings_is_dynamic(provider_manager_fixture):
    """Test that provider_tts_settings property dynamically reflects config changes."""
    manager, acm, config = provider_manager_fixture

    # Initial state
    assert manager.provider_tts_settings["provider_id"] == "tts1"

    # Modify the config
    config["provider_tts_settings"]["provider_id"] = "tts2"

    # Verify the property reflects the change
    assert manager.provider_tts_settings["provider_id"] == "tts2"


def test_multiple_provider_additions(provider_manager_fixture):
    """Test that multiple provider additions are properly reflected.

    This test simulates the bug scenario where adding providers would
    not be reflected in the ProviderManager's providers_config.
    """
    manager, acm, config = provider_manager_fixture

    # Initial state: one provider
    assert len(manager.providers_config) == 1

    # Simulate adding multiple providers as the WebUI would do
    new_providers = [
        {"id": "deepseek-st", "type": "openai_chat_completion", "enable": True},
        {"id": "deepseek-st_copy", "type": "openai_chat_completion", "enable": True},
        {"id": "deepseek-st_copy2", "type": "openai_chat_completion", "enable": True},
    ]

    for provider in new_providers:
        config["provider"].append(provider)

    # Verify all providers are visible through the property
    assert len(manager.providers_config) == 4
    provider_ids = [p["id"] for p in manager.providers_config]
    assert "provider1" in provider_ids
    assert "deepseek-st" in provider_ids
    assert "deepseek-st_copy" in provider_ids
    assert "deepseek-st_copy2" in provider_ids
