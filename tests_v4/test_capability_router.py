"""
Tests for runtime/capability_router.py - CapabilityRouter implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
)
from astrbot_sdk.runtime.capability_router import (
    CAPABILITY_NAME_PATTERN,
    RESERVED_CAPABILITY_PREFIXES,
    StreamExecution,
    _CapabilityRegistration,
)
from astrbot_sdk.runtime.capability_router import CapabilityRouter


class TestStreamExecution:
    """Tests for StreamExecution dataclass."""

    def test_init(self):
        """StreamExecution should store iterator and finalize."""

        async def gen():
            yield {"text": "a"}

        def fin(chunks):
            return {"count": len(chunks)}

        execution = StreamExecution(iterator=gen(), finalize=fin)
        assert execution.iterator is not None
        assert execution.finalize is fin


class TestCapabilityRegistration:
    """Tests for _CapabilityRegistration dataclass."""

    def test_init(self):
        """_CapabilityRegistration should store all fields."""
        descriptor = CapabilityDescriptor(name="test.cap", description="Test")
        call_handler = AsyncMock()

        reg = _CapabilityRegistration(
            descriptor=descriptor,
            call_handler=call_handler,
            exposed=True,
        )

        assert reg.descriptor == descriptor
        assert reg.call_handler == call_handler
        assert reg.stream_handler is None
        assert reg.finalize is None
        assert reg.exposed is True

    def test_defaults(self):
        """_CapabilityRegistration should have correct defaults."""
        descriptor = CapabilityDescriptor(name="test.cap", description="Test")

        reg = _CapabilityRegistration(descriptor=descriptor)

        assert reg.call_handler is None
        assert reg.stream_handler is None
        assert reg.finalize is None
        assert reg.exposed is True


class TestCapabilityNamePattern:
    """Tests for capability name validation pattern."""

    def test_valid_names(self):
        """Valid capability names should match pattern."""
        valid_names = [
            "llm.chat",
            "db.get",
            "memory.search",
            "platform.send",
            "a.b",
            "my_module.my_method",
            "ns123.method456",
        ]
        for name in valid_names:
            assert CAPABILITY_NAME_PATTERN.fullmatch(name), f"{name} should be valid"

    def test_invalid_names(self):
        """Invalid capability names should not match pattern."""
        invalid_names = [
            "llm",  # No dot
            "LLM.chat",  # Uppercase
            "llm.Chat",  # Uppercase method
            "llm.chat.extra",  # Too many parts
            "1llm.chat",  # Starts with number
            "llm.1chat",  # Method starts with number
            ".chat",  # Empty namespace
            "llm.",  # Empty method
            "llm-chat",  # Hyphen instead of dot
        ]
        for name in invalid_names:
            assert not CAPABILITY_NAME_PATTERN.fullmatch(name), (
                f"{name} should be invalid"
            )


class TestReservedCapabilityPrefixes:
    """Tests for reserved capability prefixes."""

    def test_reserved_prefixes(self):
        """Reserved prefixes should be defined."""
        assert "handler." in RESERVED_CAPABILITY_PREFIXES
        assert "system." in RESERVED_CAPABILITY_PREFIXES
        assert "internal." in RESERVED_CAPABILITY_PREFIXES

    def test_reserved_names_are_detected(self):
        """Reserved names should be detected by startswith."""
        reserved_names = [
            "handler.demo",
            "system.health",
            "internal.trace",
        ]
        for name in reserved_names:
            assert any(
                name.startswith(prefix) for prefix in RESERVED_CAPABILITY_PREFIXES
            ), f"{name} should be reserved"


class TestCapabilityRouterInit:
    """Tests for CapabilityRouter initialization."""

    def test_init_creates_empty_stores(self):
        """CapabilityRouter should start with empty stores."""
        router = CapabilityRouter()
        # _registrations 会有内置 capabilities，但 stores 应该为空
        assert router.db_store == {}
        assert router.memory_store == {}
        assert router.sent_messages == []

    def test_init_registers_builtin_capabilities(self):
        """CapabilityRouter should register built-in capabilities on init."""
        router = CapabilityRouter()
        descriptors = router.descriptors()

        capability_names = [d.name for d in descriptors]

        # LLM capabilities
        assert "llm.chat" in capability_names
        assert "llm.chat_raw" in capability_names
        assert "llm.stream_chat" in capability_names

        # Memory capabilities
        assert "memory.search" in capability_names
        assert "memory.save" in capability_names
        assert "memory.get" in capability_names
        assert "memory.delete" in capability_names

        # DB capabilities
        assert "db.get" in capability_names
        assert "db.set" in capability_names
        assert "db.delete" in capability_names
        assert "db.list" in capability_names

        # Platform capabilities
        assert "platform.send" in capability_names
        assert "platform.send_image" in capability_names
        assert "platform.get_members" in capability_names

    def test_builtin_descriptors_use_protocol_schema_registry(self):
        """CapabilityRouter should source built-in schemas from protocol constants."""
        router = CapabilityRouter()
        descriptors = {
            descriptor.name: descriptor for descriptor in router.descriptors()
        }

        for name, schema in BUILTIN_CAPABILITY_SCHEMAS.items():
            assert descriptors[name].input_schema == schema["input"]
            assert descriptors[name].output_schema == schema["output"]


class TestCapabilityRouterRegister:
    """Tests for CapabilityRouter.register method."""

    def test_register_adds_capability(self):
        """register should add capability to registrations."""
        router = CapabilityRouter()
        descriptor = CapabilityDescriptor(name="test.cap", description="Test")

        router.register(descriptor)

        assert "test.cap" in router._registrations
        assert router._registrations["test.cap"].descriptor == descriptor

    def test_register_with_handlers(self):
        """register should store handlers."""
        router = CapabilityRouter()
        descriptor = CapabilityDescriptor(name="test.cap", description="Test")

        async def call_handler(req_id, payload, token):
            return {"result": "ok"}

        async def stream_handler(req_id, payload, token):
            yield {"chunk": 1}

        def finalize(chunks):
            return {"count": len(chunks)}

        router.register(
            descriptor,
            call_handler=call_handler,
            stream_handler=stream_handler,
            finalize=finalize,
        )

        reg = router._registrations["test.cap"]
        assert reg.call_handler == call_handler
        assert reg.stream_handler == stream_handler
        assert reg.finalize == finalize

    def test_register_invalid_name_raises(self):
        """register should reject invalid capability names."""
        router = CapabilityRouter()

        with pytest.raises(ValueError, match="capability 名称必须匹配"):
            router.register(CapabilityDescriptor(name="invalid", description="Bad"))

    def test_register_reserved_name_raises(self):
        """register should reject reserved names for exposed registrations."""
        router = CapabilityRouter()

        with pytest.raises(ValueError, match="保留 capability"):
            router.register(
                CapabilityDescriptor(name="handler.demo", description="Reserved")
            )

    def test_register_reserved_name_allowed_for_internal(self):
        """register should allow reserved names for internal (exposed=False)."""
        router = CapabilityRouter()

        # Should not raise
        router.register(
            CapabilityDescriptor(name="handler.internal", description="Internal"),
            exposed=False,
        )

        # Should not appear in descriptors
        names = [d.name for d in router.descriptors()]
        assert "handler.internal" not in names

    def test_descriptors_only_returns_exposed(self):
        """descriptors should only return exposed capabilities."""
        router = CapabilityRouter()

        router.register(
            CapabilityDescriptor(name="exposed.cap", description="Exposed"),
            exposed=True,
        )
        router.register(
            CapabilityDescriptor(name="hidden.cap", description="Hidden"),
            exposed=False,
        )

        names = [d.name for d in router.descriptors()]
        assert "exposed.cap" in names
        assert "hidden.cap" not in names


class TestCapabilityRouterExecute:
    """Tests for CapabilityRouter.execute method."""

    @pytest.mark.asyncio
    async def test_execute_calls_handler(self):
        """execute should call the registered handler."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(name="test.cap", description="Test"),
            call_handler=AsyncMock(return_value={"result": "ok"}),
        )

        token = CancelToken()
        result = await router.execute(
            "test.cap",
            {},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_execute_validates_input_schema(self):
        """execute should validate input against schema."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="test.cap",
                description="Test",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            call_handler=AsyncMock(return_value={}),
        )

        token = CancelToken()

        # Missing required field
        with pytest.raises(AstrBotError, match="缺少必填字段"):
            await router.execute(
                "test.cap",
                {},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_execute_validates_output_schema(self):
        """execute should validate output against schema."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="test.cap",
                description="Test",
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                    "required": ["result"],
                },
            ),
            call_handler=AsyncMock(return_value={}),  # Missing required field
        )

        token = CancelToken()

        with pytest.raises(AstrBotError, match="缺少必填字段"):
            await router.execute(
                "test.cap",
                {},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_execute_missing_capability_raises(self):
        """execute should raise for unknown capability."""
        router = CapabilityRouter()
        token = CancelToken()

        with pytest.raises(AstrBotError, match="未找到能力"):
            await router.execute(
                "unknown.cap",
                {},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_execute_stream_returns_stream_execution(self):
        """execute with stream=True should return StreamExecution."""
        router = CapabilityRouter()

        async def stream_handler(req_id, payload, token):
            yield {"chunk": 1}
            yield {"chunk": 2}

        router.register(
            CapabilityDescriptor(
                name="test.stream",
                description="Test",
                supports_stream=True,
            ),
            stream_handler=stream_handler,
        )

        token = CancelToken()
        result = await router.execute(
            "test.stream",
            {},
            stream=True,
            cancel_token=token,
            request_id="req-1",
        )

        assert isinstance(result, StreamExecution)

    @pytest.mark.asyncio
    async def test_execute_stream_without_handler_raises(self):
        """execute with stream=True and no stream_handler should raise."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(name="test.cap", description="Test"),
            call_handler=AsyncMock(return_value={}),
        )

        token = CancelToken()

        with pytest.raises(AstrBotError, match="不支持 stream=true"):
            await router.execute(
                "test.cap",
                {},
                stream=True,
                cancel_token=token,
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_execute_call_without_handler_raises(self):
        """execute without stream and no call_handler should raise."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(
                name="test.stream_only",
                description="Stream only",
                supports_stream=True,
            ),
            stream_handler=AsyncMock(),
        )

        token = CancelToken()

        with pytest.raises(AstrBotError, match="只能以 stream=true 调用"):
            await router.execute(
                "test.stream_only",
                {},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )


