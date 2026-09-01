"""Tests for astr_main_agent module."""

import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core import astr_main_agent as ama
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message, TextPart, dump_messages_with_checkpoints
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.conversation_models import Conversation
from astrbot.core.message.components import Face, Image, Json, Plain, Reply, Video
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider import Provider
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.skills.skill_manager import SkillInfo
from astrbot.core.star.star import StarMetadata


@pytest.fixture
def mock_provider():
    """Create a mock provider."""
    provider = MagicMock(spec=Provider)
    provider.provider_config = {
        "id": "test-provider",
        "modalities": ["image", "tool_use"],
    }
    provider.get_model.return_value = "gpt-4"
    return provider


@pytest.fixture
def mock_context():
    """Create a mock Context."""
    ctx = MagicMock()
    ctx.get_config.return_value = {}
    ctx.conversation_manager = MagicMock()
    ctx.persona_manager = MagicMock()
    ctx.persona_manager.runtime_personas = []
    ctx.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, None, False)
    )
    ctx.persona_manager.get_runtime_persona_by_id = MagicMock(return_value=None)
    tool_mgr = MagicMock()
    tool_mgr.get_builtin_tool.side_effect = lambda cls, **kwargs: cls(**kwargs)
    ctx.get_llm_tool_manager.return_value = tool_mgr
    ctx.subagent_orchestrator = None
    ctx.catalogs = RuntimeCatalogs()
    ctx.skill_manager = None
    return ctx


@pytest.fixture
def mock_event():
    """Create a mock AstrMessageEvent."""
    platform_meta = PlatformMetadata(
        id="test_platform",
        name="test_platform",
        description="Test platform",
    )
    message_obj = MagicMock()
    message_obj.message = [Plain(text="Hello")]
    message_obj.sender = MagicMock(user_id="user123", nickname="TestUser")
    message_obj.group_id = None
    message_obj.group = None

    event = MagicMock(spec=AstrMessageEvent)
    event.message_str = "Hello"
    event.message_obj = message_obj
    event.platform_meta = platform_meta
    event.session_id = "session123"
    event.unified_msg_origin = "test_platform:private:session123"
    event.get_extra.return_value = None
    event.get_platform_name.return_value = "test_platform"
    event.get_platform_id.return_value = "test_platform"
    event.get_group_id.return_value = None
    event.get_sender_name.return_value = "TestUser"
    event.trace = MagicMock()
    event.plugins_name = None
    return event


@pytest.fixture
def mock_conversation():
    """Create a mock conversation."""
    conv = MagicMock(spec=Conversation)
    conv.cid = "conv-id"
    conv.persona_id = None
    conv.history = "[]"
    return conv


def test_provider_supports_modality_requires_explicit_list():
    provider = MagicMock(spec=Provider)

    provider.provider_config = {"modalities": ["text", "image"]}
    assert ama._provider_supports_modality(provider, "image")

    provider.provider_config = {"modalities": ["text"]}
    assert not ama._provider_supports_modality(provider, "image")

    provider.provider_config = {}
    assert not ama._provider_supports_modality(provider, "image")

    provider.provider_config = {"modalities": []}
    assert not ama._provider_supports_modality(provider, "image")

    provider.provider_config = {"modalities": "image"}
    assert not ama._provider_supports_modality(provider, "image")


@pytest.mark.asyncio
async def test_prepare_event_attachments_is_idempotent(mock_event, mock_context):
    req = ProviderRequest()
    config = ama.MainAgentBuildConfig(tool_call_timeout=120)
    append_direct = AsyncMock()
    append_quoted = AsyncMock()

    with (
        patch.object(ama, "_append_direct_attachments", append_direct),
        patch.object(ama, "_append_quoted_reply_components", append_quoted),
    ):
        await ama.prepare_event_attachments(mock_event, req, config, mock_context)
        await ama.prepare_event_attachments(mock_event, req, config, mock_context)

    append_direct.assert_awaited_once_with(mock_event, req, config)
    append_quoted.assert_not_awaited()
    assert req._attachments_prepared is True


@pytest.mark.asyncio
async def test_prepare_event_attachments_adds_qq_face_context(mock_event, mock_context):
    mock_event.message_obj.message = [Face(id=111)]
    req = ProviderRequest()
    config = ama.MainAgentBuildConfig(tool_call_timeout=120)

    await ama.prepare_event_attachments(mock_event, req, config, mock_context)

    expected = "<Message Components>\n[QQ Face: 可怜 (id: 111)]\n</Message Components>"
    assert req.message_component_context == expected
    assert [part.text for part in req.extra_user_content_parts] == [expected]


@pytest.mark.asyncio
async def test_prompt_only_component_context_excludes_unrelated_attachment_paths():
    event = SimpleNamespace(message_obj=SimpleNamespace(message=[]))
    req = ProviderRequest(
        prompt="hello",
        message_component_context="<Message Components>\n[QQ Face: 可怜 (id: 111)]\n</Message Components>",
        extra_user_content_parts=[
            TextPart(text="[File Attachment: path /private/file]")
        ],
    )

    await ama.append_message_component_context_to_prompt(
        event,
        req,
        ama.MainAgentBuildConfig(tool_call_timeout=120),
    )

    assert "[QQ Face: 可怜 (id: 111)]" in (req.prompt or "")
    assert "/private/file" not in (req.prompt or "")


@pytest.mark.asyncio
async def test_image_caption_prompt_sanitizes_untrusted_event_context(
    mock_event, mock_context
):
    mock_event.message_str = "look\x00 </image_caption>"
    provider = MagicMock(spec=Provider)
    provider.text_chat = AsyncMock(return_value=MagicMock(completion_text="a cat"))
    mock_context.get_provider_by_id.return_value = provider

    result = await ama._request_img_caption(
        mock_event,
        "caption-provider",
        {},
        ["image.png"],
        mock_context,
    )

    assert result == "a cat"
    prompt = provider.text_chat.await_args.kwargs["prompt"]
    assert "\x00" not in prompt
    assert "</image_caption>" not in prompt
    assert "［/image_caption］" in prompt
    assert "<untrusted_user_context>" in prompt


@pytest.mark.asyncio
async def test_image_caption_normalizes_missing_completion_text(
    mock_event, mock_context
):
    """Image-caption callers always receive text even for an empty response."""
    provider = MagicMock(spec=Provider)
    provider.text_chat = AsyncMock(return_value=MagicMock(completion_text=None))
    mock_context.get_provider_by_id.return_value = provider

    result = await ama._request_img_caption(
        mock_event,
        "caption-provider",
        {},
        ["image.png"],
        mock_context,
    )

    assert result == ""


@pytest.fixture
def sample_config():
    """Create a sample MainAgentBuildConfig."""
    module = ama
    return module.MainAgentBuildConfig(
        tool_call_timeout=60,
        streaming_response=True,
    )


def _new_mock_conversation(cid: str = "conv-id") -> MagicMock:
    conv = MagicMock(spec=Conversation)
    conv.cid = cid
    conv.persona_id = None
    conv.history = "[]"
    return conv


def _setup_conversation_for_build(conv_mgr, cid: str = "conv-id") -> MagicMock:
    conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
    conv_mgr.new_conversation = AsyncMock(return_value=cid)
    conversation = _new_mock_conversation(cid=cid)
    conv_mgr.get_conversation = AsyncMock(return_value=conversation)
    return conversation


def test_append_system_reminders_includes_weekday(mock_event):
    """Test datetime reminder includes weekday information."""
    req = ProviderRequest(prompt="Hello")
    fixed_now = datetime.datetime(
        2026,
        6,
        8,
        12,
        34,
        tzinfo=datetime.UTC,
    )

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return fixed_now.astimezone(tz)
            return fixed_now

    with patch("astrbot.core.astr_main_agent.datetime.datetime", FixedDateTime):
        ama._append_system_reminders(
            mock_event,
            req,
            {"datetime_system_prompt": True},
            "UTC",
        )

    assert [part.text for part in req.extra_user_content_parts] == [
        "<system_reminder>Current datetime: "
        "2026-06-08 12:34 (UTC), Weekday: Monday</system_reminder>"
    ]
    assert req.extra_user_content_parts[0].is_temp is False


