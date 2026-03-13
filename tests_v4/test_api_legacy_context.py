"""
Tests for _legacy_api.py - Legacy compatibility layer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk._legacy_api import (
    MIGRATION_DOC_URL,
    CommandComponent,
    Context,
    LegacyContext,
    LegacyConversationManager,
    LegacyStar,
)
from astrbot_sdk.api.event.filter import (
    llm_tool,
    on_llm_request,
    on_llm_response,
    on_llm_tool_respond,
    on_using_llm_tool,
)
from astrbot_sdk.api.message import Comp, MessageChain
from astrbot_sdk.api.provider.entities import LLMResponse
from astrbot_sdk.star import Star


class TestLegacyContext:
    """Tests for LegacyContext."""

    def test_init_with_plugin_id(self):
        """LegacyContext should store plugin_id."""
        ctx = LegacyContext("test_plugin")
        assert ctx.plugin_id == "test_plugin"

    def test_has_conversation_manager(self):
        """LegacyContext should have conversation_manager."""
        ctx = LegacyContext("test_plugin")
        assert hasattr(ctx, "conversation_manager")
        assert isinstance(ctx.conversation_manager, LegacyConversationManager)

    def test_require_runtime_context_raises_when_not_bound(self):
        """require_runtime_context() should raise when not bound."""
        ctx = LegacyContext("test_plugin")
        with pytest.raises(RuntimeError, match="尚未绑定运行时 Context"):
            ctx.require_runtime_context()

    def test_bind_runtime_context(self):
        """bind_runtime_context() should bind a NewContext."""
        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "test"

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.bind_runtime_context(mock_ctx)

        assert legacy_ctx.require_runtime_context() is mock_ctx

    def test_get_config_returns_empty_dict_without_runtime_context(self):
        """get_config() should gracefully degrade before runtime binding."""
        legacy_ctx = LegacyContext("test_plugin")

        assert legacy_ctx.get_config() == {}

    def test_get_config_reads_runtime_context_config_dict(self):
        """get_config() should expose the bound runtime config mapping."""
        mock_ctx = MagicMock()
        mock_ctx._astrbot_config = {"admins_id": ["1001"]}

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.bind_runtime_context(mock_ctx)

        assert legacy_ctx.get_config() == {"admins_id": ["1001"]}

    def test_context_alias_is_legacy_context(self):
        """Context should be an alias for LegacyContext."""
        assert Context is LegacyContext

    def test_auto_registers_conversation_manager_with_legacy_name(self):
        """LegacyContext should expose ConversationManager.* legacy names."""
        ctx = LegacyContext("test_plugin")

        assert (
            ctx._registered_managers["ConversationManager"] is ctx.conversation_manager
        )
        assert "ConversationManager.new_conversation" in ctx._registered_functions

    def test_register_component_skips_property_side_effects(self):
        """_register_component() should not touch unrelated properties."""

        class ComponentWithProperty:
            @property
            def explode(self):
                raise RuntimeError("property should not be touched")

            def greet(self) -> str:
                return "hello"

        ctx = LegacyContext("test_plugin")

        ctx._register_component(ComponentWithProperty())

        assert "ComponentWithProperty.greet" in ctx._registered_functions

    @pytest.mark.asyncio
    async def test_call_context_function_wraps_registered_result(self):
        """call_context_function() should preserve the legacy {data: ...} shape."""

        class SyncComponent:
            def greet(self, name: str) -> str:
                return f"hello {name}"

        ctx = LegacyContext("test_plugin")
        ctx._register_component(SyncComponent())

        result = await ctx.call_context_function(
            "SyncComponent.greet",
            {"name": "astrbot"},
        )

        assert result == {"data": "hello astrbot"}

    @pytest.mark.asyncio
    async def test_execute_registered_function_supports_async_methods(self):
        """execute_registered_function() should await async component methods."""

        class AsyncComponent:
            async def double(self, value: int) -> int:
                return value * 2

        ctx = LegacyContext("test_plugin")
        ctx._register_component(AsyncComponent())

        result = await ctx.execute_registered_function(
            "AsyncComponent.double",
            {"value": 21},
        )

        assert result == 42


class TestLegacyConversationManager:
    """Tests for LegacyConversationManager."""

    def test_init_with_parent(self):
        """LegacyConversationManager should store parent reference."""
        parent = LegacyContext("test_plugin")
        manager = LegacyConversationManager(parent)
        assert manager._parent is parent

    @pytest.mark.asyncio
    async def test_new_conversation_creates_id(self):
        """new_conversation() should create a conversation ID."""
        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = AsyncMock()
        mock_ctx.db.get = AsyncMock(return_value=None)
        mock_ctx.db.set = AsyncMock()

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx

        conv_id = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-1"
        )

        assert conv_id.startswith("my_plugin-conv-")
        assert conv_id.endswith("-1")

    @pytest.mark.asyncio
    async def test_new_conversation_stores_metadata(self):
        """new_conversation() should store conversation metadata."""
        stored_data = {}

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_set(key, value):
            stored_data[key] = value

        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = MagicMock()
        mock_ctx.db.get = mock_get
        mock_ctx.db.set = mock_set

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx

        conv_id = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-1",
            platform_id="telegram",
            title="Test Chat",
            persona_id="assistant",
        )

        # Verify stored data
        assert "__compat_conversations__" in stored_data
        assert conv_id in stored_data["__compat_conversations__"]
        data = stored_data["__compat_conversations__"][conv_id]
        assert data["platform_id"] == "telegram"
        assert data["title"] == "Test Chat"
        assert data["persona_id"] == "assistant"

    @pytest.mark.asyncio
    async def test_new_conversation_increments_counter(self):
        """new_conversation() should keep conversation IDs unique within a plugin."""
        stored_data = {}

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_set(key, value):
            stored_data[key] = value

        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = MagicMock()
        mock_ctx.db.get = mock_get
        mock_ctx.db.set = mock_set

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx

        id1 = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-1"
        )
        id2 = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-1"
        )
        id3 = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-2"
        )

        assert id1.endswith("-1")
        assert id2.endswith("-2")
        assert id3.endswith("-3")
        assert len({id1, id2, id3}) == 3

    @pytest.mark.asyncio
    async def test_new_conversation_skips_persisted_id_collisions(self):
        """new_conversation() should not reuse IDs that already exist in storage."""
        stored_data = {
            "__compat_conversations__": {
                "my_plugin-conv-1": {"unified_msg_origin": "session-1"},
            }
        }

        async def mock_get(key):
            return stored_data.get(key)

        async def mock_set(key, value):
            stored_data[key] = value

        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = MagicMock()
        mock_ctx.db.get = mock_get
        mock_ctx.db.set = mock_set

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx

        conv_id = await legacy_ctx.conversation_manager.new_conversation(
            unified_msg_origin="session-1"
        )

        assert conv_id == "my_plugin-conv-2"

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_filters_by_keyword(self):
        """get_filtered_conversations() should search over stored conversation payloads."""
        stored_data = {
            "__compat_conversations__": {
                "conv-1": {
                    "unified_msg_origin": "session-1",
                    "platform_id": "qq",
                    "content": [{"role": "user", "content": "hello astrbot"}],
                },
                "conv-2": {
                    "unified_msg_origin": "session-1",
                    "platform_id": "qq",
                    "content": [{"role": "user", "content": "other topic"}],
                },
            }
        }

        async def mock_get(key):
            return stored_data.get(key)

        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = MagicMock()
        mock_ctx.db.get = mock_get

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx

        result = await legacy_ctx.conversation_manager.get_filtered_conversations(
            unified_msg_origin="session-1",
            keyword="astrbot",
        )

        assert [item["conversation_id"] for item in result] == ["conv-1"]

    @pytest.mark.asyncio
    async def test_get_human_readable_context_renders_conversation_content(self):
        """get_human_readable_context() should render stored message pairs as readable text."""
        stored_data = {
            "__compat_conversations__": {
                "conv-1": {
                    "unified_msg_origin": "session-1",
                    "content": [
                        {"role": "user", "content": "hello"},
                        {"role": "assistant", "content": "world"},
                    ],
                }
            }
        }

        async def mock_get(key):
            return stored_data.get(key)

        mock_ctx = MagicMock()
        mock_ctx.plugin_id = "my_plugin"
        mock_ctx.db = MagicMock()
        mock_ctx.db.get = mock_get

        legacy_ctx = LegacyContext("my_plugin")
        legacy_ctx._runtime_context = mock_ctx
        legacy_ctx.conversation_manager._current_conversations["session-1"] = "conv-1"

        result = await legacy_ctx.conversation_manager.get_human_readable_context(
            unified_msg_origin="session-1"
        )

        assert result == "user: hello\nassistant: world"


class TestLegacyContextMethods:
    """Tests for LegacyContext methods that delegate to NewContext."""

    @pytest.mark.asyncio
    async def test_put_kv_data(self):
        """put_kv_data() should delegate to db.set()."""
        mock_db = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.db = mock_db

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.put_kv_data("test_key", {"value": 123})

        mock_db.set.assert_called_once_with("test_key", {"value": 123})

    @pytest.mark.asyncio
    async def test_put_kv_data_accepts_scalar_value(self):
        """put_kv_data() should support scalar JSON values."""
        mock_db = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.db = mock_db

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.put_kv_data("greeted", True)

        mock_db.set.assert_called_once_with("greeted", True)

    @pytest.mark.asyncio
    async def test_get_kv_data(self):
        """get_kv_data() should delegate to db.get()."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value={"data": "hello"})

        mock_ctx = MagicMock()
        mock_ctx.db = mock_db

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        result = await legacy_ctx.get_kv_data("my_key")

        mock_db.get.assert_called_once_with("my_key")
        assert result == {"data": "hello"}

    @pytest.mark.asyncio
    async def test_get_kv_data_returns_default_when_missing(self):
        """get_kv_data() should honor the legacy default parameter."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        mock_ctx = MagicMock()
        mock_ctx.db = mock_db

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        result = await legacy_ctx.get_kv_data("missing", False)

        mock_db.get.assert_called_once_with("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_kv_data(self):
        """delete_kv_data() should delegate to db.delete()."""
        mock_db = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.db = mock_db

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.delete_kv_data("to_delete")

        mock_db.delete.assert_called_once_with("to_delete")


class TestLegacyContextSendMessage:
    """Tests for LegacyContext.send_message()."""

    @pytest.mark.asyncio
    async def test_send_message_with_plain_string(self):
        """send_message() should handle plain string."""
        mock_platform = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.platform = mock_platform

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.send_message("session-1", "hello world")

        mock_platform.send.assert_called_once_with("session-1", "hello world")

    @pytest.mark.asyncio
    async def test_send_message_with_get_plain_text_method(self):
        """send_message() should use get_plain_text() if available."""

        class MockMessageChain:
            def get_plain_text(self):
                return "extracted text"

        mock_platform = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.platform = mock_platform

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.send_message("session-1", MockMessageChain())

        mock_platform.send.assert_called_once_with("session-1", "extracted text")

    @pytest.mark.asyncio
    async def test_send_message_with_message_chain_uses_send_chain(self):
        """send_message() should preserve rich chains when MessageChain is available."""
        mock_platform = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.platform = mock_platform

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        chain = MessageChain(
            [
                Comp.Plain(text="hello"),
                Comp.Image(file="https://example.com/image.png"),
            ]
        )

        await legacy_ctx.send_message("session-1", chain)

        mock_platform.send_chain.assert_called_once_with(
            "session-1",
            [
                {"type": "Plain", "text": "hello"},
                {"type": "Image", "file": "https://example.com/image.png"},
            ],
        )

    @pytest.mark.asyncio
    async def test_send_message_with_to_text_method(self):
        """send_message() should use to_text() if get_plain_text() not available."""

        class MockMessageChain:
            def to_text(self):
                return "to_text result"

        mock_platform = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.platform = mock_platform

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.send_message("session-1", MockMessageChain())

        mock_platform.send.assert_called_once_with("session-1", "to_text result")

    @pytest.mark.asyncio
    async def test_send_message_falls_back_to_str(self):
        """send_message() should fall back to str() if no text method."""

        class MockObject:
            def __str__(self):
                return "stringified"

        mock_platform = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.platform = mock_platform

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        await legacy_ctx.send_message("session-1", MockObject())

        mock_platform.send.assert_called_once_with("session-1", "stringified")


class TestLegacyContextLLMMethods:
    """Tests for LegacyContext LLM methods."""

    @pytest.mark.asyncio
    async def test_llm_generate_returns_compat_response_and_applies_hook_mutation(self):
        """llm_generate() should return legacy LLMResponse and honor hook-mutated request data."""
        mock_llm = AsyncMock()
        mock_llm.chat_raw = AsyncMock(
            return_value={"role": "assistant", "text": "response"}
        )

        mock_ctx = MagicMock()
        mock_ctx.llm = mock_llm

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        seen_completion_texts = []

        class CompatHooks:
            @on_llm_request()
            async def mutate_request(self, request):
                request.model = "hook-model"

            @on_llm_response()
            async def capture_response(self, response: LLMResponse):
                seen_completion_texts.append(response.completion_text)

        legacy_ctx._register_component(CompatHooks())

        result = await legacy_ctx.llm_generate(
            chat_provider_id="provider-1",
            prompt="hello",
            system_prompt="be helpful",
            contexts=[{"role": "user", "content": "hi"}],
        )

        mock_llm.chat_raw.assert_called_once()
        call_kwargs = mock_llm.chat_raw.call_args[1]
        assert call_kwargs["provider_id"] == "provider-1"
        assert call_kwargs["model"] == "hook-model"
        assert isinstance(result, LLMResponse)
        assert result.completion_text == "response"
        assert result.text == "response"
        assert seen_completion_texts == ["response"]

    @pytest.mark.asyncio
    async def test_tool_loop_agent_runs_registered_compat_tools(self):
        """tool_loop_agent() should execute registered compat llm tools and continue the loop."""
        mock_llm = AsyncMock()
        mock_llm.chat_raw = AsyncMock(
            side_effect=[
                {
                    "role": "assistant",
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "math.add",
                                "arguments": '{"a": 1, "b": 2}',
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "text": "result ready",
                },
            ]
        )

        mock_ctx = MagicMock()
        mock_ctx.llm = mock_llm

        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx._runtime_context = mock_ctx

        seen_tool_events = []

        class CompatToolComponent:
            @llm_tool(name="math.add")
            async def add(self, a: int, b: int):
                return str(a + b)

            @on_using_llm_tool()
            async def before_tool(self, tool_args):
                seen_tool_events.append(("before", dict(tool_args)))

            @on_llm_tool_respond()
            async def after_tool(self, tool_result):
                seen_tool_events.append(("after", tool_result))

        legacy_ctx._register_component(CompatToolComponent())

        result = await legacy_ctx.tool_loop_agent(
            chat_provider_id="provider-1",
            prompt="hello",
            max_steps=10,
        )

        assert mock_llm.chat_raw.await_count == 2
        first_call = mock_llm.chat_raw.await_args_list[0]
        second_call = mock_llm.chat_raw.await_args_list[1]
        assert first_call.kwargs["provider_id"] == "provider-1"
        assert first_call.kwargs["max_steps"] == 10
        assert second_call.kwargs["history"][-1] == {
            "role": "tool",
            "tool_call_id": "call-1",
            "name": "math.add",
            "content": "3",
        }
        assert isinstance(result, LLMResponse)
        assert result.completion_text == "result ready"
        assert result.text == "result ready"
        assert seen_tool_events == [
            ("before", {"a": 1, "b": 2}),
            ("after", "3"),
        ]

    @pytest.mark.asyncio
    async def test_add_llm_tools_registers_compat_tool_object(self):
        """add_llm_tools() should accept legacy tool objects and expose them via the tool manager."""
        legacy_ctx = LegacyContext("test_plugin")

        class ToolObject:
            name = "demo.echo"
            description = "Echo input"
            parameters = {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }

            async def handler(self, text: str) -> str:
                return text

        await legacy_ctx.add_llm_tools(ToolObject())

        manager = legacy_ctx.get_llm_tool_manager()
        tool = manager.get_func("demo.echo")

        assert tool is not None
        assert tool.description == "Echo input"
        assert tool.parameters["required"] == ["text"]


class TestCommandComponent:
    """Tests for CommandComponent."""

    def test_is_star_subclass(self):
        """CommandComponent should be a Star subclass."""
        assert issubclass(CommandComponent, Star)

    def test_is_not_new_star(self):
        """CommandComponent should NOT be recognized as new-style star."""
        assert CommandComponent.__astrbot_is_new_star__() is False

    def test_create_legacy_context(self):
        """_astrbot_create_legacy_context() should create LegacyContext."""
        ctx = CommandComponent._astrbot_create_legacy_context("my_plugin")
        assert isinstance(ctx, LegacyContext)
        assert ctx.plugin_id == "my_plugin"


class TestLegacyStarDelegation:
    """Tests for LegacyStar methods that proxy to LegacyContext."""

    @pytest.mark.asyncio
    async def test_put_kv_data_delegates_to_context(self):
        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.put_kv_data = AsyncMock()
        star = LegacyStar(legacy_ctx)

        await star.put_kv_data("key", 1)

        legacy_ctx.put_kv_data.assert_awaited_once_with("key", 1)

    @pytest.mark.asyncio
    async def test_get_kv_data_delegates_to_context(self):
        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.get_kv_data = AsyncMock(return_value=True)
        star = LegacyStar(legacy_ctx)

        result = await star.get_kv_data("key", False)

        legacy_ctx.get_kv_data.assert_awaited_once_with("key", False)
        assert result is True

    def test_get_config_delegates_to_context(self):
        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.get_config = MagicMock(return_value={"admins_id": ["42"]})
        star = LegacyStar(legacy_ctx)

        assert star.get_config() == {"admins_id": ["42"]}

    def test_get_config_works_when_subclass_does_not_call_super_init(self):
        """LegacyStar proxy should stay lazy for old plugins that skip super().__init__()."""
        legacy_ctx = LegacyContext("test_plugin")
        legacy_ctx.get_config = MagicMock(return_value={"admins_id": ["7"]})

        class LegacySubclass(LegacyStar):
            def __init__(self, context):
                self.context = context

        star = LegacySubclass(legacy_ctx)

        assert star.get_config() == {"admins_id": ["7"]}


class TestMigrationDocUrl:
    """Tests for migration documentation URL."""

    def test_migration_doc_url_exists(self):
        """MIGRATION_DOC_URL should be defined."""
        assert MIGRATION_DOC_URL is not None
        assert "docs.astrbot.app" in MIGRATION_DOC_URL
