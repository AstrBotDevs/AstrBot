"""Tests for astrbot.core.provider.entities.

Covers ProviderRequest, LLMResponse, TokenUsage, ToolCallsResult,
ProviderMeta, ProviderMetaData, and RerankResult construction and edge cases.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    ContentPart,
    ToolCall,
    ToolCallMessageSegment,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    ProviderMetaData,
    ProviderRequest,
    ProviderType,
    RerankResult,
    TokenUsage,
    ToolCallsResult,
)


# =========================================================================
# ProviderMeta / ProviderMetaData
# =========================================================================


class TestProviderMeta:
    def test_basic_construction(self):
        meta = ProviderMeta(id="p1", model="gpt-4", type="openai")
        assert meta.id == "p1"
        assert meta.model == "gpt-4"
        assert meta.type == "openai"
        assert meta.provider_type == ProviderType.CHAT_COMPLETION

    def test_construction_with_provider_type(self):
        meta = ProviderMeta(
            id="emb1",
            model="text-embedding-3",
            type="openai_embedding",
            provider_type=ProviderType.EMBEDDING,
        )
        assert meta.provider_type == ProviderType.EMBEDDING


class TestProviderMetaData:
    def test_basic_construction(self):
        pmd = ProviderMetaData(
            id="p1", model=None, type="openai", desc="OpenAI provider"
        )
        assert pmd.id == "p1"
        assert pmd.desc == "OpenAI provider"
        assert pmd.cls_type is None
        assert pmd.default_config_tmpl is None
        assert pmd.provider_display_name is None

    def test_construction_with_all_fields(self):
        fake_cls = type("FakeProvider", (), {})
        pmd = ProviderMetaData(
            id="p2",
            model="gpt-4o",
            type="openai",
            desc="desc",
            provider_type=ProviderType.CHAT_COMPLETION,
            cls_type=fake_cls,
            default_config_tmpl={"key": "val"},
            provider_display_name="OpenAI Official",
        )
        assert pmd.cls_type is fake_cls
        assert pmd.default_config_tmpl == {"key": "val"}
        assert pmd.provider_display_name == "OpenAI Official"


# =========================================================================
# TokenUsage
# =========================================================================


class TestTokenUsage:
    def test_defaults(self):
        tu = TokenUsage()
        assert tu.input_other == 0
        assert tu.input_cached == 0
        assert tu.output == 0
        assert tu.total == 0
        assert tu.input == 0

    def test_properties(self):
        tu = TokenUsage(input_other=10, input_cached=5, output=20)
        assert tu.total == 35
        assert tu.input == 15

    def test_addition(self):
        a = TokenUsage(input_other=5, input_cached=2, output=10)
        b = TokenUsage(input_other=3, input_cached=1, output=4)
        result = a + b
        assert result.input_other == 8
        assert result.input_cached == 3
        assert result.output == 14

    def test_subtraction(self):
        a = TokenUsage(input_other=10, input_cached=5, output=20)
        b = TokenUsage(input_other=3, input_cached=2, output=5)
        result = a - b
        assert result.input_other == 7
        assert result.input_cached == 3
        assert result.output == 15

    def test_addition_preserves_immutability(self):
        a = TokenUsage(input_other=1, output=2)
        b = TokenUsage(input_other=3, output=4)
        c = a + b
        assert a.input_other == 1
        assert b.input_other == 3
        assert c.input_other == 4


# =========================================================================
# ToolCallsResult
# =========================================================================


class TestToolCallsResult:
    def test_construction(self):
        info = MagicMock(spec=AssistantMessageSegment)
        info.model_dump.return_value = {"role": "assistant", "content": "thinking"}
        result_seg = MagicMock(spec=ToolCallMessageSegment)
        result_seg.model_dump.return_value = {"role": "tool", "content": "result"}

        tcr = ToolCallsResult(
            tool_calls_info=info,
            tool_calls_result=[result_seg],
        )
        assert tcr.tool_calls_info is info
        assert len(tcr.tool_calls_result) == 1

    def test_to_openai_messages(self):
        info = MagicMock(spec=AssistantMessageSegment)
        info.model_dump.return_value = {"role": "assistant"}
        r1 = MagicMock(spec=ToolCallMessageSegment)
        r1.model_dump.return_value = {"role": "tool", "name": "get_weather"}
        r2 = MagicMock(spec=ToolCallMessageSegment)
        r2.model_dump.return_value = {"role": "tool", "name": "search"}

        tcr = ToolCallsResult(tool_calls_info=info, tool_calls_result=[r1, r2])
        msgs = tcr.to_openai_messages()
        assert len(msgs) == 3
        assert msgs[0] == {"role": "assistant"}
        assert msgs[1] == {"role": "tool", "name": "get_weather"}
        assert msgs[2] == {"role": "tool", "name": "search"}

    def test_to_openai_messages_model(self):
        info = MagicMock(spec=AssistantMessageSegment)
        r1 = MagicMock(spec=ToolCallMessageSegment)

        tcr = ToolCallsResult(tool_calls_info=info, tool_calls_result=[r1])
        models = tcr.to_openai_messages_model()
        assert len(models) == 2
        assert models[0] is info
        assert models[1] is r1

    def test_to_openai_messages_empty_result(self):
        info = MagicMock(spec=AssistantMessageSegment)
        info.model_dump.return_value = {"role": "assistant"}
        tcr = ToolCallsResult(tool_calls_info=info, tool_calls_result=[])
        msgs = tcr.to_openai_messages()
        assert len(msgs) == 1
        assert msgs[0] == {"role": "assistant"}


# =========================================================================
# ProviderRequest
# =========================================================================


class TestProviderRequest:
    def test_default_construction(self):
        req = ProviderRequest()
        assert req.prompt is None
        assert req.session_id == ""
        assert req.image_urls == []
        assert req.audio_urls == []
        assert req.contexts == []
        assert req.func_tool is None
        assert req.system_prompt is None
        assert req.conversation is None
        assert req.tool_calls_result is None
        assert req.model is None

    def test_construction_with_values(self):
        req = ProviderRequest(
            prompt="Hello",
            session_id="sess-1",
            image_urls=["http://example.com/img.png"],
            system_prompt="You are a bot",
            model="gpt-4",
        )
        assert req.prompt == "Hello"
        assert req.session_id == "sess-1"
        assert req.image_urls == ["http://example.com/img.png"]
        assert req.system_prompt == "You are a bot"
        assert req.model == "gpt-4"

    def test_repr_without_context(self):
        req = ProviderRequest(prompt="hi", session_id="s1")
        text = repr(req)
        assert "prompt=hi" in text
        assert "session_id=s1" in text
        assert "image_count=0" in text

    def test_repr_with_conversation(self):
        conversation = MagicMock()
        conversation.cid = "conv-abc"
        req = ProviderRequest(prompt="test", conversation=conversation)
        text = repr(req)
        assert "conversation_id=conv-abc" in text

    def test_append_tool_calls_result_none_to_single(self):
        req = ProviderRequest()
        tcr = MagicMock(spec=ToolCallsResult)
        req.append_tool_calls_result(tcr)
        assert isinstance(req.tool_calls_result, list)
        assert len(req.tool_calls_result) == 1
        assert req.tool_calls_result[0] is tcr

    def test_append_tool_calls_result_single_to_list(self):
        tcr1 = MagicMock(spec=ToolCallsResult)
        req = ProviderRequest(tool_calls_result=tcr1)
        tcr2 = MagicMock(spec=ToolCallsResult)
        req.append_tool_calls_result(tcr2)
        assert isinstance(req.tool_calls_result, list)
        assert len(req.tool_calls_result) == 2
        assert req.tool_calls_result[0] is tcr1
        assert req.tool_calls_result[1] is tcr2

    def test_append_tool_calls_result_list(self):
        tcr1 = MagicMock(spec=ToolCallsResult)
        tcr2 = MagicMock(spec=ToolCallsResult)
        req = ProviderRequest(tool_calls_result=[tcr1])
        tcr3 = MagicMock(spec=ToolCallsResult)
        req.append_tool_calls_result(tcr3)
        assert len(req.tool_calls_result) == 2

    def test_print_friendly_context_no_contexts(self):
        req = ProviderRequest(prompt="hello", image_urls=["a.png"], audio_urls=["b.wav"])
        result = req._print_friendly_context()
        assert "prompt: hello" in result
        assert "image_count: 1" in result
        assert "audio_count: 1" in result

    def test_print_friendly_context_with_text_contexts(self):
        req = ProviderRequest(contexts=[{"role": "user", "content": "hello"}])
        result = req._print_friendly_context()
        assert "user: hello" in result

    def test_print_friendly_context_filters_checkpoints(self):
        req = ProviderRequest(
            contexts=[
                {"role": "user", "content": "hi", "checkpoint": True},
                {"role": "assistant", "content": "hello"},
            ]
        )
        with patch(
            "astrbot.core.provider.entities.is_checkpoint_message",
            side_effect=lambda c: c.get("checkpoint", False),
        ):
            result = req._print_friendly_context()
            assert "user: hi" not in result
            assert "assistant: hello" in result

    def test_print_friendly_context_multimodal(self):
        req = ProviderRequest(
            contexts=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "describe this"},
                        {"type": "image_url", "image_url": {"url": "x.jpg"}},
                        {"type": "image_url", "image_url": {"url": "y.jpg"}},
                        {"type": "audio_url", "audio_url": {"url": "z.wav"}},
                    ],
                }
            ]
        )
        result = req._print_friendly_context()
        assert "user: describe this[+2 images][+1 audios]" in result

    def test_assemble_context_simple_text(self):
        """When there's only a plain text prompt and no extra content, it returns a simple str content."""
        req = ProviderRequest(prompt="hello world")
        import asyncio

        ctx = asyncio.run(req.assemble_context())
        assert ctx == {"role": "user", "content": "hello world"}

    def test_assemble_context_empty_prompt_with_images_adds_placeholder(self):
        req = ProviderRequest(prompt="", image_urls=[])
        import asyncio

        with patch.object(req, "_encode_image_bs64", return_value="data:image/jpeg;base64,abc"):
            req.image_urls = ["http://example.com/img.png"]
            ctx = asyncio.run(req.assemble_context())
            assert ctx["role"] == "user"
            # Should include "[图片]" placeholder
            content = ctx["content"]
            assert isinstance(content, list)
            assert any(b.get("text") == "[图片]" for b in content)

    def test_assemble_context_empty_prompt_with_audio_adds_placeholder(self):
        req = ProviderRequest(prompt="", audio_urls=["http://example.com/a.wav"])
        import asyncio

        with (
            patch.object(req, "_encode_audio_bs64", return_value="data:audio/wav;base64,xyz"),
            patch("astrbot.core.provider.entities.download_file", AsyncMock()),
        ):
            ctx = asyncio.run(req.assemble_context())
            assert ctx["role"] == "user"
            content = ctx["content"]
            assert isinstance(content, list)
            assert any(b.get("text") == "[音频]" for b in content)

    def test_assemble_context_with_extra_user_content(self):
        extra_part = MagicMock(spec=ContentPart)
        extra_part.model_dump.return_value = {"type": "text", "text": "extra instruction"}
        req = ProviderRequest(
            prompt="translate this",
            extra_user_content_parts=[extra_part],
        )
        import asyncio

        ctx = asyncio.run(req.assemble_context())
        assert ctx["role"] == "user"
        content = ctx["content"]
        assert isinstance(content, list)
        texts = [b["text"] for b in content if b.get("type") == "text"]
        assert "translate this" in texts
        assert "extra instruction" in texts

    def test_encode_image_bs64_base64_prefix(self):
        req = ProviderRequest()
        import asyncio

        result = asyncio.run(req._encode_image_bs64("base64://rawdata"))
        assert result == "data:image/jpeg;base64,rawdata"

    def test_encode_audio_bs64_base64_prefix(self):
        req = ProviderRequest()
        import asyncio

        result = asyncio.run(req._encode_audio_bs64("base64://rawdata"))
        assert result == "data:audio/wav;base64,rawdata"

    def test_str_equals_repr(self):
        req = ProviderRequest(prompt="test", session_id="s1")
        assert str(req) == repr(req)


