"""Unit tests for clean KB retrieval queries, score gating, and hybrid mode."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core import agent_input as core_input
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.astr_agent_runtime import execution as native_execution
from astrbot.core.astr_agent_runtime.main_agent import (
    MainAgentBuildConfig,
    build_main_agent,
)
from astrbot.core.astr_agent_runtime.main_agent import builder as builder_mod
from astrbot.core.astr_agent_runtime.main_agent import (
    knowledge_base as kb_mod,
)
from astrbot.core.astr_agent_runtime.tools import (
    knowledge_base_tools as kb_tools,
)
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    DEFAULT_CONFIG,
)
from astrbot.core.message.components import Plain, Reply
from astrbot.core.provider.entities import ProviderRequest


class TestExtractRetrievalQuery:
    """Tests for clean retrieval query extraction and placeholder filtering."""

    @pytest.mark.parametrize(
        "prompt",
        [
            None,
            "",
            "   \n\t  ",
            "<attachment>",
            "<提及自己>",
            "[提及机器人]",
            "<提及自己> <attachment> [图片]",
            "[Image unavailable] [Voice unavailable]",
        ],
    )
    def test_pure_placeholders_produce_empty_query(self, prompt):
        assert kb_mod.extract_retrieval_query(prompt) == ""

    def test_extracts_quoted_text_for_attachment_only_reply(self):
        parts = [
            TextPart(
                text="<Quoted Message>\n(Alice): Where is the Vienna concert hall?\n</Quoted Message>"
            )
        ]
        assert (
            kb_mod.extract_retrieval_query("<attachment>", parts)
            == "Where is the Vienna concert hall?"
        )

    def test_combines_clean_prompt_and_quoted_excerpt_with_truncation(self):
        long_quote = "A" * 400
        parts = [
            TextPart(text=f"<Quoted Message>\n(Bob): {long_quote}\n</Quoted Message>")
        ]
        query = kb_mod.extract_retrieval_query("<提及自己> explain this", parts)
        assert query.startswith("explain this\n")
        assert len(query.split("\n", 1)[1]) == kb_mod._MAX_QUOTED_EXCERPT_CHARS

    def test_ignores_empty_text_quoted_placeholder(self):
        parts = [
            TextPart(text="<Quoted Message>\n(Bob): [Empty Text]\n</Quoted Message>")
        ]
        assert kb_mod.extract_retrieval_query("<attachment>", parts) == ""


class TestKbConfigAndModes:
    """Tests for kb_retrieval_mode, kb_min_score, and backward compatibility."""

    def test_default_config_and_metadata_locales_in_sync(self):
        assert DEFAULT_CONFIG["kb_min_score"] == 0.0
        assert DEFAULT_CONFIG["kb_retrieval_mode"] == ""
        assert "kb_min_score" in CONFIG_METADATA_2["misc_config_group"]["metadata"]
        assert "kb_retrieval_mode" in CONFIG_METADATA_2["misc_config_group"]["metadata"]
        kb_items = CONFIG_METADATA_3["ai_group"]["metadata"]["knowledgebase"]["items"]
        assert "kb_min_score" in kb_items
        assert "kb_retrieval_mode" in kb_items
        expected_options = kb_items["kb_retrieval_mode"]["options"]
        assert expected_options == ["", "auto", "agentic", "hybrid"]

        locales_root = (
            Path(__file__).resolve().parents[2]
            / "dashboard"
            / "src"
            / "i18n"
            / "locales"
        )
        for locale in ("en-US", "zh-CN", "ja-JP", "ru-RU"):
            meta_path = locales_root / locale / "features" / "config-metadata.json"
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            kb_locale = data["ai_group"]["knowledgebase"]
            assert "kb_min_score" in kb_locale
            assert "kb_retrieval_mode" in kb_locale
            assert len(kb_locale["kb_retrieval_mode"]["labels"]) == len(
                expected_options
            )

    def test_from_config_preserves_legacy_agentic_mode_and_validates_inputs(self):
        legacy_auto = MainAgentBuildConfig.from_config({"kb_agentic_mode": False})
        assert legacy_auto.effective_kb_mode == "auto"
        assert legacy_auto.kb_min_score == 0.0

        legacy_agentic = MainAgentBuildConfig.from_config({"kb_agentic_mode": True})
        assert legacy_agentic.effective_kb_mode == "agentic"

        hybrid = MainAgentBuildConfig.from_config(
            {
                "kb_agentic_mode": False,
                "kb_retrieval_mode": "hybrid",
                "kb_min_score": 0.45,
            }
        )
        assert hybrid.effective_kb_mode == "hybrid"
        assert hybrid.kb_min_score == pytest.approx(0.45)

        invalid = MainAgentBuildConfig.from_config(
            {
                "kb_agentic_mode": True,
                "kb_retrieval_mode": "unknown_mode",
                "kb_min_score": -0.5,
            }
        )
        assert invalid.kb_retrieval_mode == ""
        assert invalid.effective_kb_mode == "agentic"
        assert invalid.kb_min_score == 0.0

        bool_score = MainAgentBuildConfig.from_config({"kb_min_score": True})
        assert bool_score.kb_min_score == 0.0


class TestMinScoreFiltering:
    """Tests for kb_min_score gating in retrieve_knowledge_base."""

    def _make_context(self, results, *, min_score=0.0):
        kb_helper = SimpleNamespace(kb=SimpleNamespace(doc_count=1, chunk_count=2))
        kb_mgr = SimpleNamespace(
            get_kb_by_name=AsyncMock(return_value=kb_helper),
            retrieve=AsyncMock(
                return_value={
                    "context_text": "RAW_CONTEXT_TEXT",
                    "results": results,
                }
            ),
        )
        ctx = SimpleNamespace(
            kb_manager=kb_mgr,
            get_config=MagicMock(
                return_value={
                    "kb_names": ["docs"],
                    "kb_final_top_k": 5,
                    "kb_fusion_top_k": 20,
                    "kb_min_score": min_score,
                }
            ),
        )
        return ctx

    @pytest.mark.asyncio
    async def test_zero_min_score_preserves_original_context_text(self):
        results = [
            {
                "kb_name": "docs",
                "doc_name": "a.md",
                "content": "low score",
                "score": 0.01,
            }
        ]
        ctx = self._make_context(results, min_score=0.0)
        text = await kb_tools.retrieve_knowledge_base("q", "umo-1", ctx)
        assert text == "RAW_CONTEXT_TEXT"

    @pytest.mark.asyncio
    async def test_min_score_filters_low_results_and_returns_none_when_empty(self):
        results = [
            {
                "kb_name": "docs",
                "doc_name": "high.md",
                "content": "exact answer",
                "score": 0.82,
            },
            {
                "kb_name": "docs",
                "doc_name": "low.md",
                "content": "unrelated chatter",
                "score": 0.15,
            },
        ]
        ctx = self._make_context(results, min_score=0.5)
        partial = await kb_tools.retrieve_knowledge_base("q", "umo-1", ctx)
        assert partial is not None
        assert "exact answer" in partial
        assert "unrelated chatter" not in partial
        assert "0.82" in partial

        none_pass = await kb_tools.retrieve_knowledge_base(
            "q", "umo-1", ctx, min_score=0.95
        )
        assert none_pass is None

    @pytest.mark.asyncio
    async def test_agentic_tool_call_bypasses_auto_injection_min_score(self):
        results = [
            {
                "kb_name": "docs",
                "doc_name": "mid.md",
                "content": "mid relevance detail",
                "score": 0.25,
            }
        ]
        ctx = self._make_context(results, min_score=0.7)
        tool = kb_tools.KnowledgeBaseQueryTool()
        wrapper = SimpleNamespace(
            context=SimpleNamespace(
                event=SimpleNamespace(unified_msg_origin="umo-1"),
                context=ctx,
            )
        )
        output = await tool.call(wrapper, query="detail")
        assert output == "RAW_CONTEXT_TEXT"


class TestHybridAndPostHookRetrieval:
    """Tests for hybrid mode, explicit retrieval_query, and one-shot post-hook lookup."""

    @staticmethod
    def _configure_builtin_tool_mgr(mock_context):
        tool_mgr = MagicMock()
        tool_mgr.get_builtin_tool.side_effect = lambda cls, **kwargs: cls(**kwargs)
        mock_context.get_llm_tool_manager = MagicMock(return_value=tool_mgr)
        return mock_context

    @pytest.mark.asyncio
    async def test_hybrid_mode_mounts_tool_and_injects_high_score_hits(
        self, mock_event, mock_context
    ):
        self._configure_builtin_tool_mgr(mock_context)
        req = ProviderRequest(prompt="test question", retrieval_query="clean query")
        config = MainAgentBuildConfig(
            tool_call_timeout=60,
            kb_retrieval_mode="hybrid",
            kb_min_score=0.4,
        )
        retrieve = AsyncMock(return_value="Relevant chunk")

        with patch.object(kb_mod, "retrieve_knowledge_base", retrieve):
            ran = await kb_mod.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        assert ran is True
        assert req.func_tool is not None
        assert req.func_tool.get_tool("astr_kb_search") is not None
        retrieve.assert_awaited_once_with(
            query="clean query",
            umo=mock_event.unified_msg_origin,
            context=mock_context,
            min_score=0.4,
        )
        assert len(req.extra_user_content_parts) == 1
        assert "Relevant chunk" in req.extra_user_content_parts[0].text

    @pytest.mark.asyncio
    async def test_hybrid_mode_keeps_tool_when_min_score_filters_all_hits(
        self, mock_event, mock_context
    ):
        self._configure_builtin_tool_mgr(mock_context)
        req = ProviderRequest(prompt="good morning")
        config = MainAgentBuildConfig(
            tool_call_timeout=60,
            kb_retrieval_mode="hybrid",
            kb_min_score=0.6,
        )
        retrieve = AsyncMock(return_value=None)

        with patch.object(kb_mod, "retrieve_knowledge_base", retrieve):
            ran = await kb_mod.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        assert ran is True
        assert req.func_tool.get_tool("astr_kb_search") is not None
        assert req.extra_user_content_parts == []

    @pytest.mark.asyncio
    async def test_explicit_empty_retrieval_query_suppresses_lookup(
        self, mock_event, mock_context
    ):
        req = ProviderRequest(prompt="non-empty prompt", retrieval_query="")
        config = MainAgentBuildConfig(tool_call_timeout=60, kb_retrieval_mode="auto")
        retrieve = AsyncMock(return_value="should not run")

        with patch.object(kb_mod, "retrieve_knowledge_base", retrieve):
            ran = await kb_mod.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        assert ran is False
        retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prepare_input_content_seeds_clean_query_before_prompt_prefix(
        self, mock_event, mock_context, mock_provider
    ):
        mock_event.message_obj.message = [
            Reply(id="r1", message_str="Quoted fact", sender_nickname="Bob"),
            Plain("What is this?"),
        ]
        req = ProviderRequest(prompt="What is this?")
        config = MainAgentBuildConfig(
            tool_call_timeout=60,
            provider_settings={"prompt_prefix": "[PREFIX] {{prompt}}"},
        )

        prepared = await core_input.prepare_input_content(
            mock_event,
            mock_context,
            config,
            mock_provider,
            req,
            collected_request=True,
            quote_image_ref=None,
            quoted_image_refs=set(),
        )

        assert prepared is not None
        assert req.prompt == "[PREFIX] What is this?"
        assert req.retrieval_query == "What is this?\nQuoted fact"

    @pytest.mark.asyncio
    async def test_build_main_agent_post_hook_retrieves_once_and_never_duplicates(
        self, mock_event, mock_context, mock_provider
    ):
        """Post-hook fills KB when pre-hook had no clean query, and skips if already run."""
        self._configure_builtin_tool_mgr(mock_context)
        runner = MagicMock()
        runner.reset = AsyncMock()

        async def _run_case(initial_prompt, hook_fn, *, mode="hybrid"):
            req = ProviderRequest(
                prompt=initial_prompt,
                func_tool=ToolSet(),
            )
            config = MainAgentBuildConfig(
                tool_call_timeout=60,
                call_request_hook=True,
                kb_retrieval_mode=mode,
            )
            retrieve = AsyncMock(return_value="KB hit")

            async def fake_hook(event, event_type, hook_req, **_kw):
                hook_fn(hook_req)
                return False

            with (
                patch.object(native_execution, "AgentRunner", return_value=runner),
                patch.object(
                    builder_mod,
                    "AstrAgentContext",
                    side_effect=lambda **kw: SimpleNamespace(**kw),
                ),
                patch.object(builder_mod, "call_event_hook", side_effect=fake_hook),
                patch.object(kb_mod, "retrieve_knowledge_base", retrieve),
                patch.object(
                    builder_mod.persona, "apply_persona", AsyncMock(return_value=None)
                ),
                patch.object(
                    builder_mod.workspace,
                    "apply_workspace_instructions",
                    AsyncMock(return_value=None),
                ),
                patch.object(
                    builder_mod.subagent,
                    "apply_subagents",
                    AsyncMock(return_value=True),
                ),
            ):
                result = await build_main_agent(
                    event=mock_event,
                    plugin_context=mock_context,
                    provider=mock_provider,
                    config=config,
                    req=req,
                )
            return result, req, retrieve

        # 1. Pre-hook had placeholder "<attachment>", hook populates retrieval_query -> 1 lookup.
        res1, req1, ret1 = await _run_case(
            "<attachment>",
            lambda r: setattr(r, "retrieval_query", "transcribed voice query"),
        )
        assert res1 is not None
        ret1.assert_awaited_once()
        assert ret1.await_args.kwargs["query"] == "transcribed voice query"
        assert req1.func_tool.get_tool("astr_kb_search") is not None
        assert any(
            kb_mod.KB_RESULTS_HEADER in getattr(p, "text", "")
            for p in req1.extra_user_content_parts
        )

        # 2. Pre-hook had placeholder "<attachment>", legacy hook only updates req.prompt -> 1 lookup.
        res2, req2, ret2 = await _run_case(
            "<attachment>",
            lambda r: setattr(r, "prompt", "legacy stt transcript"),
        )
        assert res2 is not None
        ret2.assert_awaited_once()
        assert ret2.await_args.kwargs["query"] == "legacy stt transcript"

        # 3. Pre-hook ALREADY ran retrieval; hook updates prompt/retrieval_query -> still only 1 lookup!
        res3, req3, ret3 = await _run_case(
            "initial user question",
            lambda r: setattr(r, "retrieval_query", "merged follow-up question"),
        )
        assert res3 is not None
        ret3.assert_awaited_once()
        assert ret3.await_args.kwargs["query"] == "initial user question"
        kb_parts = [
            p
            for p in req3.extra_user_content_parts
            if kb_mod.KB_RESULTS_HEADER in getattr(p, "text", "")
        ]
        assert len(kb_parts) == 1

        # 4. Bare mention restored in hook to "<提及自己>" -> 0 lookups.
        res4, _req4, ret4 = await _run_case(
            " ",
            lambda r: setattr(r, "prompt", "<提及自己>"),
        )
        assert res4 is not None
        ret4.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_empty_retrieval_query_and_prompt_prefix_suppression(
        self, mock_event, mock_context, mock_provider
    ):
        """Explicit retrieval_query='' is never overwritten, and prompt_prefix never leaks."""
        self._configure_builtin_tool_mgr(mock_context)
        runner = MagicMock()
        runner.reset = AsyncMock()

        async def _run_explicit(req, hook_fn, *, provider_settings=None):
            config = MainAgentBuildConfig(
                tool_call_timeout=60,
                call_request_hook=True,
                kb_retrieval_mode="hybrid",
                provider_settings=provider_settings or {},
            )
            retrieve = AsyncMock(return_value="KB hit")

            async def fake_hook(event, event_type, hook_req, **_kw):
                hook_fn(hook_req)
                return False

            with (
                patch.object(native_execution, "AgentRunner", return_value=runner),
                patch.object(
                    builder_mod,
                    "AstrAgentContext",
                    side_effect=lambda **kw: SimpleNamespace(**kw),
                ),
                patch.object(builder_mod, "call_event_hook", side_effect=fake_hook),
                patch.object(kb_mod, "retrieve_knowledge_base", retrieve),
                patch.object(
                    builder_mod.persona, "apply_persona", AsyncMock(return_value=None)
                ),
                patch.object(
                    builder_mod.workspace,
                    "apply_workspace_instructions",
                    AsyncMock(return_value=None),
                ),
                patch.object(
                    builder_mod.subagent,
                    "apply_subagents",
                    AsyncMock(return_value=True),
                ),
            ):
                result = await build_main_agent(
                    event=mock_event,
                    plugin_context=mock_context,
                    provider=mock_provider,
                    config=config,
                    req=req,
                )
            return result, retrieve

        # (a) Caller pre-sets retrieval_query="" before build; hook mutates prompt -> still 0 lookups.
        req_a = ProviderRequest(prompt=" ", retrieval_query="", func_tool=ToolSet())
        res_a, ret_a = await _run_explicit(
            req_a, lambda r: setattr(r, "prompt", "hello from hook")
        )
        assert res_a is not None
        assert req_a.retrieval_query == ""
        ret_a.assert_not_awaited()

        # (b) Placeholder turn (retrieval_query stays None); hook sets retrieval_query="" AND prompt -> 0 lookups.
        req_b = ProviderRequest(prompt="<attachment>", func_tool=ToolSet())

        def _hook_suppress(r):
            r.retrieval_query = ""
            r.prompt = "hello from hook"

        res_b, ret_b = await _run_explicit(req_b, _hook_suppress)
        assert res_b is not None
        assert req_b.retrieval_query == ""
        ret_b.assert_not_awaited()

        # (c) prompt_prefix + "<attachment>" without hook changes -> 0 lookups (no prefix leak).
        req_c = ProviderRequest(prompt="<attachment>", func_tool=ToolSet())
        res_c, ret_c = await _run_explicit(
            req_c,
            lambda _r: None,
            provider_settings={"prompt_prefix": "[PREFIX] {{prompt}}"},
        )
        assert res_c is not None
        assert req_c.prompt == "[PREFIX] <attachment>"
        assert req_c.retrieval_query is None
        ret_c.assert_not_awaited()
