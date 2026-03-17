import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBDocument, KBMedia, KnowledgeBase
from astrbot.core.knowledge_base.package_io import (
    KnowledgeBasePackageExporter,
    KnowledgeBasePackageImporter,
)
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self, provider_id: str, dimensions: int, model: str = "bge-m3"
    ) -> None:
        provider_config = {
            "id": provider_id,
            "type": "openai_embedding",
            "embedding_model": model,
        }
        super().__init__(provider_config, {})
        self.model = model
        self._dimensions = dimensions

    async def get_embedding(self, text: str) -> list[float]:
        return [0.0] * self._dimensions

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.0] * self._dimensions for _ in text]

    def get_dim(self) -> int:
        return self._dimensions

    def get_model(self) -> str:
        return self.model


class FakeRerankProvider(RerankProvider):
    def __init__(self, provider_id: str, model: str = "bge-reranker") -> None:
        provider_config = {
            "id": provider_id,
            "type": "bailian_rerank",
            "rerank_model": model,
        }
        super().__init__(provider_config, {})
        self.model = model

    async def rerank(self, query: str, documents: list[str]):
        return []

    def get_model(self) -> str:
        return self.model


class FakeKnowledgeBaseManager:
    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        source_helper: SimpleNamespace,
        temp_root: Path,
        embedding_provider: FakeEmbeddingProvider,
        rerank_provider: FakeRerankProvider,
    ) -> None:
        self.kb_db = kb_db
        self._source_helper = source_helper
        self._temp_root = temp_root
        self.provider_manager = SimpleNamespace(
            embedding_provider_insts=[embedding_provider],
            rerank_provider_insts=[rerank_provider],
            get_provider_by_id=AsyncMock(
                side_effect=lambda provider_id: {
                    embedding_provider.provider_config["id"]: embedding_provider,
                    rerank_provider.provider_config["id"]: rerank_provider,
                }.get(provider_id)
            ),
        )
        self.kb_insts = {source_helper.kb.kb_id: source_helper}

    async def get_kb(self, kb_id: str):
        return self.kb_insts.get(kb_id)

    async def get_kb_by_name(self, kb_name: str):
        for helper in self.kb_insts.values():
            if helper.kb.kb_name == kb_name:
                return helper
        return None

    async def create_kb(
        self,
        kb_name: str,
        description: str | None = None,
        emoji: str | None = None,
        embedding_provider_id: str | None = None,
        rerank_provider_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k_dense: int | None = None,
        top_k_sparse: int | None = None,
        top_m_final: int | None = None,
    ):
        kb = KnowledgeBase(
            kb_name=kb_name,
            description=description,
            emoji=emoji,
            embedding_provider_id=embedding_provider_id,
            rerank_provider_id=rerank_provider_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k_dense=top_k_dense,
            top_k_sparse=top_k_sparse,
            top_m_final=top_m_final,
        )
        async with self.kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

        kb_dir = self._temp_root / kb.kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        helper = SimpleNamespace(
            kb=kb,
            kb_dir=kb_dir,
            terminate=AsyncMock(),
            initialize=AsyncMock(),
            refresh_kb=AsyncMock(),
            vec_db=SimpleNamespace(count_documents=AsyncMock(return_value=1)),
        )
        self.kb_insts[kb.kb_id] = helper
        return helper

    async def delete_kb(self, kb_id: str) -> bool:
        self.kb_insts.pop(kb_id, None)
        return True


