"""Tests for astr_main_agent module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core import astr_main_agent as ama
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Plain, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest


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
    ctx.persona_manager.personas_v3 = []
    ctx.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, None, False)
    )
    ctx.get_llm_tool_manager.return_value = MagicMock()
    ctx.subagent_orchestrator = None
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


@pytest.fixture
def sample_config():
    """Create a sample MainAgentBuildConfig."""
    module = ama
    return module.MainAgentBuildConfig(
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


class TestMainAgentBuildConfig:
    """Tests for MainAgentBuildConfig dataclass."""

    def test_config_initialization(self):
        """Test MainAgentBuildConfig initialization with defaults."""
        module = ama
        config = module.MainAgentBuildConfig(tool_call_timeout=60)
        assert config.tool_call_timeout == 60
        assert config.tool_schema_mode == "full"
        assert config.provider_wake_prefix == ""
        assert config.streaming_response is True
        assert config.sanitize_context_by_modalities is False
        assert config.kb_agentic_mode is False
        assert config.file_extract_enabled is False
        assert config.llm_safety_mode is True

    def test_config_with_custom_values(self):
        """Test MainAgentBuildConfig with custom values."""
        module = ama
        config = module.MainAgentBuildConfig(
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

    def test_select_provider_invalid_type(self, mock_event, mock_context):
        """Test selecting provider when result is not a Provider instance."""
        module = ama
        mock_event.get_extra.side_effect = lambda k: (
            "invalid" if k == "selected_provider" else None
        )
        mock_context.get_provider_by_id.return_value = "not a provider"

        result = module._select_provider(mock_event, mock_context)

        assert result is None

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

        assert "[Related Knowledge Base Results]:" in req.system_prompt
        assert "KB result" in req.system_prompt

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
    async def test_apply_kb_no_result(self, mock_event, mock_context):
        """Test applying knowledge base when no result is returned."""
        module = ama
        req = ProviderRequest(prompt="test", system_prompt="System")
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, kb_agentic_mode=False
        )

        with patch(
            "astrbot.core.astr_main_agent.retrieve_knowledge_base",
            AsyncMock(return_value=None),
        ):
            await module._apply_kb(mock_event, req, mock_context, config)

        assert req.system_prompt == "System"

    @pytest.mark.asyncio
    async def test_apply_kb_with_existing_tools(self, mock_event, mock_context):
        """Test applying knowledge base with existing toolset."""
        module = ama
        existing_tools = ToolSet()
        req = ProviderRequest(prompt="test", func_tool=existing_tools)
        config = module.MainAgentBuildConfig(tool_call_timeout=60, kb_agentic_mode=True)

        await module._apply_kb(mock_event, req, mock_context, config)

        assert req.func_tool is not None


class TestApplyFileExtract:
    """Tests for _apply_file_extract function."""

    @pytest.mark.asyncio
    async def test_file_extract_basic(self, mock_event, sample_config):
        """Test basic file extraction."""
        module = ama
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt="Summarize")

        with patch(
            "astrbot.core.astr_main_agent.extract_file_moonshotai"
        ) as mock_extract:
            mock_extract.return_value = "File content"

            await module._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 1
        assert "File Extract Results" in req.contexts[0]["content"]

    @pytest.mark.asyncio
    async def test_file_extract_no_files(self, mock_event, sample_config):
        """Test file extraction when no files present."""
        module = ama
        mock_event.message_obj.message = [Plain(text="Hello")]
        req = ProviderRequest(prompt="Hello")

        await module._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 0

    @pytest.mark.asyncio
    async def test_file_extract_in_reply(self, mock_event, sample_config):
        """Test file extraction from reply chain."""
        module = ama
        mock_file = MagicMock(spec=File)
        mock_file.name = "reply.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/reply.pdf")
        mock_reply = MagicMock(spec=Reply)
        mock_reply.chain = [mock_file]
        mock_event.message_obj.message = [mock_reply]

        req = ProviderRequest(prompt="Summarize")

        with patch(
            "astrbot.core.astr_main_agent.extract_file_moonshotai"
        ) as mock_extract:
            mock_extract.return_value = "Reply content"

            await module._apply_file_extract(mock_event, req, sample_config)

        assert len(req.contexts) == 1

    @pytest.mark.asyncio
    async def test_file_extract_no_prompt(self, mock_event, sample_config):
        """Test file extraction when prompt is empty."""
        module = ama
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt=None)

        with patch(
            "astrbot.core.astr_main_agent.extract_file_moonshotai"
        ) as mock_extract:
            mock_extract.return_value = "Content"

            await module._apply_file_extract(mock_event, req, sample_config)

        assert req.prompt == "总结一下文件里面讲了什么？"

    @pytest.mark.asyncio
    async def test_file_extract_no_api_key(self, mock_event):
        """Test file extraction when no API key is configured."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            file_extract_enabled=True,
            file_extract_msh_api_key="",
        )
        mock_file = MagicMock(spec=File)
        mock_file.name = "test.pdf"
        mock_file.get_file = AsyncMock(return_value="/path/to/test.pdf")
        mock_event.message_obj.message = [mock_file]

        req = ProviderRequest(prompt="Summarize")

        await module._apply_file_extract(mock_event, req, config)

        assert len(req.contexts) == 0


