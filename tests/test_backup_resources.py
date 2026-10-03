"""Regression coverage for backup resource limits and task exclusion."""

import asyncio
import io
import json
import threading
import tracemalloc
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import ijson
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrbot.core.backup import resources
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import (
    AstrBotImporter,
    DatabaseClearError,
    ImportResult,
)
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import Attachment, ConversationV2, Persona
from astrbot.core.knowledge_base.models import KnowledgeBase
from astrbot.dashboard.services.backup_service import BackupService, BackupServiceError


@pytest.mark.parametrize("backend_name", sorted({"python", ijson.backend}))
def test_large_database_stream_has_bounded_memory(tmp_path, monkeypatch, backend_name):
    monkeypatch.setattr(
        resources.ijson,
        "basic_parse_coro",
        ijson.get_backend(backend_name).basic_parse_coro,
    )
    path = tmp_path / "large.zip"
    row = json.dumps({"content": "x" * 8192}).encode()
    count = 4200
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        with archive.open("databases/main_db.json", "w") as dest:
            dest.write(b'{"conversations":[')
            for index in range(count):
                if index:
                    dest.write(b",")
                dest.write(row)
            dest.write(b"]}")
    with resources.open_backup(path) as archive:
        assert archive.getinfo("databases/main_db.json").file_size > 32 * 1024 * 1024
        tracemalloc.start()
        try:
            data = resources.read_backup_json(archive, "databases/main_db.json")
            assert isinstance(data, resources.BackupTableStream)
            assert sum(1 for _ in data.get("conversations")) == count
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < 8 * 1024 * 1024


@pytest.mark.parametrize(
    "name,limit",
    [
        ("databases/main_db.json", "MAX_DATABASE_JSON_BYTES"),
        ("databases/kb_metadata.json", "MAX_DATABASE_JSON_BYTES"),
        ("databases/kb_test/documents.json", "MAX_KB_DOCUMENT_JSON_BYTES"),
    ],
)
def test_streaming_entries_use_their_own_limits(tmp_path, monkeypatch, name, limit):
    path = tmp_path / "typed.zip"
    content = json.dumps({"documents": [{"text": "x" * 100}]})
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, content)
    monkeypatch.setattr(resources, "MAX_JSON_BYTES", 16)
    monkeypatch.setattr(resources, limit, 1024)
    with resources.open_backup(path) as archive:
        data = resources.read_backup_json(archive, name)
        assert list(data.get("documents")) == [{"text": "x" * 100}]
        monkeypatch.setattr(resources, limit, 32)
        with pytest.raises(ValueError, match="size limit"):
            resources.read_backup_json(archive, name)


def test_record_scanner_handles_escapes_and_utf8_across_chunks():
    data = {"rows": [{"text": '汉字😀\\"[]{}\\\\end', "nested": {"x": [1, 2]}}]}
    source = io.BytesIO(json.dumps(data, ensure_ascii=False).encode())
    reader = resources._RecordLimitedReader(source)
    assert list(ijson.items(reader, "rows.item", buf_size=3)) == data["rows"]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_name", sorted({"python", ijson.backend}))
@pytest.mark.parametrize("case", ["string", "record", "depth", "scalar", "truncated"])
async def test_bad_stream_fails_before_any_database_write(
    tmp_path, monkeypatch, case, backend_name
):
    monkeypatch.setattr(
        resources.ijson,
        "basic_parse_coro",
        ijson.get_backend(backend_name).basic_parse_coro,
    )
    path = tmp_path / "bad.zip"
    if case == "string":
        payload = b'{"conversations":[{"text":"' + b"x" * 2048
        monkeypatch.setattr(resources, "MAX_JSON_RECORD_BYTES", 256)
    elif case == "record":
        payload = json.dumps(
            {"conversations": [{str(i): "x" * 30 for i in range(30)}]}
        ).encode()
        monkeypatch.setattr(resources, "MAX_JSON_RECORD_BYTES", 256)
    elif case == "depth":
        payload = b'{"conversations":[{"text":' + b"[" * 80 + b"0" + b"]" * 80 + b"}]}"
    elif case == "scalar":
        payload = b'{"conversations":' + b"1" * 2048
        monkeypatch.setattr(resources, "MAX_JSON_RECORD_BYTES", 256)
    else:
        good = {"conversation_id": "one", "platform_id": "p", "user_id": "u"}
        payload = b'{"conversations":[' + json.dumps(good).encode() + b","
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        archive.writestr("databases/main_db.json", payload)
    db = MagicMock()
    result = await AstrBotImporter(db).import_all(str(path), components=["database"])
    assert not result.success
    db.get_db.assert_not_called()
    if case != "truncated":
        assert any("limit" in error for error in result.errors)


