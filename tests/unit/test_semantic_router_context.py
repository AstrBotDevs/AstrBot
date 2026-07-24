from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.execution_policy import AGENT_EXECUTION_POLICY_EXTRA_KEY
from astrbot.core.agent.tool import FunctionTool, ToolSet
from data.plugins.astrbot_plugin_semantic_router.main import SemanticRouterPlugin


class _ContextEvent:
    def __init__(
        self,
        *,
        sender_id: str,
        sender_name: str,
        text: str,
        message_id: str,
    ) -> None:
        self.message_str = text
        self.message_obj = SimpleNamespace(message_id=message_id)
        self.extras = {
            AGENT_EXECUTION_POLICY_EXTRA_KEY: {
                "route": "standard",
            }
        }
        self._sender_id = sender_id
        self._sender_name = sender_name

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_group_id(self) -> str:
        return "group-1"

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_sender_name(self) -> str:
        return self._sender_name

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value


def _plugin() -> SemanticRouterPlugin:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context_state = {"scopes": {}, "conversations": {}}
    plugin.max_context_text_chars = 900
    plugin.max_recent_messages = 24
    plugin.context_ttl_days = 30
    plugin.include_search_image_guidance = False
    plugin._schedule_context_save = lambda: None
    return plugin


def test_group_context_collects_other_speakers_without_exposing_raw_ids() -> None:
    plugin = _plugin()
    first = _ContextEvent(
        sender_id="10001",
        sender_name="甲",
        text="我们在讨论今天的黄金价格",
        message_id="m1",
    )
    second = _ContextEvent(
        sender_id="20002",
        sender_name="乙",
        text="我觉得应该先查实时来源",
        message_id="m2",
    )
    current = _ContextEvent(
        sender_id="10001",
        sender_name="甲",
        text="那现在是多少钱？",
        message_id="m3",
    )

    plugin._record_message(first)
    plugin._record_message(second)
    prompt = plugin._build_scope_prompt(current, SimpleNamespace())

    shared = plugin.context_state["scopes"]["aiocqhttp:group:group-1:shared"]
    assert len(shared["recent"]) == 2
    assert "我们在讨论今天的黄金价格" in prompt
    assert "我觉得应该先查实时来源" in prompt
    assert "群友" in prompt
    assert "20002" not in prompt


def test_context_prompt_deduplicates_shared_and_personal_messages() -> None:
    plugin = _plugin()
    previous = _ContextEvent(
        sender_id="10001",
        sender_name="user",
        text="duplicate-context-marker",
        message_id="m1",
    )
    current = _ContextEvent(
        sender_id="10001",
        sender_name="user",
        text="follow-up",
        message_id="m2",
    )

    plugin._record_message(previous)
    prompt = plugin._build_scope_prompt(current, SimpleNamespace())

    assert prompt.count("duplicate-context-marker") == 1


def test_private_user_context_does_not_create_shared_group_scope() -> None:
    plugin = _plugin()
    event = _ContextEvent(
        sender_id="10001",
        sender_name="甲",
        text="记住我的偏好",
        message_id="m1",
    )
    event.get_group_id = lambda: ""

    plugin._record_message(event)

    assert all(not key.endswith(":shared") for key in plugin.context_state["scopes"])


@pytest.mark.asyncio
async def test_route_policy_filters_request_toolset_before_provider_call() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context_enabled = False
    plugin.inject_context_to_llm = False

    event = _ContextEvent(
        sender_id="10001",
        sender_name="用户",
        text="今日天气",
        message_id="m1",
    )
    event.extras[AGENT_EXECUTION_POLICY_EXTRA_KEY] = {
        "route": "standard",
        "allowed_tools": ["browser_search"],
        "tool_required": True,
        "permission_snapshot": {"role": "member"},
    }
    req = SimpleNamespace(
        system_prompt="",
        func_tool=ToolSet(
            tools=[
                FunctionTool(
                    name="browser_search",
                    description="Search public websites.",
                    parameters={"type": "object", "properties": {}},
                ),
                FunctionTool(
                    name="browser_click",
                    description="Click a browser element.",
                    parameters={"type": "object", "properties": {}},
                ),
            ]
        ),
    )

    await plugin.inject_scoped_context(event, req)

    assert req.func_tool.names() == ["browser_search"]


@pytest.mark.asyncio
async def test_saturated_route_stops_llm_before_provider_execution() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.control_plane = SimpleNamespace(acquire_route=AsyncMock(return_value=False))
    state = {"should_call_llm": True, "stopped": False}
    event = SimpleNamespace(
        should_call_llm=lambda enabled: state.__setitem__("should_call_llm", enabled),
        stop_event=lambda: state.__setitem__("stopped", True),
    )

    await plugin.acquire_route_before_llm(event, None)

    assert state == {"should_call_llm": False, "stopped": True}


@pytest.mark.asyncio
async def test_wake_request_rebuilds_context_when_upstream_marker_is_missing() -> None:
    plugin = _plugin()
    plugin.context_enabled = False
    plugin.inject_context_to_llm = False
    plugin.context_on_wake_required = True

    previous = _ContextEvent(
        sender_id="10001",
        sender_name="甲",
        text="我们刚才在讨论今天的天气",
        message_id="m1",
    )
    plugin._record_message(previous)

    current = _ContextEvent(
        sender_id="10001",
        sender_name="甲",
        text="亚托莉，接着说",
        message_id="m2",
    )
    current.is_wake = True
    current.extras[AGENT_EXECUTION_POLICY_EXTRA_KEY] = None
    req = SimpleNamespace(system_prompt="", func_tool=None)

    await plugin.inject_scoped_context(current, req)

    assert "<scoped_context_by_semantic_router>" in req.system_prompt


@pytest.mark.asyncio
async def test_audio_only_event_is_not_discarded_by_empty_text_guard() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.enabled = True
    plugin.context_enabled = False
    plugin._recent_conversation_images = {}
    plugin.recent_image_ttl_seconds = 10.0
    plugin._contains_image = lambda event: False
    plugin._scope_info = lambda event: {"conversation_key": "audio-test"}
    plugin._references_recent_image = lambda text: False

    def targeting_guard(event, text):
        raise RuntimeError("audio reached semantic targeting")

    plugin._targeting_allowed = targeting_guard
    record = type("Record", (), {})()
    event = SimpleNamespace(message_str="", get_messages=lambda: [record])

    with pytest.raises(RuntimeError, match="audio reached semantic targeting"):
        await plugin.route_message(event).__anext__()
