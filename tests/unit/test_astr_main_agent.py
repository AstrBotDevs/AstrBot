"""Tests for astr_main_agent ama."""

import asyncio
import datetime
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core import agent_input as core_input
from astrbot.core import llm_error_messages as agent_errors
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.message import Message, dump_messages_with_checkpoints
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent_wakeup import wake_main_agent
from astrbot.core.astr_agent_runtime import execution as native_execution
from astrbot.core.astr_agent_runtime import main_agent as ama
from astrbot.core.astr_agent_runtime.main_agent import builder as builder_build
from astrbot.core.astr_agent_runtime.main_agent import (
    computer_use as computer_use_build,
)
from astrbot.core.astr_agent_runtime.main_agent import (
    knowledge_base as knowledge_base_build,
)
from astrbot.core.astr_agent_runtime.main_agent import persona as persona_build
from astrbot.core.astr_agent_runtime.main_agent import providers as providers_build
from astrbot.core.astr_agent_runtime.main_agent import request as request_build
from astrbot.core.astr_agent_runtime.main_agent import web_search as web_search_build
from astrbot.core.astr_agent_runtime.main_agent import workspace as workspace_build
from astrbot.core.config.agent_runner import resolve_context_compression_config
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Plain, Record, Reply, Video
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
    webchat as webchat_build,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider import Provider
from astrbot.core.provider import manager as provider_manager_module
from astrbot.core.provider.entities import ProviderRequest, ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.skills.skill_manager import SkillInfo
from astrbot.core.star import agent_capabilities as plugins_build
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata
from astrbot.core.utils.active_event_registry import active_event_registry


async def _apply_persona_capabilities(req, cfg, context, event):
    """Exercise persona selection together with the registered-tool policy."""
    await persona_build.apply_persona(req, cfg, context, event)


@pytest.fixture
def valid_image_path(tmp_path):
    """Create a real image for builder tests that exercise provider selection."""
    from PIL import Image as PILImage

    path = tmp_path / "input.jpg"
    PILImage.new("RGB", (8, 8), "red").save(path)
    return str(path)


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
    ctx.get_platform_inst.return_value = SimpleNamespace(
        meta=lambda: PlatformMetadata(
            id="test", name="test_platform", description="Test"
        )
    )
    ctx.get_using_provider_async = AsyncMock(
        side_effect=lambda *args, **kwargs: ctx.get_using_provider(*args, **kwargs)
    )
    ctx.conversation_manager = MagicMock()
    ctx.persona_manager = MagicMock()
    ctx.persona_manager.personas_v3 = []
    ctx.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, None, False)
    )
    ctx.persona_manager.get_persona_v3_by_id = MagicMock(return_value=None)
    tool_mgr = MagicMock()
    tool_mgr.get_builtin_tool.side_effect = lambda cls, **kwargs: cls(**kwargs)
    ctx.get_llm_tool_manager.return_value = tool_mgr
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
    assert providers_build.supports_modality(provider, "image")

    provider.provider_config = {"modalities": ["text"]}
    assert not providers_build.supports_modality(provider, "image")

    provider.provider_config = {}
    assert not providers_build.supports_modality(provider, "image")

    provider.provider_config = {"modalities": "image"}
    assert not providers_build.supports_modality(provider, "image")


@pytest.fixture
def sample_config():
    """Create a sample MainAgentBuildConfig."""
    return ama.MainAgentBuildConfig(
        tool_call_timeout=60,
        streaming_response=True,
        file_extract_enabled=True,
        file_extract_prov="moonshotai",
        file_extract_msh_api_key="test-api-key",
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
        tzinfo=datetime.timezone.utc,
    )

    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return fixed_now.astimezone(tz)
            return fixed_now

    with patch("astrbot.core.agent_input.datetime.datetime", FixedDateTime):
        request_build.append_system_reminders(
            mock_event,
            req,
            {"datetime_system_prompt": True},
            "UTC",
        )

    assert [part.text for part in req.extra_user_content_parts] == [
        "<system_reminder>Current datetime: "
        "2026-06-08 12:34 (UTC), Weekday: Monday</system_reminder>"
    ]


def test_local_mode_prompt_uses_windows_powershell_51():
    with (
        patch(
            "astrbot.core.astr_agent_runtime.main_agent.computer_use.platform.system",
            return_value="Windows",
        ),
        patch.object(
            computer_use_build,
            "resolve_windows_shell",
            return_value="powershell.exe",
        ),
    ):
        prompt = computer_use_build._build_local_mode_prompt()

    assert "Windows PowerShell 5.1 (powershell.exe)" in prompt
    assert "PowerShell 7-only syntax" in prompt
    assert "cmd.exe" not in prompt
    assert "Restricted Windows execution uses AppContainer" in prompt
    assert "Workspace:\\" in prompt


def test_local_mode_prompt_hints_pwsh_when_resolved():
    with (
        patch(
            "astrbot.core.astr_agent_runtime.main_agent.computer_use.platform.system",
            return_value="Windows",
        ),
        patch.object(
            computer_use_build,
            "resolve_windows_shell",
            return_value="pwsh.exe",
        ),
    ):
        prompt = computer_use_build._build_local_mode_prompt()

    assert "PowerShell 7 (pwsh.exe)" in prompt
    assert "Windows PowerShell 5.1" not in prompt
    assert "Unix-like" not in prompt
    assert "Restricted Windows execution uses AppContainer" in prompt


def test_local_mode_prompt_ignores_pwsh_on_non_windows():
    with (
        patch(
            "astrbot.core.astr_agent_runtime.main_agent.computer_use.platform.system",
            return_value="Linux",
        ),
        patch.object(
            computer_use_build,
            "resolve_windows_shell",
            return_value="pwsh.exe",
        ),
    ):
        prompt = computer_use_build._build_local_mode_prompt()

    assert "Unix-like" in prompt
    assert "POSIX-compatible" in prompt
    assert "PowerShell" not in prompt
    assert "AppContainer" not in prompt


def test_local_mode_prompt_keeps_posix_shell_guidance():
    with patch(
        "astrbot.core.astr_agent_runtime.main_agent.computer_use.platform.system",
        return_value="Linux",
    ):
        prompt = computer_use_build._build_local_mode_prompt()

    assert "Unix-like" in prompt
    assert "POSIX-compatible" in prompt
    assert "PowerShell" not in prompt