def test_row_batches_are_limited_by_bytes_as_well_as_count(monkeypatch):
    monkeypatch.setattr(resources, "MAX_JSON_RECORD_BYTES", 128)
    rows = [{"text": "x" * 70} for _ in range(3)]
    batches = list(resources.backup_row_batches(iter(rows)))
    assert [len(batch) for batch in batches] == [1, 1, 1]
    assert [row for batch in batches for row in batch] == rows


def test_streamed_statistics_merge_matches_legacy_merge():
    rows = [
        {
            "id": 1,
            "timestamp": "2025-01-01T00:00:00Z",
            "platform_id": "p",
            "platform_type": "web",
            "count": 2,
        },
        {
            "id": 2,
            "timestamp": "2025-01-02T00:00:00Z",
            "platform_id": "p",
            "platform_type": "web",
            "count": "3",
        },
        {
            "id": 3,
            "timestamp": "2025-01-01T00:00:00+00:00",
            "platform_id": "p",
            "platform_type": "web",
            "count": 4,
        },
        {
            "id": 4,
            "timestamp": "",
            "platform_id": "p",
            "platform_type": "web",
            "count": 1,
        },
        {
            "id": 5,
            "timestamp": "",
            "platform_id": "p",
            "platform_type": "web",
            "count": 1,
        },
    ]
    importer = AstrBotImporter(MagicMock())
    assert list(
        importer._preprocess_main_table_rows("platform_stats", iter(rows))
    ) == importer._merge_platform_stats_rows(rows)


@pytest.mark.asyncio
async def test_streamed_export_restore_roundtrip(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    db = SimpleNamespace(get_db=sessions)
    models = {"conversations": ConversationV2}
    monkeypatch.setattr("astrbot.core.backup.exporter.MAIN_DB_MODELS", models)
    monkeypatch.setattr("astrbot.core.backup.importer.MAIN_DB_MODELS", models)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ConversationV2.__table__.create)
        async with sessions.begin() as session:
            session.add_all(
                ConversationV2(
                    conversation_id=str(i),
                    platform_id="p",
                    user_id="u",
                    content=[{"role": "user", "content": "汉字😀"}],
                )
                for i in range(1001)
            )
        exporter = AstrBotExporter(db)
        path = await exporter.export_all(str(tmp_path), components=["database"])
        async with sessions.begin() as session:
            await session.execute(ConversationV2.__table__.delete())
        result = await AstrBotImporter(db).import_all(path, components=["database"])
        assert result.success, result.errors
        assert result.imported_tables["conversations"] == 1001
        async with sessions() as session:
            records = (await session.execute(select(ConversationV2))).scalars().all()
            assert len(records) == 1001
            assert records[0].content == [{"role": "user", "content": "汉字😀"}]
    finally:
        await engine.dispose()


@pytest.mark.parametrize("limit", ["MAX_DIRECTORY_BYTES", "MAX_ENTRIES"])
def test_directory_limit_checked_before_zip_allocation(tmp_path, monkeypatch, limit):
    path = tmp_path / "backup.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
    monkeypatch.setattr(resources, limit, 0)
    parse = MagicMock(side_effect=AssertionError("ZIP metadata must not be allocated"))
    monkeypatch.setattr(zipfile.ZipFile, "_RealGetContents", parse)
    with pytest.raises(ValueError, match="directory"):
        with resources.open_backup(path):
            pass
    parse.assert_not_called()