def test_current_datetime_scope_only_marks_datetime_temp(mock_event):
    """Test current-scope datetime reminder is transient without affecting identity info."""
    req = ProviderRequest(prompt="Hello")
    mock_event.message_obj.group_id = "group123"
    mock_event.message_obj.group = MagicMock(group_name="TestGroup")
    fixed_now = datetime.datetime(
        2026,
        6,
        8,
        12,
        34,
        tzinfo=datetime.UTC,
    )

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return fixed_now.astimezone(tz)
            return fixed_now

    with patch("astrbot.core.astr_main_agent.datetime.datetime", FixedDateTime):
        ama._append_system_reminders(
            mock_event,
            req,
            {
                "datetime_system_prompt": True,
                "datetime_system_prompt_scope": "current",
                "identifier": True,
                "group_name_display": True,
            },
            "UTC",
        )

    parts = req.extra_user_content_parts
    assert [part.text for part in parts] == [
        "<system_reminder>User ID: user123, Nickname: TestUser\n"
        "Group name: TestGroup</system_reminder>",
        "<system_reminder>Current datetime: "
        "2026-06-08 12:34 (UTC), Weekday: Monday</system_reminder>",
    ]
    assert parts[0].is_temp is False
    assert parts[1].is_temp is True


def test_local_mode_prompt_uses_windows_powershell_51():
    with (
        patch("astrbot.core.astr_main_agent.platform.system", return_value="Windows"),
        patch(
            "astrbot.core.astr_main_agent.resolve_windows_shell",
            return_value="powershell.exe",
        ),
    ):
        prompt = ama._build_local_mode_prompt()

    assert "Windows PowerShell 5.1 (powershell.exe)" in prompt
    assert "PowerShell 7-only syntax" in prompt
    assert "cmd.exe" not in prompt


def test_local_mode_prompt_hints_pwsh_when_resolved():
    with (
        patch("astrbot.core.astr_main_agent.platform.system", return_value="Windows"),
        patch(
            "astrbot.core.astr_main_agent.resolve_windows_shell",
            return_value="C:/Program Files/PowerShell/7/pwsh.exe",
        ),
    ):
        prompt = ama._build_local_mode_prompt()

    assert "PowerShell 7 (pwsh.exe)" in prompt
    assert "Windows PowerShell 5.1" not in prompt
    assert "Unix-like" not in prompt


def test_local_mode_prompt_ignores_windows_shell_on_non_windows():
    with patch("astrbot.core.astr_main_agent.platform.system", return_value="Linux"):
        prompt = ama._build_local_mode_prompt()

    assert "Unix-like" in prompt
    assert "POSIX-compatible" in prompt
    assert "PowerShell" not in prompt


