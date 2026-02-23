"""Smoke tests for astrbot.api backward compatibility."""

import importlib
import sys


def test_api_exports_smoke():
    """astrbot.api should expose expected public symbols."""
    import astrbot.api as api

    for name in [
        "AstrBotConfig",
        "BaseFunctionToolExecutor",
        "FunctionTool",
        "ToolSet",
        "agent",
        "llm_tool",
        "logger",
        "html_renderer",
        "sp",
    ]:
        assert hasattr(api, name), f"Missing export: {name}"

    assert callable(api.agent)
    assert callable(api.llm_tool)


def test_api_event_and_platform_map_to_core():
    """api facade classes should remain mapped to core implementations."""
    from astrbot.api import event as api_event
    from astrbot.api import platform as api_platform
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform import (
        AstrBotMessage,
        AstrMessageEvent,
        MessageMember,
        MessageType,
        Platform,
        PlatformMetadata,
    )
    from astrbot.core.platform.register import register_platform_adapter

    assert api_event.AstrMessageEvent is AstrMessageEvent
    assert api_event.MessageChain is MessageChain

    assert api_platform.AstrBotMessage is AstrBotMessage
    assert api_platform.AstrMessageEvent is AstrMessageEvent
    assert api_platform.MessageMember is MessageMember
    assert api_platform.MessageType is MessageType
    assert api_platform.Platform is Platform
    assert api_platform.PlatformMetadata is PlatformMetadata
    assert api_platform.register_platform_adapter is register_platform_adapter


def test_api_message_components_smoke():
    """message_components facade should stay import-compatible."""
    from astrbot.api.message_components import File, Image, Plain

    plain = Plain("hello")
    image = Image(file="https://example.com/a.jpg", url="https://example.com/a.jpg")
    file_seg = File(file="https://example.com/a.txt", name="a.txt")

    assert plain.text == "hello"
    assert image.file == "https://example.com/a.jpg"
    assert file_seg.name == "a.txt"


def test_api_eagerly_imports_star_register(monkeypatch):
    """Importing astrbot.api should expose direct aliases from star.register."""
    monkeypatch.delitem(sys.modules, "astrbot.core.star.register", raising=False)

    api = importlib.import_module("astrbot.api")
    importlib.reload(api)
    register_mod = importlib.import_module("astrbot.core.star.register")

    assert "astrbot.core.star.register" in sys.modules
    assert api.agent is register_mod.register_agent
    assert api.llm_tool is register_mod.register_llm_tool


def test_api_agent_and_llm_tool_are_callable_aliases():
    """agent/llm_tool should remain callable after direct aliasing."""
    import astrbot.api as api

    assert callable(api.agent)
    assert callable(api.llm_tool)
