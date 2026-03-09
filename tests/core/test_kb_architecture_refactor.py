import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.knowledge_base.index_rebuilder import IndexRebuilder
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.models import DocSection, KnowledgeBase
from astrbot.core.knowledge_base.structure_parser import StructureParser
from astrbot.core.provider.provider import EmbeddingProvider


class _FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(provider_config={"id": "test-ep", "type": "openai_embedding"}, provider_settings={})

    def get_dim(self) -> int:
        return 3

    async def get_embedding(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    async def get_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> list[list[float]]:
        if progress_callback:
            await progress_callback(len(texts), len(texts))
        return [[1.0, 0.0, 0.0] for _ in texts]


class _FakeProviderManager:
    def __init__(self, provider):
        self._provider = provider

    async def get_provider_by_id(self, provider_id: str):
        return self._provider


@pytest.mark.asyncio
async def test_structure_parser_uses_unambiguous_separator() -> None:
    parser = StructureParser()
    text = "# API/REST Design\n## Endpoint/Users\nContent"
    roots = await parser.parse_structure(text, "md")
    nodes = parser.flatten(roots)
    assert nodes[0].path == "API/REST Design"
    assert nodes[1].path == "API/REST Design > Endpoint/Users"


@pytest.mark.asyncio
async def test_index_rebuilder_progress_total_uses_filtered_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        def __init__(self, dimension: int, path: str) -> None:
            self.dimension = dimension
            self.path = path

        def get_all_ids(self) -> list[int]:
            return []

        async def delete(self, ids: list[int]) -> None:
            return None

        async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
            return None

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.index_rebuilder.EmbeddingStorage",
        _FakeStorage,
    )

    order: list[str] = []
    progress_records: list[tuple[str, int, int]] = []

    class _FakeDocStorage:
        async def get_all_int_ids(self) -> list[int]:
            return [1, 2]

        async def get_documents_by_int_ids(self, ids: list[int]) -> list[dict]:
            return [{"id": 1, "text": "valid text"}, {"id": 2, "text": None}]

    class _FakeVecDB:
        def __init__(self) -> None:
            self.document_storage = _FakeDocStorage()

        async def switch_index(self, **kwargs) -> None:
            order.append("switch")

    kb = SimpleNamespace(kb_id="kb-1", active_index_provider_id="old-provider")
    kb_helper = SimpleNamespace(
        kb=kb,
        kb_dir=tmp_path / "kb1",
        vec_db=_FakeVecDB(),
        get_embedding_provider_by_id=lambda provider_id: asyncio.sleep(
            0,
            result=_FakeEmbeddingProvider(),
        ),
        get_rp=lambda: asyncio.sleep(0, result=None),
    )

    async def _persist_kb() -> None:
        order.append("persist")

    kb_helper.persist_kb = _persist_kb

    rebuilder = IndexRebuilder()
    await rebuilder.sync(
        kb_helper=kb_helper,
        new_provider_id="new-provider",
        progress_callback=lambda s, c, t: asyncio.sleep(
            0,
            result=progress_records.append((s, c, t)),
        ),
    )

    assert order == ["switch", "persist"]
    assert kb.active_index_provider_id == "new-provider"
    assert progress_records[0] == ("prepare", 0, 1)
    assert progress_records[-1] == ("finished", 1, 1)


@pytest.mark.asyncio
async def test_index_rebuilder_does_not_persist_if_switch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        def __init__(self, dimension: int, path: str) -> None:
            self.dimension = dimension
            self.path = path

        def get_all_ids(self) -> list[int]:
            return []

        async def delete(self, ids: list[int]) -> None:
            return None

        async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
            return None

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.index_rebuilder.EmbeddingStorage",
        _FakeStorage,
    )

    class _FakeDocStorage:
        async def get_all_int_ids(self) -> list[int]:
            return [1]

        async def get_documents_by_int_ids(self, ids: list[int]) -> list[dict]:
            return [{"id": 1, "text": "valid text"}]

    class _FakeVecDB:
        def __init__(self) -> None:
            self.document_storage = _FakeDocStorage()

        async def switch_index(self, **kwargs) -> None:
            raise RuntimeError("switch failed")

    persisted = False
    kb = SimpleNamespace(kb_id="kb-2", active_index_provider_id="old-provider")
    kb_helper = SimpleNamespace(
        kb=kb,
        kb_dir=tmp_path / "kb2",
        vec_db=_FakeVecDB(),
        get_embedding_provider_by_id=lambda provider_id: asyncio.sleep(
            0,
            result=_FakeEmbeddingProvider(),
        ),
        get_rp=lambda: asyncio.sleep(0, result=None),
    )

    async def _persist_kb() -> None:
        nonlocal persisted
        persisted = True

    kb_helper.persist_kb = _persist_kb

    rebuilder = IndexRebuilder()
    with pytest.raises(RuntimeError):
        await rebuilder.sync(kb_helper=kb_helper, new_provider_id="new-provider")

    assert persisted is False
    assert kb.active_index_provider_id == "old-provider"


