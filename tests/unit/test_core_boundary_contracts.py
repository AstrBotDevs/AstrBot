"""Exercise real retrieval, logging, plugin-tool, and view boundaries offline."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import TypedDict
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool, ToolSchema, ToolSet
from astrbot.core.chatui import ViewError, ViewSpec, resolve_view
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage
from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever
from astrbot.core.log import LogManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.star.agent_capabilities import filter_tools
from astrbot.core.star.base import Star
from astrbot.core.star.star import StarMetadata, star_map


class StoredVectorRow(TypedDict):
    id: int
    doc_id: str
    text: str
    metadata: str


@pytest.mark.asyncio
@pytest.mark.parametrize("dense_k", [1, 2, 4])
async def test_dense_retrieval_uses_real_faiss_signature_and_filtered_limits(
    dense_k: int,
) -> None:
    rows: list[StoredVectorRow] = [
        {
            "id": index,
            "doc_id": f"chunk-{index}",
            "text": f"Passage {index}",
            "metadata": json.dumps({"kb_id": "other" if index == 0 else "manual"}),
        }
        for index in range(8)
    ]

    async def search(vector: np.ndarray, k: int):
        return (
            np.array([[index * 0.2 for index in range(k)]], dtype=np.float32),
            np.array([list(range(k))], dtype=np.int64),
        )

    async def read_documents(metadata_filters: dict[str, str], ids):
        return [
            row
            for row in reversed(rows)
            if row["id"] in ids
            and all(
                json.loads(row["metadata"]).get(key) == value
                for key, value in metadata_filters.items()
            )
        ]

    embeddings = Mock(spec=EmbeddingProvider)
    embeddings.get_embedding = AsyncMock(return_value=[1.0, 0.0])
    index = Mock(spec=EmbeddingStorage)
    index.search = AsyncMock(side_effect=search)
    documents = Mock(spec=DocumentStorage)
    documents.get_documents = AsyncMock(side_effect=read_documents)
    reranker = Mock(spec=RerankProvider)
    reranker.rerank = AsyncMock()
    # Avoid index creation; the production retrieve method remains untouched.
    vector_store = FaissVecDB.__new__(FaissVecDB)
    vector_store.embedding_provider = embeddings
    vector_store.embedding_storage = index
    vector_store.document_storage = documents
    vector_store.rerank_provider = reranker
    manager = RetrievalManager(
        Mock(spec=SparseRetriever), Mock(spec=RankFusion), Mock(spec=KBSQLiteDatabase)
    )

    results = await manager._dense_retrieve(
        "a question",
        ["manual"],
        {"manual": {"vec_db": vector_store, "top_k_dense": dense_k}},
    )

    assert [item.data["doc_id"] for item in results] == [
        f"chunk-{number}" for number in range(1, dense_k + 1)
    ]
    assert [item.similarity for item in results] == pytest.approx(
        [1.0 - number * 0.1 for number in range(1, dense_k + 1)]
    )
    assert all(
        json.loads(item.data["metadata"])["kb_id"] == "manual" for item in results
    )
    embeddings.get_embedding.assert_awaited_once_with("a question")
    index.search.assert_awaited_once()
    assert index.search.await_args.kwargs["k"] == dense_k * 2
    np.testing.assert_array_equal(
        index.search.await_args.kwargs["vector"],
        np.array([[1.0, 0.0]], dtype=np.float32),
    )
    documents.get_documents.assert_awaited_once()
    assert documents.get_documents.await_args.kwargs["metadata_filters"] == {
        "kb_id": "manual"
    }
    np.testing.assert_array_equal(
        documents.get_documents.await_args.kwargs["ids"], np.arange(dense_k * 2)
    )
    reranker.rerank.assert_not_awaited()


@pytest.fixture
def trace_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[logging.Logger]:
    logger = logging.getLogger("astrbot.trace")
    previous_handlers, previous_filters = logger.handlers, logger.filters
    previous_level, previous_propagate = logger.level, logger.propagate
    previous_sink = LogManager._trace_sink_id
    with monkeypatch.context() as scoped:
        scoped.setattr(LogManager, "_trace_sink_id", None)
        scoped.setattr(logger, "handlers", [])
        scoped.setattr(logger, "filters", [])
        scoped.setattr(logger, "propagate", False)
        scoped.setattr(logger, "disabled", False)
        try:
            yield logger
        finally:
            LogManager._remove_sink(LogManager._trace_sink_id)
            logger.setLevel(previous_level)
    assert logger.handlers is previous_handlers
    assert logger.filters is previous_filters
    assert logger.propagate == previous_propagate
    assert logger.level == previous_level
    assert LogManager._trace_sink_id == previous_sink


@pytest.mark.parametrize("legacy_config", [False, True])
def test_trace_configuration_writes_only_trace_records_and_disables_cleanly(
    trace_logger: logging.Logger, tmp_path: Path, legacy_config: bool
) -> None:
    trace_file, ordinary_file = tmp_path / "trace.log", tmp_path / "ordinary.log"
    if legacy_config:
        config = {"log_file": {"trace_enable": True, "trace_path": str(trace_file)}}
    else:
        config = {"trace_log_enable": True, "trace_log_path": str(trace_file)}
    ordinary = logging.Logger("boundary.ordinary", level=logging.INFO)
    LogManager._ensure_logger_enricher_filter(ordinary)
    LogManager._ensure_logger_intercept_handler(ordinary)
    ordinary_sink = LogManager._add_file_sink(
        file_path=str(ordinary_file), level=logging.INFO, max_mb=None, backup_count=3
    )
    try:
        LogManager.configure_trace_logger(config)
        assert LogManager._trace_sink_id is not None
        assert trace_logger.level == logging.INFO
        assert trace_logger.propagate is False
        trace_logger.info("trace-enabled-marker")
        ordinary.info("ordinary-before-disable-marker")
        LogManager.configure_trace_logger({"trace_log_enable": False})
        assert LogManager._trace_sink_id is None
        trace_logger.info("trace-disabled-marker")
        ordinary.info("ordinary-after-disable-marker")
    finally:
        # Removing the real queued sink also flushes pending file writes.
        LogManager._remove_sink(ordinary_sink)
        for handler in ordinary.handlers:
            handler.close()
    trace_text = trace_file.read_text(encoding="utf-8")
    ordinary_text = ordinary_file.read_text(encoding="utf-8")
    assert trace_text.count("trace-enabled-marker") == 1
    assert "trace-disabled-marker" not in trace_text
    assert "ordinary-" not in trace_text
    assert "ordinary-before-disable-marker" in ordinary_text
    assert "ordinary-after-disable-marker" in ordinary_text
    assert "trace-" not in ordinary_text


@pytest.mark.parametrize("enabled_plugins", [None, [], ["allowed"]])
def test_tool_selection_preserves_unowned_schema_and_handoff_tools(
    monkeypatch: pytest.MonkeyPatch, enabled_plugins: list[str] | None
) -> None:
    owned: dict[str, FunctionTool] = {}
    for name in ("allowed", "excluded", "reserved"):
        module_path = f"boundary.plugins.{name}"
        monkeypatch.setitem(
            star_map,
            module_path,
            StarMetadata(
                name=name, module_path=module_path, reserved=name == "reserved"
            ),
        )
        owned[name] = FunctionTool(
            name=name, description=name, handler_module_path=module_path
        )
    schema = ToolSchema(name="schema_only", description="Schema without ownership")
    handoff = HandoffTool(Agent(name="delegate"))
    unresolved = FunctionTool(
        name="unknown_owner",
        description="Unregistered ownership",
        handler_module_path="boundary.unregistered.module",
    )
    tools = ToolSet(tools=[schema, *owned.values(), handoff, unresolved])
    original = tools.tools.copy()
    event = Mock(spec=AstrMessageEvent)
    event.plugins_name = enabled_plugins

    filtered = filter_tools(event, tools)

    if enabled_plugins is None:
        assert filtered is tools
        expected = original
    else:
        expected = [schema]
        if "allowed" in enabled_plugins:
            expected.append(owned["allowed"])
        expected.extend([owned["reserved"], handoff, unresolved])
        assert filtered is not tools
        assert owned["excluded"] not in filtered.tools
    assert len(filtered.tools) == len(expected)
    assert all(
        actual is wanted
        for actual, wanted in zip(filtered.tools, expected, strict=True)
    )
    assert all(
        actual is prior for actual, prior in zip(tools.tools, original, strict=True)
    )


@pytest.fixture
def view_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StarMetadata:
    root = tmp_path / "plugin"
    entry = root / "views" / "panel" / "index.html"
    entry.parent.mkdir(parents=True)
    entry.write_text("<p>Available view</p>", encoding="utf-8")
    module = ModuleType("boundary.view_plugin")
    module.__file__ = str(root / "main.py")
    plugin = StarMetadata(
        name="boundary-view",
        module_path=module.__name__,
        module=module,
        star_cls=Star.__new__(Star),
        views=[ViewSpec(name="panel", target="chat_message", version=2)],
    )
    monkeypatch.setitem(star_map, module.__name__, plugin)
    return plugin


@pytest.mark.parametrize(
    "missing", ["module", "filename_attribute", "none_filename", "empty_filename"]
)
def test_view_without_module_location_returns_controlled_unavailable(
    view_plugin: StarMetadata,
    missing: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert view_plugin.module is not None
    if missing == "module":
        view_plugin.module = None
    elif missing == "filename_attribute":
        del view_plugin.module.__file__
    elif missing == "none_filename":
        view_plugin.module.__file__ = None
    else:
        view_plugin.module.__file__ = ""
        unrelated_cwd = tmp_path / "plugin" / "unrelated"
        unrelated_cwd.mkdir()
        monkeypatch.chdir(unrelated_cwd)
    with pytest.raises(ViewError) as caught:
        resolve_view("boundary.view_plugin", "panel", 2, target="chat_message")
    assert caught.value.code == "VIEW_UNAVAILABLE"


@pytest.mark.parametrize("legacy_page", [False, True])
def test_view_location_resolution_preserves_current_and_legacy_entries(
    view_plugin: StarMetadata, tmp_path: Path, legacy_page: bool
) -> None:
    target = "plugin_page" if legacy_page else "chat_message"
    view_plugin.views = [ViewSpec(name="panel", target=target, version=2)]
    entry = tmp_path / "plugin" / "views" / "panel" / "index.html"
    if legacy_page:
        legacy_entry = tmp_path / "plugin" / "pages" / "panel" / "index.html"
        legacy_entry.parent.mkdir(parents=True)
        entry.replace(legacy_entry)
        entry = legacy_entry
    plugin, declaration, resolved = resolve_view(
        "boundary.view_plugin", "panel", 2, target=target
    )
    assert plugin is view_plugin
    assert declaration is view_plugin.views[0]
    assert resolved == entry.resolve()
    assert resolved.read_text(encoding="utf-8") == "<p>Available view</p>"