class TestMainAgentBuildConfig:
    """Tests for MainAgentBuildConfig dataclass."""

    def test_config_initialization(self):
        """Test MainAgentBuildConfig initialization with defaults."""
        module = ama
        config = module.MainAgentBuildConfig(tool_call_timeout=60)
        assert config.tool_call_timeout == 60
        assert config.tool_schema_mode == "full"
        assert config.streaming_response is True
        assert config.sanitize_context_by_modalities is False
        assert config.kb_agentic_mode is False
        assert config.llm_safety_mode is True

    def test_config_with_custom_values(self):
        """Test MainAgentBuildConfig with custom values."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=120,
            tool_schema_mode="skills-like",
            streaming_response=False,
            kb_agentic_mode=True,
            computer_use_runtime="sandbox",
            add_cron_tools=False,
        )
        assert config.tool_call_timeout == 120
        assert config.tool_schema_mode == "skills-like"
        assert config.streaming_response is False
        assert config.kb_agentic_mode is True
        assert config.computer_use_runtime == "sandbox"
        assert config.add_cron_tools is False


class TestSelectProvider:
    """Tests for _select_provider function."""

    def test_select_provider_by_id(self, mock_event, mock_context, mock_provider):
        """Test selecting provider by ID from event extra."""
        module = ama
        mock_event.get_extra.side_effect = lambda k: (
            "test-provider" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = mock_provider

        result = module._select_provider(mock_event, mock_context)

        assert result == mock_provider
        mock_context.get_provider_by_id.assert_called_once_with("test-provider")

    def test_select_provider_not_found(self, mock_event, mock_context):
        """Test selecting provider when ID is not found."""
        module = ama
        mock_event.get_extra.side_effect = lambda k: (
            "non-existent" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = None

        result = module._select_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            module.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：未找到指定的提供商 `non-existent`。请检查提供商配置或重新选择可用模型。",
        )

    def test_select_provider_invalid_type(self, mock_event, mock_context):
        """Test selecting provider when result is not a Provider instance."""
        module = ama
        mock_event.get_extra.side_effect = lambda k: (
            "invalid" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = "not a provider"

        result = module._select_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            module.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：选择的提供商类型无效（str），已跳过本次请求。",
        )

    def test_select_provider_requires_chat_model_metadata(
        self,
        mock_event,
        mock_context,
    ):
        """A chat model must provide metadata used by Agent telemetry."""
        module = ama
        mock_event.get_extra.side_effect = lambda key: (
            "incomplete" if key == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = SimpleNamespace(
            provider_config={},
            get_model=lambda: "model",
            text_chat=lambda **_: None,
            text_chat_stream=lambda **_: None,
        )

        result = module._select_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_once()

    def test_select_provider_fallback(self, mock_event, mock_context, mock_provider):
        """Test provider selection fallback to using provider."""
        module = ama
        mock_event.get_extra.return_value = None
        mock_context.get_using_provider.return_value = mock_provider

        result = module._select_provider(mock_event, mock_context)

        assert result == mock_provider
        mock_context.get_using_provider.assert_called_once_with(
            umo=mock_event.unified_msg_origin
        )

    def test_select_provider_fallback_error(self, mock_event, mock_context):
        """Test provider selection when fallback raises ValueError."""
        module = ama
        mock_event.get_extra.return_value = None
        mock_context.get_using_provider.side_effect = ValueError("Test error")

        result = module._select_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            module.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：Test error",
        )


class TestGetSessionConv:
    """Tests for _get_session_conv function."""

    @pytest.mark.asyncio
    async def test_get_session_conv_existing(
        self, mock_event, mock_context, mock_conversation
    ):
        """Test getting existing conversation."""
        module = ama
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value="existing-conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=mock_conversation)

        result = await module._get_session_conv(mock_event, mock_context)

        assert result == mock_conversation
        conv_mgr.get_curr_conversation_id.assert_called_once_with(
            mock_event.unified_msg_origin
        )
        conv_mgr.get_conversation.assert_called_once_with(
            mock_event.unified_msg_origin, "existing-conv-id"
        )

    @pytest.mark.asyncio
    async def test_get_session_conv_create_new(self, mock_event, mock_context):
        """Test creating new conversation when none exists."""
        module = ama
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="new-conv-id")
        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.cid = "new-conv-id"
        mock_conversation.persona_id = None
        mock_conversation.history = "[]"
        conv_mgr.get_conversation = AsyncMock(return_value=mock_conversation)

        result = await module._get_session_conv(mock_event, mock_context)

        assert result == mock_conversation
        conv_mgr.new_conversation.assert_called_once_with(
            mock_event.unified_msg_origin, mock_event.get_platform_id()
        )

    @pytest.mark.asyncio
    async def test_get_session_conv_retry(self, mock_event, mock_context):
        """Test retrying conversation creation after failure."""
        module = ama
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="retry-conv-id")
        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.cid = "retry-conv-id"
        mock_conversation.persona_id = None
        mock_conversation.history = "[]"
        conv_mgr.get_conversation.side_effect = [None, mock_conversation]

        result = await module._get_session_conv(mock_event, mock_context)

        assert result == mock_conversation
        assert conv_mgr.new_conversation.call_count == 1
        assert conv_mgr.get_conversation.call_count == 2

    @pytest.mark.asyncio
    async def test_get_session_conv_failure(self, mock_event, mock_context):
        """Test RuntimeError when conversation creation fails."""
        module = ama
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="new-conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="无法创建新的对话。"):
            await module._get_session_conv(mock_event, mock_context)


class TestApplyKb:
    """Tests for _apply_kb function."""

    @pytest.mark.asyncio
    async def test_apply_kb_without_agentic_mode(self, mock_event, mock_context):
        """Test applying knowledge base in non-agentic mode."""
        module = ama
        req = ProviderRequest(prompt="test question", system_prompt="System prompt")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, kb_agentic_mode=False
        )

        with patch(
            "astrbot.core.astr_main_agent.retrieve_knowledge_base",
            AsyncMock(return_value="KB result"),
        ):
            await module._apply_kb(mock_event, req, mock_context, config)

        assert req.system_prompt == "System prompt"
        assert len(req.extra_user_content_parts) == 1
        kb_part = req.extra_user_content_parts[0]
        assert kb_part.text == "[Related Knowledge Base Results]:\nKB result"

        message = Message.model_validate(await req.assemble_context())
        assert isinstance(message.content, list)
        assert message.content[0].text == "test question"
        assert message.content[1].text == "[Related Knowledge Base Results]:\nKB result"
        assert dump_messages_with_checkpoints([message]) == [
            {"role": "user", "content": [{"type": "text", "text": "test question"}]}
        ]

    @pytest.mark.asyncio
    async def test_apply_kb_with_agentic_mode(self, mock_event, mock_context):
        """Test applying knowledge base in agentic mode."""
        module = ama
        req = ProviderRequest(prompt="test question")
        config = module.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=True)

        await module._apply_kb(mock_event, req, mock_context, config)

        assert req.func_tool is not None

    @pytest.mark.asyncio
    async def test_apply_kb_no_prompt(self, mock_event, mock_context):
        """Test applying knowledge base when prompt is None."""
        module = ama
        req = ProviderRequest(prompt=None, system_prompt="System")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, kb_agentic_mode=False
        )

        await module._apply_kb(mock_event, req, mock_context, config)

        assert req.system_prompt == "System"


@pytest.mark.asyncio
async def test_persona_runtime_and_memory_context_are_extra_user_parts(
    mock_event,
    mock_context,
):
    req = ProviderRequest(prompt="hello", conversation=_new_mock_conversation())
    req.system_prompt = ""
    mock_context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(
            "persona-a",
            {
                "name": "persona-a",
                "prompt": "Stable seed.",
                "tools": [],
                "skills": [],
                "_begin_dialogs_processed": [],
                "custom_error_message": None,
            },
            None,
            False,
        )
    )
    tool_mgr = MagicMock()
    tool_mgr.get_full_tool_set.return_value = ToolSet()
    mock_context.get_llm_tool_manager.return_value = tool_mgr

    class RuntimeManager:
        async def inject_context(self, *, req, persona_id, umo):
            req.extra_user_content_parts.append(
                ama.TextPart(
                    text=f"<runtime>{persona_id}:{umo}</runtime>"
                ).mark_as_temp()
            )

    class MemoryManager:
        async def inject_context(self, *, req, event, query=None):
            req.extra_user_content_parts.append(
                ama.TextPart(text=f"<memory>{query}</memory>").mark_as_temp()
            )

    mock_context.persona_runtime_manager = RuntimeManager()
    mock_context.memory_manager = MemoryManager()

    await ama._ensure_persona_and_skills(req, {}, mock_context, mock_event)

    assert "Stable seed." in req.system_prompt
    assert "<runtime>" not in req.system_prompt
    assert "<memory>" not in req.system_prompt
    texts = [part.text for part in req.extra_user_content_parts]
    assert texts == [
        f"<runtime>persona-a:{mock_event.unified_msg_origin}</runtime>",
        "<memory>hello</memory>",
    ]
    assert all(part._no_save for part in req.extra_user_content_parts)


@pytest.mark.asyncio
async def test_memory_retrieval_tools_are_available_for_default_persona(
    mock_event,
    mock_context,
):
    req = ProviderRequest(prompt="hello", conversation=_new_mock_conversation())
    tool_mgr = MagicMock()
    tool_mgr.get_full_tool_set.return_value = ToolSet()
    tool_mgr.get_builtin_tool.side_effect = lambda cls: cls()
    mock_context.get_llm_tool_manager.return_value = tool_mgr

    class MemoryManager:
        async def inject_context(self, *, req, event, query=None):
            return None

    mock_context.memory_manager = MemoryManager()

    await ama._ensure_persona_and_skills(req, {}, mock_context, mock_event)

    assert req.func_tool is not None
    assert {
        "search_memory",
        "get_person_profile",
        "query_episode",
        "maintain_memory",
    }.issubset(set(req.func_tool.names()))


@pytest.mark.asyncio
async def test_memory_retrieval_tools_respect_explicit_empty_persona_tools(
    mock_event,
    mock_context,
):
    req = ProviderRequest(prompt="hello", conversation=_new_mock_conversation())
    mock_context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(
            "persona-no-tools",
            {
                "name": "persona-no-tools",
                "prompt": "Stable seed.",
                "tools": [],
                "skills": [],
                "_begin_dialogs_processed": [],
                "custom_error_message": None,
            },
            None,
            False,
        )
    )
    tool_mgr = MagicMock()
    tool_mgr.get_full_tool_set.return_value = ToolSet()
    mock_context.get_llm_tool_manager.return_value = tool_mgr

    class MemoryManager:
        async def inject_context(self, *, req, event, query=None):
            return None

    mock_context.memory_manager = MemoryManager()

    await ama._ensure_persona_and_skills(req, {}, mock_context, mock_event)

    assert req.func_tool is not None
    assert req.func_tool.names() == []


@pytest.mark.asyncio
async def test_memory_retrieval_tool_can_be_enabled_by_explicit_persona_tool(
    mock_event,
    mock_context,
):
    req = ProviderRequest(prompt="hello", conversation=_new_mock_conversation())
    mock_context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(
            "persona-memory-tool",
            {
                "name": "persona-memory-tool",
                "prompt": "Stable seed.",
                "tools": ["search_memory"],
                "skills": [],
                "_begin_dialogs_processed": [],
                "custom_error_message": None,
            },
            None,
            False,
        )
    )
    tool_mgr = MagicMock()
    tool_mgr.get_tool.side_effect = lambda name: (
        ama.SearchMemoryTool() if name == "search_memory" else None
    )
    mock_context.get_llm_tool_manager.return_value = tool_mgr

    class MemoryManager:
        async def inject_context(self, *, req, event, query=None):
            return None

    mock_context.memory_manager = MemoryManager()

    await ama._ensure_persona_and_skills(req, {}, mock_context, mock_event)

    assert req.func_tool is not None
    assert req.func_tool.names() == ["search_memory"]


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["", "   \n\t"])
async def test_apply_kb_blank_prompt(prompt, mock_event, mock_context):
    """Test applying knowledge base when prompt is blank."""
    module = ama
    req = ProviderRequest(prompt=prompt, system_prompt="System")
    config = module.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)
    retrieve = AsyncMock(return_value="KB result")

    with patch("astrbot.core.astr_main_agent.retrieve_knowledge_base", retrieve):
        await module._apply_kb(mock_event, req, mock_context, config)

    retrieve.assert_not_awaited()
    assert req.system_prompt == "System"


@pytest.mark.asyncio
async def test_apply_kb_no_result(mock_event, mock_context):
    """Test applying knowledge base when no result is returned."""
    module = ama
    req = ProviderRequest(prompt="test", system_prompt="System")
    config = module.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)

    with patch(
        "astrbot.core.astr_main_agent.retrieve_knowledge_base",
        AsyncMock(return_value=None),
    ):
        await module._apply_kb(mock_event, req, mock_context, config)

    assert req.system_prompt == "System"


@pytest.mark.asyncio
async def test_apply_kb_with_existing_tools(mock_event, mock_context):
    """Test applying knowledge base with existing toolset."""
    module = ama
    existing_tools = ToolSet()
    req = ProviderRequest(prompt="test", func_tool=existing_tools)
    config = module.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=True)

    await module._apply_kb(mock_event, req, mock_context, config)

    assert req.func_tool is not None


class TestBuiltinToolInjection:
    """Tests for builtin tool injection paths."""

    @pytest.mark.asyncio
    async def test_apply_web_search_tools_uses_builtin_tool_manager(
        self, mock_event, mock_context
    ):
        """Test web search tool injection through the builtin tool manager."""
        module = ama
        req = ProviderRequest()
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "baidu_ai_search",
            }
        }
        builtin_tool = MagicMock(spec=FunctionTool)
        builtin_tool.name = "web_search_baidu"
        tool_mgr = MagicMock()
        tool_mgr.get_builtin_tool.return_value = builtin_tool
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        await module._apply_web_search_tools(mock_event, req, mock_context)

        tool_mgr.get_builtin_tool.assert_called_once_with(module.BaiduWebSearchTool)
        assert req.func_tool is not None
        assert req.func_tool.get_tool("web_search_baidu") is builtin_tool

    @pytest.mark.asyncio
    async def test_apply_web_search_tools_adds_firecrawl_search_and_extract_tools(
        self, mock_event, mock_context
    ):
        """Test Firecrawl web search injects search and extract tools."""
        module = ama
        req = ProviderRequest()
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "firecrawl",
            }
        }
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_firecrawl"
        extract_tool = MagicMock(spec=FunctionTool)
        extract_tool.name = "firecrawl_extract_web_page"
        tool_mgr = MagicMock()
        tool_mgr.get_builtin_tool.side_effect = [search_tool, extract_tool]
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        await module._apply_web_search_tools(mock_event, req, mock_context)

        assert tool_mgr.get_builtin_tool.call_args_list == [
            ((module.FirecrawlWebSearchTool,),),
            ((module.FirecrawlExtractWebPageTool,),),
        ]
        assert req.func_tool is not None
        assert req.func_tool.get_tool("web_search_firecrawl") is search_tool
        assert req.func_tool.get_tool("firecrawl_extract_web_page") is extract_tool

    @pytest.mark.asyncio
    async def test_apply_web_search_tools_adds_anysearch_tool(
        self, mock_event, mock_context
    ):
        module = ama
        req = ProviderRequest()
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "anysearch",
            }
        }
        builtin_tool = MagicMock(spec=FunctionTool)
        builtin_tool.name = "web_search_anysearch"
        tool_mgr = MagicMock()
        tool_mgr.get_builtin_tool.return_value = builtin_tool
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        await module._apply_web_search_tools(mock_event, req, mock_context)

        tool_mgr.get_builtin_tool.assert_called_once_with(module.AnySearchWebSearchTool)
        assert req.func_tool is not None
        assert req.func_tool.get_tool("web_search_anysearch") is builtin_tool

    def test_apply_web_search_citation_prompt_for_webchat(self, mock_event):
        module = ama
        req = ProviderRequest(system_prompt="base")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_tavily"
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "webchat"

        module._apply_web_search_citation_prompt(mock_event, req)

        assert module.WEB_SEARCH_CITATION_PROMPT in req.system_prompt

    def test_apply_web_search_citation_prompt_is_idempotent(self, mock_event):
        module = ama
        req = ProviderRequest(system_prompt="")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_tavily"
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "webchat"

        module._apply_web_search_citation_prompt(mock_event, req)
        module._apply_web_search_citation_prompt(mock_event, req)

        assert req.system_prompt.count(module.WEB_SEARCH_CITATION_PROMPT) == 1

    def test_apply_web_search_citation_prompt_requires_webchat(self, mock_event):
        module = ama
        req = ProviderRequest(system_prompt="")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_tavily"
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "test_platform"

        module._apply_web_search_citation_prompt(mock_event, req)

        assert module.WEB_SEARCH_CITATION_PROMPT not in req.system_prompt

    def test_proactive_cron_job_tools_uses_builtin_tool_manager(self, mock_context):
        """Test cron tool injection through the builtin tool manager."""
        module = ama
        req = ProviderRequest()
        tool_mgr = MagicMock()

        future_task_tool = MagicMock(spec=FunctionTool)
        future_task_tool.name = "future_task"
        tool_mgr.get_builtin_tool.return_value = future_task_tool
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        module._proactive_cron_job_tools(req, mock_context)

        tool_mgr.get_builtin_tool.assert_called_once_with(module.FutureTaskTool)
        assert req.func_tool is not None
        assert req.func_tool.get_tool("future_task") is future_task_tool


class TestEnsurePersonaAndSkills:
    """Tests for _ensure_persona_and_skills function."""

    def test_filter_plugin_skills_uses_current_config_plugin_set(self):
        module = ama
        catalogs = RuntimeCatalogs()
        catalogs.plugins.publish(
            StarMetadata(
                name="allowed_plugin",
                root_dir_name="astrbot_plugin_allowed",
                module_path="plugin.allowed",
                activated=True,
            )
        )
        catalogs.plugins.publish(
            StarMetadata(
                name="blocked_plugin",
                root_dir_name="astrbot_plugin_blocked",
                module_path="plugin.blocked",
                activated=True,
            )
        )
        skills = [
            SkillInfo(name="local", description="", path="local/SKILL.md", active=True),
            SkillInfo(
                name="allowed-skill",
                description="",
                path="allowed/SKILL.md",
                active=True,
                source_type="plugin",
                plugin_name="astrbot_plugin_allowed",
            ),
            SkillInfo(
                name="blocked-skill",
                description="",
                path="blocked/SKILL.md",
                active=True,
                source_type="plugin",
                plugin_name="astrbot_plugin_blocked",
            ),
        ]

        filtered = module._filter_skills_for_current_config(
            skills,
            {"plugin_set": ["allowed_plugin"]},
            catalogs.plugins,
        )

        assert [skill.name for skill in filtered] == ["local", "allowed-skill"]

    def test_filter_plugin_skills_skips_inactive_plugins_even_when_all_allowed(
        self,
    ):
        module = ama
        catalogs = RuntimeCatalogs()
        catalogs.plugins.publish(
            StarMetadata(
                name="inactive_plugin",
                root_dir_name="astrbot_plugin_inactive",
                module_path="plugin.inactive",
                activated=False,
            )
        )
        skills = [
            SkillInfo(
                name="inactive-skill",
                description="",
                path="inactive/SKILL.md",
                active=True,
                source_type="plugin",
                plugin_name="astrbot_plugin_inactive",
            )
        ]

        filtered = module._filter_skills_for_current_config(
            skills,
            {"plugin_set": ["*"]},
            catalogs.plugins,
        )

        assert filtered == []

    @pytest.mark.asyncio
    async def test_ensure_persona_from_session(self, mock_event, mock_context):
        """Test applying persona from session service config."""
        module = ama
        persona = {"name": "test-persona", "prompt": "You are helpful."}
        mock_context.persona_manager.runtime_personas = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("test-persona", persona, "test-persona", False)
        )
        mock_event.trace = MagicMock(record=MagicMock())
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "You are helpful." in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_persona_from_conversation(self, mock_event, mock_context):
        """Test applying persona from conversation setting."""
        module = ama
        persona = {"name": "conv-persona", "prompt": "Custom persona."}
        mock_context.persona_manager.runtime_personas = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("conv-persona", persona, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="conv-persona")

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "Custom persona." in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_persona_none_explicit(self, mock_event, mock_context):
        """Test that [%None] persona is explicitly set to no persona."""
        module = ama
        mock_context.persona_manager.runtime_personas = []
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("[%None]", None, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="[%None]")

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "Persona Instructions" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_skills_includes_workspace_skills(
        self,
        monkeypatch,
        tmp_path,
        mock_event,
        mock_context,
    ):
        module = ama
        data_dir = tmp_path / "data"
        global_skills_dir = tmp_path / "global_skills"
        plugins_dir = tmp_path / "plugins"
        workspaces_dir = tmp_path / "workspaces"
        for path in (data_dir, global_skills_dir, plugins_dir):
            path.mkdir(parents=True, exist_ok=True)

        global_skill_dir = global_skills_dir / "workspace-skill"
        global_skill_dir.mkdir(parents=True)
        global_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Global scoped skill.\n---\n",
            encoding="utf-8",
        )

        workspace_root = workspaces_dir / module.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            module,
            "get_astrbot_workspaces_path",
            lambda: str(workspaces_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_data_path",
            lambda: str(data_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
            lambda: str(global_skills_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
            lambda: str(plugins_dir),
        )

        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)
        runtime_config = {"computer_use_runtime": "local"}

        await module._ensure_persona_and_skills(
            req, runtime_config, mock_context, mock_event
        )

        assert "**workspace-skill**" in req.system_prompt
        assert "Workspace scoped skill." in req.system_prompt
        assert "Global scoped skill." not in req.system_prompt
        assert (
            str(workspace_skill_dir / "SKILL.md").replace("\\", "/")
            in req.system_prompt
        )

    @pytest.mark.asyncio
    async def test_ensure_skills_respects_empty_persona_skills_for_workspace(
        self,
        monkeypatch,
        tmp_path,
        mock_event,
        mock_context,
    ):
        module = ama
        data_dir = tmp_path / "data"
        global_skills_dir = tmp_path / "global_skills"
        plugins_dir = tmp_path / "plugins"
        workspaces_dir = tmp_path / "workspaces"
        for path in (data_dir, global_skills_dir, plugins_dir):
            path.mkdir(parents=True, exist_ok=True)

        workspace_root = workspaces_dir / module.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            module,
            "get_astrbot_workspaces_path",
            lambda: str(workspaces_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_data_path",
            lambda: str(data_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
            lambda: str(global_skills_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
            lambda: str(plugins_dir),
        )

        persona = {"name": "no-skills", "prompt": "", "skills": []}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("no-skills", persona, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="no-skills")

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "Workspace scoped skill." not in req.system_prompt
        assert "## Skills" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_skills_skips_workspace_skills_in_sandbox_runtime(
        self,
        monkeypatch,
        tmp_path,
        mock_event,
        mock_context,
    ):
        module = ama
        data_dir = tmp_path / "data"
        global_skills_dir = tmp_path / "global_skills"
        plugins_dir = tmp_path / "plugins"
        workspaces_dir = tmp_path / "workspaces"
        for path in (data_dir, global_skills_dir, plugins_dir):
            path.mkdir(parents=True, exist_ok=True)

        workspace_root = workspaces_dir / module.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            module,
            "get_astrbot_workspaces_path",
            lambda: str(workspaces_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_data_path",
            lambda: str(data_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
            lambda: str(global_skills_dir),
        )
        monkeypatch.setattr(
            "astrbot.core.skills.skill_manager.get_astrbot_plugin_path",
            lambda: str(plugins_dir),
        )

        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await module._ensure_persona_and_skills(
            req,
            {"computer_use_runtime": "sandbox"},
            mock_context,
            mock_event,
        )

        assert "Workspace scoped skill." not in req.system_prompt
        assert "## Skills" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_tools_from_persona(self, mock_event, mock_context):
        """Test applying tools from persona."""
        module = ama
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.active = True
        persona = {"name": "persona", "prompt": "Test", "tools": ["test_tool"]}
        mock_context.persona_manager.runtime_personas = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("persona", persona, None, False)
        )
        tmgr = mock_context.get_llm_tool_manager.return_value
        tmgr.get_func.return_value = mock_tool

        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="persona")

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert req.func_tool is not None

    @pytest.mark.asyncio
    async def test_persona_empty_tools_keeps_late_builtin_tools(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        persona = {"name": "locked", "prompt": "No tools.", "tools": []}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("locked", persona, None, False)
        )
        mock_event.platform_meta.support_proactive_message = False
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "baidu_ai_search",
            }
        }
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            provider_settings={
                "web_search": True,
                "websearch_provider": "baidu_ai_search",
            },
            computer_use_runtime="none",
            add_cron_tools=False,
        )
        req = ProviderRequest(prompt="hello")
        req.conversation = MagicMock(persona_id="locked", history="[]")

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=config,
                provider=mock_provider,
                req=req,
                apply_reset=False,
            )
        assert result is not None
        try:
            assert result.provider_request.func_tool is not None
            assert result.provider_request.func_tool.names() == ["web_search_baidu"]
        finally:
            if result.reset_coro:
                result.reset_coro.close()

    @pytest.mark.asyncio
    async def test_persona_empty_tools_keeps_local_runtime_builtin_tools(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        persona = {"name": "locked", "prompt": "No tools.", "tools": []}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("locked", persona, None, False)
        )
        mock_event.platform_meta.support_proactive_message = False
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="local",
            add_cron_tools=False,
        )
        req = ProviderRequest(prompt="hello")
        req.conversation = MagicMock(persona_id="locked", history="[]")

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=config,
                provider=mock_provider,
                req=req,
                apply_reset=False,
            )
        assert result is not None
        try:
            assert result.provider_request.func_tool is not None
            tool_names = result.provider_request.func_tool.names()
            assert "astrbot_execute_shell" in tool_names
            assert "astrbot_execute_python" in tool_names
        finally:
            if result.reset_coro:
                result.reset_coro.close()

    @pytest.mark.asyncio
    async def test_subagent_dedupe_uses_default_persona_tools(
        self, mock_event, mock_context
    ):
        """Test dedupe uses resolved default persona tools in subagent mode."""
        module = ama
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=(None, None, None, False)
        )
        mock_context.persona_manager.get_runtime_persona_by_id = MagicMock(
            return_value={"name": "default", "tools": ["tool_a"]}
        )

        tool_a = FunctionTool(
            name="tool_a",
            parameters={"type": "object", "properties": {}},
            description="tool a",
        )
        tool_b = FunctionTool(
            name="tool_b",
            parameters={"type": "object", "properties": {}},
            description="tool b",
        )
        tmgr = mock_context.get_llm_tool_manager.return_value
        tmgr.func_list = [tool_a, tool_b]
        tmgr.get_full_tool_set.return_value = ToolSet([tool_a, tool_b])
        tmgr.get_func.side_effect = lambda name: {
            "tool_a": tool_a,
            "tool_b": tool_b,
        }.get(name)

        handoff = MagicMock()
        handoff.name = "transfer_to_planner"
        mock_context.subagent_orchestrator = MagicMock(handoffs=[handoff])
        mock_context.get_config.return_value = {
            "subagent_orchestrator": {
                "main_enable": True,
                "remove_main_duplicate_tools": True,
                "agents": [
                    {
                        "name": "planner",
                        "enabled": True,
                        "persona_id": "default",
                    }
                ],
            }
        }

        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert req.func_tool is not None
        assert "transfer_to_planner" in req.func_tool.names()
        assert "tool_a" not in req.func_tool.names()
        assert "tool_b" in req.func_tool.names()


class TestDecorateLlmRequest:
    """Tests for _decorate_llm_request function."""

    @pytest.mark.asyncio
    async def test_decorate_llm_request_basic(
        self, mock_event, mock_context, sample_config
    ):
        """Test basic LLM request decoration."""
        module = ama
        req = ProviderRequest(prompt="Hello", system_prompt="System")

        await module._decorate_llm_request(mock_event, req, mock_context, sample_config)

        assert req.prompt == "Hello"
        assert req.system_prompt == "System"

    @pytest.mark.asyncio
    async def test_decorate_llm_request_with_prefix(self, mock_event, mock_context):
        """Test LLM request decoration with prompt prefix."""
        module = ama
        req = ProviderRequest(prompt="Hello")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, provider_settings={"prompt_prefix": "AI: "}
        )

        with patch.object(mock_context, "get_config") as mock_get_config:
            mock_get_config.return_value = {}

            await module._decorate_llm_request(mock_event, req, mock_context, config)

        assert req.prompt == "AI: Hello"

    @pytest.mark.asyncio
    async def test_decorate_llm_request_prefix_with_placeholder(
        self, mock_event, mock_context
    ):
        """Test prompt prefix with {{prompt}} placeholder."""
        module = ama
        req = ProviderRequest(prompt="Hello")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            provider_settings={"prompt_prefix": "AI {{prompt}} - Please respond:"},
        )

        with patch.object(mock_context, "get_config") as mock_get_config:
            mock_get_config.return_value = {}

            await module._decorate_llm_request(mock_event, req, mock_context, config)

        assert req.prompt == "AI Hello - Please respond:"

    @pytest.mark.asyncio
    async def test_decorate_llm_request_no_conversation(self, mock_event, mock_context):
        """Test decoration when no conversation exists."""
        module = ama
        req = ProviderRequest(prompt="Hello")
        req.conversation = None
        config = module.MainAgentBuildConfig(tool_call_timeout=60)

        with patch.object(mock_context, "get_config") as mock_get_config:
            mock_get_config.return_value = {}

            await module._decorate_llm_request(mock_event, req, mock_context, config)

        assert req.prompt == "Hello"


class TestPluginToolFix:
    """Tests for _plugin_tool_fix function."""

    def test_plugin_tool_fix_none_plugins(self, mock_event):
        """Test plugin tool fix when no plugins specified."""
        module = ama
        req = ProviderRequest(func_tool=ToolSet())
        mock_event.plugins_name = None

        module._plugin_tool_fix(
            mock_event,
            req,
            SimpleNamespace(catalogs=RuntimeCatalogs()),
        )

        assert req.func_tool is not None

    def test_plugin_tool_fix_filters_by_plugin(self, mock_event):
        """Test plugin tool fix filters tools by enabled plugins."""
        module = ama
        mcp_tool = MagicMock(spec=MCPTool)
        mcp_tool.name = "mcp_tool"

        plugin_tool = MagicMock()
        plugin_tool.name = "plugin_tool"
        plugin_tool.handler_module_path = "test_plugin"
        plugin_tool.active = True

        tool_set = ToolSet()
        tool_set.add_tool(mcp_tool)
        tool_set.add_tool(plugin_tool)

        req = ProviderRequest(func_tool=tool_set)
        mock_event.plugins_name = ["test_plugin"]

        catalogs = RuntimeCatalogs()
        catalogs.plugins.publish(
            StarMetadata(name="test_plugin", module_path="test_plugin")
        )
        module._plugin_tool_fix(mock_event, req, SimpleNamespace(catalogs=catalogs))

        assert "mcp_tool" in req.func_tool.names()
        assert "plugin_tool" in req.func_tool.names()

    def test_plugin_tool_fix_mcp_preserved(self, mock_event):
        """Test that MCP tools are always preserved."""
        module = ama
        mcp_tool = MagicMock(spec=MCPTool)
        mcp_tool.name = "mcp_tool"
        mcp_tool.active = True

        tool_set = ToolSet()
        tool_set.add_tool(mcp_tool)

        req = ProviderRequest(func_tool=tool_set)
        mock_event.plugins_name = ["other_plugin"]

        module._plugin_tool_fix(
            mock_event,
            req,
            SimpleNamespace(catalogs=RuntimeCatalogs()),
        )

        assert "mcp_tool" in req.func_tool.names()

    def test_plugin_tool_fix_preserves_tools_without_plugin_origin(self, mock_event):
        """Tools without handler_module_path should not be filtered out."""
        module = ama
        handoff_tool = FunctionTool(
            name="transfer_to_demo_agent",
            description="Delegate to demo agent",
            parameters={"type": "object", "properties": {}},
            handler_module_path=None,
            active=True,
        )

        tool_set = ToolSet()
        tool_set.add_tool(handoff_tool)

        req = ProviderRequest(func_tool=tool_set)
        mock_event.plugins_name = ["other_plugin"]

        module._plugin_tool_fix(
            mock_event,
            req,
            SimpleNamespace(catalogs=RuntimeCatalogs()),
        )

        assert "transfer_to_demo_agent" in req.func_tool.names()


class TestBuildMainAgent:
    """Tests for build_main_agent function."""

    @pytest.mark.asyncio
    async def test_build_main_agent_basic(
        self, mock_event, mock_context, mock_provider
    ):
        """Test basic main agent building."""
        module = ama
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert isinstance(result, module.MainAgentBuildResult)

    @pytest.mark.asyncio
    async def test_build_main_agent_passes_max_context_length_to_runner(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    max_context_length=7,
                ),
            )

        assert result is not None
        mock_runner.reset.assert_awaited_once()
        assert mock_runner.reset.await_args.kwargs["enforce_max_turns"] == 7

    @pytest.mark.asyncio
    async def test_build_main_agent_no_provider(self, mock_event, mock_context):
        """Test building main agent when no provider is available."""
        module = ama
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.side_effect = ValueError("No provider")

        result = await module.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=module.MainAgentBuildConfig(tool_call_timeout=60),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_build_main_agent_with_command_prefixed_message(
        self, mock_event, mock_context, mock_provider
    ):
        """Building the main agent still succeeds for a command-prefixed message."""
        module = ama
        mock_event.message_str = "/command"
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_build_main_agent_without_command_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        """Routing owns LLM access; a missing extra prefix no longer blocks build."""
        module = ama
        mock_event.message_str = "hello"
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}
        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner
            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_build_main_agent_with_images(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with image attachments."""
        module = ama
        mock_image = MagicMock(spec=Image)
        mock_image.convert_to_file_path = AsyncMock(return_value="/path/to/image.jpg")
        mock_event.message_obj.message = [mock_image]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_build_main_agent_skips_caption_when_main_provider_supports_images(
        self, mock_event, mock_context, mock_provider
    ):
        """Test image-capable chat providers receive quoted images directly."""
        module = ama
        mock_image = Image(file="file:///tmp/quoted.jpg")
        mock_reply = Reply(
            id="reply-1",
            chain=[Plain(text="quoted text"), mock_image],
            sender_nickname="",
            message_str="quoted text",
        )
        mock_event.message_obj.message = [Plain(text="Hello"), mock_reply]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value="/tmp/quoted.jpg"),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    provider_settings={
                        "default_image_caption_provider_id": "caption-provider",
                    },
                ),
                provider=mock_provider,
            )

        assert result is not None
        assert result.provider_request.image_urls == []
        assert any(
            "image omitted" in part.text
            for part in result.provider_request.extra_user_content_parts
        )
        assert not any(
            "Image Caption" in part.text or "<image_caption>" in part.text
            for part in result.provider_request.extra_user_content_parts
        )
        mock_provider.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_main_agent_does_not_caption_quoted_image_twice(
        self, mock_event, mock_context
    ):
        """Quoted images should not be captioned again after request image captioning."""
        module = ama
        text_provider = MagicMock(spec=Provider)
        text_provider.provider_config = {
            "id": "text-provider",
            "modalities": ["text", "tool_use"],
        }
        text_provider.get_model.return_value = "text-model"

        caption_provider = MagicMock(spec=Provider)
        caption_provider.text_chat = AsyncMock(
            return_value=MagicMock(completion_text="quoted image caption")
        )

        mock_reply = Reply(
            id="reply-1",
            chain=[Plain(text="quoted text"), Image(file="file:///tmp/quoted.jpg")],
            sender_nickname="Alice",
            message_str="quoted text",
        )
        mock_event.message_obj.message = [Plain(text="Hello"), mock_reply]

        mock_context.get_provider_by_id.return_value = caption_provider
        mock_context.get_using_provider.return_value = text_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value="/tmp/quoted.jpg"),
            ),
            patch(
                "astrbot.core.astr_main_agent._compress_image_for_provider",
                AsyncMock(side_effect=lambda path, _settings: path),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    provider_settings={
                        "default_image_caption_provider_id": "caption-provider",
                    },
                ),
                provider=text_provider,
            )

        assert result is not None
        assert caption_provider.text_chat.await_count == 1

        extra_text = "\n".join(
            part.text for part in result.provider_request.extra_user_content_parts
        )
        assert "<image_caption>quoted image caption</image_caption>" in extra_text
        assert "[Image Caption in quoted message]" not in extra_text

    @pytest.mark.asyncio
    async def test_build_main_agent_does_not_retry_quoted_image_caption_when_empty(
        self, mock_event, mock_context
    ):
        """Quoted images already sent to image captioning should not be retried."""
        module = ama
        text_provider = MagicMock(spec=Provider)
        text_provider.provider_config = {
            "id": "text-provider",
            "modalities": ["text", "tool_use"],
        }
        text_provider.get_model.return_value = "text-model"

        caption_provider = MagicMock(spec=Provider)
        caption_provider.text_chat = AsyncMock(
            return_value=MagicMock(completion_text="")
        )

        mock_reply = Reply(
            id="reply-1",
            chain=[Plain(text="quoted text"), Image(file="file:///tmp/quoted.jpg")],
            sender_nickname="Alice",
            message_str="quoted text",
        )
        mock_event.message_obj.message = [Plain(text="Hello"), mock_reply]

        mock_context.get_provider_by_id.return_value = caption_provider
        mock_context.get_using_provider.return_value = text_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value="/tmp/quoted.jpg"),
            ),
            patch(
                "astrbot.core.astr_main_agent._compress_image_for_provider",
                AsyncMock(side_effect=lambda path, _settings: path),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    provider_settings={
                        "default_image_caption_provider_id": "caption-provider",
                    },
                ),
                provider=text_provider,
            )

        assert result is not None
        assert caption_provider.text_chat.await_count == 1

        extra_text = "\n".join(
            part.text for part in result.provider_request.extra_user_content_parts
        )
        assert "<image_caption>" not in extra_text
        assert "[Image Caption in quoted message]" not in extra_text

    @pytest.mark.asyncio
    async def test_build_main_agent_uses_image_fallback_provider(
        self, mock_event, mock_context
    ):
        """Test image requests use a fallback provider that supports images."""
        module = ama
        text_provider = MagicMock(spec=Provider)
        text_provider.provider_config = {
            "id": "text-provider",
            "modalities": ["text", "tool_use"],
            "max_context_tokens": 128000,
        }
        text_provider.get_model.return_value = "text-model"

        image_provider = MagicMock(spec=Provider)
        image_provider.provider_config = {
            "id": "image-provider",
            "modalities": ["text", "image", "tool_use"],
            "max_context_tokens": 128000,
        }
        image_provider.get_model.return_value = "image-model"

        req = ProviderRequest(
            prompt="describe this",
            image_urls=["/tmp/image.jpg"],
            model="text-model",
        )
        mock_context.get_provider_by_id.side_effect = lambda provider_id: (
            image_provider if provider_id == "image-provider" else None
        )
        mock_context.get_config.return_value = {}

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    llm_safety_mode=False,
                    computer_use_runtime="none",
                    add_cron_tools=False,
                    fallback_provider_ids=["image-provider"],
                    provider_settings={},
                ),
                provider=text_provider,
                req=req,
            )

        assert result is not None
        assert result.provider is image_provider
        assert req.image_urls == ["/tmp/image.jpg"]
        assert result.provider_request.image_urls == []
        assert any(
            "image omitted" in part.text
            for part in result.provider_request.extra_user_content_parts
        )
        assert result.provider_request.model is None
        assert mock_runner.reset.call_args.kwargs["provider"] is image_provider
        assert mock_runner.reset.call_args.kwargs["fallback_providers"] == []

    @pytest.mark.asyncio
    async def test_build_main_agent_keeps_text_provider_without_image_fallback(
        self, mock_event, mock_context
    ):
        """Test image requests fall back to existing sanitizing when no image provider exists."""
        module = ama
        text_provider = MagicMock(spec=Provider)
        text_provider.provider_config = {
            "id": "text-provider",
            "modalities": ["text", "tool_use"],
            "max_context_tokens": 128000,
        }
        text_provider.get_model.return_value = "text-model"

        req = ProviderRequest(
            prompt="describe this",
            image_urls=["/tmp/image.jpg"],
        )
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_config.return_value = {}

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    llm_safety_mode=False,
                    computer_use_runtime="none",
                    add_cron_tools=False,
                    fallback_provider_ids=["missing-provider"],
                    provider_settings={},
                ),
                provider=text_provider,
                req=req,
            )

        assert result is not None
        assert result.provider is text_provider
        assert req.image_urls == ["/tmp/image.jpg"]
        assert result.provider_request.image_urls == []
        assert any(
            "image omitted" in part.text
            for part in result.provider_request.extra_user_content_parts
        )
        assert mock_runner.reset.call_args.kwargs["provider"] is text_provider

    @pytest.mark.asyncio
    async def test_build_main_agent_with_video_attachment(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with video attachments."""
        module = ama
        mock_video = Video(file="file:///path/to/video.mp4")
        mock_event.message_obj.message = [mock_video]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert [
            part.text for part in result.provider_request.extra_user_content_parts
        ] == ["[Video Attachment: name video.mp4, path /path/to/video.mp4]"]

    @pytest.mark.asyncio
    async def test_build_main_agent_with_quoted_video_attachment(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with quoted video attachments."""
        module = ama
        mock_video = Video(file="file:///path/to/quoted-video.mp4")
        mock_reply = Reply(
            id="reply-1",
            chain=[mock_video],
            sender_nickname="",
            message_str="quoted message",
        )
        mock_event.message_obj.message = [Plain(text="Hello"), mock_reply]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert (
            "[Video Attachment in quoted message: "
            "name quoted-video.mp4, path /path/to/quoted-video.mp4]"
        ) in [part.text for part in result.provider_request.extra_user_content_parts]

    @pytest.mark.asyncio
    async def test_build_main_agent_preserves_quoted_video_when_conversion_fails(
        self, mock_event, mock_context, mock_provider
    ):
        """Test quoted video failures preserve the ref without error logging."""
        module = ama
        mock_video = Video(file="file:///path/to/direct.mp4")
        mock_quoted_video = Video(file="file:///path/to/quoted.mp4")
        mock_reply = Reply(
            id="reply-1",
            chain=[mock_quoted_video],
            sender_nickname="",
            message_str="quoted message",
        )
        mock_event.message_obj.message = [mock_video, mock_reply]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        async def _raise_video_conversion_error(self):
            if self.file.endswith("direct.mp4"):
                raise RuntimeError("direct")
            raise RuntimeError("quoted")

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
            patch("astrbot.core.astr_main_agent.logger") as mock_logger,
            patch(
                "astrbot.core.astr_main_agent.retrieve_knowledge_base",
                AsyncMock(return_value=None),
            ),
            patch.object(
                Video,
                "convert_to_file_path",
                AsyncMock(side_effect=_raise_video_conversion_error),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        extra_texts = [
            part.text for part in result.provider_request.extra_user_content_parts
        ]
        assert (
            "[Video Attachment in quoted message: "
            "name quoted.mp4, ref file:///path/to/quoted.mp4]"
        ) in extra_texts
        assert not any("[Video Attachment: name" in part for part in extra_texts)
        assert mock_logger.error.call_count == 1
        assert (
            "Error processing video attachment"
            in mock_logger.error.call_args_list[0][0][0]
        )
        assert not any(
            "Error processing quoted video attachment" in call[0][0]
            for call in mock_logger.error.call_args_list
        )

    @pytest.mark.asyncio
    async def test_build_main_agent_no_prompt_no_images(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent returns None when no prompt or images."""
        module = ama
        mock_event.message_str = ""
        mock_event.message_obj.message = []

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        result = await module.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=module.MainAgentBuildConfig(tool_call_timeout=60),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_prepare_request_for_agent_uses_json_card_summary(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        card_data = {"meta": {"news": {"title": "News"}}}
        mock_event.message_str = ""
        mock_event.message_obj.message = [Json(data=card_data)]
        req = ProviderRequest(prompt="")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            llm_safety_mode=False,
            computer_use_runtime="none",
        )

        with (
            patch.object(module, "_decorate_llm_request", AsyncMock()),
            patch.object(module, "_apply_kb", AsyncMock()),
            patch.object(module, "_apply_web_search_tools", AsyncMock()),
            patch.object(module, "_plugin_tool_fix"),
        ):
            ok = await module._prepare_request_for_agent(
                mock_event,
                req,
                mock_context,
                config,
                mock_provider,
            )

        assert ok is True
        assert req.prompt == "[Shared Card: Title: News]"
        assert json.dumps(card_data) not in req.prompt

    @pytest.mark.asyncio
    async def test_prepare_request_for_agent_skips_truly_empty_message(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        mock_event.message_str = ""
        mock_event.message_obj.message = []
        req = ProviderRequest(prompt="")
        config = module.MainAgentBuildConfig(tool_call_timeout=60)

        ok = await module._prepare_request_for_agent(
            mock_event,
            req,
            mock_context,
            config,
            mock_provider,
        )

        assert ok is False
        assert not req.prompt

    @pytest.mark.asyncio
    async def test_build_main_agent_json_card_prompt(
        self, mock_event, mock_context, mock_provider
    ):
        module = ama
        mock_event.message_str = ""
        mock_event.message_obj.message = [
            Json(data={"meta": {"news": {"title": "News"}}})
        ]
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}
        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert "[Shared Card: Title: News]" in result.provider_request.prompt
        assert '{"meta"' not in result.provider_request.prompt

    @pytest.mark.asyncio
    async def test_build_main_agent_apply_reset_false(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent without applying reset."""
        module = ama
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
                apply_reset=False,
            )

        assert result is not None
        assert result.reset_coro is not None
        mock_runner.reset.assert_called_once()
        result.reset_coro.close()

    @pytest.mark.asyncio
    async def test_build_main_agent_with_existing_request(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with existing ProviderRequest."""
        module = ama
        existing_req = ProviderRequest(prompt="Existing prompt")
        mock_event.get_extra.side_effect = lambda k: (
            existing_req if k == "provider_request" else None
        )

        with (
            patch("astrbot.core.astr_main_agent.AgentRunner") as mock_runner_cls,
            patch("astrbot.core.astr_main_agent.AstrAgentContext"),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await module.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=module.MainAgentBuildConfig(tool_call_timeout=60),
                provider=mock_provider,
                req=existing_req,
            )

        assert result is not None
        assert existing_req == ProviderRequest(prompt="Existing prompt")
        assert result.provider_request is not existing_req
        assert result.provider_request.prompt == "Existing prompt"


class TestHandleWebchat:
    """Tests for _handle_webchat function."""

    @pytest.mark.asyncio
    async def test_handle_webchat_generates_title(self, mock_event):
        """Test generating title for webchat session without display name."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is machine learning?")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "Machine Learning Introduction"
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.get_platform_session_by_id.assert_called_once_with(
            "webchat-session-123"
        )
        mock_db.update_platform_session.assert_called_once_with(
            session_id="webchat-session-123",
            display_name="Machine Learning Introduction",
        )

    @pytest.mark.asyncio
    async def test_handle_webchat_no_user_prompt(self, mock_event):
        """Test that title generation is skipped when no user prompt."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt=None)
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        await module._handle_webchat(mock_event, req, prov, mock_db)

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_empty_user_prompt(self, mock_event):
        """Test that title generation is skipped when user prompt is empty."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="")
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        await module._handle_webchat(mock_event, req, prov, mock_db)

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_session_already_has_display_name(self, mock_event):
        """Test that title generation is skipped when session already has display name."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is AI?")
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = "Existing Title"

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)

        await module._handle_webchat(mock_event, req, prov, mock_db)

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_no_session_found(self, mock_event):
        """Test that title generation is skipped when session is not found."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is AI?")
        prov = MagicMock(spec=Provider)

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=None)

        await module._handle_webchat(mock_event, req, prov, mock_db)

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_none_title(self, mock_event):
        """Test that title is not updated when LLM returns <None>."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="hi")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "<None>"
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_empty_title(self, mock_event):
        """Test that title is not updated when LLM returns empty string."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="hello")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "   "
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_none_response(self, mock_event):
        """Test handling when LLM returns None response."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="test question")
        prov = MagicMock(spec=Provider)
        prov.text_chat = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_no_completion_text(self, mock_event):
        """Test handling when LLM response has no completion_text."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="test question")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = None
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_strips_title_whitespace(self, mock_event):
        """Test that generated title has whitespace stripped."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is Python?")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "  Python Programming Guide  "
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()

        await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_db.update_platform_session.assert_called_once_with(
            session_id="webchat-session-123",
            display_name="Python Programming Guide",
        )

    @pytest.mark.asyncio
    async def test_handle_webchat_provider_exception_is_handled(self, mock_event):
        """Test that provider exception during title generation is handled."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is Python?")
        prov = MagicMock(spec=Provider)
        prov.text_chat = AsyncMock(side_effect=RuntimeError("provider failed"))

        mock_session = MagicMock()
        mock_session.display_name = None

        mock_db = MagicMock()
        mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
        mock_db.update_platform_session = AsyncMock()
        with patch("astrbot.core.astr_main_agent.logger") as mock_logger:
            await module._handle_webchat(mock_event, req, prov, mock_db)

        mock_logger.exception.assert_called_once()
        mock_db.update_platform_session.assert_not_called()


