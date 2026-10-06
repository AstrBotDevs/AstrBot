from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.star_handler import star_handlers_registry

from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def write_agent_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "agent bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [
                        {"id": "llm.generate"},
                        {"id": "llm.agent"},
                        {"id": "llm.tool.register"},
                    ],
                },
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.llm import AgentRequest

class TestPlugin(Plugin):
    @on.tool(name="get_weather", description="Get weather for a city")
    async def get_weather(self, city: str) -> str:
        return f"sunny in {city}"

    @on.command("research")
    async def research(self, event: MessageEvent, topic: str):
        response = await self.ctx.llm.run_agent(
            AgentRequest(
                input=f"weather of {topic}?",
                tools=("get_weather",),
            ),
        )
        yield event.reply(f"agent:{response.text}")
""",
        "utf-8",
    )


class FakeAgentProvider:
    """Minimal provider driving the real ToolLoopAgentRunner."""

    provider_config: dict = {"id": "fake-agent", "type": "fake"}

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def meta(self):
        from astrbot.core.provider.entities import ProviderMeta, ProviderType

        return ProviderMeta(
            id="fake-agent",
            model="fake-model",
            type="fake",
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        contexts = kwargs.get("contexts") or []
        has_tool_result = any(
            (isinstance(m, dict) and m.get("role") == "tool")
            or getattr(m, "role", None) == "tool"
            for m in contexts
        )
        if has_tool_result:
            return LLMResponse(role="assistant", completion_text="final answer")
        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=["get_weather"],
            tools_call_args=[{"city": "sh"}],
            tools_call_ids=["call-1"],
        )


@pytest.mark.asyncio
async def test_bridge_agent_run_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "agent_bridge_e2e"
    write_agent_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    from astrbot.core.star.context import Context

    provider = FakeAgentProvider()
    # AstrAgentContext validates the star context type with pydantic, so the
    # bridge needs a real Context; its managers can be mocks.
    context = Context(
        event_queue=MagicMock(),
        config=MagicMock(),
        db=MagicMock(),
        provider_manager=MagicMock(),
        platform_manager=MagicMock(),
        conversation_manager=MagicMock(),
        message_history_manager=MagicMock(),
        persona_manager=MagicMock(),
        astrbot_config_mgr=MagicMock(),
        knowledge_base_manager=MagicMock(),
        cron_manager=MagicMock(),
    )
    context.provider_manager.get_using_provider_async = AsyncMock(
        return_value=provider,
    )
    context.provider_manager.get_provider_by_id = AsyncMock(
        return_value=provider,
    )
    context.provider_manager.get_provider_by_id = AsyncMock(
        return_value=provider,
    )

    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[
            f"sdk_bridge.{plugin_root.name}_research"
        ]
        event = FakeCoreEvent("research sh")
        assert handler.event_filters[0].filter(event, None)
        params = event.get_extra("parsed_params") or {}

        replies = []
        async for _ in handler.handler(event, **params):
            if event.get_result():
                replies.append(event.get_result().chain[0].text)
            event.clear_result()

        assert replies == ["agent:final answer"], replies
        # The loop made two LLM calls: tool call, then final answer.
        assert len(provider.calls) == 2
        # The whitelist offered exactly the plugin's own tool.
        func_tool = provider.calls[0]["func_tool"]
        assert func_tool.names() == ["get_weather"]

        # Default (no tools) means no toolset is offered at all.
        from astrbot.core.star.sdk_bridge.services.agent import AgentRunService
        from astrbot_sdk.events import UMO, MessageType

        provider.calls.clear()
        service = AgentRunService(context, bridge._tool_names)
        with pytest.raises(Exception, match="final response"):
            # No tools offered, so the fake provider keeps demanding the
            # tool until max steps without a final answer.
            await service.handle(
                "run",
                {
                    "prompt": "hi",
                    "umo": UMO("webchat", MessageType.PRIVATE, "u1"),
                    "max_steps": 2,
                },
            )
        assert provider.calls[0]["func_tool"] is None
    finally:
        await bridge.stop()


@pytest.mark.asyncio
async def test_agent_run_with_restricted_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "agent_restricted"
    write_agent_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    provider = FakeAgentProvider()
    context = _make_agent_context(provider)
    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()

        # Ask the agent service directly with a tools whitelist.
        from astrbot.core.star.sdk_bridge.services.agent import AgentRunService
        from astrbot_sdk.events import UMO, MessageType

        service = AgentRunService(context, bridge._tool_names)
        result = await service.handle(
            "run",
            {
                "prompt": "weather of sh?",
                "umo": UMO("webchat", MessageType.PRIVATE, "u1"),
                "tools": ["get_weather"],
            },
        )
        assert result["response"].text == "final answer"
        func_tool = provider.calls[0]["func_tool"]
        assert func_tool.names() == ["get_weather"]
    finally:
        await bridge.stop()


def _make_agent_context(provider):
    from unittest.mock import AsyncMock, MagicMock

    from astrbot.core.star.context import Context

    context = Context(
        event_queue=MagicMock(),
        config=MagicMock(),
        db=MagicMock(),
        provider_manager=MagicMock(),
        platform_manager=MagicMock(),
        conversation_manager=MagicMock(),
        message_history_manager=MagicMock(),
        persona_manager=MagicMock(),
        astrbot_config_mgr=MagicMock(),
        knowledge_base_manager=MagicMock(),
        cron_manager=MagicMock(),
    )
    context.provider_manager.get_using_provider_async = AsyncMock(
        return_value=provider,
    )
    context.provider_manager.get_provider_by_id = AsyncMock(
        return_value=provider,
    )
    return context