class TestMainAgentBuildConfig:
    """Tests for MainAgentBuildConfig dataclass."""

    def test_from_config_isolates_nested_settings(self):
        """Keep build settings stable when the source session config changes."""
        source = {
            "provider_settings": {"sandbox": {"booter": "test"}},
            "agent": {"config": {"model": {"fallback_provider_ids": ["backup"]}}},
        }
        config = ama.MainAgentBuildConfig.from_config(source)
        source["provider_settings"]["sandbox"]["booter"] = "changed"
        source["agent"]["config"]["model"]["fallback_provider_ids"].clear()

        assert config.sandbox_cfg == {"booter": "test"}
        assert config.provider_settings["sandbox"] == {"booter": "test"}
        assert config.fallback_provider_ids == ["backup"]

    def test_config_initialization(self):
        """Test MainAgentBuildConfig initialization with defaults."""
        config = ama.MainAgentBuildConfig(tool_call_timeout=60)
        assert config.tool_call_timeout == 60
        assert config.tool_schema_mode == "full"
        assert config.provider_wake_prefix == ""
        assert config.streaming_response is True
        assert config.sanitize_context_by_modalities is False
        assert config.kb_agentic_mode is False
        assert config.file_extract_enabled is False
        assert config.llm_safety_mode is True
        assert config.computer_use_runtime == "none"

    def test_config_with_custom_values(self):
        """Test MainAgentBuildConfig with custom values."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=120,
            tool_schema_mode="skills-like",
            provider_wake_prefix="/",
            streaming_response=False,
            kb_agentic_mode=True,
            file_extract_enabled=True,
            computer_use_runtime="sandbox",
            add_cron_tools=False,
        )
        assert config.tool_call_timeout == 120
        assert config.tool_schema_mode == "skills-like"
        assert config.provider_wake_prefix == "/"
        assert config.streaming_response is False
        assert config.kb_agentic_mode is True
        assert config.file_extract_enabled is True
        assert config.computer_use_runtime == "sandbox"
        assert config.add_cron_tools is False


class TestSelectProvider:
    """Tests for select_chat_provider function."""

    @pytest.mark.asyncio
    async def test_select_provider_by_id(
        self,
        mock_event,
        mock_context,
        mock_provider,
    ):
        """Test selecting provider by ID from event extra."""
        mock_event.get_extra.side_effect = lambda k: (
            "test-provider" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = mock_provider

        result = await providers_build.select_chat_provider(mock_event, mock_context)

        assert result == mock_provider
        mock_context.get_provider_by_id.assert_called_once_with("test-provider")

    @pytest.mark.asyncio
    async def test_select_provider_not_found(self, mock_event, mock_context):
        """Test selecting provider when ID is not found."""
        mock_event.get_extra.side_effect = lambda k: (
            "non-existent" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = None

        result = await providers_build.select_chat_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            agent_errors.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：未找到指定的提供商 `non-existent`。请检查提供商配置或重新选择可用模型。",
        )

    @pytest.mark.asyncio
    async def test_select_provider_invalid_type(self, mock_event, mock_context):
        """Test selecting provider when result is not a Provider instance."""
        mock_event.get_extra.side_effect = lambda k: (
            "invalid" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = "not a provider"

        result = await providers_build.select_chat_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            agent_errors.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：选择的提供商类型无效（str），已跳过本次请求。",
        )

    @pytest.mark.asyncio
    async def test_select_provider_fallback(
        self,
        mock_event,
        mock_context,
        mock_provider,
    ):
        """Test provider selection fallback to using provider."""
        mock_event.get_extra.return_value = None
        mock_context.get_using_provider.return_value = mock_provider

        result = await providers_build.select_chat_provider(mock_event, mock_context)

        assert result == mock_provider
        mock_context.get_using_provider.assert_called_once_with(
            umo=mock_event.unified_msg_origin
        )

    @pytest.mark.asyncio
    async def test_select_provider_fallback_error(self, mock_event, mock_context):
        """Test provider selection when fallback raises ValueError."""
        mock_event.get_extra.return_value = None
        mock_context.get_using_provider.side_effect = ValueError("Test error")

        result = await providers_build.select_chat_provider(mock_event, mock_context)

        assert result is None
        mock_event.set_extra.assert_called_with(
            agent_errors.LLM_ERROR_MESSAGE_EXTRA_KEY,
            "LLM 请求失败：Test error",
        )


@pytest.mark.asyncio
async def test_provider_manager_async_selection_uses_session_preference(monkeypatch):
    preferred_provider = object()
    manager = ProviderManager.__new__(ProviderManager)
    manager.inst_map = {"preferred": preferred_provider}
    manager.acm = MagicMock()

    get_async = AsyncMock(return_value="preferred")
    monkeypatch.setattr(provider_manager_module.sp, "get_async", get_async)

    result = await manager.get_using_provider_async(
        ProviderType.CHAT_COMPLETION,
        "session-1",
    )

    assert result is preferred_provider
    get_async.assert_awaited_once_with(
        "umo",
        "session-1",
        "provider_perf_chat_completion",
        None,
    )


class TestGetSessionConv:
    """Tests for _get_session_conv function."""

    @pytest.mark.asyncio
    async def test_get_session_conv_existing(
        self, mock_event, mock_context, mock_conversation
    ):
        """Test getting existing conversation."""
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value="existing-conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=mock_conversation)

        result = await request_build._get_session_conv(mock_event, mock_context)

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
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="new-conv-id")
        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.cid = "new-conv-id"
        mock_conversation.persona_id = None
        mock_conversation.history = "[]"
        conv_mgr.get_conversation = AsyncMock(return_value=mock_conversation)

        result = await request_build._get_session_conv(mock_event, mock_context)

        assert result == mock_conversation
        conv_mgr.new_conversation.assert_called_once_with(
            mock_event.unified_msg_origin, mock_event.get_platform_id()
        )

    @pytest.mark.asyncio
    async def test_get_session_conv_retry(self, mock_event, mock_context):
        """Test retrying conversation creation after failure."""
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="retry-conv-id")
        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.cid = "retry-conv-id"
        mock_conversation.persona_id = None
        mock_conversation.history = "[]"
        conv_mgr.get_conversation.side_effect = [None, mock_conversation]

        result = await request_build._get_session_conv(mock_event, mock_context)

        assert result == mock_conversation
        assert conv_mgr.new_conversation.call_count == 1
        assert conv_mgr.get_conversation.call_count == 2

    @pytest.mark.asyncio
    async def test_get_session_conv_failure(self, mock_event, mock_context):
        """Test RuntimeError when conversation creation fails."""
        conv_mgr = mock_context.conversation_manager
        conv_mgr.get_curr_conversation_id = AsyncMock(return_value=None)
        conv_mgr.new_conversation = AsyncMock(return_value="new-conv-id")
        conv_mgr.get_conversation = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="无法创建新的对话。"):
            await request_build._get_session_conv(mock_event, mock_context)


class TestApplyKb:
    """Tests for knowledge-base retrieval and agentic query tools."""

    @pytest.mark.asyncio
    async def test_apply_kb_without_agentic_mode(self, mock_event, mock_context):
        """Test applying knowledge base in non-agentic mode."""
        req = ProviderRequest(prompt="test question", system_prompt="System prompt")
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)

        with patch.object(
            knowledge_base_build,
            "retrieve_knowledge_base",
            AsyncMock(return_value="KB result"),
        ):
            await knowledge_base_build.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

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
        req = ProviderRequest(prompt="test question")
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=True)

        await knowledge_base_build.apply_knowledge_base(
            mock_event, req, mock_context, config
        )

        assert (
            req.func_tool.get_tool(knowledge_base_build.KnowledgeBaseQueryTool().name)
            is not None
        )

    @pytest.mark.asyncio
    async def test_apply_kb_no_prompt(self, mock_event, mock_context):
        """Test applying knowledge base when prompt is None."""
        req = ProviderRequest(prompt=None, system_prompt="System")
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)

        await knowledge_base_build.apply_knowledge_base(
            mock_event, req, mock_context, config
        )

        assert req.system_prompt == "System"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("prompt", ["", "   \n\t"])
    async def test_apply_kb_blank_prompt(self, prompt, mock_event, mock_context):
        """Test applying knowledge base when prompt is blank."""
        req = ProviderRequest(prompt=prompt, system_prompt="System")
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)
        retrieve = AsyncMock(return_value="KB result")

        with patch.object(
            knowledge_base_build,
            "retrieve_knowledge_base",
            retrieve,
        ):
            await knowledge_base_build.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        retrieve.assert_not_awaited()
        assert req.system_prompt == "System"

    @pytest.mark.asyncio
    async def test_apply_kb_no_result(self, mock_event, mock_context):
        """Test applying knowledge base when no result is returned."""
        req = ProviderRequest(prompt="test", system_prompt="System")
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=False)

        with patch.object(
            knowledge_base_build,
            "retrieve_knowledge_base",
            AsyncMock(return_value=None),
        ):
            await knowledge_base_build.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        assert req.system_prompt == "System"

    @pytest.mark.asyncio
    async def test_apply_kb_with_existing_tools(self, mock_event, mock_context):
        """Test applying knowledge base with existing toolset."""
        existing_tools = ToolSet()
        req = ProviderRequest(prompt="test", func_tool=existing_tools)
        config = ama.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=True)

        await knowledge_base_build.apply_knowledge_base(
            mock_event, req, mock_context, config
        )

        assert req.func_tool is not None


class TestBuiltinToolInjection:
    """Tests for builtin tool injection paths."""

    @pytest.mark.asyncio
    async def test_serpapi_injects_all_search_tools(self, mock_event, mock_context):
        """Verify all configured SerpApi tools reach the model request."""
        req = ProviderRequest()
        mock_context.get_config.return_value = {
            "provider_settings": {"web_search": True, "websearch_provider": "serpapi"}
        }

        web_search_build.apply_web_search(
            req,
            mock_context,
            mock_context.get_config()["provider_settings"],
            mock_event,
        )

        assert req.func_tool.names() == [
            "web_search_serpapi",
            "news_search_serpapi",
            "image_search_serpapi",
            "finance_search_serpapi",
            "scholar_search_serpapi",
        ]
        assert isinstance(
            req.func_tool.get_tool("web_search_serpapi"),
            web_search_build.SerpApiWebSearchTool,
        )
        assert isinstance(
            req.func_tool.get_tool("image_search_serpapi"),
            web_search_build.SerpApiImageSearchTool,
        )

    @pytest.mark.asyncio
    async def test_apply_web_search_tools_uses_builtin_tool_manager(
        self, mock_event, mock_context
    ):
        """Test web search tool injection through the builtin tool manager."""
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

        web_search_build.apply_web_search(
            req,
            mock_context,
            mock_context.get_config()["provider_settings"],
            mock_event,
        )

        tool_mgr.get_builtin_tool.assert_called_once_with(
            web_search_build.BaiduWebSearchTool
        )
        assert req.func_tool is not None
        assert req.func_tool.get_tool("web_search_baidu") is builtin_tool

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider", "search_class", "extract_class", "search_name", "extract_name"),
        [
            (
                "firecrawl",
                web_search_build.FirecrawlWebSearchTool,
                web_search_build.FirecrawlExtractWebPageTool,
                "web_search_firecrawl",
                "firecrawl_extract_web_page",
            ),
            (
                "deepseek",
                web_search_build.DeepSeekWebSearchTool,
                web_search_build.DeepSeekFetchWebPageTool,
                "web_search_deepseek",
                "deepseek_fetch_web_page",
            ),
        ],
    )
    async def test_apply_web_search_tools_adds_search_and_extract_tools(
        self,
        mock_event,
        mock_context,
        provider,
        search_class,
        extract_class,
        search_name,
        extract_name,
    ):
        """Test web search providers inject both search and extraction tools."""
        req = ProviderRequest()
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": provider,
            }
        }
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = search_name
        extract_tool = MagicMock(spec=FunctionTool)
        extract_tool.name = extract_name
        tool_mgr = MagicMock()
        tool_mgr.get_builtin_tool.side_effect = [search_tool, extract_tool]
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        web_search_build.apply_web_search(
            req,
            mock_context,
            mock_context.get_config()["provider_settings"],
            mock_event,
        )

        assert tool_mgr.get_builtin_tool.call_args_list == [
            ((search_class,),),
            ((extract_class,),),
        ]
        assert req.func_tool is not None
        assert req.func_tool.get_tool(search_name) is search_tool
        assert req.func_tool.get_tool(extract_name) is extract_tool

    @pytest.mark.parametrize(
        "tool_name",
        [
            "web_search_tavily",
            "web_search_deepseek",
            "web_search_serpapi",
            "news_search_serpapi",
            "image_search_serpapi",
            "finance_search_serpapi",
            "scholar_search_serpapi",
        ],
    )
    def test_apply_web_search_citation_prompt_for_webchat(self, mock_event, tool_name):
        req = ProviderRequest(system_prompt="base")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = tool_name
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "webchat"

        req.system_prompt += web_search_build._get_citation_instructions(
            mock_event, req
        )

        assert web_search_build.WEB_SEARCH_CITATION_PROMPT in req.system_prompt

    def test_apply_web_search_citation_prompt_is_idempotent(self, mock_event):
        req = ProviderRequest(system_prompt="")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_tavily"
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "webchat"

        req.system_prompt += web_search_build._get_citation_instructions(
            mock_event, req
        )
        req.system_prompt += web_search_build._get_citation_instructions(
            mock_event, req
        )

        assert req.system_prompt.count(web_search_build.WEB_SEARCH_CITATION_PROMPT) == 1

    def test_apply_web_search_citation_prompt_requires_webchat(self, mock_event):
        req = ProviderRequest(system_prompt="")
        search_tool = MagicMock(spec=FunctionTool)
        search_tool.name = "web_search_tavily"
        req.func_tool = ToolSet()
        req.func_tool.add_tool(search_tool)
        mock_event.get_platform_name.return_value = "test_platform"

        req.system_prompt += web_search_build._get_citation_instructions(
            mock_event, req
        )

        assert web_search_build.WEB_SEARCH_CITATION_PROMPT not in req.system_prompt

    @pytest.mark.asyncio
    async def test_proactive_cron_job_tools_uses_builtin_tool_manager(
        self, mock_context, mock_event, mock_provider
    ):
        """Test cron tool injection through the builtin tool manager."""
        mock_event.platform_meta.support_proactive_message = False
        req = ProviderRequest()
        tool_mgr = MagicMock()

        future_task_tool = MagicMock(spec=FunctionTool)
        future_task_tool.name = "future_task"
        tool_mgr.get_builtin_tool.return_value = future_task_tool
        mock_context.get_llm_tool_manager.return_value = tool_mgr

        req.prompt = "Run task"
        with (
            patch.object(native_execution, "AgentRunner") as runner,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            runner.return_value.reset = AsyncMock()
            await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
                provider=mock_provider,
                req=req,
            )

        tool_mgr.get_builtin_tool.assert_called_once_with(builder_build.FutureTaskTool)
        assert req.func_tool is not None
        assert req.func_tool.get_tool("future_task") is future_task_tool


class TestApplyFileExtract:
    """Tests for _apply_file_extract function."""

    @pytest.mark.asyncio
    async def test_file_extract_basic(self, mock_event, sample_config):
        """Test basic file extraction."""
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt="Summarize")

        with patch.object(core_input, "extract_file_moonshotai") as mock_extract:
            mock_extract.return_value = "File content"

            await core_input._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 1
        assert "File Extract Results" in req.contexts[0]["content"]

    @pytest.mark.asyncio
    async def test_file_extract_no_files(self, mock_event, sample_config):
        """Test file extraction when no files present."""
        mock_event.message_obj.message = [Plain(text="Hello")]
        req = ProviderRequest(prompt="Hello")

        await core_input._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 0

    @pytest.mark.asyncio
    async def test_file_extract_in_reply(self, mock_event, sample_config):
        """Test file extraction from reply chain."""
        mock_file = MagicMock(spec=File)
        mock_file.name = "reply.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/reply.pdf")
        mock_reply = MagicMock(spec=Reply)
        mock_reply.chain = [mock_file]
        mock_event.message_obj.message = [mock_reply]

        req = ProviderRequest(prompt="Summarize")

        with patch.object(core_input, "extract_file_moonshotai") as mock_extract:
            mock_extract.return_value = "Reply content"

            await core_input._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 1

    @pytest.mark.asyncio
    async def test_file_extract_no_prompt(self, mock_event, sample_config):
        """Test file extraction when prompt is empty."""
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt=None)

        with patch.object(core_input, "extract_file_moonshotai") as mock_extract:
            mock_extract.return_value = "Content"

            await core_input._apply_file_extract(mock_event, req, sample_config)

        assert req.prompt == "总结一下文件里面讲了什么？"

    @pytest.mark.asyncio
    async def test_file_extract_no_api_key(self, mock_event):
        """Test file extraction when no API key is configured."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            file_extract_enabled=True,
            file_extract_msh_api_key="",
        )
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt="Summarize")

        await core_input._apply_file_extract(mock_event, req, config)

        assert len(req.contexts) == 0