def test_json_read_is_bounded_even_with_incorrect_size(monkeypatch):
    monkeypatch.setattr(resources, "MAX_JSON_BYTES", 64)
    archive = MagicMock()
    archive.getinfo.return_value.file_size = 0
    source = io.BytesIO(b" " * 65)
    archive.open.return_value = source
    with pytest.raises(ValueError, match="size limit"):
        resources.read_backup_json(archive, "config/cmd_config.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["manifest", "entry", "expanded"])
async def test_resource_limits_fail_before_restore(tmp_path, monkeypatch, limit):
    path = tmp_path / "backup.zip"
    config = tmp_path / "config.json"
    config.write_text('{"old": true}')
    manifest = {"version": "1.1", "astrbot_version": VERSION}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("databases/main_db.json", '{"conversations": []}')
        archive.writestr("config/cmd_config.json", '{"new": true}')
    if limit == "manifest":
        monkeypatch.setattr(resources, "MAX_MANIFEST_BYTES", 8)
    elif limit == "entry":
        monkeypatch.setattr(resources, "MAX_DATABASE_JSON_BYTES", 8)
    else:
        monkeypatch.setattr(resources, "MAX_EXTRACTED_BYTES", 8)
    db = MagicMock()
    importer = AstrBotImporter(db, config_path=str(config))
    result = await importer.import_all(str(path))
    assert not result.success
    assert any("limit" in error for error in result.errors)
    db.get_db.assert_not_called()
    assert config.read_text() == '{"old": true}'


def test_manifest_limit_applies_to_listing_and_precheck(tmp_path, monkeypatch):
    path = tmp_path / "backup.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"padding": "x" * 1000}))
    monkeypatch.setattr(resources, "MAX_MANIFEST_BYTES", 100)
    service = BackupService(MagicMock(), MagicMock())
    assert service.get_backup_manifest(str(path)) is None
    check = AstrBotImporter(MagicMock()).pre_check(str(path))
    assert not check.can_import
    assert "size limit" in check.error


@pytest.mark.asyncio
async def test_attachment_hints_do_not_read_oversized_unselected_database(
    tmp_path, monkeypatch
):
    path = tmp_path / "backup.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        archive.writestr("databases/main_db.json", json.dumps({"padding": "x" * 1000}))
        archive.writestr("files/attachments/test.txt", "attachment")
    monkeypatch.setattr(resources, "MAX_DATABASE_JSON_BYTES", 100)
    importer = AstrBotImporter(MagicMock())
    importer._import_attachments = AsyncMock(return_value=1)
    result = await importer.import_all(str(path), components=["attachments"])
    assert result.success
    assert any("path hints skipped" in warning for warning in result.warnings)
    assert importer._import_attachments.call_args.args[1] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["import", "export"])
@pytest.mark.parametrize("status", ["pending", "processing"])
async def test_busy_task_rejects_both_operations(tmp_path, first, status):
    service = BackupService(MagicMock(), MagicMock())
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").touch()
    service._init_task("active", first, status)
    with pytest.raises(BackupServiceError, match="正在运行"):
        service.export_backup()
    with pytest.raises(BackupServiceError, match="正在运行"):
        service.import_backup({"filename": "backup.zip", "confirmed": True})
    assert list(service.backup_tasks) == ["active"]
    service._set_task_result("active", "failed")
    service._init_task("next", "export")
    assert service.backup_tasks["next"]["status"] == "pending"


@pytest.mark.asyncio
async def test_export_worker_yields_and_cancellation_waits_for_writer(tmp_path):
    exporter = AstrBotExporter(MagicMock())
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    path = tmp_path / "output.zip"

    def write(archive):
        entered.set()
        assert release.wait(5)
        archive.writestr("entry", "complete")
        finished.set()

    with zipfile.ZipFile(path, "w") as archive:
        task = asyncio.create_task(exporter._run_io(write, archive))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert finished.is_set()
    with zipfile.ZipFile(path) as archive:
        assert archive.read("entry") == b"complete"


@pytest.mark.asyncio
async def test_export_json_limit_removes_partial_archive(tmp_path, monkeypatch):
    exporter = AstrBotExporter(MagicMock())
    exporter._export_main_database = AsyncMock(
        return_value={"conversations": [{"data": "x" * 100}]}
    )
    monkeypatch.setattr(resources, "MAX_DATABASE_JSON_BYTES", 50)
    with pytest.raises(ValueError, match="size limit"):
        await exporter.export_all(str(tmp_path), components=["database"])
    assert list(tmp_path.glob("*.zip")) == []


