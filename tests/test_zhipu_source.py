"""Tests for ProviderZhipu GLM non-standard special token handling.

Covers the three layers of cleaning introduced to fix issue #5556:
1. ``_clean_glm_special_tokens`` — pure regex-based cleaner
2. ``_normalize_content``         — overrides the base static method
3. ``_parse_openai_completion``   — second-pass cleaning on assembled text
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from astrbot.core.agent.tool import (
    ToolSet,  # noqa: F401 – ensures the module is importable
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.zhipu_source import ProviderZhipu

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_provider() -> ProviderZhipu:
    return ProviderZhipu(
        provider_config={
            "id": "test-zhipu",
            "type": "zhipu_chat_completion",
            "model": "glm-4.6v-flash",
            "key": ["test-key"],
        },
        provider_settings={},
    )


def _make_llm_response(text: str) -> LLMResponse:
    """Return an LLMResponse whose completion_text equals *text*."""
    r = LLMResponse("assistant")
    r.result_chain = MessageChain().message(text)
    return r


# ──────────────────────────────────────────────────────────────────────────────
# _clean_glm_special_tokens
# ──────────────────────────────────────────────────────────────────────────────


class TestCleanGLMSpecialTokens:
    """Unit tests for the pure-function token cleaner."""

    # <None> — null-response signal ----------------------------------------

    def test_null_token_alone(self):
        assert ProviderZhipu._clean_glm_special_tokens("<None>") == ""

    def test_null_token_with_leading_newline(self):
        # Exact pattern observed from glm-4.6v-flash: content='\n<None>'
        assert ProviderZhipu._clean_glm_special_tokens("\n<None>") == ""

    def test_null_token_surrounded_by_whitespace(self):
        assert ProviderZhipu._clean_glm_special_tokens("  <None>  ") == ""

    def test_null_token_case_insensitive_lower(self):
        # Without re.IGNORECASE, lowercase <none> is not a GLM token and must be preserved.
        assert ProviderZhipu._clean_glm_special_tokens("<none>") == "<none>"

    def test_null_token_case_insensitive_upper(self):
        # Without re.IGNORECASE, uppercase <NONE> is not a GLM token and must be preserved.
        assert ProviderZhipu._clean_glm_special_tokens("<NONE>") == "<NONE>"

    def test_null_token_in_middle_of_text(self):
        result = ProviderZhipu._clean_glm_special_tokens("hello <None> world")
        # Token itself must be gone; surrounding spaces are collapsed to one
        assert "<None>" not in result
        assert "hello" in result and "world" in result

    # Role / control tokens ------------------------------------------------

    def test_endoftext_token(self):
        assert ProviderZhipu._clean_glm_special_tokens("<|endoftext|>") == ""

    def test_user_role_token(self):
        assert ProviderZhipu._clean_glm_special_tokens("<|user|>") == ""

    def test_assistant_role_token(self):
        assert ProviderZhipu._clean_glm_special_tokens("<|assistant|>") == ""

    def test_system_role_token(self):
        assert ProviderZhipu._clean_glm_special_tokens("<|system|>") == ""

    def test_observation_role_token(self):
        assert ProviderZhipu._clean_glm_special_tokens("<|observation|>") == ""

    def test_role_token_prefix_removed(self):
        result = ProviderZhipu._clean_glm_special_tokens(
            "<|assistant|>Hello, how can I help?"
        )
        assert result == "Hello, how can I help?"

    def test_multiple_role_tokens(self):
        result = ProviderZhipu._clean_glm_special_tokens("<|user|>Hi<|assistant|>Hello")
        assert result == "HiHello"

    def test_endoftext_at_end_of_reply(self):
        result = ProviderZhipu._clean_glm_special_tokens(
            "Python 最新版本是 3.13。<|endoftext|>"
        )
        assert result == "Python 最新版本是 3.13。"

    # Normal text must not be affected ------------------------------------

    def test_normal_text_unchanged(self):
        text = "我是 GLM，很高兴认识你！"
        assert ProviderZhipu._clean_glm_special_tokens(text) == text

    def test_empty_string(self):
        assert ProviderZhipu._clean_glm_special_tokens("") == ""

    def test_angle_bracket_in_normal_text_unchanged(self):
        """Angle brackets that are not special tokens must survive."""
        text = "if a < b and b > 0: pass"
        assert ProviderZhipu._clean_glm_special_tokens(text) == text

    def test_html_like_tag_unchanged(self):
        """HTML-style tags (not GLM tokens) must not be stripped."""
        text = "Use <strong>bold</strong> for emphasis."
        assert ProviderZhipu._clean_glm_special_tokens(text) == text


# ──────────────────────────────────────────────────────────────────────────────
# _normalize_content (static override)
# ──────────────────────────────────────────────────────────────────────────────


class TestNormalizeContent:
    """Verify that ProviderZhipu._normalize_content applies GLM cleaning on top
    of the base ProviderOpenAIOfficial normalisation."""

    def test_null_token_string_returns_empty(self):
        assert ProviderZhipu._normalize_content("\n<None>") == ""

    def test_normal_string_unchanged(self):
        text = "Hello, world!"
        assert ProviderZhipu._normalize_content(text) == text

    def test_list_content_null_token(self):
        raw = [{"type": "text", "text": "<None>"}]
        assert ProviderZhipu._normalize_content(raw) == ""

    def test_list_content_normal_text(self):
        raw = [{"type": "text", "text": "Hello"}]
        assert ProviderZhipu._normalize_content(raw) == "Hello"

    def test_list_content_endoftext(self):
        raw = [{"type": "text", "text": "Done<|endoftext|>"}]
        assert ProviderZhipu._normalize_content(raw) == "Done"

    def test_dict_content_null_token(self):
        raw = {"type": "text", "text": "<None>"}
        assert ProviderZhipu._normalize_content(raw) == ""

    def test_override_is_distinct_from_base(self):
        """The Zhipu override should differ from the base when GLM tokens are present."""
        text = "\n<None>"
        base_result = ProviderOpenAIOfficial._normalize_content(text)
        zhipu_result = ProviderZhipu._normalize_content(text)
        # Base keeps "<None>" after strip; Zhipu must remove it
        assert "<None>" not in zhipu_result
        assert zhipu_result == ""
        # Confirm the base does NOT clean it (so the override is meaningful)
        assert base_result == "<None>"


# ──────────────────────────────────────────────────────────────────────────────
# _parse_openai_completion  — second-pass cleaning
# ──────────────────────────────────────────────────────────────────────────────


class TestParseOpenAICompletionCleaning:
    """Integration tests for the post-processing pass in _parse_openai_completion.

    We patch ProviderOpenAIOfficial._parse_openai_completion so that we can
    control what the base class "returns" and verify that ProviderZhipu
    correctly applies the extra GLM cleaning pass on top.
    """

    @pytest_asyncio.fixture
    async def provider(self) -> AsyncGenerator[ProviderZhipu, None]:
        p = _make_provider()
        yield p
        await p.terminate()

    @pytest.mark.asyncio
    async def test_null_token_content_becomes_empty(self, provider: ProviderZhipu):
        """content='\\n<None>' (real API response) should produce an empty reply."""
        fake_completion = MagicMock()
        parent_response = _make_llm_response("\n<None>")

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(fake_completion, None)

        assert result.completion_text == ""

    @pytest.mark.asyncio
    async def test_endoftext_token_stripped_from_end(self, provider: ProviderZhipu):
        parent_response = _make_llm_response("当然可以！<|endoftext|>")

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.completion_text == "当然可以！"

    @pytest.mark.asyncio
    async def test_assistant_role_token_prefix_stripped(self, provider: ProviderZhipu):
        parent_response = _make_llm_response("<|assistant|>我是一个AI助手。")

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.completion_text == "我是一个AI助手。"

    @pytest.mark.asyncio
    async def test_normal_content_unchanged(self, provider: ProviderZhipu):
        """Normal GLM replies must not be modified."""
        normal = "好的，我来帮你解答这个问题。"
        parent_response = _make_llm_response(normal)

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.completion_text == normal

    @pytest.mark.asyncio
    async def test_empty_completion_text_not_modified(self, provider: ProviderZhipu):
        """When the base class returns empty completion_text, don't error out."""
        parent_response = LLMResponse("assistant")
        parent_response.result_chain = None
        parent_response._completion_text = ""

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.completion_text == ""

    @pytest.mark.asyncio
    async def test_reasoning_content_preserved(self, provider: ProviderZhipu):
        """Cleaning must not touch reasoning_content."""
        parent_response = _make_llm_response("\n<None>")
        parent_response.reasoning_content = "思考过程：用户打了招呼，不需要回复。"

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.completion_text == ""
        assert "思考过程" in result.reasoning_content

    @pytest.mark.asyncio
    async def test_other_response_fields_preserved(self, provider: ProviderZhipu):
        """id, usage and other metadata must survive the cleaning pass."""
        parent_response = _make_llm_response("普通回复")
        parent_response.id = "cmp-test-id-123"

        with patch.object(
            ProviderOpenAIOfficial,
            "_parse_openai_completion",
            new=AsyncMock(return_value=parent_response),
        ):
            result = await provider._parse_openai_completion(MagicMock(), None)

        assert result.id == "cmp-test-id-123"
        assert result.completion_text == "普通回复"
