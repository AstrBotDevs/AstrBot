"""Native web-search configuration and key rotation use isolated state."""

import asyncio
from unittest.mock import Mock

import pytest

from astrbot.core.astr_agent_runtime.tools.web_search_tools import (
    _KeyRotator,
    normalize_legacy_web_search_config,
)


class Config(dict):
    def __init__(self, values):
        super().__init__(values)
        self.save_config = Mock()


def test_legacy_search_configuration_is_migrated_once():
    config = Config(
        {
            "provider_settings": {
                "websearch_provider": "default",
                "web_search": True,
                "websearch_tavily_key": "example-key",
                "websearch_bocha_key": "",
            }
        }
    )
    normalize_legacy_web_search_config(config)
    assert config["provider_settings"] == {
        "websearch_provider": "default",
        "web_search": False,
        "websearch_tavily_key": ["example-key"],
        "websearch_bocha_key": [],
    }
    config.save_config.assert_called_once_with()
    normalize_legacy_web_search_config(config)
    config.save_config.assert_called_once_with()


def test_canonical_provider_and_keys_are_preserved():
    config = Config(
        {
            "provider_settings": {
                "websearch_provider": "tavily",
                "web_search": True,
                "websearch_tavily_key": ["one", "two"],
            }
        }
    )
    normalize_legacy_web_search_config(config)
    assert config["provider_settings"]["web_search"] is True
    assert config["provider_settings"]["websearch_tavily_key"] == ["one", "two"]
    config.save_config.assert_not_called()


@pytest.mark.asyncio
async def test_key_rotation_is_deterministic_across_concurrent_requests_and_reload():
    rotator = _KeyRotator("keys", "Test")
    settings = {"keys": ["one", "two", "three"]}
    assert await asyncio.gather(*(rotator.get(settings) for _ in range(5))) == [
        "one",
        "two",
        "three",
        "one",
        "two",
    ]
    assert await rotator.get({"keys": ["only"]}) == "only"
    assert settings == {"keys": ["one", "two", "three"]}


@pytest.mark.asyncio
async def test_failed_keys_are_not_retried_within_one_request():
    rotator = _KeyRotator("keys", "Test")
    tried = set()
    settings = {"keys": ["one", "one", "two"]}
    assert await rotator.get(settings, tried) == "one"
    assert await rotator.get(settings, tried) == "two"
    with pytest.raises(ValueError, match="No untried"):
        await rotator.get(settings, tried)
    assert tried == {"one", "two"}
    with pytest.raises(ValueError, match="not configured"):
        await rotator.get({})
