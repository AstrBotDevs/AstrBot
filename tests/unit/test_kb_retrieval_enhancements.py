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
from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult
from astrbot.core.message.components import Plain, Reply
from astrbot.core.provider.entities import ProviderRequest, RerankResult


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
        long_quote = "".join(f"[{idx:03d}]" for idx in range(100))
        assert len(long_quote) > kb_mod._MAX_QUOTED_EXCERPT_CHARS
        parts = [
            TextPart(text=f"<Quoted Message>\n(Bob): {long_quote}\n</Quoted Message>")
        ]
        query = kb_mod.extract_retrieval_query("<提及自己> explain this", parts)
        expected_excerpt = long_quote[: kb_mod._MAX_QUOTED_EXCERPT_CHARS]
        assert query == f"explain this\n{expected_excerpt}"

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
        default_labels = kb_items["kb_retrieval_mode"]["labels"]
        assert len(default_labels) == len(expected_options)
        assert all(isinstance(label, str) and label.strip() for label in default_labels)
        assert len(set(default_labels)) == len(expected_options)
        for option, label in zip(expected_options, default_labels, strict=True):
            if option:
                assert f"({option})" in label
            else:
                assert "Agentic" in label

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
            for key in ("kb_min_score", "kb_retrieval_mode"):
                assert isinstance(kb_locale[key].get("description"), str)
                assert kb_locale[key]["description"].strip()
                assert isinstance(kb_locale[key].get("hint"), str)
                assert kb_locale[key]["hint"].strip()
            labels = kb_locale["kb_retrieval_mode"]["labels"]
            assert len(labels) == len(expected_options)
            assert all(isinstance(label, str) and label.strip() for label in labels)
            assert len(set(labels)) == len(expected_options)
            for option, label in zip(expected_options, labels, strict=True):
                if option:
                    assert f"({option})" in label
                else:
                    assert "Agentic" in label

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

        for extreme in (10**400, float("inf"), float("nan")):
            fallback_cfg = MainAgentBuildConfig.from_config({"kb_min_score": extreme})
            assert fallback_cfg.kb_min_score == 0.0

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

    @pytest.mark.asyncio
    async def test_overflow_threshold_falls_back_to_zero(self):
        results = [
            {
                "kb_name": "docs",
                "doc_name": "a.md",
                "content": "kept on fallback",
                "score": 0.2,
                "relevance_score": 0.2,
            }
        ]
        ctx_cfg_overflow = self._make_context(results, min_score=10**400)
        assert (
            await kb_tools.retrieve_knowledge_base("q", "umo-1", ctx_cfg_overflow)
            == "RAW_CONTEXT_TEXT"
        )

        ctx_arg_overflow = self._make_context(results, min_score=0.9)
        assert (
            await kb_tools.retrieve_knowledge_base(
                "q", "umo-1", ctx_arg_overflow, min_score=10**400
            )
            == "RAW_CONTEXT_TEXT"
        )

    @pytest.mark.asyncio
    async def test_min_score_gates_on_absolute_relevance_not_batch_normalized_fusion(
        self,
    ):
        """Lone or tied weak hits must not bypass kb_min_score via min-max normalization."""

        def _make_dense(chunk_id: str, similarity: float, text: str) -> Result:
            return Result(
                similarity=similarity,
                data={
                    "doc_id": chunk_id,
                    "text": text,
                    "metadata": json.dumps(
                        {
                            "chunk_index": 0,
                            "kb_doc_id": f"doc-{chunk_id}",
                            "kb_id": "kb-1",
                        }
                    ),
                },
            )

        def _make_sparse(
            chunk_id: str, score: float, rank: int, text: str
        ) -> SparseResult:
            return SparseResult(
                chunk_index=0,
                chunk_id=chunk_id,
                doc_id=f"doc-{chunk_id}",
                kb_id="kb-1",
                content=text,
                score=score,
                rank=rank,
            )

        async def _run_pipeline(
            dense_results: list[Result],
            sparse_results: list[SparseResult],
            *,
            min_score: float,
            rerank_scores: list[RerankResult] | None = None,
        ) -> str | None:
            vec_db = SimpleNamespace(
                retrieve=AsyncMock(return_value=dense_results),
                rerank_provider=(
                    SimpleNamespace(rerank=AsyncMock(return_value=rerank_scores))
                    if rerank_scores is not None
                    else None
                ),
            )
            kb_record = SimpleNamespace(
                kb_id="kb-1",
                kb_name="docs",
                doc_count=1,
                chunk_count=max(len(dense_results), len(sparse_results), 1),
                top_k_dense=20,
                top_k_sparse=20,
                top_m_final=5,
                rerank_provider_id="rr-1" if rerank_scores is not None else None,
            )
            kb_helper = SimpleNamespace(kb=kb_record, vec_db=vec_db, init_error=None)
            kb_db = SimpleNamespace(
                get_documents_with_metadata_batch=AsyncMock(
                    side_effect=lambda doc_ids: {
                        doc_id: {
                            "document": SimpleNamespace(doc_name=f"{doc_id}.md"),
                            "knowledge_base": kb_record,
                        }
                        for doc_id in doc_ids
                    }
                )
            )
            sparse_retriever = SimpleNamespace(
                retrieve=AsyncMock(return_value=sparse_results)
            )
            retrieval_mgr = RetrievalManager(
                sparse_retriever=sparse_retriever,
                rank_fusion=RankFusion(kb_db=kb_db),
                kb_db=kb_db,
            )
            kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
            kb_mgr.kb_insts = {"kb-1": kb_helper}
            kb_mgr.retrieval_manager = retrieval_mgr

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
            return await kb_tools.retrieve_knowledge_base("query", "umo-1", ctx)

        # 1. Lone weak candidate: RankFusion assigns normalized score=1.0, but
        # absolute dense similarity is 0.15 -> must be filtered out at min_score=0.5.
        lone_weak = await _run_pipeline(
            [_make_dense("c1", 0.15, "unrelated chunk")],
            [_make_sparse("c1", 0.2, 1, "unrelated chunk")],
            min_score=0.5,
        )
        assert lone_weak is None

        # 2. Tied weak candidates: RankFusion assigns normalized score=1.0 to both,
        # but absolute dense similarity is 0.20 -> both must be filtered out.
        tied_weak = await _run_pipeline(
            [
                _make_dense("c1", 0.20, "weak one"),
                _make_dense("c2", 0.20, "weak two"),
            ],
            [
                _make_sparse("c1", 0.5, 1, "weak one"),
                _make_sparse("c2", 0.5, 2, "weak two"),
            ],
            min_score=0.5,
        )
        assert tied_weak is None

        # 3. Two strong candidates: min-max fusion gives the second candidate 0.0,
        # but its absolute dense similarity is 0.88 -> both must be retained.
        both_strong = await _run_pipeline(
            [
                _make_dense("c1", 0.92, "strong one"),
                _make_dense("c2", 0.88, "strong two"),
            ],
            [],
            min_score=0.5,
        )
        assert both_strong is not None
        assert "strong one" in both_strong
        assert "strong two" in both_strong

        # 4. Rerank relevance_score overrides dense similarity for threshold gating.
        reranked = await _run_pipeline(
            [
                _make_dense("c1", 0.90, "demoted by reranker"),
                _make_dense("c2", 0.15, "promoted by reranker"),
            ],
            [],
            min_score=0.6,
            rerank_scores=[
                RerankResult(index=0, relevance_score=0.12),
                RerankResult(index=1, relevance_score=0.84),
            ],
        )
        assert reranked is not None
        assert "promoted by reranker" in reranked
        assert "demoted by reranker" not in reranked
        assert "0.84" in reranked

        # 5. Sparse-only candidate without reranker lacks a calibrated absolute score:
        # filtered out when min_score > 0.0, kept when min_score == 0.0.
        sparse_only_gated = await _run_pipeline(
            [],
            [_make_sparse("s1", 0.01, 1, "sparse only chunk")],
            min_score=0.05,
        )
        assert sparse_only_gated is None
        sparse_only_ungated = await _run_pipeline(
            [],
            [_make_sparse("s1", 0.01, 1, "sparse only chunk")],
            min_score=0.0,
        )
        assert sparse_only_ungated is not None
        assert "sparse only chunk" in sparse_only_ungated


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

        # (d) prompt_prefix + hook appends substantive text without retrieval_query ->
        # supplemental retrieval strips the prefix and queries only the clean text.
        req_d = ProviderRequest(prompt="<attachment>", func_tool=ToolSet())
        res_d, ret_d = await _run_explicit(
            req_d,
            lambda r: setattr(r, "prompt", f"{r.prompt}\nHow do I reset my password?"),
            provider_settings={"prompt_prefix": "[PREFIX] {{prompt}}"},
        )
        assert res_d is not None
        ret_d.assert_awaited_once()
        assert ret_d.await_args.kwargs["query"] == "How do I reset my password?"

        # (e) Template prefix with suffix + hook replaces placeholder inside template ->
        # both prefix and suffix are stripped from the supplemental query.
        req_e = ProviderRequest(prompt="<attachment>", func_tool=ToolSet())
        res_e, ret_e = await _run_explicit(
            req_e,
            lambda r: setattr(
                r, "prompt", r.prompt.replace("<attachment>", "Vienna concert hall")
            ),
            provider_settings={"prompt_prefix": "[PRE] {{prompt}} [SUF]"},
        )
        assert res_e is not None
        ret_e.assert_awaited_once()
        assert ret_e.await_args.kwargs["query"] == "Vienna concert hall"

    @pytest.mark.asyncio
    async def test_quoted_or_plugin_header_text_does_not_skip_retrieval_and_reentry_does(
        self, mock_event, mock_context
    ):
        """Literal KB header text in quoted/plugin parts must not suppress retrieval."""
        req = ProviderRequest(
            prompt="What is the release schedule?",
            extra_user_content_parts=[
                TextPart(
                    text=(
                        "<Quoted Message>\n"
                        f"(Alice): See {kb_mod.KB_RESULTS_HEADER} old snippet\n"
                        "</Quoted Message>"
                    )
                )
            ],
        )
        config = MainAgentBuildConfig(tool_call_timeout=60, kb_retrieval_mode="auto")
        retrieve = AsyncMock(return_value="Fresh KB result")

        with patch.object(kb_mod, "retrieve_knowledge_base", retrieve):
            first = await kb_mod.apply_knowledge_base(
                mock_event, req, mock_context, config
            )
            second = await kb_mod.apply_knowledge_base(
                mock_event, req, mock_context, config
            )

        assert first is True
        assert second is True
        retrieve.assert_awaited_once()
        assert any(
            "Fresh KB result" in getattr(part, "text", "")
            for part in req.extra_user_content_parts
        )

    @pytest.mark.asyncio
    async def test_per_turn_zero_min_score_overrides_positive_session_threshold(
        self, mock_event
    ):
        """Explicit MainAgentBuildConfig(kb_min_score=0.0) disables session min_score."""
        kb_helper = SimpleNamespace(kb=SimpleNamespace(doc_count=1, chunk_count=1))
        kb_mgr = SimpleNamespace(
            get_kb_by_name=AsyncMock(return_value=kb_helper),
            retrieve=AsyncMock(
                return_value={
                    "context_text": "LOW_SCORE_HIT",
                    "results": [
                        {
                            "kb_name": "docs",
                            "doc_name": "a.md",
                            "content": "low relevance content",
                            "score": 0.2,
                            "relevance_score": 0.2,
                        }
                    ],
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
                    "kb_min_score": 0.9,
                }
            ),
        )
        req = ProviderRequest(prompt="test query")
        config = MainAgentBuildConfig(
            tool_call_timeout=60,
            kb_retrieval_mode="auto",
            kb_min_score=0.0,
        )

        ran = await kb_mod.apply_knowledge_base(mock_event, req, ctx, config)

        assert ran is True
        assert len(req.extra_user_content_parts) == 1
        assert "LOW_SCORE_HIT" in req.extra_user_content_parts[0].text