@pytest.mark.asyncio
async def test_export_archive_limit_removes_unrestorable_backup(tmp_path, monkeypatch):
    exporter = AstrBotExporter(MagicMock())
    exporter._export_main_database = AsyncMock(return_value={"conversations": []})
    monkeypatch.setattr(resources, "MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="resource limit"):
        await exporter.export_all(str(tmp_path), components=["database"])
    assert list(tmp_path.glob("*.zip")) == []


@pytest.mark.asyncio
async def test_batched_flush_preserves_whole_restore_transaction(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ConversationV2.__table__.create)
        async with sessions.begin() as session:
            session.add(
                ConversationV2(conversation_id="old", platform_id="p", user_id="u")
            )
        monkeypatch.setattr(
            "astrbot.core.backup.importer.MAIN_DB_MODELS",
            {"conversations": ConversationV2},
        )
        session = sessions()
        counts = []
        event.listen(
            session.sync_session,
            "before_flush",
            lambda current, *_: counts.append(len(current.new)),
        )
        importer = AstrBotImporter(SimpleNamespace(get_db=lambda: session))
        rows = [
            {"conversation_id": str(i), "platform_id": "p", "user_id": "u"}
            for i in range(501)
        ]
        rows.append(rows[0].copy())
        with pytest.raises(IntegrityError):
            await importer._import_main_database({"conversations": rows}, clear=True)
        assert counts == [500, 2]
        async with sessions() as session:
            ids = (
                (await session.execute(select(ConversationV2.conversation_id)))
                .scalars()
                .all()
            )
            assert ids == ["old"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_export_streams_rows_and_converts_off_loop(
    tmp_path, monkeypatch
):
    def reject_orm_json(raw):
        raise AssertionError("JSON must not be decoded by the ORM on the event loop")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'export.sqlite'}",
        json_deserializer=reject_orm_json,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    exporter = AstrBotExporter(MagicMock())
    convert = exporter._model_to_dict
    thread_ids = set()
    decode_threads = set()
    loads = json.loads

    def track_decode(raw, *args, **kwargs):
        if (isinstance(raw, str) and "export-thread" in raw) or (
            isinstance(raw, bytes) and b"export-thread" in raw
        ):
            decode_threads.add(threading.get_ident())
        return loads(raw, *args, **kwargs)

    monkeypatch.setattr(json, "loads", track_decode)
    monkeypatch.setattr("astrbot.core.backup.exporter.MAX_JSON_RECORD_BYTES", 4096)

    def track_conversion(record):
        thread_ids.add(threading.get_ident())
        return convert(record)

    exporter._model_to_dict = track_conversion
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ConversationV2.__table__.create)
        async with sessions.begin() as session:
            session.add_all(
                ConversationV2(
                    conversation_id=str(i),
                    platform_id="p",
                    user_id="u",
                    content=[{"marker": "export-thread", "text": "x" * 500}],
                )
                for i in range(1001)
            )
        batches = [
            batch
            async for batch in exporter._export_records(
                sessions, ConversationV2, exporter._model_to_dict
            )
        ]
        rows = [row for batch in batches for row in batch]
        assert max(map(len, batches)) < 500
        assert {row["conversation_id"] for row in rows} == {str(i) for i in range(1001)}
        assert thread_ids
        assert threading.get_ident() not in thread_ids
        assert decode_threads and threading.get_ident() not in decode_threads
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kb_document_restore_uses_bounded_batches(tmp_path, monkeypatch):
    storage = MagicMock()
    storage.initialize = AsyncMock()
    storage.insert_documents_batch = AsyncMock()
    storage.close = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.db.vec_db.faiss_impl.document_storage.DocumentStorage",
        MagicMock(return_value=storage),
    )
    importer = AstrBotImporter(MagicMock())
    importer.kb_root_dir = str(tmp_path)
    documents = [
        {"doc_id": str(i), "text": "text", "metadata": "{}"} for i in range(1001)
    ]
    await importer._import_kb_documents("kb", {"documents": documents})
    assert [
        len(call.kwargs["doc_ids"])
        for call in storage.insert_documents_batch.await_args_list
    ] == [500, 500, 1]
    storage.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_streamed_kb_documents_preserve_text_and_metadata(tmp_path):
    from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage

    source = DocumentStorage(str(tmp_path / "source.sqlite"))
    restored = None
    try:
        await source.initialize()
        await source.insert_documents_batch(
            doc_ids=["one", "two"],
            texts=["汉字😀\x00tail", "second"],
            metadatas=[{"source": "文档"}, {"n": 2}],
        )
        exporter = AstrBotExporter(MagicMock())
        helper = SimpleNamespace(vec_db=SimpleNamespace(document_storage=source))
        data = await exporter._export_kb_documents(helper)
        path = tmp_path / "kb.zip"
        name = "databases/kb_test/documents.json"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            await exporter._write_table_dump(archive, name, data)
        importer = AstrBotImporter(MagicMock())
        importer.kb_root_dir = str(tmp_path / "restored")
        (tmp_path / "restored" / "test").mkdir(parents=True)
        with resources.open_backup(path) as archive:
            document_stream = resources.read_backup_json(archive, name)
            await importer._import_kb_documents("test", document_stream)
        restored = DocumentStorage(str(tmp_path / "restored" / "test" / "doc.db"))
        await restored.initialize()
        docs = await restored.get_documents({}, limit=None)
        assert {doc["doc_id"]: doc["text"] for doc in docs} == {
            "one": "汉字😀\x00tail",
            "two": "second",
        }
        assert {doc["doc_id"]: json.loads(doc["metadata"]) for doc in docs} == {
            "one": {"source": "文档"},
            "two": {"n": 2},
        }
    finally:
        await source.close()
        if restored is not None:
            await restored.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_name", sorted({"python", ijson.backend}))