@pytest.mark.asyncio
async def test_kb_db_upsert_doc_section_and_deterministic_contains(
    tmp_path: Path,
) -> None:
    db = KBSQLiteDatabase((tmp_path / "kb.db").as_posix())
    await db.initialize()

    section_id = "sec-fixed"
    section_1 = DocSection(
        section_id=section_id,
        doc_id="doc-1",
        kb_id="kb-1",
        section_path="Guide > API",
        section_level=1,
        section_title="API",
        section_body="old body",
        sort_order=0,
    )
    await db.upsert_doc_section(section_1)
    section_2 = DocSection(
        section_id=section_id,
        doc_id="doc-1",
        kb_id="kb-1",
        section_path="Guide > API",
        section_level=1,
        section_title="API",
        section_body="new body",
        sort_order=0,
    )
    await db.upsert_doc_section(section_2)

    fetched = await db.get_doc_section("kb-1", "doc-1", "Guide > API")
    assert fetched is not None
    assert fetched.section_body == "new body"

    now = datetime.now(timezone.utc)
    s3 = DocSection(
        section_id="sec-a",
        doc_id="doc-2",
        kb_id="kb-1",
        section_path="prefix A% path 1",
        section_level=1,
        section_title="A1",
        section_body="body 1",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    s4 = DocSection(
        section_id="sec-b",
        doc_id="doc-2",
        kb_id="kb-1",
        section_path="prefix A% path 2",
        section_level=1,
        section_title="A2",
        section_body="body 2",
        sort_order=1,
        created_at=now + timedelta(seconds=1),
        updated_at=now + timedelta(seconds=1),
    )
    await db.upsert_doc_section(s3)
    await db.upsert_doc_section(s4)

    contains_result = await db.get_doc_section("kb-1", "doc-2", "A%")
    assert contains_result is not None
    assert contains_result.section_path == "prefix A% path 1"

    await db.close()


@pytest.mark.asyncio
async def test_faiss_vecdb_switch_index_lock_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeStorage:
        def __init__(self, dimension: int, path: str) -> None:
            self.dimension = dimension
            self.path = path
            self.closed = False

        async def close(self) -> None:
            self.closed = True

        async def search(self, vector: np.ndarray, k: int):
            return np.array([[0.0]], dtype=np.float32), np.array([[-1]], dtype=np.int64)

    monkeypatch.setattr(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.EmbeddingStorage",
        _FakeStorage,
    )

    db = FaissVecDB.__new__(FaissVecDB)
    db._index_switch_lock = asyncio.Lock()
    db.embedding_provider = _FakeEmbeddingProvider()
    db.rerank_provider = None
    db.document_storage = SimpleNamespace(
        get_documents=lambda **kwargs: asyncio.sleep(0, result=[]),
    )
    old_storage = _FakeStorage(3, "old.faiss")
    db.embedding_storage = old_storage

    provider = _FakeEmbeddingProvider()
    await db._index_switch_lock.acquire()
    switch_task = asyncio.create_task(
        db.switch_index("new.faiss", provider, None),
    )
    await asyncio.sleep(0.05)
    assert not switch_task.done()
    db._index_switch_lock.release()
    await switch_task
    assert old_storage.closed is True

    await db._index_switch_lock.acquire()
    retrieve_task = asyncio.create_task(db.retrieve("q"))
    await asyncio.sleep(0.05)
    assert not retrieve_task.done()
    db._index_switch_lock.release()
    result = await retrieve_task
    assert result == []


@pytest.mark.asyncio
async def test_kb_helper_structured_upload_progress_order(tmp_path: Path) -> None:
    kb_db = KBSQLiteDatabase((tmp_path / "kb_meta.db").as_posix())
    await kb_db.initialize()
    await kb_db.migrate_to_v1()
    await kb_db.migrate_to_v2(tmp_path.as_posix())
    await kb_db.migrate_to_v3()

    provider = _FakeEmbeddingProvider()
    kb = KnowledgeBase(
        kb_name="kb-test",
        embedding_provider_id="ep-1",
        active_index_provider_id="ep-1",
        default_index_mode="structure",
    )
    async with kb_db.get_db() as session:
        session.add(kb)
        await session.commit()

    helper = KBHelper(
        kb_db=kb_db,
        kb=kb,
        provider_manager=_FakeProviderManager(provider),  # type: ignore[arg-type]
        kb_root_dir=tmp_path.as_posix(),
        chunker=SimpleNamespace(chunk=lambda *args, **kwargs: asyncio.sleep(0, result=[])),
    )
    await helper.initialize()

    records: list[tuple[str, int, int]] = []

    async def _progress(stage: str, current: int, total: int) -> None:
        records.append((stage, current, total))

    doc = await helper.upload_document(
        file_name="test.md",
        file_content=b"# H1\n## H2\nbody",
        file_type="md",
        index_mode="structure",
        progress_callback=_progress,
    )
    assert doc.index_mode == "structure"
    first_chunking_done_idx = records.index(("chunking", 100, 100))
    first_embedding_idx = next(i for i, r in enumerate(records) if r[0] == "embedding")
    assert first_chunking_done_idx < first_embedding_idx

    await helper.terminate()
    await kb_db.close()


@pytest.mark.asyncio
async def test_kb_manager_rebuild_task_tracking_and_terminate_cancel() -> None:
    mgr = KnowledgeBaseManager(provider_manager=MagicMock())
    fake_helper = SimpleNamespace(last_rebuild_task_id=None)

    async def _get_kb(_kb_id: str):
        return fake_helper

    mgr.get_kb = _get_kb  # type: ignore[method-assign]
    gate = asyncio.Event()

    async def _sync(**kwargs):
        await gate.wait()

    mgr.index_rebuilder.sync = _sync  # type: ignore[method-assign]
    task_id = await mgr.start_rebuild_index("kb-id", "provider-id")
    assert task_id in mgr._running_rebuild_tasks

    task_obj = mgr._running_rebuild_tasks[task_id]
    await mgr.terminate()
    await asyncio.sleep(0)
    assert task_obj.cancelled() or task_obj.done()
    assert task_id not in mgr._running_rebuild_tasks

    assert mgr._validate_index_mode("flat") == "flat"
    with pytest.raises(ValueError):
        mgr._validate_index_mode("invalid")