class TestBuiltinLlmCapabilities:
    """Tests for built-in LLM capabilities."""

    @pytest.mark.asyncio
    async def test_llm_chat(self):
        """llm.chat should return echo response."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "llm.chat",
            {"prompt": "hello"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert result["text"] == "Echo: hello"

    @pytest.mark.asyncio
    async def test_llm_chat_raw(self):
        """llm.chat_raw should return full response."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "llm.chat_raw",
            {"prompt": "test"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert result["text"] == "Echo: test"
        assert "usage" in result
        assert "finish_reason" in result
        assert "tool_calls" in result

    @pytest.mark.asyncio
    async def test_llm_stream_chat(self):
        """llm.stream_chat should yield characters."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "llm.stream_chat",
            {"prompt": "hi"},
            stream=True,
            cancel_token=token,
            request_id="req-1",
        )

        assert isinstance(result, StreamExecution)

        chunks = []
        async for chunk in result.iterator:
            chunks.append(chunk)

        # Should yield each character
        text = "".join(c.get("text", "") for c in chunks)
        assert text == "Echo: hi"


class TestBuiltinMemoryCapabilities:
    """Tests for built-in memory capabilities."""

    @pytest.mark.asyncio
    async def test_memory_save_and_get(self):
        """memory.save and memory.get should work together."""
        router = CapabilityRouter()
        token = CancelToken()

        # Save
        await router.execute(
            "memory.save",
            {"key": "test_key", "value": {"data": "test_value"}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        # Get
        result = await router.execute(
            "memory.get",
            {"key": "test_key"},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )

        assert result["value"] == {"data": "test_value"}

    @pytest.mark.asyncio
    async def test_memory_save_and_search(self):
        """memory.save and memory.search should work together."""
        router = CapabilityRouter()
        token = CancelToken()

        await router.execute(
            "memory.save",
            {"key": "test_key", "value": {"data": "test_value"}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        result = await router.execute(
            "memory.search",
            {"query": "test"},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )

        assert len(result["items"]) == 1
        assert result["items"][0]["key"] == "test_key"

    @pytest.mark.asyncio
    async def test_memory_get_missing_key(self):
        """memory.get should return None for missing key."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "memory.get",
            {"key": "missing"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert result["value"] is None

    @pytest.mark.asyncio
    async def test_memory_delete(self):
        """memory.delete should remove saved memory."""
        router = CapabilityRouter()
        token = CancelToken()

        # Save
        await router.execute(
            "memory.save",
            {"key": "to_delete", "value": {"data": "value"}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        # Delete
        await router.execute(
            "memory.delete",
            {"key": "to_delete"},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )

        # Search should return empty
        result = await router.execute(
            "memory.search",
            {"query": "to_delete"},
            stream=False,
            cancel_token=token,
            request_id="req-3",
        )

        assert len(result["items"]) == 0

    @pytest.mark.asyncio
    async def test_memory_save_invalid_value(self):
        """memory.save should reject non-object value."""
        router = CapabilityRouter()
        token = CancelToken()

        with pytest.raises(AstrBotError, match="value 必须是 object"):
            await router.execute(
                "memory.save",
                {"key": "test", "value": "not_an_object"},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )


class TestBuiltinDbCapabilities:
    """Tests for built-in DB capabilities."""

    @pytest.mark.asyncio
    async def test_db_set_and_get(self):
        """db.set and db.get should work together."""
        router = CapabilityRouter()
        token = CancelToken()

        # Set
        await router.execute(
            "db.set",
            {"key": "test_key", "value": {"data": "test_value"}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        # Get
        result = await router.execute(
            "db.get",
            {"key": "test_key"},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )

        assert result["value"] == {"data": "test_value"}

    @pytest.mark.asyncio
    async def test_db_get_missing_key(self):
        """db.get should return None for missing key."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "db.get",
            {"key": "nonexistent"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert result["value"] is None

    @pytest.mark.asyncio
    async def test_db_delete(self):
        """db.delete should remove stored value."""
        router = CapabilityRouter()
        token = CancelToken()

        # Set
        await router.execute(
            "db.set",
            {"key": "to_delete", "value": {"data": "value"}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        # Delete
        await router.execute(
            "db.delete",
            {"key": "to_delete"},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )

        # Get should return None
        result = await router.execute(
            "db.get",
            {"key": "to_delete"},
            stream=False,
            cancel_token=token,
            request_id="req-3",
        )

        assert result["value"] is None

    @pytest.mark.asyncio
    async def test_db_list(self):
        """db.list should return keys."""
        router = CapabilityRouter()
        token = CancelToken()

        # Set multiple keys
        await router.execute(
            "db.set",
            {"key": "prefix_a", "value": {}},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )
        await router.execute(
            "db.set",
            {"key": "prefix_b", "value": {}},
            stream=False,
            cancel_token=token,
            request_id="req-2",
        )
        await router.execute(
            "db.set",
            {"key": "other", "value": {}},
            stream=False,
            cancel_token=token,
            request_id="req-3",
        )

        # List all
        result = await router.execute(
            "db.list",
            {},
            stream=False,
            cancel_token=token,
            request_id="req-4",
        )

        assert "prefix_a" in result["keys"]
        assert "prefix_b" in result["keys"]
        assert "other" in result["keys"]

        # List with prefix
        result = await router.execute(
            "db.list",
            {"prefix": "prefix_"},
            stream=False,
            cancel_token=token,
            request_id="req-5",
        )

        assert "prefix_a" in result["keys"]
        assert "prefix_b" in result["keys"]
        assert "other" not in result["keys"]

    @pytest.mark.asyncio
    async def test_db_set_invalid_value(self):
        """db.set should reject non-object value."""
        router = CapabilityRouter()
        token = CancelToken()

        with pytest.raises(AstrBotError, match="value 必须是 object"):
            await router.execute(
                "db.set",
                {"key": "test", "value": "not_an_object"},
                stream=False,
                cancel_token=token,
                request_id="req-1",
            )


class TestBuiltinPlatformCapabilities:
    """Tests for built-in platform capabilities."""

    @pytest.mark.asyncio
    async def test_platform_send(self):
        """platform.send should store message."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "platform.send",
            {"session": "session-1", "text": "Hello"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert "message_id" in result
        assert len(router.sent_messages) == 1
        assert router.sent_messages[0]["session"] == "session-1"
        assert router.sent_messages[0]["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_platform_send_image(self):
        """platform.send_image should store image message."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "platform.send_image",
            {"session": "session-1", "image_url": "http://example.com/image.png"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert "message_id" in result
        assert len(router.sent_messages) == 1
        assert router.sent_messages[0]["image_url"] == "http://example.com/image.png"

    @pytest.mark.asyncio
    async def test_platform_get_members(self):
        """platform.get_members should return mock members."""
        router = CapabilityRouter()
        token = CancelToken()

        result = await router.execute(
            "platform.get_members",
            {"session": "session-1"},
            stream=False,
            cancel_token=token,
            request_id="req-1",
        )

        assert len(result["members"]) == 2
        assert result["members"][0]["user_id"] == "session-1:member-1"


class TestValidateSchema:
    """Tests for _validate_schema method."""

    @pytest.mark.asyncio
    async def test_none_schema_passes(self):
        """_validate_schema with None schema should pass."""
        router = CapabilityRouter()

        # Should not raise
        router._validate_schema(None, {"any": "data"})

    @pytest.mark.asyncio
    async def test_non_object_payload_raises(self):
        """_validate_schema should reject non-object when schema type is object."""
        router = CapabilityRouter()

        with pytest.raises(AstrBotError, match="输入必须是 object"):
            router._validate_schema({"type": "object"}, "not an object")

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self):
        """_validate_schema should reject missing required fields."""
        router = CapabilityRouter()

        with pytest.raises(AstrBotError, match="缺少必填字段"):
            router._validate_schema(
                {"type": "object", "required": ["name"]},
                {},
            )

    @pytest.mark.asyncio
    async def test_none_required_field_raises(self):
        """_validate_schema should reject None required fields."""
        router = CapabilityRouter()

        with pytest.raises(AstrBotError, match="缺少必填字段"):
            router._validate_schema(
                {"type": "object", "required": ["name"]},
                {"name": None},
            )