async def test_compact_record_and_large_integer_export_restore(
    tmp_path, monkeypatch, backend_name
):
    monkeypatch.setattr(
        resources.ijson,
        "basic_parse_coro",
        ijson.get_backend(backend_name).basic_parse_coro,
    )
    monkeypatch.setattr(resources, "MAX_JSON_RECORD_BYTES", 2048)
    monkeypatch.setattr("astrbot.core.backup.exporter.MAX_JSON_RECORD_BYTES", 2048)
    row = {
        "conversation_id": "x",
        "platform_id": "p",
        "user_id": "u",
        "content": [2**80, 1.25] + [0] * 800,
    }
    assert len(json.dumps(row)) > 2048
    assert len(json.dumps(row, separators=(",", ":"))) < 2048
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'compact.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "astrbot.core.backup.importer.MAIN_DB_MODELS", {"conversations": ConversationV2}
    )
    monkeypatch.setattr(
        "astrbot.core.backup.exporter.MAIN_DB_MODELS", {"conversations": ConversationV2}
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ConversationV2.__table__.create)
        async with sessions.begin() as session:
            session.add(ConversationV2(**row))
        path = await AstrBotExporter(SimpleNamespace(get_db=sessions)).export_all(
            str(tmp_path), components=["database"]
        )
        result = await AstrBotImporter(SimpleNamespace(get_db=sessions)).import_all(
            path, components=["database"]
        )
        assert result.success, result.errors
        async with sessions() as session:
            restored = (await session.execute(select(ConversationV2))).scalar_one()
            assert restored.content == row["content"]
            assert type(restored.content[0]) is int
            assert type(restored.content[1]) is float
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["depth", "nonfinite"])
async def test_export_rejects_unreadable_json_before_success(tmp_path, case):
    value = float("nan")
    if case == "depth":
        value = 0
        for _ in range(70):
            value = [value]
    exporter = AstrBotExporter(MagicMock())
    exporter._export_main_database = AsyncMock(
        return_value={
            "conversations": [
                {
                    "conversation_id": "x",
                    "platform_id": "p",
                    "user_id": "u",
                    "content": [value],
                }
            ]
        }
    )
    with pytest.raises(ValueError):
        await exporter.export_all(str(tmp_path), components=["database"])
    assert not list(tmp_path.glob("*.zip"))
    assert exporter.exported_components == []