class TestEnsurePersonaAndSkills:
    """Tests for _ensure_persona_and_skills function."""

    def test_filter_plugin_skills_uses_current_config_plugin_set(self, monkeypatch):
        monkeypatch.setattr(
            plugins_build,
            "star_registry",
            [
                StarMetadata(
                    name="allowed_plugin",
                    root_dir_name="astrbot_plugin_allowed",
                    activated=True,
                ),
                StarMetadata(
                    name="blocked_plugin",
                    root_dir_name="astrbot_plugin_blocked",
                    activated=True,
                ),
            ],
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

        filtered = plugins_build.filter_skills(
            skills,
            {"plugin_set": ["allowed_plugin"]},
        )

        assert [skill.name for skill in filtered] == ["local", "allowed-skill"]

    def test_filter_plugin_skills_skips_inactive_plugins_even_when_all_allowed(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            plugins_build,
            "star_registry",
            [
                StarMetadata(
                    name="inactive_plugin",
                    root_dir_name="astrbot_plugin_inactive",
                    activated=False,
                )
            ],
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

        filtered = plugins_build.filter_skills(
            skills,
            {"plugin_set": ["*"]},
        )

        assert filtered == []

    @pytest.mark.asyncio
    async def test_ensure_persona_from_session(self, mock_event, mock_context):
        """Test applying persona from session service config."""
        persona = {"name": "test-persona", "prompt": "You are helpful."}
        mock_context.persona_manager.personas_v3 = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("test-persona", persona, "test-persona", False)
        )
        mock_event.trace = MagicMock(record=MagicMock())
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "You are helpful." in req.system_prompt
        assert (
            "<persona_instructions>\nYou are helpful.\n</persona_instructions>"
            in req.system_prompt
        )
        mock_event.set_extra.assert_any_call("_trace_persona_id", "test-persona")
        assert not any(
            call.args[0] == "sel_persona"
            for call in mock_event.trace.record.call_args_list
        )

    @pytest.mark.asyncio
    async def test_ensure_persona_from_conversation(self, mock_event, mock_context):
        """Test applying persona from conversation setting."""
        persona = {"name": "conv-persona", "prompt": "Custom persona."}
        mock_context.persona_manager.personas_v3 = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("conv-persona", persona, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="conv-persona")

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "Custom persona." in req.system_prompt
        mock_event.set_extra.assert_any_call("_trace_persona_id", "conv-persona")

    @pytest.mark.asyncio
    async def test_inline_genui_prompt_is_added_with_custom_persona(
        self, mock_event, mock_context
    ):
        """Test inline GenUI instructions are independent of persona selection."""
        persona = {"name": "conv-persona", "prompt": "Custom persona."}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("conv-persona", persona, None, False)
        )
        mock_event.get_extra.side_effect = lambda key: key == "enable_inline_genui"
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="conv-persona")

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "Custom persona." in req.system_prompt
        assert persona_build.CHATUI_INLINE_GENUI_SYSTEM_PROMPT in req.system_prompt
        assert req.system_prompt.index(
            "</genui_instructions>"
        ) < req.system_prompt.index("<persona_instructions>")

    @pytest.mark.asyncio
    async def test_inline_genui_prompt_does_not_require_conversation(
        self, mock_event, mock_context
    ):
        """Test inline GenUI instructions are added before conversation setup."""
        mock_event.get_extra.side_effect = lambda key: key == "enable_inline_genui"
        req = ProviderRequest()

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert persona_build.CHATUI_INLINE_GENUI_SYSTEM_PROMPT in req.system_prompt
        mock_context.persona_manager.resolve_selected_persona.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_system_prompt_can_be_disabled(
        self, mock_event, mock_context
    ):
        """Test the default ChatUI persona prompt honors its request flag."""
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("_chatui_default_", None, None, True)
        )
        mock_event.get_extra.side_effect = lambda key: {
            "enable_inline_genui": False,
            "enable_default_system_prompt": False,
        }.get(key)
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert (
            persona_build.CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT not in req.system_prompt
        )
        assert "<persona_instructions>" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_webchat_implicit_default_injects_chatui_prompt(
        self, mock_event, mock_context
    ):
        """WebChat implicit default uses the ChatUI prompt, not the DB persona."""
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("_chatui_default_", None, None, True)
        )
        mock_event.get_platform_name.return_value = "webchat"
        mock_event.get_extra.side_effect = lambda key: {
            "enable_inline_genui": False,
            "enable_default_system_prompt": True,
        }.get(key)
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert persona_build.CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT in req.system_prompt
        assert "Persona Instructions" not in req.system_prompt
        assert req.system_prompt.count("<persona_instructions>") == 1
        assert req.system_prompt.count("</persona_instructions>") == 1

    @pytest.mark.asyncio
    async def test_non_webchat_implicit_default_injects_db_persona(
        self, mock_event, mock_context
    ):
        """Non-WebChat implicit default injects the editable DB default persona."""
        persona = {"name": "default", "prompt": "EDITED DEFAULT"}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("default", persona, None, False)
        )
        mock_event.get_extra.side_effect = lambda key: None
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "EDITED DEFAULT" in req.system_prompt
        assert (
            persona_build.CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT not in req.system_prompt
        )

    @pytest.mark.asyncio
    async def test_explicit_default_persona_ignores_default_system_prompt_flag(
        self, mock_event, mock_context
    ):
        """Explicitly selecting the default persona uses the record even when the flag is off."""
        persona = {"name": "default", "prompt": "EDITED DEFAULT"}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("default", persona, None, False)
        )
        mock_event.get_platform_name.return_value = "webchat"
        mock_event.get_extra.side_effect = lambda key: {
            "enable_inline_genui": False,
            "enable_default_system_prompt": False,
        }.get(key)
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="default")

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "EDITED DEFAULT" in req.system_prompt
        assert (
            persona_build.CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT not in req.system_prompt
        )

    @pytest.mark.asyncio
    async def test_webchat_implicit_default_regression_with_real_persona_manager(
        self, mock_event, mock_context
    ):
        """A seeded system default must not swallow the WebChat ChatUI prompt."""
        from astrbot.core import persona_mgr as pm
        from astrbot.core.db.po import Persona

        conf = {
            "agent": {
                "runtime": "astrbot",
                "config": {"persona": {"persona_id": "default"}},
            },
            "provider_settings": {},
        }
        acm = MagicMock()
        acm.default_conf = conf
        acm.get_conf.return_value = conf

        db = MagicMock()
        db.get_personas = AsyncMock(
            return_value=[
                Persona(
                    persona_id="default",
                    system_prompt="EDITED DEFAULT",
                    begin_dialogs=[],
                    tools=None,
                    skills=None,
                    custom_error_message=None,
                    folder_id=None,
                    sort_order=0,
                )
            ]
        )
        db.insert_persona = AsyncMock()
        manager = pm.PersonaManager(db_helper=db, acm=acm)
        await manager.initialize()
        mock_context.persona_manager = manager

        mock_event.get_platform_name.return_value = "webchat"
        mock_event.get_extra.side_effect = lambda key: {
            "enable_inline_genui": False,
            "enable_default_system_prompt": True,
        }.get(key)
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id=None)

        with patch.object(pm.sp, "get_async", new=AsyncMock(return_value={})):
            await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert persona_build.CHATUI_SPECIAL_DEFAULT_PERSONA_PROMPT in req.system_prompt
        assert "EDITED DEFAULT" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_persona_none_explicit(self, mock_event, mock_context):
        """Test that [%None] persona is explicitly set to no persona."""
        mock_context.persona_manager.personas_v3 = []
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("[%None]", None, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="[%None]")

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert "Persona Instructions" not in req.system_prompt
        assert "<persona_instructions>" not in req.system_prompt

    @pytest.mark.asyncio
    @pytest.mark.parametrize("runtime", ["none", "local", "sandbox"])
    @pytest.mark.parametrize("allowed", [None, [], ["selected-skill"]])
    async def test_skills_block_contains_filtered_inventory_and_runtime_notice(
        self, mock_event, mock_context, runtime, allowed
    ):
        """Keep skill rules and runtime notices inside the filtered skills block.

        Args:
            mock_event: Event identifying the current session.
            mock_context: Persona and tool services used by the builder.
            runtime: Computer-use runtime controlling the skill capability notice.
            allowed: Persona skill selection, including all or no skills.
        """
        selected = {"prompt": "Persona marker", "tools": [], "skills": allowed}
        mock_context.persona_manager.resolve_selected_persona.return_value = (
            "persona",
            selected,
            None,
            False,
        )
        req = ProviderRequest(conversation=MagicMock(persona_id="persona"))
        with patch.object(persona_build, "SkillManager") as manager:
            manager.return_value.list_skills.return_value = [
                SkillInfo(
                    name=name,
                    description=name,
                    path=f"/skills/{name}/SKILL.md",
                    active=True,
                )
                for name in ("selected-skill", "excluded-skill")
            ]
            manager.return_value.list_workspace_skills.return_value = []
            await _apply_persona_capabilities(
                req, {"computer_use_runtime": runtime}, mock_context, mock_event
            )

        if allowed == []:
            assert "<skills_instructions>" not in req.system_prompt
            assert "</skills_instructions>" not in req.system_prompt
            assert "User has not enabled" not in req.system_prompt
            return
        before, _, block = req.system_prompt.partition("<skills_instructions>")
        block, closing, after = block.partition("</skills_instructions>")
        assert "</persona_instructions>" in before
        assert closing
        assert not after.strip()
        assert "Persona marker" not in block
        assert "**selected-skill**" in block
        assert ("**excluded-skill**" in block) is (allowed is None)
        assert "### Skill rules" in block
        assert "Mandatory grounding" in block
        assert ("User has not enabled" in block) is (runtime == "none")

    @pytest.mark.asyncio
    async def test_ensure_skills_includes_workspace_skills(
        self,
        monkeypatch,
        tmp_path,
        mock_event,
        mock_context,
    ):
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

        workspace_root = workspaces_dir / workspace_build.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            workspace_build,
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

        await _apply_persona_capabilities(req, runtime_config, mock_context, mock_event)

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
        data_dir = tmp_path / "data"
        global_skills_dir = tmp_path / "global_skills"
        plugins_dir = tmp_path / "plugins"
        workspaces_dir = tmp_path / "workspaces"
        for path in (data_dir, global_skills_dir, plugins_dir):
            path.mkdir(parents=True, exist_ok=True)

        workspace_root = workspaces_dir / workspace_build.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            workspace_build,
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

        await _apply_persona_capabilities(
            req, {"computer_use_runtime": "local"}, mock_context, mock_event
        )

        assert "Workspace scoped skill." not in req.system_prompt
        assert "## Skills" not in req.system_prompt
        assert "<skills_instructions>" not in req.system_prompt

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "runtime_settings",
        [{}, {"computer_use_runtime": "none"}, {"computer_use_runtime": "sandbox"}],
    )
    async def test_ensure_skills_skips_workspace_skills_outside_local_runtime(
        self,
        runtime_settings,
        monkeypatch,
        tmp_path,
        mock_event,
        mock_context,
    ):
        data_dir = tmp_path / "data"
        global_skills_dir = tmp_path / "global_skills"
        plugins_dir = tmp_path / "plugins"
        workspaces_dir = tmp_path / "workspaces"
        for path in (data_dir, global_skills_dir, plugins_dir):
            path.mkdir(parents=True, exist_ok=True)

        workspace_root = workspaces_dir / workspace_build.normalize_umo_for_workspace(
            mock_event.unified_msg_origin
        )
        workspace_skill_dir = workspace_root / "skills" / "workspace-skill"
        workspace_skill_dir.mkdir(parents=True)
        workspace_skill_dir.joinpath("SKILL.md").write_text(
            "---\ndescription: Workspace scoped skill.\n---\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            workspace_build,
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

        await _apply_persona_capabilities(
            req,
            runtime_settings,
            mock_context,
            mock_event,
        )

        assert "Workspace scoped skill." not in req.system_prompt
        assert "## Skills" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_tools_from_persona(self, mock_event, mock_context):
        """Test applying tools from persona."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.active = True
        persona = {"name": "persona", "prompt": "Test", "tools": ["test_tool"]}
        mock_context.persona_manager.personas_v3 = [persona]
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("persona", persona, None, False)
        )
        tmgr = mock_context.get_llm_tool_manager.return_value
        tmgr.get_func.return_value = mock_tool

        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="persona")

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert req.func_tool is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider", "tool_names"),
        [
            ("baidu_ai_search", ["web_search_baidu"]),
            (
                "serpapi",
                [
                    "web_search_serpapi",
                    "news_search_serpapi",
                    "image_search_serpapi",
                    "finance_search_serpapi",
                    "scholar_search_serpapi",
                ],
            ),
        ],
    )
    async def test_persona_empty_tools_keeps_late_builtin_tools(
        self, mock_event, mock_context, mock_provider, provider, tool_names
    ):
        persona = {"name": "locked", "prompt": "No tools.", "tools": []}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("locked", persona, None, False)
        )
        mock_event.platform_meta.support_proactive_message = False
        mock_context.get_config.return_value = {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": provider,
            }
        }
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            provider_settings={
                "web_search": True,
                "websearch_provider": provider,
            },
            computer_use_runtime="none",
            add_cron_tools=False,
        )
        req = ProviderRequest(prompt="hello")
        req.conversation = MagicMock(persona_id="locked", history="[]")

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=config,
                provider=mock_provider,
                req=req,
            )
        assert result is not None
        assert result.provider_request.func_tool is not None
        assert result.provider_request.func_tool.names() == tool_names
        assert "<execution_environment" not in result.provider_request.system_prompt
        assert "<tool_use_instructions>" in result.provider_request.system_prompt

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["admin", "member"])
    @pytest.mark.parametrize(
        "isolation_status", ["detected", "missing", "unavailable", "unsupported"]
    )
    @pytest.mark.parametrize(
        ("allow_execution", "allow_network"),
        [(True, False), (True, True), (False, False)],
    )
    async def test_persona_empty_tools_keeps_local_runtime_builtin_tools(
        self,
        monkeypatch,
        mock_event,
        mock_context,
        mock_provider,
        role,
        allow_execution,
        allow_network,
        isolation_status,
    ):
        monkeypatch.setattr(
            "astrbot.core.astr_agent_runtime.tools.computer_tools.util.get_process_sandbox_status",
            lambda: {"status": isolation_status},
        )
        persona = {"name": "locked", "prompt": "No tools.", "tools": []}
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("locked", persona, None, False)
        )
        mock_event.platform_meta.support_proactive_message = False
        mock_event.role = role
        mock_context.get_config.return_value = {
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": {
                    role: {
                        "allow_execution": allow_execution,
                        "allow_network": allow_network,
                        "filesystem_scope": "workspace",
                    }
                },
            }
        }
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="local",
            add_cron_tools=False,
        )
        req = ProviderRequest(prompt="hello")
        req.conversation = MagicMock(persona_id="locked", history="[]")

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                return_value=SimpleNamespace(context=mock_context, event=mock_event),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=config,
                provider=mock_provider,
                req=req,
            )
        assert result is not None
        assert result.provider_request.func_tool is not None
        tool_names = result.provider_request.func_tool.names()
        assert "astrbot_execute_shell" in tool_names
        assert "astrbot_shell_session" in tool_names
        assert "astrbot_execute_python" in tool_names
        shell_tool = result.provider_request.func_tool.get_tool("astrbot_execute_shell")
        assert shell_tool is not None
        assert "background" not in shell_tool.parameters["properties"]
        assert "yield_time_ms" in shell_tool.parameters["properties"]
        assert result.provider_request.system_prompt.count(
            computer_use_build.LOCAL_NETWORK_POLICY_NOTICE
        ) == int(
            allow_execution and not allow_network and isolation_status == "detected"
        )
        assert (
            "The Agent Computer Use runtime is the local environment"
            not in result.provider_request.system_prompt
        )
        assert (
            "These restrictions require Local process isolation"
            not in result.provider_request.system_prompt
        )

    @pytest.mark.asyncio
    async def test_legacy_plugin_experts_are_not_mounted_by_main(
        self, mock_event, mock_context
    ):
        """The plugin compatibility entry does not activate native main routing."""
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=(None, None, None, False)
        )
        mock_context.persona_manager.get_persona_v3_by_id = MagicMock(
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
        mock_context.get_config.return_value = {
            "subagent_orchestrator": {
                "main_enable": True,
                "remove_main_duplicate_tools": True,
                "router_system_prompt": "Legacy expert routing.",
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

        await _apply_persona_capabilities(req, {}, mock_context, mock_event)

        assert req.func_tool is not None
        assert "transfer_to_planner" not in req.func_tool.names()
        assert "tool_a" in req.func_tool.names()
        assert "tool_b" in req.func_tool.names()
        assert "Legacy expert routing." not in req.system_prompt


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        (None, "Hello"),
        ("", "Hello"),
        ("AI: ", "AI: Hello"),
        ("AI {{prompt}} - Please respond:", "AI Hello - Please respond:"),
    ],
)
def test_prompt_prefix(prefix, expected):
    req = ProviderRequest(prompt="Hello")
    request_build.apply_prompt_prefix(req, {"prompt_prefix": prefix})
    assert req.prompt == expected


class TestPluginToolFix:
    """Tests for _filter_plugin_tools function."""

    def test_filter_plugin_tools_none_plugins(self, mock_event):
        """Test plugin tool fix when no plugins specified."""
        req = ProviderRequest(func_tool=ToolSet())
        mock_event.plugins_name = None

        req.func_tool = plugins_build.filter_tools(mock_event, req.func_tool)

        assert req.func_tool is not None

    def test_filter_plugin_tools_filters_by_plugin(self, mock_event):
        """Test plugin tool fix filters tools by enabled plugins."""
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

        with patch.object(plugins_build, "star_map") as mock_star_map:
            mock_plugin = MagicMock()
            mock_plugin.name = "test_plugin"
            mock_plugin.reserved = False
            mock_star_map.get.return_value = mock_plugin

            req.func_tool = plugins_build.filter_tools(mock_event, req.func_tool)

        assert "mcp_tool" in req.func_tool.names()
        assert "plugin_tool" in req.func_tool.names()

    def test_filter_plugin_tools_mcp_preserved(self, mock_event):
        """Test that MCP tools are always preserved."""
        mcp_tool = MagicMock(spec=MCPTool)
        mcp_tool.name = "mcp_tool"
        mcp_tool.active = True

        tool_set = ToolSet()
        tool_set.add_tool(mcp_tool)

        req = ProviderRequest(func_tool=tool_set)
        mock_event.plugins_name = ["other_plugin"]

        with patch.object(plugins_build, "star_map"):
            req.func_tool = plugins_build.filter_tools(mock_event, req.func_tool)

        assert "mcp_tool" in req.func_tool.names()

    def test_filter_plugin_tools_preserves_tools_without_plugin_origin(
        self, mock_event
    ):
        """Tools without handler_module_path should not be filtered out."""
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

        with patch.object(plugins_build, "star_map"):
            req.func_tool = plugins_build.filter_tools(mock_event, req.func_tool)

        assert "transfer_to_demo_agent" in req.func_tool.names()


class TestBuildMainAgent:
    """Tests for build_main_agent function."""

    @pytest.mark.asyncio
    async def test_returned_runner_contains_final_request_messages(
        self, mock_event, mock_context, mock_provider
    ):
        """Initialize the real runner with the request after plugin modifications.

        Args:
            mock_event: Event identifying the current turn.
            mock_context: Services used to construct the agent.
            mock_provider: Selected provider without any actual model calls.
        """
        mock_context.mock_add_spec(Context)
        req = ProviderRequest(prompt="Original input")

        async def hook(event, kind, request):
            request.prompt = "Plugin input"
            request.system_prompt = "Plugin instructions"
            return False

        with patch.object(
            builder_build, "call_event_hook", AsyncMock(side_effect=hook)
        ):
            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    call_request_hook=True,
                    validate_provider_endpoint=True,
                ),
                provider=mock_provider,
                req=req,
            )

        assert result is not None
        runner = result.agent_runner
        assert runner.state is AgentState.IDLE
        assert runner.req is req
        assert runner.provider is mock_provider
        assert runner.run_context.context.event is mock_event
        assert [message.role for message in runner.run_context.messages] == [
            "system",
            "user",
        ]
        assert runner.run_context.messages[0].content == "Plugin instructions"
        assert runner.run_context.messages[1].content[0].text == "Plugin input"

    @pytest.mark.asyncio
    async def test_build_main_agent_basic(
        self, mock_event, mock_context, mock_provider
    ):
        """Test basic main agent building."""
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert isinstance(result, ama.MainAgentBuildResult)

    @pytest.mark.asyncio
    async def test_build_main_agent_passes_max_context_length_to_runner(
        self, mock_event, mock_context, mock_provider
    ):
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    max_context_length=7,
                ),
            )

        assert result is not None
        mock_runner.reset.assert_awaited_once()
        assert mock_runner.reset.await_args.kwargs["enforce_max_turns"] == 7

    @pytest.mark.asyncio
    async def test_build_main_agent_passes_session_compression_to_runner(
        self, mock_event, mock_context, mock_provider
    ):
        """Pass the summary provider, token budget and turn limits to the runner."""
        compressor = MagicMock(spec=Provider)
        mock_context.get_provider_by_id.side_effect = lambda provider_id: (
            compressor if provider_id == "summary-model" else None
        )
        mock_context.get_using_provider.return_value = mock_provider
        mock_provider.get_model.return_value = "unknown-model-for-compression-test"
        _setup_conversation_for_build(mock_context.conversation_manager)

        with (
            patch.object(native_execution, "AgentRunner") as runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            runner = runner_cls.return_value
            runner.reset = AsyncMock()
            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    **resolve_context_compression_config(
                        {
                            "overflow_strategy": "llm_compress",
                            "provider_id": "summary-model",
                            "instruction": "Keep unfinished tasks.",
                            "keep_recent_ratio": 0.3,
                            "max_turns": 12,
                            "trim_turns": 3,
                            "fallback_max_tokens": 16384,
                        }
                    ),
                ),
            )

        assert result is not None
        runner.reset.assert_awaited_once()
        kwargs = runner.reset.await_args.kwargs
        assert kwargs["llm_compress_provider"] is compressor
        assert kwargs["llm_compress_instruction"] == "Keep unfinished tasks."
        assert kwargs["llm_compress_keep_recent_ratio"] == 0.3
        assert kwargs["enforce_max_turns"] == 12
        assert kwargs["truncate_turns"] == 3
        assert kwargs["max_context_tokens"] == 16384
        assert "max_context_tokens" not in kwargs["provider"].provider_config

    @pytest.mark.asyncio
    async def test_build_main_agent_no_provider(self, mock_event, mock_context):
        """Test building main agent when no provider is available."""
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.side_effect = ValueError("No provider")

        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=ama.MainAgentBuildConfig(tool_call_timeout=60),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_build_main_agent_with_wake_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with wake prefix."""
        mock_event.message_str = "/command"
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60, provider_wake_prefix="/"
                ),
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_build_main_agent_no_wake_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent without matching wake prefix."""
        mock_event.message_str = "hello"
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider

        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=ama.MainAgentBuildConfig(
                tool_call_timeout=60, provider_wake_prefix="/"
            ),
        )

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quoted", [False, True])
    @pytest.mark.parametrize("compression_enabled", [False, True])
    async def test_build_main_agent_with_images(
        self,
        mock_event,
        mock_context,
        mock_provider,
        tmp_path,
        monkeypatch,
        quoted,
        compression_enabled,
    ):
        """Direct builders prepare both ordinary and quoted images before reset."""

        from PIL import Image as PILImage

        from astrbot.core.utils import image_input

        monkeypatch.setattr(image_input, "get_astrbot_temp_path", lambda: str(tmp_path))
        source_path = tmp_path / "image.jpg"
        PILImage.new("RGB", (8, 8), (255, 0, 0)).save(source_path)
        original = source_path.read_bytes()
        image = Image.fromFileSystem(str(source_path))
        mock_event.message_obj.message = (
            [Reply(id="reply-1", chain=[image])] if quoted else [image]
        )

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    provider_settings={
                        "image_compress_enabled": compression_enabled,
                        "image_compress_options": {"max_size": 4},
                    },
                ),
            )

        assert result is not None
        request = result.provider_request
        label = "Image 1 in quoted message" if quoted else "Image 1"
        assert f"[{label}: original path {source_path}]" in [
            part.text for part in request.extra_user_content_parts
        ]
        assert len(request.image_urls) == 1
        visual_path = Path(request.image_urls[0])
        assert visual_path != source_path
        with PILImage.open(visual_path) as visual_image:
            assert visual_image.size == (4, 4)
        mock_event.track_temporary_local_file.assert_called_once_with(str(visual_path))
        mock_event.untrack_temporary_local_file.assert_called_once_with(
            str(source_path)
        )
        AstrMessageEvent.cleanup_temporary_local_files(
            SimpleNamespace(
                _temporary_local_files=[
                    call.args[0]
                    for call in mock_event.track_temporary_local_file.call_args_list
                ]
            )
        )
        assert source_path.read_bytes() == original

    @pytest.mark.asyncio
    async def test_build_main_agent_skips_caption_when_main_provider_supports_images(
        self, mock_event, mock_context, mock_provider, valid_image_path
    ):
        """Test image-capable chat providers receive quoted images directly."""
        mock_image = Image(file=Path(valid_image_path).as_uri())
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value=valid_image_path),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    provider_settings={
                        "default_image_caption_provider_id": "caption-provider",
                    },
                ),
                provider=mock_provider,
            )

        assert result is not None
        assert result.provider_request.image_urls == [valid_image_path]
        assert not any(
            "Image Caption" in part.text or "<image_caption>" in part.text
            for part in result.provider_request.extra_user_content_parts
        )
        mock_provider.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_main_agent_does_not_caption_quoted_image_twice(
        self, mock_event, mock_context, valid_image_path
    ):
        """Quoted images should not be captioned again after request image captioning."""
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
            chain=[
                Plain(text="quoted text"),
                Image(file=Path(valid_image_path).as_uri()),
            ],
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value=valid_image_path),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
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
        self, mock_event, mock_context, valid_image_path
    ):
        """Quoted images already sent to image captioning should not be retried."""
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
            chain=[
                Plain(text="quoted text"),
                Image(file=Path(valid_image_path).as_uri()),
            ],
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Image,
                "convert_to_file_path",
                AsyncMock(return_value=valid_image_path),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
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
        self, mock_event, mock_context, valid_image_path
    ):
        """Test image requests use a fallback provider that supports images."""
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
            image_urls=[valid_image_path],
            model="text-model",
        )
        mock_context.get_provider_by_id.side_effect = lambda provider_id: (
            image_provider if provider_id == "image-provider" else None
        )
        mock_context.get_config.return_value = {}

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    llm_safety_mode=False,
                    computer_use_runtime="none",
                    add_cron_tools=False,
                    fallback_provider_ids=["image-provider"],
                ),
                provider=text_provider,
                req=req,
            )

        assert result is not None
        assert result.provider is image_provider
        assert result.provider_request.image_urls == [valid_image_path]
        assert result.provider_request.model is None
        assert mock_runner.reset.call_args.kwargs["provider"] is image_provider
        assert mock_runner.reset.call_args.kwargs["fallback_providers"] == []

    @pytest.mark.asyncio
    async def test_build_main_agent_keeps_text_provider_without_image_fallback(
        self, mock_event, mock_context, valid_image_path
    ):
        """Test image requests fall back to existing sanitizing when no image provider exists."""
        text_provider = MagicMock(spec=Provider)
        text_provider.provider_config = {
            "id": "text-provider",
            "modalities": ["text", "tool_use"],
            "max_context_tokens": 128000,
        }
        text_provider.get_model.return_value = "text-model"

        req = ProviderRequest(
            prompt="describe this",
            image_urls=[valid_image_path],
        )
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_config.return_value = {}

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60,
                    llm_safety_mode=False,
                    computer_use_runtime="none",
                    add_cron_tools=False,
                    provider_settings={
                        "fallback_chat_models": ["missing-provider"],
                    },
                ),
                provider=text_provider,
                req=req,
            )

        assert result is not None
        assert result.provider is text_provider
        assert result.provider_request.image_urls == [valid_image_path]
        assert mock_runner.reset.call_args.kwargs["provider"] is text_provider

    @pytest.mark.asyncio
    async def test_build_main_agent_with_video_attachment(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with video attachments."""
        video_path = str(Path("/path/to/video.mp4"))
        mock_video = Video(file="file:///path/to/video.mp4")
        mock_event.message_obj.message = [mock_video]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert [
            part.text for part in result.provider_request.extra_user_content_parts
        ] == [f"[Video Attachment: name video.mp4, path {video_path}]"]

    @pytest.mark.asyncio
    async def test_build_main_agent_with_quoted_video_attachment(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with quoted video attachments."""
        video_path = str(Path("/path/to/quoted-video.mp4"))
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert (
            "[Video Attachment in quoted message: "
            f"name quoted-video.mp4, path {video_path}]"
        ) in [part.text for part in result.provider_request.extra_user_content_parts]

    @pytest.mark.asyncio
    async def test_build_main_agent_preserves_quoted_video_when_conversion_fails(
        self, mock_event, mock_context, mock_provider
    ):
        """Test quoted video failures preserve the ref without error logging."""
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch("astrbot.core.agent_media.logger") as mock_logger,
            patch.object(
                Video,
                "convert_to_file_path",
                AsyncMock(side_effect=_raise_video_conversion_error),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
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
    async def test_build_main_agent_with_voice_attachments(
        self, mock_event, mock_context, mock_provider
    ):
        """Test that resolvable voice attachments keep their local paths."""
        direct_path = str(Path("/path/to/voice.wav"))
        quoted_path = str(Path("/path/to/quoted.wav"))
        mock_record = Record(file="direct.amr")
        mock_quoted_record = Record(file="quoted.amr")
        mock_reply = Reply(
            id="reply-1",
            chain=[mock_quoted_record],
            sender_nickname="",
            message_str="quoted message",
        )
        mock_event.message_obj.message = [mock_record, mock_reply]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        async def _resolve_voice(self):
            return quoted_path if self.file == "quoted.amr" else direct_path

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Record,
                "convert_to_file_path",
                _resolve_voice,
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert result.provider_request.audio_urls == [direct_path, quoted_path]
        extra_texts = [
            part.text for part in result.provider_request.extra_user_content_parts
        ]
        assert f"[Audio Attachment: path {direct_path}]" in extra_texts
        assert (
            f"[Audio Attachment in quoted message: path {quoted_path}]" in extra_texts
        )
        assert "[Voice unavailable]" not in extra_texts

    @pytest.mark.asyncio
    async def test_build_main_agent_skips_unavailable_voice_attachments(
        self, mock_event, mock_context, mock_provider
    ):
        """Unresolvable voice attachments degrade instead of failing the turn.

        Both the current message and the quoted chain raise a bare ``Exception``,
        which ``is_recoverable_image_error`` rejects, so the branches must degrade
        unconditionally rather than re-raise.
        """
        mock_record = Record(file="")
        mock_quoted_record = Record(file="")
        mock_reply = Reply(
            id="reply-1",
            chain=[Plain(text="quoted text"), mock_quoted_record],
            sender_nickname="",
            message_str="quoted text",
        )
        mock_event.message_obj.message = [Plain(text="Hello"), mock_reply, mock_record]

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        async def _raise_unavailable_voice(self):
            raise Exception(f"not a valid file: {self.file}")

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Record,
                "convert_to_file_path",
                _raise_unavailable_voice,
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
            )

        assert result is not None
        assert result.provider_request.audio_urls == []
        extra_texts = [
            part.text for part in result.provider_request.extra_user_content_parts
        ]
        assert extra_texts.count("[Voice unavailable]") == 2
        assert not any("Audio Attachment" in part for part in extra_texts)

    @pytest.mark.asyncio
    async def test_build_main_agent_propagates_voice_cancellation(
        self, mock_event, mock_context, mock_provider
    ):
        """Cancellation must not be swallowed by the voice degrade path."""
        mock_quoted_record = Record(file="quoted.amr")
        mock_reply = Reply(
            id="reply-1",
            chain=[mock_quoted_record],
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
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                Record,
                "convert_to_file_path",
                AsyncMock(side_effect=asyncio.CancelledError),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            with pytest.raises(asyncio.CancelledError):
                await ama.build_main_agent(
                    event=mock_event,
                    plugin_context=mock_context,
                    config=ama.MainAgentBuildConfig(tool_call_timeout=60),
                )

    @pytest.mark.asyncio
    async def test_build_main_agent_no_prompt_no_images(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent returns None when no prompt or images."""
        mock_event.message_str = ""
        mock_event.message_obj.message = []

        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=ama.MainAgentBuildConfig(tool_call_timeout=60),
        )

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call_request_hook", [False, True])
    @pytest.mark.parametrize("stop", [False, True])
    async def test_build_main_agent_initializes_after_request_hook(
        self, mock_event, mock_context, mock_provider, call_request_hook, stop
    ):
        """Return a ready runner, or reject the request before initialization.

        Args:
            mock_event: Interactive event fixture.
            mock_context: Services used during construction.
            mock_provider: Selected chat provider.
            call_request_hook: Whether this entrypoint dispatches request hooks.
            stop: Whether the hook stops the request.
        """
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider
        mock_context.get_config.return_value = {}

        conv_mgr = mock_context.conversation_manager
        _setup_conversation_for_build(conv_mgr)

        async def request_hook(event, kind, req):
            assert kind is builder_build.EventType.OnLLMRequestEvent
            mock_runner.reset.assert_not_called()
            req.prompt = "Changed by the plugin"
            return stop

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
            patch.object(
                builder_build,
                "call_event_hook",
                AsyncMock(side_effect=request_hook),
            ) as hook,
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(
                    tool_call_timeout=60, call_request_hook=call_request_hook
                ),
            )

        assert hook.await_count == int(call_request_hook)
        if call_request_hook and stop:
            assert result is None
            mock_runner.reset.assert_not_called()
            return
        assert result is not None
        mock_runner.reset.assert_awaited_once()
        assert mock_runner.reset.await_args.kwargs["request"] is result.provider_request
        assert result.provider_request.prompt == (
            "Changed by the plugin" if call_request_hook else "Hello"
        )

    @pytest.mark.asyncio
    async def test_build_main_agent_with_existing_request(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with existing ProviderRequest."""
        existing_req = ProviderRequest(prompt="Existing prompt")
        mock_event.get_extra.side_effect = lambda k: (
            existing_req if k == "provider_request" else None
        )

        with (
            patch.object(native_execution, "AgentRunner") as mock_runner_cls,
            patch.object(
                builder_build,
                "AstrAgentContext",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.reset = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            result = await ama.build_main_agent(
                event=mock_event,
                plugin_context=mock_context,
                config=ama.MainAgentBuildConfig(tool_call_timeout=60),
                provider=mock_provider,
                req=existing_req,
            )

        assert result is not None
        assert result.provider_request == existing_req


class TestHandleWebchat:
    """Tests for _handle_webchat function."""

    @pytest.mark.asyncio
    async def test_handle_webchat_generates_title(self, mock_event):
        """Test generating title for webchat session without display name."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is machine learning?")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "Machine Learning Introduction"
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

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
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt=None)
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_empty_user_prompt(self, mock_event):
        """Test that title generation is skipped when user prompt is empty."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="")
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_session_already_has_display_name(self, mock_event):
        """Test that title generation is skipped when session already has display name."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is AI?")
        prov = MagicMock(spec=Provider)

        mock_session = MagicMock()
        mock_session.display_name = "Existing Title"

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_no_session_found(self, mock_event):
        """Test that title generation is skipped when session is not found."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is AI?")
        prov = MagicMock(spec=Provider)

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=None)

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_none_title(self, mock_event):
        """Test that title is not updated when LLM returns <None>."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="hi")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "<None>"
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_empty_title(self, mock_event):
        """Test that title is not updated when LLM returns empty string."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="hello")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "   "
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_none_response(self, mock_event):
        """Test handling when LLM returns None response."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="test question")
        prov = MagicMock(spec=Provider)
        prov.text_chat = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_llm_returns_no_completion_text(self, mock_event):
        """Test handling when LLM response has no completion_text."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="test question")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = None
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_db.update_platform_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_strips_title_whitespace(self, mock_event):
        """Test that generated title has whitespace stripped."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is Python?")
        prov = MagicMock(spec=Provider)
        llm_response = MagicMock()
        llm_response.completion_text = "  Python Programming Guide  "
        prov.text_chat = AsyncMock(return_value=llm_response)

        mock_session = MagicMock()
        mock_session.display_name = None

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_db.update_platform_session.assert_called_once_with(
            session_id="webchat-session-123",
            display_name="Python Programming Guide",
        )

    @pytest.mark.asyncio
    async def test_handle_webchat_provider_exception_is_handled(self, mock_event):
        """Test that provider exception during title generation is handled."""
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is Python?")
        prov = MagicMock(spec=Provider)
        prov.text_chat = AsyncMock(side_effect=RuntimeError("provider failed"))

        mock_session = MagicMock()
        mock_session.display_name = None

        with (
            patch("astrbot.core.db_helper") as mock_db,
            patch(
                "astrbot.core.pipeline.process_stage.method.agent_sub_stages.webchat.logger"
            ) as mock_logger,
        ):
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await webchat_build.generate_conversation_title(
                mock_event, req.prompt, prov
            )

        mock_logger.exception.assert_called_once()
        mock_db.update_platform_session.assert_not_called()


