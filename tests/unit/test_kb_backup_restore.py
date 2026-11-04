import json
import shutil
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB


@pytest.mark.asyncio
async def test_kb_restore_preserves_sparse_document_ids_and_retrieval(tmp_path):
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    vectors = {
        "alpha": [1.0, 0.0],
        "bravo": [0.5, 0.5],
        "charlie": [0.0, 1.0],
        "delta": [-1.0, 0.0],
    }
    provider = MagicMock()
    provider.get_dim.return_value = 2
    provider.get_embedding = AsyncMock(side_effect=lambda content: vectors[content])
    original = FaissVecDB(
        str(original_dir / "doc.db"), str(original_dir / "index.faiss"), provider
    )
    await original.initialize()
    try:
        for content in ("alpha", "bravo", "charlie"):
            await original.insert(content, id=content)
        await original.delete("bravo")
        documents = await original.document_storage.get_documents({})
        assert [(doc["id"], doc["doc_id"]) for doc in documents] == [
            (1, "alpha"),
            (3, "charlie"),
        ]
        backup_data = json.loads(json.dumps({"documents": documents[::-1]}))
    finally:
        await original.close()

    restored_root = tmp_path / "restored"
    restored_dir = restored_root / "kb1"
    restored_dir.mkdir(parents=True)
    importer = AstrBotImporter(main_db=MagicMock(), kb_root_dir=str(restored_root))
    await importer._import_kb_documents("kb1", backup_data)
    shutil.copyfile(original_dir / "index.faiss", restored_dir / "index.faiss")

    restored = FaissVecDB(
        str(restored_dir / "doc.db"), str(restored_dir / "index.faiss"), provider
    )
    await restored.initialize()
    try:
        restored_documents = await restored.document_storage.get_documents({})
        assert {doc["doc_id"]: doc["id"] for doc in restored_documents} == {
            "alpha": 1,
            "charlie": 3,
        }
        results = await restored.retrieve("charlie", k=1)
        assert [result.data["doc_id"] for result in results] == ["charlie"]
        sparse_results = await restored.document_storage.search_sparse(
            ["charlie"], limit=1
        )
        assert sparse_results is not None
        assert [(doc["id"], doc["doc_id"]) for doc in sparse_results] == [
            (3, "charlie")
        ]

        assert await restored.insert("delta", id="delta") == 4
        results = await restored.retrieve("charlie", k=1)
        assert [result.data["doc_id"] for result in results] == ["charlie"]
    finally:
        await restored.close()

    reopened = FaissVecDB(
        str(restored_dir / "doc.db"), str(restored_dir / "index.faiss"), provider
    )
    await reopened.initialize()
    try:
        results = await reopened.retrieve("charlie", k=1)
        assert [result.data["doc_id"] for result in results] == ["charlie"]
        results = await reopened.retrieve("delta", k=1)
        assert [result.data["doc_id"] for result in results] == ["delta"]
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_kb_restore_without_integer_ids_uses_auto_increment(tmp_path):
    kb_dir = tmp_path / "kb1"
    kb_dir.mkdir()
    importer = AstrBotImporter(main_db=MagicMock(), kb_root_dir=str(tmp_path))
    await importer._import_kb_documents(
        "kb1",
        {
            "documents": [
                {"doc_id": "legacy", "text": "legacy document", "metadata": "{}"}
            ]
        },
    )

    storage = DocumentStorage(str(kb_dir / "doc.db"))
    await storage.initialize()
    try:
        document = await storage.get_document_by_doc_id("legacy")
        assert document is not None
        assert document["id"] == 1
        assert await storage.insert_document("new", "new document", {}) == 2
    finally:
        await storage.close()