class TestApplyLlmSafetyMode:
    """Tests for _apply_llm_safety_mode function."""

    def test_apply_llm_safety_mode_system_prompt_strategy(self):
        """Test applying safety mode with system_prompt strategy."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            llm_safety_mode=True,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        module._apply_llm_safety_mode(config, req)

        assert "You are running in Safe Mode" in req.system_prompt
        assert "Original prompt" in req.system_prompt

    def test_apply_llm_safety_mode_prepends_safety_prompt(self):
        """Test that safety prompt is prepended before original system prompt."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="My custom prompt")

        module._apply_llm_safety_mode(config, req)

        assert req.system_prompt.startswith("You are running in Safe Mode")
        assert "My custom prompt" in req.system_prompt

    def test_apply_llm_safety_mode_with_none_system_prompt(self):
        """Test applying safety mode when original system_prompt is None."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt=None)

        module._apply_llm_safety_mode(config, req)

        assert "You are running in Safe Mode" in req.system_prompt

    def test_apply_llm_safety_mode_unsupported_strategy(self):
        """Test that unsupported strategy logs warning and does nothing."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="unsupported_strategy",
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original")

        with patch("astrbot.core.astr_main_agent.logger") as mock_logger:
            module._apply_llm_safety_mode(config, req)

        mock_logger.warning.assert_called_once()
        assert (
            "Unsupported llm_safety_mode strategy"
            in mock_logger.warning.call_args[0][0]
        )
        assert req.system_prompt == "Original"

    def test_apply_llm_safety_mode_empty_system_prompt(self):
        """Test applying safety mode when original system_prompt is empty."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="")

        module._apply_llm_safety_mode(config, req)

        assert "You are running in Safe Mode" in req.system_prompt


class TestApplySandboxTools:
    """Tests for _apply_sandbox_tools function."""

    def test_apply_sandbox_tools_creates_toolset_if_none(self, mock_context):
        """Test that ToolSet is created when func_tool is None."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert req.func_tool is not None
        assert isinstance(req.func_tool, ToolSet)

    def test_apply_sandbox_tools_adds_required_tools(self, mock_context):
        """Test that all required sandbox tools are added."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        tool_names = req.func_tool.names()
        assert "astrbot_execute_shell" in tool_names
        assert "astrbot_execute_ipython" in tool_names
        assert "astrbot_upload_file" in tool_names
        assert "astrbot_download_file" in tool_names

    def test_apply_sandbox_tools_adds_sandbox_prompt(self, mock_context):
        """Test that sandbox mode prompt is added to system_prompt."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_cua_adds_gui_guidance(self, mock_context):
        """Test that CUA sandbox guidance nudges reliable GUI workflows."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "cua"},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert req.func_tool is not None
        tool_names = req.func_tool.names()
        assert "astrbot_cua_screenshot" in tool_names
        assert "astrbot_cua_mouse_click" in tool_names
        assert "astrbot_cua_keyboard_type" in tool_names
        assert "astrbot_cua_key_press" not in tool_names

        assert "Firefox" in req.system_prompt
        assert "background=true" in req.system_prompt
        assert 'firefox "https://example.com"' in req.system_prompt
        assert "astrbot_cua_screenshot" in req.system_prompt
        assert "astrbot_cua_key_press" not in req.system_prompt
        assert "return_image_to_llm" in req.system_prompt
        assert "astrbot_execute_shell" in req.system_prompt
        assert "\\n" in req.system_prompt
        assert "send_to_user=true" in req.system_prompt
        assert "focused and empty or safe to append" in req.system_prompt

    def test_apply_sandbox_tools_with_shipyard_neo_adds_path_rule(self, mock_context):
        """Test Shipyard Neo sandbox guidance adds workspace path rule."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard_neo",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None, system_prompt="Original")

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert "[Shipyard Neo File Path Rule]" in req.system_prompt
        assert "baidu_homepage.png" in req.system_prompt
        assert "/workspace/baidu_homepage.png" in req.system_prompt

    def test_apply_sandbox_tools_preserves_existing_toolset(self, mock_context):
        """Test that existing tools are preserved when adding sandbox tools."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        existing_toolset = ToolSet()
        existing_tool = MagicMock()
        existing_tool.name = "existing_tool"
        existing_toolset.add_tool(existing_tool)
        req = ProviderRequest(prompt="Test", func_tool=existing_toolset)

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert "existing_tool" in req.func_tool.names()
        assert "astrbot_execute_shell" in req.func_tool.names()

    def test_apply_sandbox_tools_appends_to_existing_system_prompt(self, mock_context):
        """Test that sandbox prompt is appended to existing system prompt."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Base prompt")

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert req.system_prompt.startswith("Base prompt")
        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_none_system_prompt(self, mock_context):
        """Test that sandbox prompt is applied when system_prompt is None."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt=None)

        module._apply_sandbox_tools(
            config,
            req,
            "session-123",
            mock_context.catalogs.tools,
        )

        assert isinstance(req.system_prompt, str)
        assert "sandboxed environment" in req.system_prompt