@pytest.mark.asyncio
async def test_kb_clear_failure_rolls_back_before_removing_files(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'kb.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    kb_dir = tmp_path / "old-kb"
    kb_dir.mkdir()
    original = kb_dir / "original.txt"
    original.write_text("keep")
    helper = SimpleNamespace(kb_dir=kb_dir, terminate=AsyncMock())
    manager = SimpleNamespace(
        kb_db=SimpleNamespace(get_db=sessions),
        kb_insts={"old": helper},
        load_kbs=AsyncMock(),
    )
    monkeypatch.setattr(
        "astrbot.core.backup.importer.KB_METADATA_MODELS",
        {"knowledge_bases": KnowledgeBase, "missing_table": ConversationV2},
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(KnowledgeBase.__table__.create)
        async with sessions.begin() as session:
            session.add(KnowledgeBase(kb_id="old", kb_name="original"))
        result = ImportResult()
        with zipfile.ZipFile(tmp_path / "kb.zip", "w") as archive:
            with pytest.raises(DatabaseClearError):
                await AstrBotImporter(MagicMock(), manager)._import_knowledge_bases(
                    archive,
                    {"knowledge_bases": [{"kb_id": "new", "kb_name": "new"}]},
                    result,
                    clear=True,
                )
        async with sessions() as session:
            assert (
                await session.execute(select(KnowledgeBase.kb_id))
            ).scalars().all() == ["old"]
        assert original.read_text() == "keep"
        assert result.imported_tables == {}
        helper.terminate.assert_not_awaited()
        manager.load_kbs.assert_not_awaited()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_attachment_restore_parses_main_dump_only_twice(
    tmp_path, monkeypatch
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'attachments.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    models = {"conversations": ConversationV2, "attachments": Attachment}
    monkeypatch.setattr("astrbot.core.backup.importer.MAIN_DB_MODELS", models)
    destination = tmp_path / "attachments" / "nested" / "original.txt"
    row = {
        "attachment_id": "att",
        "path": str(destination),
        "type": "file",
        "mime_type": "text/plain",
    }
    path = tmp_path / "restore.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        archive.writestr(
            "databases/main_db.json",
            json.dumps(
                {
                    "conversations": [
                        {"conversation_id": "x", "platform_id": "p", "user_id": "u"}
                    ],
                    "attachments": [row],
                }
            ),
        )
        archive.writestr("files/attachments/att.txt", b"restored")
    passes = []
    records = resources.BackupTableStream._records

    def count_passes(stream):
        passes.append(stream.name)
        yield from records(stream)

    monkeypatch.setattr(resources.BackupTableStream, "_records", count_passes)
    try:
        async with engine.begin() as conn:
            for model in models.values():
                await conn.run_sync(model.__table__.create)
        result = await AstrBotImporter(
            SimpleNamespace(get_db=sessions),
            config_path=str(tmp_path / "cmd_config.json"),
        ).import_all(str(path), components=["database", "attachments"])
        assert result.success, result.errors
        assert passes == ["databases/main_db.json"] * 2
        assert destination.read_bytes() == b"restored"
        assert result.imported_files["attachments"] == 1
    finally:
        await engine.dispose()


def test_manifest_kb_inventory_uses_only_written_entries():
    manager = SimpleNamespace(kb_insts={"not-exported": MagicMock()})
    exporter = AstrBotExporter(MagicMock(), manager)
    exporter._checksums = {
        "databases/kb_written/documents.json": "sha256:docs",
        "files/kb_media/written/images/saved.png": "sha256:media",
    }
    manifest = exporter._generate_manifest({}, {})
    assert manifest["tables"]["kb_documents"] == {"written": "documents"}
    assert manifest["files"]["kb_media"] == {"written": ["saved.png"]}


@pytest.mark.parametrize("backend_name", sorted({"python", ijson.backend}))
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        2**80,
        -1.25e-8,
        '汉字😀\x00\\"',
        [[], {}, 1, {"x": [False, None, "汉字"]}],
        {"nested": {"a": 1, "b": [1, 2]}, "empty": {}},
    ],
)
def test_raw_json_check_matches_compact_encoding(monkeypatch, backend_name, value):
    monkeypatch.setattr(
        resources.ijson, "basic_parse", ijson.get_backend(backend_name).basic_parse
    )
    raw = json.dumps(value, ensure_ascii=True, indent=2).encode()
    expected = len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert resources.check_backup_json_field(raw, expected) == expected
    with pytest.raises(ValueError, match="size limit"):
        resources.check_backup_json_field(raw, expected - 1)