class TestEnsurePersonaAndSkills:
    """Tests for _ensure_persona_and_skills function."""

    @pytest.mark.asyncio
    async def test_ensure_persona_from_session(self, mock_event, mock_context):
        """Test applying persona from session service config."""
        module = ama
        persona = {"name": "test-persona", "prompt": "You are helpful."}
        mock_context.persona_manager.personas_v3 = [persona]
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
        mock_context.persona_manager.personas_v3 = [persona]
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
        mock_context.persona_manager.personas_v3 = []
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=("[%None]", None, None, False)
        )
        req = ProviderRequest()
        req.conversation = MagicMock(persona_id="[%None]")

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "Persona Instructions" not in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_skills(self, mock_event, mock_context):
        """Test applying skills to request."""
        module = ama
        mock_skill = MagicMock()
        mock_skill.name = "test_skill"
        mock_skill.to_prompt.return_value = "Skill description"
        mock_skill.description = "Skill description"
        mock_skill.path = "data/skills/test_skill/SKILL.md"
        mock_context.persona_manager.personas_v3 = []
        mock_context.persona_manager.resolve_selected_persona = AsyncMock(
            return_value=(None, None, None, False)
        )

        with patch("astrbot.core.astr_main_agent.SkillManager") as mock_skill_mgr_cls:
            mock_skill_mgr = MagicMock()
            mock_skill_mgr.list_skills.return_value = [mock_skill]
            mock_skill_mgr_cls.return_value = mock_skill_mgr

            req = ProviderRequest()
            req.conversation = MagicMock(persona_id=None)

            await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert "test_skill" in req.system_prompt

    @pytest.mark.asyncio
    async def test_ensure_tools_from_persona(self, mock_event, mock_context):
        """Test applying tools from persona."""
        module = ama
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

        await module._ensure_persona_and_skills(req, {}, mock_context, mock_event)

        assert req.func_tool is not None


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


class TestModalitiesFix:
    """Tests for _modalities_fix function."""

    def test_modalities_fix_image_not_supported(self, mock_provider):
        """Test modality fix when image is not supported."""
        module = ama
        mock_provider.provider_config = {"modalities": ["text"]}
        req = ProviderRequest(prompt="Hello", image_urls=["/path/to/image.jpg"])

        module._modalities_fix(mock_provider, req)

        assert "[图片]" in req.prompt
        assert req.image_urls == []

    def test_modalities_fix_tool_not_supported(self, mock_provider):
        """Test modality fix when tool is not supported."""
        module = ama
        mock_provider.provider_config = {"modalities": ["text", "image"]}
        req = ProviderRequest(prompt="Hello")
        req.func_tool = ToolSet()
        req.func_tool.add_tool(
            FunctionTool(
                name="dummy_tool",
                description="dummy",
                parameters={"type": "object", "properties": {}},
            )
        )

        module._modalities_fix(mock_provider, req)

        assert req.func_tool is None

    def test_modalities_fix_all_supported(self, mock_provider):
        """Test modality fix when all features are supported."""
        module = ama
        mock_provider.provider_config = {"modalities": ["image", "tool_use"]}
        tool_set = ToolSet()
        tool_set.add_tool(
            FunctionTool(
                name="dummy_tool",
                description="dummy",
                parameters={"type": "object", "properties": {}},
            )
        )
        req = ProviderRequest(
            prompt="Hello",
            image_urls=["/path/to/image.jpg"],
            func_tool=tool_set,
        )

        module._modalities_fix(mock_provider, req)

        assert req.prompt == "Hello"
        assert len(req.image_urls) == 1
        assert req.func_tool is not None