class TestApplyLlmSafetyMode:
    """Tests for apply_safety_instructions function."""

    def test_apply_llm_safety_mode_system_prompt_strategy(self):
        """Test applying safety mode with system_prompt strategy."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            llm_safety_mode=True,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        persona_build.apply_safety_instructions(config, req)

        assert "You are running in Safe Mode" in req.system_prompt
        assert "Original prompt" in req.system_prompt

    def test_apply_llm_safety_mode_prepends_safety_prompt(self):
        """Test that safety prompt is prepended before original system prompt."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="My custom prompt")

        persona_build.apply_safety_instructions(config, req)

        assert req.system_prompt.startswith(
            "<safety_instructions>\nYou are running in Safe Mode"
        )
        assert req.system_prompt.index(
            "</safety_instructions>"
        ) < req.system_prompt.index("My custom prompt")
        assert "My custom prompt" in req.system_prompt

    def test_apply_llm_safety_mode_with_none_system_prompt(self):
        """Test applying safety mode when original system_prompt is None."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt=None)

        persona_build.apply_safety_instructions(config, req)

        assert "You are running in Safe Mode" in req.system_prompt

    def test_apply_llm_safety_mode_unsupported_strategy(self):
        """Test that unsupported strategy logs warning and does nothing."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="unsupported_strategy",
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original")

        with patch.object(persona_build, "logger") as mock_logger:
            persona_build.apply_safety_instructions(config, req)

        mock_logger.warning.assert_called_once()
        assert (
            "Unsupported llm_safety_mode strategy"
            in mock_logger.warning.call_args[0][0]
        )
        assert req.system_prompt == "Original"

    def test_apply_llm_safety_mode_empty_system_prompt(self):
        """Test applying safety mode when original system_prompt is empty."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            safety_mode_strategy="system_prompt",
        )
        req = ProviderRequest(prompt="Test", system_prompt="")

        persona_build.apply_safety_instructions(config, req)

        assert "You are running in Safe Mode" in req.system_prompt


class TestApplySandboxTools:
    """Tests for _apply_sandbox_tools function."""

    def test_apply_sandbox_tools_creates_toolset_if_none(self, mock_context):
        """Test that ToolSet is created when func_tool is None."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert req.func_tool is not None
        assert isinstance(req.func_tool, ToolSet)

    def test_apply_sandbox_tools_adds_required_tools(self, mock_context):
        """Test that all required sandbox tools are added."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        tool_names = req.func_tool.names()
        assert "astrbot_execute_shell" in tool_names
        assert "astrbot_execute_ipython" in tool_names
        assert "astrbot_upload_file" in tool_names
        assert "astrbot_download_file" in tool_names

    def test_apply_sandbox_tools_adds_sandbox_prompt(self, mock_context):
        """Test that sandbox mode prompt is added to system_prompt."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_cua_adds_gui_guidance(self, mock_context):
        """Test that CUA sandbox guidance nudges reliable GUI workflows."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={"booter": "cua"},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

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

    def test_apply_sandbox_tools_with_shipyard_booter(self, monkeypatch, mock_context):
        """Test sandbox tools with shipyard booter configuration."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "https://shipyard.example.com",
                "shipyard_access_token": "test-token",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        monkeypatch.delenv("SHIPYARD_ENDPOINT", raising=False)
        monkeypatch.delenv("SHIPYARD_ACCESS_TOKEN", raising=False)

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert os.environ.get("SHIPYARD_ENDPOINT") == "https://shipyard.example.com"
        assert os.environ.get("SHIPYARD_ACCESS_TOKEN") == "test-token"

    def test_apply_sandbox_tools_shipyard_missing_endpoint(self, mock_context):
        """Test that shipyard config is skipped when endpoint is missing."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "",
                "shipyard_access_token": "test-token",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        with patch.object(computer_use_build, "logger") as mock_logger:
            req.system_prompt = (
                req.system_prompt or ""
            ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        mock_logger.error.assert_called_once()
        assert (
            "Shipyard sandbox configuration is incomplete"
            in mock_logger.error.call_args[0][0]
        )

    def test_apply_sandbox_tools_shipyard_missing_access_token(self, mock_context):
        """Test that shipyard config is skipped when access token is missing."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "https://shipyard.example.com",
                "shipyard_access_token": "",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        with patch.object(computer_use_build, "logger") as mock_logger:
            req.system_prompt = (
                req.system_prompt or ""
            ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        mock_logger.error.assert_called_once()

    def test_apply_sandbox_tools_preserves_existing_toolset(self, mock_context):
        """Test that existing tools are preserved when adding sandbox tools."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        existing_toolset = ToolSet()
        existing_tool = MagicMock()
        existing_tool.name = "existing_tool"
        existing_toolset.add_tool(existing_tool)
        req = ProviderRequest(prompt="Test", func_tool=existing_toolset)

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert "existing_tool" in req.func_tool.names()
        assert "astrbot_execute_shell" in req.func_tool.names()

    def test_apply_sandbox_tools_appends_to_existing_system_prompt(self, mock_context):
        """Test that sandbox prompt is appended to existing system prompt."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Base prompt")

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert req.system_prompt.startswith("Base prompt")
        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_none_system_prompt(self, mock_context):
        """Test that sandbox prompt is applied when system_prompt is None."""
        config = ama.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt=None)

        req.system_prompt = (
            req.system_prompt or ""
        ) + computer_use_build._apply_sandbox_tools(config, req, "session-123")

        assert isinstance(req.system_prompt, str)
        assert "sandboxed environment" in req.system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("call_hook", [False, True])