@pytest.mark.asyncio
async def test_export_restore_preserves_nul_in_text_and_autostring(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'nul.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    for module in ("exporter", "importer"):
        monkeypatch.setattr(
            f"astrbot.core.backup.{module}.MAIN_DB_MODELS", {"personas": Persona}
        )
    prompt = "before\x00汉字😀after"
    persona_id = "id\x00suffix"
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Persona.__table__.create)
        async with sessions.begin() as session:
            session.add(Persona(persona_id=persona_id, system_prompt=prompt))
        db = SimpleNamespace(get_db=sessions)
        path = await AstrBotExporter(db).export_all(
            str(tmp_path), components=["database"]
        )
        result = await AstrBotImporter(db).import_all(path, components=["database"])
        assert result.success, result.errors
        async with sessions() as session:
            restored = (await session.execute(select(Persona))).scalar_one()
            assert restored.system_prompt == prompt
            assert restored.persona_id == persona_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["size", "combined", "depth"])
async def test_export_checks_json_before_materializing_containers(
    tmp_path, monkeypatch, case
):
    limit = 256 * 1024
    monkeypatch.setattr("astrbot.core.backup.exporter.MAX_JSON_RECORD_BYTES", limit)
    monkeypatch.setattr(
        "astrbot.core.backup.exporter.MAIN_DB_MODELS", {"personas": Persona}
    )
    if case == "depth":
        first, second = "[" * 70 + "0" + "]" * 70, "null"
    else:
        count = 200000 if case == "size" else 50000
        first = "[" + ", ".join(["{}"] * count) + "]"
        second = first if case == "combined" else "null"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'limited.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    decoded = []
    loads = json.loads

    def track_decode(raw, *args, **kwargs):
        if isinstance(raw, bytes) and raw.startswith(b"["):
            decoded.append(len(raw))
        return loads(raw, *args, **kwargs)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Persona.__table__.create)
        async with sessions.begin() as session:
            session.add(Persona(persona_id="x", system_prompt="prompt"))
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE personas SET begin_dialogs=:first, tools=:second"),
                {"first": first, "second": second},
            )
        monkeypatch.setattr(json, "loads", track_decode)
        tracemalloc.start()
        try:
            with pytest.raises(ValueError, match="limit"):
                await AstrBotExporter(SimpleNamespace(get_db=sessions)).export_all(
                    str(tmp_path), components=["database"]
                )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert decoded == []
        assert peak < 8 * 1024 * 1024
        assert not list(tmp_path.glob("*.zip"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_raw_autostring_fetch_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("astrbot.core.backup.exporter.MAX_JSON_RECORD_BYTES", 256)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'autostring.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # Inspect values delivered by the query, independently of the exporter's
    # later size check. AutoString must not bypass the SQL read bound.
    fetched = []
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ConversationV2.__table__.create)
        async with sessions.begin() as session:
            session.add(
                ConversationV2(
                    conversation_id="x", platform_id="p" * 10000, user_id="u"
                )
            )
        session = sessions()
        stream = session.stream

        async def capture(statement, *args, **kwargs):
            async with sessions() as probe:
                result = await probe.stream(statement)
                try:
                    fetched.extend(await result.mappings().all())
                finally:
                    await result.close()
            return await stream(statement, *args, **kwargs)

        monkeypatch.setattr(session, "stream", capture)
        exporter = AstrBotExporter(MagicMock())
        with pytest.raises(ValueError, match="size limit"):
            async for _ in exporter._export_records(
                lambda: session, ConversationV2, exporter._model_to_dict
            ):
                pass
        assert len(fetched[0]["platform_id"]) == 257
        assert isinstance(fetched[0]["platform_id"], bytes)
    finally:
        await engine.dispose()