class TestSanitizeContextByModalities:
    """Tests for _sanitize_context_by_modalities function."""

    def test_sanitize_no_op(self, mock_provider):
        """Test sanitize when disabled or modalities support everything."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, sanitize_context_by_modalities=False
        )
        mock_provider.provider_config = {"modalities": ["image", "tool_use"]}
        req = ProviderRequest(contexts=[{"role": "user", "content": "Hello"}])

        module._sanitize_context_by_modalities(config, mock_provider, req)

        assert len(req.contexts) == 1

    def test_sanitize_removes_tool_messages(self, mock_provider):
        """Test sanitize removes tool messages when tool_use not supported."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, sanitize_context_by_modalities=True
        )
        mock_provider.provider_config = {"modalities": ["image"]}
        req = ProviderRequest(
            contexts=[
                {"role": "user", "content": "Hello"},
                {"role": "tool", "content": "Tool result"},
            ]
        )

        module._sanitize_context_by_modalities(config, mock_provider, req)

        assert len(req.contexts) == 1
        assert req.contexts[0]["role"] == "user"

    def test_sanitize_removes_tool_calls(self, mock_provider):
        """Test sanitize removes tool_calls from assistant messages."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, sanitize_context_by_modalities=True
        )
        mock_provider.provider_config = {"modalities": ["image"]}
        req = ProviderRequest(
            contexts=[
                {
                    "role": "assistant",
                    "content": "Response",
                    "tool_calls": [{"name": "tool"}],
                }
            ]
        )

        module._sanitize_context_by_modalities(config, mock_provider, req)

        assert "tool_calls" not in req.contexts[0]

    def test_sanitize_removes_image_blocks(self, mock_provider):
        """Test sanitize removes image blocks when image not supported."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60, sanitize_context_by_modalities=True
        )
        mock_provider.provider_config = {"modalities": ["tool_use"]}
        req = ProviderRequest(
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "image_url", "url": "image.jpg"},
                    ],
                }
            ]
        )

        module._sanitize_context_by_modalities(config, mock_provider, req)

        assert len(req.contexts[0]["content"]) == 1
        assert req.contexts[0]["content"][0]["type"] == "text"


