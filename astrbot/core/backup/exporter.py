"""AstrBot 数据导出器

负责将所有数据导出为 ZIP 备份文件。
导出格式为 JSON，这是数据库无关的方案，支持未来向 MySQL/PostgreSQL 迁移。
"""

import asyncio
import functools
import hashlib
import json
import os
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_data_path,
)

# 从共享常量模块导入
from .constants import (
    BACKUP_MANIFEST_VERSION,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    get_backup_directories,
)

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

CMD_CONFIG_FILE_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")


class AstrBotExporter:
    """AstrBot 数据导出器

    导出内容：
    - 主数据库所有表（data/data_v4.db）
    - 知识库元数据（data/knowledge_base/kb.db）
    - 每个知识库的向量文档数据
    - 配置文件（data/cmd_config.json）
    - 附件文件
    - 知识库多媒体文件
    - 插件目录（data/plugins）
    - 插件数据目录（data/plugin_data）
    - 配置目录（data/config）
    - T2I 模板目录（data/t2i_templates）
    - WebChat 数据目录（data/webchat）
    - 临时文件目录（data/temp）
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
        self._archive_executor: ThreadPoolExecutor | None = None

    async def _run_in_archive_thread(
        self, func: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Any:
        """Run an archive operation on the executor that owns the archive.

        Args:
            func: The blocking archive callable to execute, e.g. ``zf.write``.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever ``func`` returns.

        Raises:
            RuntimeError: If the private archive helpers are called outside
                ``export_all``, i.e. while no archive executor owns the archive.
        """
        # The private archive helpers are only valid while export_all owns the
        # executor. Fail loudly instead of silently falling back to run_in_executor(None),
        # which would use the shared multi-threaded default pool and break serialisation.
        if self._archive_executor is None:
            raise RuntimeError(
                "Internal misuse: _run_in_archive_thread was called outside "
                "export_all, so no archive executor owns the archive."
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._archive_executor, functools.partial(func, *args, **kwargs)
        )

    async def export_all(
        self,
        output_dir: str | None = None,
        progress_callback: Any | None = None,
    ) -> str:
        """导出所有数据到 ZIP 文件

        Args:
            output_dir: 输出目录
            progress_callback: 进度回调函数，接收参数 (stage, current, total, message)

        Returns:
            str: 生成的 ZIP 文件路径

        Raises:
            RuntimeError: If another export is already running on this instance.
            BaseException: Whatever the export failed or was cancelled with. A failure to
                finalise the archive (such as ``OSError`` from a full disk) is reported
                here too, so a caller can never mistake an unopenable ZIP for a
                completed backup.
        """
        # Re-entrancy guard, deliberately placed before any instance state is mutated.
        # A second concurrent call would otherwise replace self._archive_executor while
        # the first call is still using it, and whichever call finishes first destroys the
        # executor the other one is still submitting to. Real call sites
        # (dashboard/services/backup_service.py) build a fresh exporter per export, so
        # refusing here costs nothing in production and keeps the failure mode obvious.
        if self._archive_executor is not None:
            raise RuntimeError(
                "A backup export is already running on this exporter instance; create a "
                "separate AstrBotExporter for each concurrent export."
            )

        if output_dir is None:
            output_dir = get_astrbot_backups_path()

        # 确保输出目录存在
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"astrbot_backup_{timestamp}.zip"
        zip_path = os.path.join(output_dir, zip_filename)

        logger.info(f"开始导出备份到 {zip_path}")

        # Compression of multi-GB plugin data previously ran on the event loop and
        # froze it for minutes. A single dedicated worker moves that work off the loop,
        # and having exactly one worker serialises every access to the ZipFile, which
        # is not safe for concurrent use.
        archive_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="astrbot-backup-zip"
        )
        self._archive_executor = archive_executor

        zf: zipfile.ZipFile | None = None
        open_task: asyncio.Future | None = None
        # Set only when the export itself raises. Kept separate from the close result so
        # the teardown can tell "the archive was never finished" apart from "the archive
        # finished but could not be finalised".
        export_error: BaseException | None = None
        close_error: BaseException | None = None
        cancelled_while_cleaning = False

        try:
            # The ZipFile is created on the archive worker instead of on the event loop.
            # The matching close happens on that same worker in the `finally` below, and
            # because the executor has exactly one worker (run_in_executor is a FIFO
            # queue served by it), a close submitted after an in-flight write is
            # guaranteed to run after that write finishes and can never overlap it.
            # Closing from the event loop instead would call ZipFile.close() while a
            # zf.write is still running, which raises "Can't close the ZIP file while
            # there is an open writing handle on it" and leaves an unusable partial zip.
            open_task = asyncio.ensure_future(
                self._run_in_archive_thread(
                    zipfile.ZipFile, zip_path, "w", zipfile.ZIP_DEFLATED
                )
            )
            zf = await asyncio.shield(open_task)

            # 1. 导出主数据库
            if progress_callback:
                await progress_callback("main_db", 0, 100, "正在导出主数据库...")
            main_data = await self._export_main_database()
            main_db_json = json.dumps(
                main_data, ensure_ascii=False, indent=2, default=str
            )
            await self._run_in_archive_thread(
                zf.writestr, "databases/main_db.json", main_db_json
            )
            self._add_checksum("databases/main_db.json", main_db_json)
            if progress_callback:
                await progress_callback("main_db", 100, 100, "主数据库导出完成")

            # 2. 导出知识库数据
            kb_meta_data: dict[str, Any] = {
                "knowledge_bases": [],
                "kb_documents": [],
                "kb_media": [],
            }
            if self.kb_manager:
                if progress_callback:
                    await progress_callback(
                        "kb_metadata", 0, 100, "正在导出知识库元数据..."
                    )
                kb_meta_data = await self._export_kb_metadata()
                kb_meta_json = json.dumps(
                    kb_meta_data, ensure_ascii=False, indent=2, default=str
                )
                await self._run_in_archive_thread(
                    zf.writestr, "databases/kb_metadata.json", kb_meta_json
                )
                self._add_checksum("databases/kb_metadata.json", kb_meta_json)
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
                    doc_json = json.dumps(
                        doc_data, ensure_ascii=False, indent=2, default=str
                    )
                    doc_path = f"databases/kb_{kb_id}/documents.json"
                    await self._run_in_archive_thread(zf.writestr, doc_path, doc_json)
                    self._add_checksum(doc_path, doc_json)

                    # 导出 FAISS 索引文件
                    await self._export_faiss_index(zf, kb_helper, kb_id)

                    # 导出知识库多媒体文件
                    await self._export_kb_media_files(zf, kb_helper, kb_id)

                if progress_callback:
                    await progress_callback(
                        "kb_documents", total_kbs, total_kbs, "知识库文档导出完成"
                    )

            # 3. 导出配置文件
            if progress_callback:
                await progress_callback("config", 0, 100, "正在导出配置文件...")
            if os.path.exists(self.config_path):
                with open(self.config_path, encoding="utf-8") as f:
                    config_content = f.read()
                await self._run_in_archive_thread(
                    zf.writestr, "config/cmd_config.json", config_content
                )
                self._add_checksum("config/cmd_config.json", config_content)
            if progress_callback:
                await progress_callback("config", 100, 100, "配置文件导出完成")

            # 4. 导出附件文件
            if progress_callback:
                await progress_callback("attachments", 0, 100, "正在导出附件...")
            await self._export_attachments(zf, main_data.get("attachments", []))
            if progress_callback:
                await progress_callback("attachments", 100, 100, "附件导出完成")

            # 5. 导出插件和其他目录
            if progress_callback:
                await progress_callback(
                    "directories", 0, 100, "正在导出插件和数据目录..."
                )
            dir_stats = await self._export_directories(zf)
            if progress_callback:
                await progress_callback("directories", 100, 100, "目录导出完成")

            # 6. 生成 manifest
            if progress_callback:
                await progress_callback("manifest", 0, 100, "正在生成清单...")
            manifest = self._generate_manifest(main_data, kb_meta_data, dir_stats)
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
            await self._run_in_archive_thread(
                zf.writestr, "manifest.json", manifest_json
            )
            if progress_callback:
                await progress_callback("manifest", 100, 100, "清单生成完成")

        except Exception as e:
            # Only real failures are logged here. asyncio.CancelledError does not inherit
            # from Exception, so a cancelled export falls straight through to the cleanup
            # below instead of being reported as a failed backup.
            logger.error(f"备份导出失败: {e}")
            export_error = e
            raise
        except BaseException as e:
            # A cancellation that arrives while the export is still producing data. It is
            # remembered so the teardown can tell it apart from an export that produced a
            # finished archive, and re-raised untouched.
            export_error = e
            raise
        finally:
            # Teardown never returns early. A cancellation delivered while the archive is
            # still being closed is remembered here and re-raised only after every
            # cleanup step has run, so a partial zip is never left behind and the worker
            # is never left running with self._archive_executor still set.
            try:
                # Waiting on a shield is the whole cancellation story here. asyncio.shield
                # raises the caller's CancelledError immediately while the inner operation
                # keeps running on the archive worker, so the wait continues until that
                # operation truly finishes; abandoning it would leave the archive half
                # closed. Nothing in this class ever cancels these two tasks, so any
                # CancelledError raised at these awaits is this caller's own cancellation.
                if open_task is not None:
                    while not open_task.done():
                        try:
                            await asyncio.shield(open_task)
                        except asyncio.CancelledError:
                            cancelled_while_cleaning = True
                        except Exception:
                            # The open itself failed. Its result is read below to report
                            # why, so swallow it here and let the teardown continue.
                            pass
                    if not open_task.cancelled():
                        try:
                            # The archive exists even though zf was never assigned when the
                            # export was cancelled while ZipFile() was still opening. Take
                            # the instance so its handle gets closed instead of leaked.
                            if zf is None:
                                zf = open_task.result()
                        except Exception as e:
                            logger.warning(f"打开备份归档失败: {e}")

                if zf is not None:
                    # Close the archive on its own worker. The close is submitted after the
                    # last write on the same FIFO single-worker executor, so it can never
                    # overlap a write that is still in flight, and awaiting it keeps the
                    # event loop responsive while a large compression finishes. A worker
                    # that hangs forever is not bounded here; the caller waits for it so
                    # the executor can always be shut down without a dangling writer.
                    close_task = asyncio.ensure_future(
                        self._run_in_archive_thread(zf.close)
                    )
                    while not close_task.done():
                        try:
                            await asyncio.shield(close_task)
                        except asyncio.CancelledError:
                            cancelled_while_cleaning = True
                        except Exception:
                            # A failed close is an export failure, reported below.
                            pass
                    if not close_task.cancelled():
                        try:
                            close_task.result()
                        except BaseException as e:
                            close_error = e
            finally:
                # Everything else in the teardown is best-effort, but this is not: a
                # BaseException escaping the waits above (KeyboardInterrupt, SystemExit)
                # must still release the instance, or every later export_all on it would
                # be refused as "already running" forever. The worker has drained the
                # archive by now, so shutdown(wait=True) joins an idle thread and returns
                # promptly instead of stalling the event loop behind a compression.
                self._archive_executor = None
                archive_executor.shutdown(wait=True)

            if (
                export_error is not None
                or close_error is not None
                or cancelled_while_cleaning
            ):
                # This call is not going to report a usable archive: the export failed, it
                # was cancelled, or the archive could not be finalised and is left without
                # its central directory. Remove the file so no caller can pick up a
                # truncated zip that looks usable, and so a cancelled export does not
                # orphan a file nothing will ever reference. Removal is best-effort and
                # must never mask the error raised below; ZipFile.close() always clears
                # its handle in a `finally`, so the usual reason a removal fails here is
                # an unrelated filesystem condition.
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError as remove_error:
                        logger.warning(f"清理残缺备份文件失败: {remove_error}")

            if close_error is not None:
                # The archive could not be finalised, so it is unopenable. Reporting
                # success here would tell the caller a corrupt backup was written, which
                # is the worst outcome for a backup feature: this is an export failure.
                logger.error(f"备份归档收尾失败，导出按失败处理: {close_error}")
                if export_error is not None:
                    # Keep whatever was already in flight reachable as the cause.
                    raise close_error from export_error
                raise close_error

            if export_error is None:
                # Nothing else is propagating, so the teardown's own bookkeeping decides
                # the outcome. Otherwise the exception from the try block resumes by
                # itself, with its original traceback (and, for a cancellation, with the
                # task still reported as cancelled).
                if cancelled_while_cleaning:
                    # Restore the cancellation that the teardown deliberately absorbed, so
                    # the caller still observes this export as cancelled. It is
                    # deliberately not restored when the export already failed: that error
                    # is the more useful report, and a bare CancelledError would hide it
                    # from the dashboard's `except Exception`, leaving the task stuck in
                    # "processing".
                    raise asyncio.CancelledError
                logger.info(f"备份导出完成: {zip_path}")

        return zip_path

    async def _export_main_database(self) -> dict[str, list[dict]]:
        """导出主数据库所有表"""
        export_data: dict[str, list[dict]] = {}

        async with self.main_db.get_db() as session:
            for table_name, model_class in MAIN_DB_MODELS.items():
                try:
                    result = await session.execute(select(model_class))
                    records = result.scalars().all()
                    export_data[table_name] = [
                        self._model_to_dict(record) for record in records
                    ]
                    logger.debug(
                        f"导出表 {table_name}: {len(export_data[table_name])} 条记录"
                    )
                except Exception as e:
                    logger.warning(f"导出表 {table_name} 失败: {e}")
                    export_data[table_name] = []

        return export_data

    async def _export_kb_metadata(self) -> dict[str, list[dict]]:
        """导出知识库元数据库"""
        if not self.kb_manager:
            return {"knowledge_bases": [], "kb_documents": [], "kb_media": []}

        export_data: dict[str, list[dict]] = {}

        async with self.kb_manager.kb_db.get_db() as session:
            for table_name, model_class in KB_METADATA_MODELS.items():
                try:
                    result = await session.execute(select(model_class))
                    records = result.scalars().all()
                    export_data[table_name] = [
                        self._model_to_dict(record) for record in records
                    ]
                    logger.debug(
                        f"导出知识库表 {table_name}: {len(export_data[table_name])} 条记录"
                    )
                except Exception as e:
                    logger.warning(f"导出知识库表 {table_name} 失败: {e}")
                    export_data[table_name] = []

        return export_data

    async def _export_kb_documents(self, kb_helper: Any) -> dict[str, Any]:
        """导出知识库的文档块数据"""
        try:
            from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB

            vec_db: FaissVecDB = kb_helper.vec_db
            if not vec_db or not vec_db.document_storage:
                return {"documents": []}

            # 获取所有文档
            docs = await vec_db.document_storage.get_documents(
                metadata_filters={},
                offset=0,
                limit=None,  # 获取全部
            )

            return {"documents": docs}
        except Exception as e:
            logger.warning(f"导出知识库文档失败: {e}")
            return {"documents": []}

    async def _export_faiss_index(
        self,
        zf: zipfile.ZipFile,
        kb_helper: Any,
        kb_id: str,
    ) -> None:
        """导出 FAISS 索引文件"""
        try:
            index_path = kb_helper.kb_dir / "index.faiss"
            if index_path.exists():
                archive_path = f"databases/kb_{kb_id}/index.faiss"
                await self._run_in_archive_thread(
                    zf.write, str(index_path), archive_path
                )
                logger.debug(f"导出 FAISS 索引: {archive_path}")
        except Exception as e:
            logger.warning(f"导出 FAISS 索引失败: {e}")

    async def _export_kb_media_files(
        self, zf: zipfile.ZipFile, kb_helper: Any, kb_id: str
    ) -> None:
        """导出知识库的多媒体文件"""
        await self._run_in_archive_thread(_write_kb_media_files, zf, kb_helper, kb_id)

    async def _export_directories(
        self, zf: zipfile.ZipFile
    ) -> dict[str, dict[str, int]]:
        """导出插件和其他数据目录

        Args:
            zf: 备份 ZIP 归档对象，所有写入都在归档线程中串行执行

        Returns:
            dict: 每个目录的统计信息 {dir_name: {"files": count, "size": bytes}}
        """
        return await self._run_in_archive_thread(_write_backup_directories, zf)

    async def _export_attachments(
        self, zf: zipfile.ZipFile, attachments: list[dict]
    ) -> None:
        """导出附件文件"""
        await self._run_in_archive_thread(_write_attachments, zf, attachments)

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
        main_data: dict[str, list[dict]],
        kb_meta_data: dict[str, list[dict]],
        dir_stats: dict[str, dict[str, int]] | None = None,
    ) -> dict:
        """生成备份清单"""
        if dir_stats is None:
            dir_stats = {}
        # 收集知识库 ID
        kb_document_tables = {}
        if self.kb_manager:
            for kb_id in self.kb_manager.kb_insts.keys():
                kb_document_tables[kb_id] = "documents"

        # 收集附件文件列表
        attachment_files = []
        for attachment in main_data.get("attachments", []):
            attachment_id = attachment.get("attachment_id", "")
            path = attachment.get("path", "")
            if attachment_id and path:
                ext = os.path.splitext(path)[1]
                attachment_files.append(f"{attachment_id}{ext}")

        # 收集知识库媒体文件
        kb_media_files: dict[str, list[str]] = {}
        if self.kb_manager:
            for kb_id, kb_helper in self.kb_manager.kb_insts.items():
                media_files: list[str] = []
                media_dir = kb_helper.kb_medias_dir
                if media_dir.exists():
                    for root, _, files in os.walk(media_dir):
                        for file in files:
                            media_files.append(file)
                if media_files:
                    kb_media_files[kb_id] = media_files

        manifest = {
            "version": BACKUP_MANIFEST_VERSION,
            "astrbot_version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "origin": "exported",  # 标记备份来源：exported=本实例导出, uploaded=用户上传
            "schema_version": {
                "main_db": "v4",
                "kb_db": "v1",
            },
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


def _write_backup_directories(zf: zipfile.ZipFile) -> dict[str, dict[str, int]]:
    """将插件和其他数据目录写入备份归档。

    这是阻塞式目录遍历与压缩逻辑，必须通过 ``AstrBotExporter._run_in_archive_thread``
    在归档线程中执行，避免冻结事件循环。

    Args:
        zf: 备份 ZIP 归档对象，写入操作由调用方保证串行执行

    Returns:
        dict: 每个目录的统计信息 {dir_name: {"files": count, "size": bytes}}
    """
    stats: dict[str, dict[str, int]] = {}
    backup_directories = get_backup_directories()

    for dir_name, dir_path in backup_directories.items():
        full_path = Path(dir_path)
        if not full_path.exists():
            logger.debug(f"目录不存在，跳过: {full_path}")
            continue

        file_count = 0
        total_size = 0

        try:
            for root, dirs, files in os.walk(full_path):
                # 跳过 __pycache__ 目录
                dirs[:] = [d for d in dirs if d != "__pycache__"]

                for file in files:
                    # 跳过 .pyc 文件
                    if file.endswith(".pyc"):
                        continue

                    file_path = Path(root) / file
                    try:
                        # 计算相对路径
                        rel_path = file_path.relative_to(full_path)
                        archive_path = f"directories/{dir_name}/{rel_path}"
                        zf.write(str(file_path), archive_path)
                        file_count += 1
                        total_size += file_path.stat().st_size
                    except Exception as e:
                        logger.warning(f"导出文件 {file_path} 失败: {e}")

            stats[dir_name] = {"files": file_count, "size": total_size}
            logger.debug(f"导出目录 {dir_name}: {file_count} 个文件, {total_size} 字节")
        except Exception as e:
            logger.warning(f"导出目录 {dir_path} 失败: {e}")
            stats[dir_name] = {"files": 0, "size": 0}

    return stats


def _write_attachments(zf: zipfile.ZipFile, attachments: list[dict]) -> None:
    """将附件文件写入备份归档。

    Args:
        zf: 备份 ZIP 归档对象，写入操作由调用方保证串行执行
        attachments: 附件记录列表，每项包含 path 与 attachment_id 字段
    """
    for attachment in attachments:
        try:
            file_path = attachment.get("path", "")
            if file_path and os.path.exists(file_path):
                # 使用 attachment_id 作为文件名
                attachment_id = attachment.get("attachment_id", "")
                ext = os.path.splitext(file_path)[1]
                archive_path = f"files/attachments/{attachment_id}{ext}"
                zf.write(file_path, archive_path)
        except Exception as e:
            logger.warning(f"导出附件失败: {e}")


def _write_kb_media_files(zf: zipfile.ZipFile, kb_helper: Any, kb_id: str) -> None:
    """将知识库多媒体文件写入备份归档。

    Args:
        zf: 备份 ZIP 归档对象，写入操作由调用方保证串行执行
        kb_helper: 知识库实例，提供 kb_dir 与 kb_medias_dir 路径
        kb_id: 知识库 ID，用于生成归档内的相对路径
    """
    try:
        media_dir = kb_helper.kb_medias_dir
        if not media_dir.exists():
            return

        for root, _, files in os.walk(media_dir):
            for file in files:
                file_path = Path(root) / file
                # 计算相对路径
                rel_path = file_path.relative_to(kb_helper.kb_dir)
                archive_path = f"files/kb_media/{kb_id}/{rel_path}"
                zf.write(str(file_path), archive_path)
    except Exception as e:
        logger.warning(f"导出知识库媒体文件失败: {e}")
