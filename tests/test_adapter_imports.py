"""Keep built-in imports lazy and separate from custom adapter registration."""

import asyncio
from unittest.mock import Mock

import pytest

from astrbot.core.platform import manager as platform_module
from astrbot.core.provider import manager as provider_module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope, adapter, expected",
    [
        (provider_module, "openai_chat_completion", "sources.openai_source"),
        (provider_module, "googlegenai_chat_completion", "sources.gemini_source"),
        (provider_module, "xinference_stt", "sources.xinference_stt_provider"),
        (platform_module, "telegram", "sources.telegram.tg_adapter"),
        (
            platform_module,
            "qq_official_webhook",
            "sources.qqofficial_webhook.qo_webhook_adapter",
        ),
        (platform_module, "slack", "sources.slack.slack_adapter"),
        (provider_module, "plugin_custom", None),
        (platform_module, "plugin_custom", None),
        (provider_module, "../../os", None),
        (platform_module, "../../os", None),
    ],
)
async def test_import_uses_only_the_explicit_module_map(
    monkeypatch, scope, adapter, expected
):
    imported = Mock()
    monkeypatch.setattr(scope, "import_module", imported)
    if scope is provider_module:
        manager = provider_module.ProviderManager.__new__(provider_module.ProviderManager)
        manager.dynamic_import_provider(adapter)
    else:
        monkeypatch.setattr(platform_module, "platform_cls_map", {})
        manager = platform_module.PlatformManager(
            {"platform": [], "platform_settings": {}}, asyncio.Queue()
        )
        await manager.load_platform({"id": "test", "type": adapter, "enable": True})
    if expected is None:
        imported.assert_not_called()
    else:
        imported.assert_called_once_with(f".{expected}", package=scope.__package__)