# =========================================================================
# LLMResponse
# =========================================================================


class TestLLMResponse:
    def test_default_role_assistant(self):
        resp = LLMResponse(role="assistant")
        assert resp.role == "assistant"
        assert resp.completion_text is None or resp.completion_text == ""
        assert resp.tools_call_args == []
        assert resp.tools_call_name == []
        assert resp.tools_call_ids == []
        assert resp.tools_call_extra_content == {}
        assert resp.reasoning_content is None
        assert resp.raw_completion is None
        assert resp.is_chunk is False
        assert resp.id is None
        assert resp.usage is None

    def test_construction_with_completion_text(self):
        resp = LLMResponse(role="assistant", completion_text="Hello world")
        assert resp.completion_text == "Hello world"

    def test_construction_with_result_chain(self):
        chain = MessageChain()
        chain.message("Hello from chain")
        resp = LLMResponse(role="assistant", result_chain=chain)
        assert resp.completion_text == "Hello from chain"

    def test_completion_text_setter_with_result_chain(self):
        chain = MessageChain()
        chain.message("Old text")
        resp = LLMResponse(role="assistant", result_chain=chain)
        assert resp.completion_text == "Old text"
        resp.completion_text = "New text"
        # The setter inserts a Plain component at the start after removing old ones
        assert "New text" in resp.completion_text

    def test_completion_text_setter_without_result_chain(self):
        resp = LLMResponse(role="assistant")
        resp.completion_text = "direct text"
        assert resp.completion_text == "direct text"

    def test_tool_calls_defaults_to_empty(self):
        resp = LLMResponse(role="assistant")
        # They should be empty lists, not None
        assert resp.tools_call_args == []
        assert resp.tools_call_name == []
        assert resp.tools_call_ids == []
        assert resp.tools_call_extra_content == {}

    def test_construction_with_tool_calls(self):
        resp = LLMResponse(
            role="assistant",
            tools_call_args=[{"location": "NYC"}],
            tools_call_name=["get_weather"],
            tools_call_ids=["call_123"],
            tools_call_extra_content={"call_123": {"source": "web"}},
        )
        assert resp.tools_call_args == [{"location": "NYC"}]
        assert resp.tools_call_name == ["get_weather"]
        assert resp.tools_call_ids == ["call_123"]
        assert resp.tools_call_extra_content == {"call_123": {"source": "web"}}

    def test_to_openai_tool_calls(self):
        resp = LLMResponse(
            role="assistant",
            tools_call_args=[{"q": "weather"}, {"q": "news"}],
            tools_call_name=["search", "search"],
            tools_call_ids=["c1", "c2"],
            tools_call_extra_content={"c1": {"priority": 1}},
        )
        calls = resp.to_openai_tool_calls()
        assert len(calls) == 2
        assert calls[0]["id"] == "c1"
        assert calls[0]["function"]["name"] == "search"
        assert json.loads(calls[0]["function"]["arguments"]) == {"q": "weather"}
        assert calls[0]["extra_content"] == {"priority": 1}
        assert calls[1]["id"] == "c2"
        assert "extra_content" not in calls[1]

    def test_to_openai_to_calls_model(self):
        resp = LLMResponse(
            role="assistant",
            tools_call_args=[{"x": 1}],
            tools_call_name=["foo"],
            tools_call_ids=["cid1"],
            tools_call_extra_content={"cid1": {"meta": "data"}},
        )
        calls = resp.to_openai_to_calls_model()
        assert len(calls) == 1
        assert isinstance(calls[0], ToolCall)
        assert calls[0].id == "cid1"
        assert calls[0].function.name == "foo"
        assert calls[0].extra_content == {"meta": "data"}

    def test_to_openai_tool_calls_empty(self):
        resp = LLMResponse(role="assistant")
        calls = resp.to_openai_tool_calls()
        assert calls == []

    def test_to_openai_to_calls_model_empty(self):
        resp = LLMResponse(role="assistant")
        calls = resp.to_openai_to_calls_model()
        assert calls == []

    def test_construction_with_reasoning(self):
        resp = LLMResponse(
            role="assistant",
            completion_text="final answer",
            reasoning_content="thinking step by step",
            reasoning_signature="sig_abc",
        )
        assert resp.reasoning_content == "thinking step by step"
        assert resp.reasoning_signature == "sig_abc"

    def test_construction_with_raw_completion(self):
        raw = MagicMock()
        resp = LLMResponse(role="assistant", raw_completion=raw)
        assert resp.raw_completion is raw

    def test_construction_with_usage(self):
        usage = TokenUsage(input_other=10, output=20)
        resp = LLMResponse(role="assistant", usage=usage)
        assert resp.usage is usage

    def test_construction_with_chunk_and_id(self):
        resp = LLMResponse(role="assistant", is_chunk=True, id="chunk_1")
        assert resp.is_chunk is True
        assert resp.id == "chunk_1"


# =========================================================================
# RerankResult
# =========================================================================


class TestRerankResult:
    def test_construction(self):
        rr = RerankResult(index=0, relevance_score=0.95)
        assert rr.index == 0
        assert rr.relevance_score == 0.95

    def test_negative_score(self):
        rr = RerankResult(index=5, relevance_score=-0.1)
        assert rr.relevance_score == -0.1

    def test_zero_values(self):
        rr = RerankResult(index=0, relevance_score=0.0)
        assert rr.index == 0
        assert rr.relevance_score == 0.0