async def test_endpoint_validation_does_not_depend_on_hook_dispatch(
    mock_context, mock_provider, mock_event, call_hook
):
    mock_provider.provider_config["api_base"] = "https://kourichat.example/v1"
    with (
        patch.object(
            builder_build, "call_event_hook", AsyncMock(return_value=False)
        ) as hook,
        patch.object(native_execution, "AgentRunner") as runner,
        patch.object(
            builder_build,
            "AstrAgentContext",
            side_effect=lambda **kw: SimpleNamespace(**kw),
        ),
    ):
        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            provider=mock_provider,
            req=ProviderRequest(prompt="Hello"),
            config=ama.MainAgentBuildConfig(
                tool_call_timeout=60,
                call_request_hook=call_hook,
                validate_provider_endpoint=True,
            ),
        )
    assert result is None
    hook.assert_not_awaited()
    runner.assert_not_called()


@pytest.mark.asyncio
async def test_stopping_during_history_loading_does_not_initialize_an_agent(
    mock_context, mock_provider, mock_event, mock_conversation
):
    """A background stop during input preparation prevents all later build stages."""
    stop_signal = asyncio.Event()
    mock_event.get_extra.side_effect = {"_background_stop_signal": stop_signal}.get

    async def load_conversation(*args):
        stop_signal.set()
        return mock_conversation

    with (
        patch.object(request_build, "_get_session_conv", side_effect=load_conversation),
        patch.object(native_execution, "AgentRunner") as runner,
        patch.object(persona_build, "apply_persona", AsyncMock()) as persona,
    ):
        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            provider=mock_provider,
            config=ama.MainAgentBuildConfig(tool_call_timeout=60),
        )
    assert result is None
    runner.assert_not_called()
    persona.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "booter", "agentic_kb", "tool_schema_mode"),
    [
        ("local", "shipyard_neo", True, "full"),
        ("sandbox", "cua", False, "skills_like"),
        ("sandbox", "shipyard_neo", True, "full"),
    ],
)
async def test_feature_composition_preserves_tool_scope_and_instruction_order(
    mock_context,
    mock_event,
    mock_provider,
    mock_conversation,
    tmp_path,
    runtime,
    booter,
    agentic_kb,
    tool_schema_mode,
):
    """Compose real features to protect their filtering scopes and prompt order."""

    registered = [
        FunctionTool(name=name, description=name, parameters={"type": "object"})
        for name in ("kept", "delegated", "disabled_plugin")
    ]
    registered[-1].handler_module_path = "plugins.disabled"
    tool_mgr = mock_context.get_llm_tool_manager.return_value
    tool_mgr.get_func.side_effect = lambda name: next(
        (tool for tool in registered if tool.name == name), None
    )
    selected = {
        "prompt": "Persona marker",
        "tools": [tool.name for tool in registered],
        "skills": ["selected-skill"],
        "_begin_dialogs_processed": [{"role": "assistant", "content": "Opening"}],
    }
    mock_context.persona_manager.resolve_selected_persona.return_value = (
        "persona",
        selected,
        None,
        False,
    )
    mock_event.plugins_name = []
    mock_event.platform_meta.support_proactive_message = False
    mock_event.get_platform_name.return_value = "webchat"
    mock_event.get_extra.side_effect = {"enable_inline_genui": True}.get
    workspace_root = tmp_path / workspace_build.normalize_umo_for_workspace(
        mock_event.unified_msg_origin
    )
    workspace_root.mkdir(parents=True)
    (workspace_root / "EXTRA_PROMPT.md").write_text(
        "Workspace marker", encoding="utf-8"
    )
    mock_context.get_config.return_value = {
        "subagent_orchestrator": {
            "main_enable": True,
            "remove_main_duplicate_tools": True,
            "router_system_prompt": "Router marker",
            "agents": [{"tools": ["delegated", "send_message_to_user"]}],
        },
    }
    config = ama.MainAgentBuildConfig.from_config(
        {
            "kb_agentic_mode": agentic_kb,
            "agent": {"config": {"misc": {"tool_schema_mode": tool_schema_mode}}},
            "provider_settings": {
                "computer_use_runtime": runtime,
                "sandbox": {"booter": booter},
                "web_search": True,
                "websearch_provider": "tavily",
                "identifier": True,
                "proactive_capability": {"add_cron_tools": False},
            },
        }
    )
    config.enable_message_delivery = True
    req = ProviderRequest(
        prompt="Question",
        system_prompt="Caller marker",
        conversation=mock_conversation,
        func_tool=ToolSet(
            [
                FunctionTool(
                    name="caller",
                    description="Caller tool",
                    parameters={"type": "object"},
                )
            ]
        ),
    )
    runner = MagicMock()
    runner.reset = AsyncMock()
    with (
        patch.object(native_execution, "AgentRunner", return_value=runner),
        patch.object(
            builder_build,
            "AstrAgentContext",
            side_effect=lambda **kw: SimpleNamespace(**kw),
        ),
        patch.object(persona_build, "SkillManager") as skills,
        patch.object(
            workspace_build, "get_astrbot_workspaces_path", return_value=str(tmp_path)
        ),
        patch.object(
            plugins_build,
            "star_map",
            {"plugins.disabled": SimpleNamespace(name="disabled", reserved=False)},
        ),
        patch.object(
            computer_use_build,
            "get_local_permission_policy",
            return_value=SimpleNamespace(allow_execution=True, allow_network=False),
        ),
        patch.object(
            knowledge_base_build,
            "retrieve_knowledge_base",
            AsyncMock(return_value="Knowledge marker"),
        ) as retrieve,
    ):
        skills.return_value.list_skills.return_value = [
            SkillInfo(
                name=name,
                description=name,
                path=f"/skills/{name}/SKILL.md",
                active=True,
            )
            for name in ("selected-skill", "excluded-skill")
        ]
        skills.return_value.list_workspace_skills.return_value = []
        result = await ama.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            provider=mock_provider,
            config=config,
            req=req,
        )
    assert result is not None
    names = req.func_tool.names()
    assert names[:4] == ["caller", "send_message_to_user", "kept", "delegated"]
    assert not {"disabled_plugin", "transfer_to_worker"}.intersection(names)
    assert "Router marker" not in req.system_prompt
    assert {
        "web_search_tavily",
        "astrbot_execute_shell",
        "astrbot_file_read_tool",
    }.issubset(names)
    assert names.index("web_search_tavily") < names.index("astrbot_execute_shell")
    kb_name = knowledge_base_build.KnowledgeBaseQueryTool().name
    assert (kb_name in names) == agentic_kb
    assert retrieve.await_count == int(not agentic_kb)
    assert "User ID: user123" in req.extra_user_content_parts[0].text
    if not agentic_kb:
        assert "Knowledge marker" in req.extra_user_content_parts[1].text
    assert req.contexts[0] == {"role": "assistant", "content": "Opening"}
    markers = [
        persona_build.LLM_SAFETY_MODE_SYSTEM_PROMPT,
        "Caller marker",
        "<genui_instructions>",
        "</genui_instructions>",
        "<persona_instructions>",
        "Persona marker",
        "</persona_instructions>",
        "<skills_instructions>",
        "**selected-skill**",
        "</skills_instructions>",
        "Workspace marker",
        "Local computer tools are available"
        if runtime == "local"
        else "CUA Desktop Control"
        if booter == "cua"
        else "Shipyard Neo File Path Rule",
    ]
    if runtime == "local":
        markers.append(f"Current workspace: `{workspace_root}`")
        assert (
            req.system_prompt.count(computer_use_build.LOCAL_NETWORK_POLICY_NOTICE) == 1
        )
    tool_prompt = (
        builder_build.TOOL_CALL_PROMPT
        if tool_schema_mode == "full"
        else builder_build.TOOL_CALL_PROMPT_SKILLS_LIKE_MODE
    )
    markers.append(tool_prompt)
    markers.append(web_search_build.WEB_SEARCH_CITATION_PROMPT)
    positions = [req.system_prompt.index(marker) for marker in markers]
    assert positions == sorted(positions)
    for name in (
        "safety_instructions",
        "genui_instructions",
        "persona_instructions",
        "skills_instructions",
    ):
        assert req.system_prompt.count(f"<{name}>") == 1
        assert req.system_prompt.count(f"</{name}>") == 1
    assert "excluded-skill" not in req.system_prompt
    assert req.system_prompt.endswith(
        web_search_build.WEB_SEARCH_CITATION_PROMPT + "\n"
    )
    environment_start = f'<execution_environment runtime="{runtime}">'
    assert req.system_prompt.count(environment_start) == 1
    environment = req.system_prompt.split(environment_start, 1)[1].split(
        "</execution_environment>", 1
    )[0]
    instructions = req.system_prompt.split("<tool_use_instructions>", 1)[1].split(
        "</tool_use_instructions>", 1
    )[0]
    assert (
        f"<tool_use_instructions>{instructions}</tool_use_instructions>" == tool_prompt
    )
    assert req.system_prompt.count("</execution_environment>") == 1
    assert req.system_prompt.count("<tool_use_instructions>") == 1
    assert req.system_prompt.count("</tool_use_instructions>") == 1
    assert req.system_prompt.index(
        "</execution_environment>"
    ) < req.system_prompt.index("<tool_use_instructions>")
    assert "Persona marker" not in environment
    assert "Workspace marker" not in environment
    if runtime == "local":
        assert "## Shell and sessions" in environment
        assert "## Execution policy" in environment
        assert "Local execution policy:" in environment
        assert f"Current workspace: `{workspace_root}`" in environment
    else:
        assert "sandboxed environment" in environment
        assert "Current workspace:" not in environment
        assert "Local execution policy:" not in environment