@pytest_asyncio.fixture
async def kb_package_fixture(tmp_path):
    kb_root = tmp_path / "knowledge_base"
    kb_root.mkdir()
    kb_db = KBSQLiteDatabase((kb_root / "kb.db").as_posix())
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    kb = KnowledgeBase(
        kb_name="Source KB",
        emoji="📚",
        embedding_provider_id="embedding-source",
        rerank_provider_id="rerank-source",
        chunk_size=256,
        chunk_overlap=32,
        top_k_dense=8,
        top_k_sparse=6,
        top_m_final=4,
        doc_count=1,
        chunk_count=1,
    )
    async with kb_db.get_db() as session:
        session.add(kb)
        await session.commit()
        await session.refresh(kb)

        document = KBDocument(
            kb_id=kb.kb_id,
            doc_name="source.txt",
            file_type="txt",
            file_size=12,
            file_path="",
            chunk_count=1,
            media_count=1,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

        media = KBMedia(
            doc_id=document.doc_id,
            kb_id=kb.kb_id,
            media_type="image",
            file_name="figure.png",
            file_path=f"/tmp/{kb.kb_id}/medias/{kb.kb_id}/figure.png",
            file_size=4,
            mime_type="image/png",
        )
        session.add(media)
        await session.commit()
        await session.refresh(media)

    kb_dir = kb_root / kb.kb_id
    media_dir = kb_dir / "medias" / kb.kb_id
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "figure.png").write_bytes(b"PNG")
    (kb_dir / "index.faiss").write_bytes(b"FAISS")

    connection = sqlite3.connect(kb_dir / "doc.db")
    connection.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT,
            text TEXT,
            metadata TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    metadata = json.dumps(
        {
            "kb_id": kb.kb_id,
            "kb_doc_id": document.doc_id,
            "chunk_index": 0,
        },
        ensure_ascii=False,
    )
    connection.execute(
        """
        INSERT INTO documents (doc_id, text, metadata, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "chunk-1",
            "hello world",
            metadata,
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    embedding_provider = FakeEmbeddingProvider("embedding-local", 1024)
    rerank_provider = FakeRerankProvider("rerank-local")

    helper = SimpleNamespace(
        kb=kb,
        kb_dir=kb_dir,
        get_ep=AsyncMock(return_value=FakeEmbeddingProvider("embedding-source", 1024)),
        get_rp=AsyncMock(return_value=FakeRerankProvider("rerank-source")),
    )
    manager = FakeKnowledgeBaseManager(
        kb_db=kb_db,
        source_helper=helper,
        temp_root=kb_root,
        embedding_provider=embedding_provider,
        rerank_provider=rerank_provider,
    )
    return {
        "kb_db": kb_db,
        "kb": kb,
        "document": document,
        "manager": manager,
        "kb_root": kb_root,
    }


@pytest.mark.asyncio
async def test_export_kb_package_creates_expected_zip(kb_package_fixture, tmp_path):
    exporter = KnowledgeBasePackageExporter(kb_package_fixture["manager"])
    zip_path = await exporter.export_kb(
        kb_id=kb_package_fixture["kb"].kb_id,
        output_dir=tmp_path.as_posix(),
    )

    assert Path(zip_path).exists()

    with Path(zip_path).open("rb"):
        pass

    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "kb_metadata.json" in names
        assert "runtime/doc.db" in names
        assert "runtime/index.faiss" in names
        assert any(name.endswith("figure.png") for name in names)

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["knowledge_base"]["kb_name"] == "Source KB"
        assert manifest["statistics"]["documents"] == 1
        assert manifest["providers"]["embedding"]["dimensions"] == 1024


@pytest.mark.asyncio
async def test_import_kb_package_rewrites_metadata(kb_package_fixture, tmp_path):
    exporter = KnowledgeBasePackageExporter(kb_package_fixture["manager"])
    zip_path = await exporter.export_kb(
        kb_id=kb_package_fixture["kb"].kb_id,
        output_dir=tmp_path.as_posix(),
    )

    importer = KnowledgeBasePackageImporter(kb_package_fixture["manager"])
    check_result = importer.pre_check(zip_path)
    assert check_result.valid is True
    assert (
        check_result.local_provider_matches["embedding"]["preselected_provider_id"]
        == "embedding-local"
    )

    imported_kb = await importer.import_kb(
        zip_path=zip_path,
        kb_name="Source KB (Imported)",
        embedding_provider_id="embedding-local",
        rerank_provider_id="rerank-local",
    )

    assert imported_kb.kb_id != kb_package_fixture["kb"].kb_id
    assert imported_kb.kb_name == "Source KB (Imported)"

    async with kb_package_fixture["kb_db"].get_db() as session:
        documents = list(
            (
                await session.execute(
                    select(KBDocument).where(KBDocument.kb_id == imported_kb.kb_id)
                )
            ).scalars()
        )
        media = list(
            (
                await session.execute(
                    select(KBMedia).where(KBMedia.kb_id == imported_kb.kb_id)
                )
            ).scalars()
        )

    assert len(documents) == 1
    assert len(media) == 1
    assert documents[0].doc_id != kb_package_fixture["document"].doc_id
    assert media[0].doc_id == documents[0].doc_id

    connection = sqlite3.connect(
        kb_package_fixture["kb_root"] / imported_kb.kb_id / "doc.db"
    )
    metadata_raw = connection.execute("SELECT metadata FROM documents").fetchone()[0]
    connection.close()

    metadata = json.loads(metadata_raw)
    assert metadata["kb_id"] == imported_kb.kb_id
    assert metadata["kb_doc_id"] == documents[0].doc_id