class TestPluginToolFix:
    """Tests for _plugin_tool_fix function."""

    def test_plugin_tool_fix_none_plugins(self, mock_event):
        """Test plugin tool fix when no plugins specified."""
        module = ama
        req = ProviderRequest(func_tool=ToolSet())
        mock_event.plugins_name = None

        module._plugin_tool_fix(mock_event, req)

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

        with patch("astrbot.core.astr_main_agent.star_map") as mock_star_map:
            mock_plugin = MagicMock()
            mock_plugin.name = "test_plugin"
            mock_plugin.reserved = False
            mock_star_map.get.return_value = mock_plugin

            module._plugin_tool_fix(mock_event, req)

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

        with patch("astrbot.core.astr_main_agent.star_map"):
            module._plugin_tool_fix(mock_event, req)

        assert "mcp_tool" in req.func_tool.names()


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
    async def test_build_main_agent_with_wake_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent with wake prefix."""
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
                config=module.MainAgentBuildConfig(
                    tool_call_timeout=60, provider_wake_prefix="/"
                ),
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_build_main_agent_no_wake_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        """Test building main agent without matching wake prefix."""
        module = ama
        mock_event.message_str = "hello"
        mock_context.get_provider_by_id.return_value = None
        mock_context.get_using_provider.return_value = mock_provider

        result = await module.build_main_agent(
            event=mock_event,
            plugin_context=mock_context,
            config=module.MainAgentBuildConfig(
                tool_call_timeout=60, provider_wake_prefix="/"
            ),
        )

        assert result is None

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
        assert result.provider_request == existing_req


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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)

            await module._handle_webchat(mock_event, req, prov)

        prov.text_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webchat_no_session_found(self, mock_event):
        """Test that title generation is skipped when session is not found."""
        module = ama
        mock_event.session_id = "platform!webchat-session-123"

        req = ProviderRequest(prompt="What is AI?")
        prov = MagicMock(spec=Provider)

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=None)

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with patch("astrbot.core.db_helper") as mock_db:
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

        with (
            patch("astrbot.core.db_helper") as mock_db,
            patch("astrbot.core.astr_main_agent.logger") as mock_logger,
        ):
            mock_db.get_platform_session_by_id = AsyncMock(return_value=mock_session)
            mock_db.update_platform_session = AsyncMock()

            await module._handle_webchat(mock_event, req, prov)

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

    def test_apply_sandbox_tools_creates_toolset_if_none(self):
        """Test that ToolSet is created when func_tool is None."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        module._apply_sandbox_tools(config, req, "session-123")

        assert req.func_tool is not None
        assert isinstance(req.func_tool, ToolSet)

    def test_apply_sandbox_tools_adds_required_tools(self):
        """Test that all required sandbox tools are added."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        module._apply_sandbox_tools(config, req, "session-123")

        tool_names = req.func_tool.names()
        assert "astrbot_execute_shell" in tool_names
        assert "astrbot_execute_ipython" in tool_names
        assert "astrbot_upload_file" in tool_names
        assert "astrbot_download_file" in tool_names

    def test_apply_sandbox_tools_adds_sandbox_prompt(self):
        """Test that sandbox mode prompt is added to system_prompt."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Original prompt")

        module._apply_sandbox_tools(config, req, "session-123")

        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_shipyard_booter(self, monkeypatch):
        """Test sandbox tools with shipyard booter configuration."""
        module = ama
        config = module.MainAgentBuildConfig(
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

        module._apply_sandbox_tools(config, req, "session-123")

        assert os.environ.get("SHIPYARD_ENDPOINT") == "https://shipyard.example.com"
        assert os.environ.get("SHIPYARD_ACCESS_TOKEN") == "test-token"

    def test_apply_sandbox_tools_shipyard_missing_endpoint(self):
        """Test that shipyard config is skipped when endpoint is missing."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "",
                "shipyard_access_token": "test-token",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        with patch("astrbot.core.astr_main_agent.logger") as mock_logger:
            module._apply_sandbox_tools(config, req, "session-123")

        mock_logger.error.assert_called_once()
        assert (
            "Shipyard sandbox configuration is incomplete"
            in mock_logger.error.call_args[0][0]
        )

    def test_apply_sandbox_tools_shipyard_missing_access_token(self):
        """Test that shipyard config is skipped when access token is missing."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={
                "booter": "shipyard",
                "shipyard_endpoint": "https://shipyard.example.com",
                "shipyard_access_token": "",
            },
        )
        req = ProviderRequest(prompt="Test", func_tool=None)

        with patch("astrbot.core.astr_main_agent.logger") as mock_logger:
            module._apply_sandbox_tools(config, req, "session-123")

        mock_logger.error.assert_called_once()

    def test_apply_sandbox_tools_preserves_existing_toolset(self):
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

        module._apply_sandbox_tools(config, req, "session-123")

        assert "existing_tool" in req.func_tool.names()
        assert "astrbot_execute_shell" in req.func_tool.names()

    def test_apply_sandbox_tools_appends_to_existing_system_prompt(self):
        """Test that sandbox prompt is appended to existing system prompt."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt="Base prompt")

        module._apply_sandbox_tools(config, req, "session-123")

        assert req.system_prompt.startswith("Base prompt")
        assert "sandboxed environment" in req.system_prompt

    def test_apply_sandbox_tools_with_none_system_prompt(self):
        """Test that sandbox prompt is applied when system_prompt is None."""
        module = ama
        config = module.MainAgentBuildConfig(
            tool_call_timeout=60,
            computer_use_runtime="sandbox",
            sandbox_cfg={},
        )
        req = ProviderRequest(prompt="Test", system_prompt=None)

        module._apply_sandbox_tools(config, req, "session-123")

        assert isinstance(req.system_prompt, str)
        assert "sandboxed environment" in req.system_prompt
