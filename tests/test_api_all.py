"""Behavior and identity contracts exposed to plugin authors."""

import importlib

import pytest


@pytest.mark.parametrize(
    ("public_name", "source_module", "source_name"),
    [
        ("AstrBotConfig", "astrbot.core.config.astrbot_config", "AstrBotConfig"),
        ("html_renderer", "astrbot.core", "html_renderer"),
        ("llm_tool", "astrbot.core.star.register", "register_llm_tool"),
        (
            "MessageEventResult",
            "astrbot.core.message.message_event_result",
            "MessageEventResult",
        ),
        ("MessageChain", "astrbot.core.message.message_event_result", "MessageChain"),
        ("CommandResult", "astrbot.core.message.message_event_result", "CommandResult"),
        (
            "EventResultType",
            "astrbot.core.message.message_event_result",
            "EventResultType",
        ),
        ("AstrMessageEvent", "astrbot.core.platform", "AstrMessageEvent"),
        ("Platform", "astrbot.core.platform", "Platform"),
        ("AstrBotMessage", "astrbot.core.platform", "AstrBotMessage"),
        ("MessageMember", "astrbot.core.platform", "MessageMember"),
        ("MessageType", "astrbot.core.platform", "MessageType"),
        ("PlatformMetadata", "astrbot.core.platform", "PlatformMetadata"),
        ("command", "astrbot.core.star.register", "register_command"),
        ("command_group", "astrbot.core.star.register", "register_command_group"),
        (
            "event_message_type",
            "astrbot.core.star.register",
            "register_event_message_type",
        ),
        ("regex", "astrbot.core.star.register", "register_regex"),
        (
            "platform_adapter_type",
            "astrbot.core.star.register",
            "register_platform_adapter_type",
        ),
        ("button_action", "astrbot.core.star.register", "register_button_action"),
        ("ui_action", "astrbot.core.star.register", "register_ui_action"),
        (
            "EventMessageTypeFilter",
            "astrbot.core.star.filter.event_message_type",
            "EventMessageTypeFilter",
        ),
        (
            "EventMessageType",
            "astrbot.core.star.filter.event_message_type",
            "EventMessageType",
        ),
        (
            "PlatformAdapterTypeFilter",
            "astrbot.core.star.filter.platform_adapter_type",
            "PlatformAdapterTypeFilter",
        ),
        (
            "PlatformAdapterType",
            "astrbot.core.star.filter.platform_adapter_type",
            "PlatformAdapterType",
        ),
        ("Provider", "astrbot.core.provider", "Provider"),
        ("ProviderMetaData", "astrbot.core.provider", "ProviderMetaData"),
        ("Personality", "astrbot.core.db.po", "Personality"),
        ("Context", "astrbot.core.star", "Context"),
        ("Star", "astrbot.core.star", "Star"),
    ],
)
def test_api_all_reexports_canonical_objects(public_name, source_module, source_name):
    public_api = importlib.import_module("astrbot.api.all")
    canonical = getattr(importlib.import_module(source_module), source_name)
    assert getattr(public_api, public_name) is canonical


def test_public_message_chain_builds_real_message_components() -> None:
    from astrbot.api import message_components
    from astrbot.api.all import MessageChain
    from astrbot.api.event import MessageChain as EventMessageChain
    from astrbot.core.message.components import Plain

    chain = MessageChain().message("Plugin reply")
    assert MessageChain is EventMessageChain
    assert message_components.Plain is Plain
    assert len(chain.chain) == 1
    assert isinstance(chain.chain[0], Plain)
    assert chain.chain[0].text == "Plugin reply"


@pytest.mark.parametrize(
    "module_name", ["astrbot.api.event", "astrbot.api.event.filter", "astrbot.api.util"]
)
def test_declared_public_exports_are_resolvable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__all__
    assert len(module.__all__) == len(set(module.__all__))
    for name in module.__all__:
        assert getattr(module, name) is not None, f"{module_name}.{name}"
