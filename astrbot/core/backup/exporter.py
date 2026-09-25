"""AstrBot 数据导出器

负责将所有数据导出为 ZIP 备份文件。
导出格式为 JSON，这是数据库无关的方案，支持未来向 MySQL/PostgreSQL 迁移。
"""

import asyncio
import hashlib
import io
import json
import os
import zipfile
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, LargeBinary, String, Text, cast, func, inspect, select
from sqlmodel.sql.sqltypes import AutoString

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Attachment
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_data_path,
)

# 从共享常量模块导入
from .constants import (
    BACKUP_MANIFEST_VERSION,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    component_of_entry,
    get_backup_components,
    get_backup_directories,
)
from .importer import AstrBotImporter
from .resources import (
    MAX_JSON_RECORD_BYTES,
    BackupTableStream,
    backup_json_limit,
    check_backup_json_field,
)

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

CMD_CONFIG_FILE_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")


class AstrBotExporter:
    """Export selected database, configuration, attachment, and extension data.

    Attachments include legacy WebChat images in data/webchat/imgs; upload
    fragments in data/webchat/.chunks are excluded.
    """

    def __init__(
        self,
        main_db: BaseDatabase,
        kb_manager: "KnowledgeBaseManager | None" = None,
        config_path: str = CMD_CONFIG_FILE_PATH,
    ) -> None:
        self.main_db = main_db
        self.kb_manager = kb_manager
        self.config_path = config_path
        self._checksums: dict[str, str] = {}
        # Export report: components actually written and entries skipped
        # (with reasons). Surfaced by the service layer in the task result.
        self.exported_components: list[str] = []
        self.skipped_entries: list[dict[str, str]] = []

    async def export_all(
        self,
        output_dir: str | None = None,
        progress_callback: Any | None = None,
        components: list[str] | None = None,
    ) -> str:
        """导出选定组件到 ZIP 文件

        Args:
            output_dir: 输出目录
            progress_callback: 进度回调函数，接收参数 (stage, current, total, message)
            components: 要导出的组件 id 列表。None 表示全量（向后兼容）。

        Returns:
            str: 生成的 ZIP 文件路径

        Raises:
            ValueError: components 不含任何有效组件 id。
            RuntimeError: ZIP 条目写入中途失败；半成品 ZIP 会被清理，
                不会留下无法通过完整性校验的备份产物。
        """
        selected = self._normalize_components(components)
        self._checksums.clear()
        self.exported_components.clear()
        self.skipped_entries.clear()
        if output_dir is None:
            output_dir = get_astrbot_backups_path()

        # 确保输出目录存在
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"astrbot_backup_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)

        logger.info(f"Starting backup export to {zip_path}")

        try:
            included: list[str] = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. 导出主数据库
                main_data: dict[str, Any] = {}
                if "database" in selected:
                    if progress_callback:
                        await progress_callback(
                            "main_db", 0, 100, "正在导出主数据库..."
                        )
                    main_data = await self._export_main_database()
                    await self._write_table_dump(
                        zf, "databases/main_db.json", main_data
                    )
                    included.append("database")
                    if progress_callback:
                        await progress_callback("main_db", 100, 100, "主数据库导出完成")

                # 2. 导出知识库数据
                kb_meta_data: dict[str, Any] = {
                    "knowledge_bases": [],
                    "kb_documents": [],
                    "kb_media": [],
                }
                if "knowledge_base" in selected and self.kb_manager:
                    if progress_callback:
                        await progress_callback(
                            "kb_metadata", 0, 100, "正在导出知识库元数据..."
                        )
                    kb_meta_data = await self._export_kb_metadata()
                    await self._write_table_dump(
                        zf, "databases/kb_metadata.json", kb_meta_data
                    )
                    if progress_callback:
                        await progress_callback(
                            "kb_metadata", 100, 100, "知识库元数据导出完成"
                        )

                    # 导出每个知识库的文档数据
                    kb_insts = self.kb_manager.kb_insts
                    total_kbs = len(kb_insts)
                    for idx, (kb_id, kb_helper) in enumerate(kb_insts.items()):
                        if progress_callback:
                            await progress_callback(
                                "kb_documents",
                                idx,
                                total_kbs,
                                f"正在导出知识库 {kb_helper.kb.kb_name} 的文档数据...",
                            )
                        doc_data = await self._export_kb_documents(kb_helper)
                        doc_path = f"databases/kb_{kb_id}/documents.json"
                        await self._write_table_dump(zf, doc_path, doc_data)
                        del doc_data

                        # 导出 FAISS 索引文件
                        await self._run_io(
                            self._export_faiss_index, zf, kb_helper, kb_id
                        )

                        # 导出知识库多媒体文件
                        await self._run_io(
                            self._export_kb_media_files, zf, kb_helper, kb_id
                        )

                    if progress_callback:
                        await progress_callback(
                            "kb_documents", total_kbs, total_kbs, "知识库文档导出完成"
                        )
                    included.append("knowledge_base")

                # 3. 导出配置文件
                if "cmd_config" in selected:
                    if progress_callback:
                        await progress_callback("config", 0, 100, "正在导出配置文件...")
                    if os.path.exists(self.config_path):
                        await self._run_io(
                            self._write_entry,
                            zf,
                            "config/cmd_config.json",
                            Path(self.config_path),
                        )
                        included.append("cmd_config")
                    else:
                        self._record_skip(
                            "config/cmd_config.json", "config file does not exist"
                        )
                    if progress_callback:
                        await progress_callback("config", 100, 100, "配置文件导出完成")

                # 4. 导出附件文件
                if "attachments" in selected:
                    if progress_callback:
                        await progress_callback(
                            "attachments", 0, 100, "正在导出附件..."
                        )
                    attachment_rows = await self._export_attachment_records()
                    attachment_count = 0
                    if isinstance(attachment_rows, list):
                        attachment_count = await self._run_io(
                            self._export_attachments, zf, attachment_rows
                        )
                    else:
                        try:
                            async for batch in attachment_rows:
                                attachment_count += await self._run_io(
                                    self._export_attachments, zf, batch
                                )
                        finally:
                            await attachment_rows.aclose()
                    if attachment_count > 0:
                        included.append("attachments")
                    if progress_callback:
                        await progress_callback("attachments", 100, 100, "附件导出完成")

                # 5. 导出插件和其他目录
                dir_names = [
                    d
                    for d in get_backup_directories()
                    if d in selected or (d == "webchat" and "attachments" in selected)
                ]
                dir_stats: dict[str, dict[str, int]] = {}
                if dir_names:
                    if progress_callback:
                        await progress_callback(
                            "directories", 0, 100, "正在导出插件和数据目录..."
                        )
                    dir_stats = await self._run_io(
                        self._export_directories, zf, dir_names
                    )
                    for directory, stats in dir_stats.items():
                        component = (
                            "attachments" if directory == "webchat" else directory
                        )
                        if stats["files"] > 0 and component not in included:
                            included.append(component)
                    if progress_callback:
                        await progress_callback("directories", 100, 100, "目录导出完成")

                if "attachments" in selected and "attachments" not in included:
                    self._record_skip(
                        "files/attachments/", "no attachment files to export"
                    )

                # 6. 生成 manifest
                if progress_callback:
                    await progress_callback("manifest", 0, 100, "正在生成清单...")
                manifest = await self._run_io(
                    self._generate_manifest,
                    main_data,
                    kb_meta_data,
                    dir_stats,
                    included,
                )
                await self._run_io(
                    self._write_json_entry, zf, "manifest.json", manifest
                )
                await self._run_io(zf.close)
                # Apply the same ZIP metadata limits before publishing the file.
                check = await self._run_io(
                    AstrBotImporter(self.main_db).pre_check, zip_path
                )
                if check.error or not check.valid:
                    raise ValueError(check.error or "Backup archive validation failed")
                if progress_callback:
                    await progress_callback("manifest", 100, 100, "清单生成完成")

            self.exported_components = included
            logger.info(f"Backup export completed: {zip_path}")
            return zip_path

        except (Exception, asyncio.CancelledError) as e:
            logger.error(f"Backup export failed: {e}")
            # 清理失败的文件
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise

    async def _run_io(self, operation: Any, *args: Any) -> Any:
        """Run blocking work and wait for it before closing a cancelled export.

        Args:
            operation: Synchronous operation using the archive.
            *args: Positional arguments for the operation.

        Returns:
            The operation result.
        """
        task = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A worker cannot be cancelled; it must finish before ZipFile closes.
            try:
                await task
            finally:
                raise

    async def _write_table_dump(
        self, zf: zipfile.ZipFile, name: str, data: dict
    ) -> None:
        """Write table batches directly to ZIP and retain only manifest row counts.

        Args:
            zf: Destination archive.
            name: Database JSON entry name.
            data: Table names mapped to row lists or async batch iterators. Values
                are replaced with lightweight ranges holding the final row counts.

        Raises:
            ValueError: A record or the entire entry exceeds its resource budget.
        """
        limit = backup_json_limit(name)
        hasher = hashlib.sha256()
        written = 0
        first_row = True
        encoder = json.JSONEncoder(
            ensure_ascii=False, separators=(",", ":"), default=str, allow_nan=False
        )
        dest = io.BufferedWriter(
            zf.open(name, "w", force_zip64=True), buffer_size=1 << 20
        )

        def write(value: str | list[dict]) -> None:
            """Encode one marker or batch in the worker thread.

            Args:
                value: A raw JSON delimiter or a batch of table rows.

            Raises:
                ValueError: The entry or an individual record is oversized.
            """
            nonlocal written, first_row
            for row in [None] if isinstance(value, str) else value:
                if row is None:
                    parts = (value,)
                else:
                    parts = chain(("" if first_row else ",",), encoder.iterencode(row))
                    first_row = False
                row_size = 0
                for part in parts:
                    chunk = part.encode("utf-8")
                    written += len(chunk)
                    row_size += len(chunk)
                    if written > limit:
                        raise ValueError(f"Backup JSON {name} exceeds the size limit")
                    if row_size > MAX_JSON_RECORD_BYTES:
                        raise ValueError("Backup JSON record exceeds the size limit")
                    hasher.update(chunk)
                    dest.write(chunk)

        try:
            await self._run_io(write, "{")
            for index, (table, rows) in enumerate(data.items()):
                first_row = True
                prefix = ("," if index else "") + json.dumps(table) + ":["
                await self._run_io(write, prefix)
                count = 0
                if isinstance(rows, list):
                    await self._run_io(write, rows)
                    count = len(rows)
                else:
                    try:
                        async for batch in rows:
                            await self._run_io(write, batch)
                            count += len(batch)
                    finally:
                        await rows.aclose()
                data[table] = range(count)
                await self._run_io(write, "]")
            await self._run_io(write, "}")
        finally:
            await self._run_io(dest.close)
        # Consume without retaining rows, using the importer's exact parser and
        # resource limits before publishing an archive as successfully exported.
        await self._run_io(
            deque,
            chain.from_iterable(
                rows for _, rows in BackupTableStream(zf, name).items()
            ),
            0,
        )
        self._checksums[name] = f"sha256:{hasher.hexdigest()}"

    def _write_json_entry(self, zf: zipfile.ZipFile, name: str, data: Any) -> None:
        """Encode, hash and compress JSON incrementally in the worker thread.

        Args:
            zf: Destination archive.
            name: JSON entry name.
            data: JSON-serializable data.

        Raises:
            ValueError: The JSON exceeds the importer's resource budget.
        """
        limit = backup_json_limit(name)
        hasher = hashlib.sha256()
        size = 0
        buffer = bytearray()
        encoder = json.JSONEncoder(ensure_ascii=False, indent=2, default=str)
        with zf.open(name, "w", force_zip64=True) as dest:
            for text in encoder.iterencode(data):
                chunk = text.encode("utf-8")
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"Backup JSON {name} exceeds the size limit")
                buffer.extend(chunk)
                if len(buffer) >= 1 << 20:
                    hasher.update(buffer)
                    dest.write(buffer)
                    buffer.clear()
            if buffer:
                hasher.update(buffer)
                dest.write(buffer)
        if name != "manifest.json":
            self._checksums[name] = f"sha256:{hasher.hexdigest()}"

    def _normalize_components(self, components: list[str] | None) -> set[str]:
        """Validate requested component ids against the known set.

        Args:
            components: Requested ids, or None for a full backup.

        Returns:
            The effective set of component ids to export.

        Raises:
            ValueError: If a list was given but contains no valid ids.
        """
        known = set(get_backup_components())
        if components is None:
            return known
        selected = set(components) & known
        unknown = set(components) - known
        if unknown:
            logger.warning(f"Ignoring unknown backup components: {sorted(unknown)}")
        if not selected:
            raise ValueError("No valid backup components selected")
        return selected

    def _record_skip(self, arcname: str, reason: str) -> None:
        """Record a skipped entry with its reason (never silent)."""
        self.skipped_entries.append({"entry": arcname, "reason": reason})
        logger.warning(f"Export entry skipped: {arcname} ({reason})")

    def _write_entry(self, zf: zipfile.ZipFile, arcname: str, src_path: Path) -> None:
        """Stream a disk file into the ZIP while computing its sha256.

        Single pass, constant memory. The source is opened before the ZIP
        entry is created, so a missing/unreadable source raises OSError
        *before* any entry bytes exist and callers may treat it as a
        skippable pre-write failure. Any error after the entry write started
        leaves a partial entry in the archive, so it is re-raised as
        RuntimeError and the whole export aborts (the half-written ZIP is
        removed by export_all).

        Args:
            zf: Open ZIP file being written.
            arcname: Entry path inside the archive.
            src_path: Source file on disk.

        Raises:
            OSError: Source cannot be opened (pre-write, skippable).
            RuntimeError: Entry failed mid-write (must abort the export).
        """
        fsrc = open(src_path, "rb")
        try:
            hasher = hashlib.sha256()
            try:
                size = 0
                with zf.open(arcname, mode="w", force_zip64=True) as fdst:
                    while chunk := fsrc.read(1 << 20):
                        if arcname == "config/cmd_config.json":
                            size += len(chunk)
                            if size > backup_json_limit(arcname):
                                raise ValueError("Backup JSON exceeds the size limit")
                        hasher.update(chunk)
                        fdst.write(chunk)
            except Exception as e:
                raise RuntimeError(f"Entry {arcname} failed mid-write: {e}") from e
        finally:
            fsrc.close()
        self._checksums[arcname] = f"sha256:{hasher.hexdigest()}"

    async def _export_attachment_records(self) -> AsyncIterator[list[dict]]:
        """Return attachment batches without retaining the whole table.

        Returns:
            An async iterator of attachment record batches.
        """
        return self._export_records(
            self.main_db.get_db, Attachment, self._model_to_dict
        )

    async def _export_records(
        self, get_session: Any, model_class: type, convert: Any
    ) -> AsyncIterator[list[dict]]:
        """Fetch bounded raw rows and decode JSON in the export worker.

        Args:
            get_session: Factory returning an async database session.
            model_class: Model to export.
            convert: Function converting a transient model to its dump schema.
                JSON fields are placeholders here and filled after validation.

        Yields:
            A batch of rows serialized to dictionaries.
        """
        columns = []
        json_fields = set()
        text_fields = set()
        for attr in inspect(model_class).column_attrs:
            column = attr.columns[0]
            expression = column
            if isinstance(column.type, JSON):
                json_fields.add(attr.key)
                expression = cast(column, Text)
            if isinstance(column.type, (JSON, String, AutoString)):
                text_fields.add(attr.key)
                # Fetch one extra byte to detect oversize values without
                # transferring an arbitrarily large field into Python first.
                # SQLite TEXT substr stops at NUL; BLOB substr preserves it.
                # Include SQLModel's AutoString decorator explicitly.
                # Stored JSON may contain ASCII escapes and separator spaces;
                # allow their expansion relative to our compact UTF-8 dump.
                raw_limit = MAX_JSON_RECORD_BYTES * (
                    6 if attr.key in json_fields else 1
                )
                expression = func.substr(
                    cast(expression, LargeBinary), 1, raw_limit + 1
                )
            columns.append(expression.label(attr.key))

        def convert_batch(batch: list[dict]) -> list[dict]:
            """Decode raw fields and convert transient models in the worker.

            Args:
                batch: Bounded raw database rows.

            Returns:
                Records in the existing backup schema.
            """
            converted = []
            for values in batch:
                # Convert only scalar fields first. This preserves the existing
                # schema without making model_dump copy decoded JSON containers.
                scalar_values = {
                    key: None
                    if key in json_fields
                    else (
                        value.decode("utf-8")
                        if key in text_fields and value is not None
                        else value
                    )
                    for key, value in values.items()
                }
                row = convert(model_class(**scalar_values))
                size = len(
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                        allow_nan=False,
                    ).encode("utf-8")
                )
                size -= 4 * sum(values[key] is not None for key in json_fields)
                if size > MAX_JSON_RECORD_BYTES:
                    raise ValueError("Backup JSON record exceeds the size limit")
                # Validate every JSON field before materializing any of them.
                # The placeholder null already accounts for four bytes per field.
                for key in json_fields:
                    if values[key] is not None:
                        size += check_backup_json_field(
                            values[key], MAX_JSON_RECORD_BYTES - size
                        )
                for key in json_fields:
                    if values[key] is not None:
                        row[key] = json.loads(values[key])
                converted.append(row)
            return converted

        async with get_session() as session:
            result = await session.stream(
                select(*columns).execution_options(yield_per=1)
            )
            try:
                batch = []
                batch_size = 0
                async for row in result.mappings():
                    values = dict(row)
                    if any(
                        isinstance(value, (str, bytes))
                        and len(value)
                        > MAX_JSON_RECORD_BYTES * (6 if key in json_fields else 1)
                        for key, value in values.items()
                    ):
                        raise ValueError("Backup JSON record exceeds the size limit")
                    # Four bytes per character conservatively bounds Unicode
                    # storage; count small scalar fields too. Never prefetch 500
                    # potentially multi-megabyte ORM objects on the event loop.
                    size = sum(
                        len(value) * 4 if isinstance(value, (str, bytes)) else 32
                        for value in values.values()
                    )
                    if batch and (
                        len(batch) >= 500 or batch_size + size > MAX_JSON_RECORD_BYTES
                    ):
                        yield await self._run_io(convert_batch, batch)
                        batch = []
                        batch_size = 0
                    batch.append(values)
                    batch_size += size
                if batch:
                    yield await self._run_io(convert_batch, batch)
            finally:
                await result.close()

    def _component_checksums(self, included: list[str]) -> dict[str, str]:
        """Derive a deterministic per-component digest from entry checksums.

        The digest is sha256 over the sorted "path:entry_hash" lines of every
        entry owned by the component, giving import a component-level
        verification anchor without re-reading raw bytes.
        """
        result: dict[str, str] = {}
        for comp in included:
            lines = sorted(
                f"{path}:{checksum}"
                for path, checksum in self._checksums.items()
                if component_of_entry(path) == comp
            )
            digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
            result[comp] = f"sha256:{digest}"
        return result

    async def _export_main_database(self) -> dict[str, Any]:
        """Prepare replay-free streams for the main database tables.

        Returns:
            Table names mapped to async row-batch iterators.
        """
        return {
            table: self._export_records(self.main_db.get_db, model, self._model_to_dict)
            for table, model in MAIN_DB_MODELS.items()
        }

    async def _export_kb_metadata(self) -> dict[str, Any]:
        """Prepare streams for the knowledge base metadata tables.

        Returns:
            Table names mapped to async row-batch iterators.
        """
        if not self.kb_manager:
            return {}
        return {
            table: self._export_records(
                self.kb_manager.kb_db.get_db, model, self._model_to_dict
            )
            for table, model in KB_METADATA_MODELS.items()
        }

    async def _export_kb_documents(self, kb_helper: Any) -> dict[str, Any]:
        """Prepare the knowledge base document stream using its existing database.

        Args:
            kb_helper: Knowledge base being exported.

        Returns:
            Document table mapped to an async row-batch iterator.
        """
        from astrbot.core.db.vec_db.faiss_impl.document_storage import Document

        vec_db = kb_helper.vec_db
        if not vec_db or not vec_db.document_storage:
            return {"documents": []}
        # DocumentStorage exposes get_session rather than get_db. Its own
        # conversion also preserves the exported field names used by import.
        storage = vec_db.document_storage
        return {
            "documents": self._export_records(
                storage.get_session, Document, storage._document_to_dict
            )
        }

    def _export_faiss_index(
        self,
        zf: zipfile.ZipFile,
        kb_helper: Any,
        kb_id: str,
    ) -> None:
        """导出 FAISS 索引文件"""
        index_path = kb_helper.kb_dir / "index.faiss"
        if not index_path.exists():
            return
        archive_path = f"databases/kb_{kb_id}/index.faiss"
        try:
            self._write_entry(zf, archive_path, index_path)
            logger.debug(f"Exported FAISS index: {archive_path}")
        except OSError as e:
            # Source unreadable before the entry write started: skippable.
            self._record_skip(archive_path, str(e))

    def _export_kb_media_files(
        self, zf: zipfile.ZipFile, kb_helper: Any, kb_id: str
    ) -> None:
        """导出知识库的多媒体文件"""
        media_dir = kb_helper.kb_medias_dir
        if not media_dir.exists():
            return

        for root, _, files in os.walk(media_dir):
            for file in files:
                file_path = Path(root) / file
                # 计算相对路径
                rel_path = file_path.relative_to(kb_helper.kb_dir).as_posix()
                archive_path = f"files/kb_media/{kb_id}/{rel_path}"
                try:
                    self._write_entry(zf, archive_path, file_path)
                except OSError as e:
                    # Source unreadable before the entry write started.
                    self._record_skip(archive_path, str(e))

    def _export_directories(
        self, zf: zipfile.ZipFile, dir_names: list[str]
    ) -> dict[str, dict[str, int]]:
        """导出选定的插件和其他数据目录

        Args:
            zf: 打开的 ZIP 文件对象
            dir_names: 要导出的目录键列表（get_backup_directories 的子集）

        Returns:
            dict: 每个目录的统计信息 {dir_name: {"files": count, "size": bytes}}
        """
        stats: dict[str, dict[str, int]] = {}
        backup_directories = get_backup_directories()

        for dir_name in dir_names:
            full_path = Path(backup_directories[dir_name])
            scan_path = full_path / "imgs" if dir_name == "webchat" else full_path
            if not scan_path.exists():
                logger.debug(f"Skipping missing directory: {scan_path}")
                continue

            file_count = 0
            total_size = 0

            try:
                for root, dirs, files in os.walk(scan_path):
                    # 跳过 __pycache__ 目录
                    dirs[:] = [d for d in dirs if d != "__pycache__"]

                    for file in files:
                        # 跳过 .pyc 文件
                        if file.endswith(".pyc"):
                            continue

                        file_path = Path(root) / file
                        # 计算相对路径
                        rel_path = file_path.relative_to(full_path).as_posix()
                        archive_path = f"directories/{dir_name}/{rel_path}"
                        try:
                            self._write_entry(zf, archive_path, file_path)
                            file_count += 1
                            total_size += file_path.stat().st_size
                        except OSError as e:
                            # Source vanished or unreadable before the entry
                            # write started: skip and record, never silent.
                            self._record_skip(archive_path, str(e))

                stats[dir_name] = {"files": file_count, "size": total_size}
                logger.debug(
                    f"Exported directory {dir_name}: {file_count} files, {total_size} bytes"
                )
            except RuntimeError:
                # Mid-write entry failure: the archive now holds a partial
                # entry — the whole export must fail.
                raise
            except Exception as e:
                logger.warning(f"Failed to export directory {full_path}: {e}")
                stats[dir_name] = {"files": 0, "size": 0}

        return stats

    def _export_attachments(self, zf: zipfile.ZipFile, attachments: list[dict]) -> int:
        """导出附件文件

        Returns:
            int: 实际写入的附件文件数量
        """
        count = 0
        for attachment in attachments:
            file_path = attachment.get("path", "")
            if not file_path or not os.path.exists(file_path):
                continue
            # 使用 attachment_id 作为文件名
            attachment_id = attachment.get("attachment_id", "")
            ext = os.path.splitext(file_path)[1]
            archive_path = f"files/attachments/{attachment_id}{ext}"
            try:
                self._write_entry(zf, archive_path, Path(file_path))
                count += 1
            except OSError as e:
                # Source unreadable before the entry write started.
                self._record_skip(archive_path, str(e))
        return count

    def _model_to_dict(self, record: Any) -> dict:
        """将 SQLModel 实例转换为字典

        这是数据库无关的序列化方式，支持未来迁移到其他数据库。
        """
        # 使用 SQLModel 内置的 model_dump 方法（如果可用）
        if hasattr(record, "model_dump"):
            data = record.model_dump(mode="python")
            # 处理 datetime 类型
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
            return data

        # 回退到手动提取
        data = {}
        # 使用 inspect 获取表信息
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(record.__class__)
        for column in mapper.columns:
            value = getattr(record, column.name)
            # 处理 datetime 类型 - 统一转为 ISO 格式字符串
            if isinstance(value, datetime):
                value = value.isoformat()
            data[column.name] = value
        return data

    def _add_checksum(self, path: str, content: str | bytes) -> None:
        """计算并添加文件校验和"""
        if isinstance(content, str):
            content = content.encode("utf-8")
        checksum = hashlib.sha256(content).hexdigest()
        self._checksums[path] = f"sha256:{checksum}"

    def _generate_manifest(
        self,
        main_data: dict[str, Any],
        kb_meta_data: dict[str, Any],
        dir_stats: dict[str, dict[str, int]] | None = None,
        included_components: list[str] | None = None,
    ) -> dict:
        """生成备份清单

        Args:
            main_data: 主数据库导出数据
            kb_meta_data: 知识库元数据
            dir_stats: 目录导出统计
            included_components: 实际写入 ZIP 的组件 id 列表
        """
        if dir_stats is None:
            dir_stats = {}
        if included_components is None:
            included_components = []
        kb_document_tables = {
            path.removeprefix("databases/kb_").removesuffix(
                "/documents.json"
            ): "documents"
            for path in self._checksums
            if path.startswith("databases/kb_") and path.endswith("/documents.json")
        }

        attachment_files = [
            path.removeprefix("files/attachments/")
            for path in self._checksums
            if path.startswith("files/attachments/")
        ]

        kb_media_files: dict[str, list[str]] = {}
        for path in self._checksums:
            if path.startswith("files/kb_media/"):
                kb_id, _, relative_path = path.removeprefix(
                    "files/kb_media/"
                ).partition("/")
                kb_media_files.setdefault(kb_id, []).append(Path(relative_path).name)

        manifest = {
            "version": BACKUP_MANIFEST_VERSION,
            "astrbot_version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "origin": "exported",  # 标记备份来源：exported=本实例导出, uploaded=用户上传
            "schema_version": {
                "main_db": "v4",
                "kb_db": "v1",
            },
            "components": sorted(included_components),
            "component_checksums": self._component_checksums(included_components),
            "tables": {
                "main_db": list(main_data.keys()),
                "kb_metadata": list(kb_meta_data.keys()),
                "kb_documents": kb_document_tables,
            },
            "files": {
                "attachments": attachment_files,
                "kb_media": kb_media_files,
            },
            "directories": list(dir_stats.keys()),
            "checksums": self._checksums,
            "statistics": {
                "main_db": {
                    table: len(records) for table, records in main_data.items()
                },
                "kb_metadata": {
                    table: len(records) for table, records in kb_meta_data.items()
                },
                "directories": dir_stats,
            },
        }

        return manifest