@pytest.mark.asyncio
async def test_wakeup_rejects_a_missing_platform_before_loading_history(mock_context):
    """Fail explicitly instead of constructing internal metadata for a missing adapter.

    Args:
        mock_context: Services with no adapter for the requested UMO.
    """
    umo = "missing:FriendMessage:target"
    mock_context.get_platform_inst.return_value = None
    with patch.object(ama, "build_main_agent", AsyncMock()) as build:
        with pytest.raises(ValueError, match="Platform adapter 'missing' not found"):
            await wake_main_agent(
                mock_context,
                umo=umo,
                user_prompt="Continue the task.",
                source="plugin",
            )
        build.assert_not_awaited()
    mock_context.get_config.assert_not_called()
    mock_context.conversation_manager.get_curr_conversation_id.assert_not_called()
    mock_context.conversation_manager.update_conversation.assert_not_called()
    assert umo not in active_event_registry._events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_name", "prompt"),
    [
        ("test_platform", "Continue this conversation."),
        ("lark", "/llm Keep this exact input."),
        ("webchat", "/llm Keep this exact input."),
    ],
)
async def test_wakeup_collects_current_conversation_without_an_explicit_request(
    platform_name,
    prompt,
):
    """Collect history normally while preserving all programmatic input text.

    Args:
        platform_name: Target adapter type with its normal prefix behavior.
        prompt: Input with or without the configured provider prefix.
    """
    from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
    from astrbot.core.platform.message_session import MessageSession

    history = [{"role": "user", "content": "Existing context"}]
    conversation = SimpleNamespace(cid="conversation", history=json.dumps(history))
    manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="conversation"),
        get_conversation=AsyncMock(return_value=conversation),
    )
    context = SimpleNamespace(conversation_manager=manager)
    event = AgentWakeupEvent(
        context=context,
        session=MessageSession.from_str("target:FriendMessage:user"),
        platform_meta=PlatformMetadata(
            id="target", name=platform_name, description="Target"
        ),
        prompt=prompt,
        source="plugin",
    )
    prepared = await request_build.prepare_request(
        event,
        context,
        ama.MainAgentBuildConfig(tool_call_timeout=60, provider_wake_prefix="/llm "),
        SimpleNamespace(provider_config={"modalities": ["text"]}),
        None,
    )
    assert prepared is not None
    request = prepared.request
    assert request.prompt == prompt
    assert request.conversation is conversation
    assert request.contexts == history
    assert request.session_id == event.unified_msg_origin
    manager.get_curr_conversation_id.assert_awaited_once_with(event.unified_msg_origin)
    manager.get_conversation.assert_awaited_once_with(
        event.unified_msg_origin, "conversation"
    )
