"""AstrBot 数据导入器

负责从 ZIP 备份文件恢复所有数据。
导入时进行版本校验：
- 主版本（前两位）不同时直接拒绝导入
- 小版本（第三位）不同时提示警告，用户可选择强制导入
- 版本匹配时也需要用户确认
"""

import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
)
from astrbot.core.utils.version_comparator import VersionComparator

# 从共享常量模块导入
from .constants import (
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    get_backup_directories,
)

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


def _get_major_version(version_str: str) -> str:
    """提取版本的主版本部分（前两位）

    Args:
        version_str: 版本字符串，如 "4.9.1", "4.10.0-beta"

    Returns:
        主版本字符串，如 "4.9", "4.10"
    """
    if not version_str:
        return "0.0"
    # 移除 v 前缀和预发布标签
    version = version_str.lower().replace("v", "").split("-")[0].split("+")[0]
    parts = [p for p in version.split(".") if p]  # 过滤空字符串
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    elif len(parts) == 1 and parts[0]:
        return f"{parts[0]}.0"
    return "0.0"


CMD_CONFIG_FILE_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")
KB_PATH = get_astrbot_knowledge_base_path()


@dataclass
class ImportPreCheckResult:
    """导入预检查结果

    用于在实际导入前检查备份文件的版本兼容性，
    并返回确认信息让用户决定是否继续导入。
    """

    # 检查是否通过（文件有效且版本可导入）
    valid: bool = False
    # 是否可以导入（版本兼容）
    can_import: bool = False
    # 版本状态: match（完全匹配）, minor_diff（小版本差异）, major_diff（主版本不同，拒绝）
    version_status: str = ""
    # 备份文件中的 AstrBot 版本
    backup_version: str = ""
    # 当前运行的 AstrBot 版本
    current_version: str = VERSION
    # 备份创建时间
    backup_time: str = ""
    # 确认消息（显示给用户）
    confirm_message: str = ""
    # 警告消息列表
    warnings: list[str] = field(default_factory=list)
    # 错误消息（如果检查失败）
    error: str = ""
    # 备份包含的内容摘要
    backup_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "can_import": self.can_import,
            "version_status": self.version_status,
            "backup_version": self.backup_version,
            "current_version": self.current_version,
            "backup_time": self.backup_time,
            "confirm_message": self.confirm_message,
            "warnings": self.warnings,
            "error": self.error,
            "backup_summary": self.backup_summary,
        }


class ImportResult:
    """导入结果"""

    def __init__(self):
        self.success = True
        self.imported_tables: dict[str, int] = {}
        self.imported_files: dict[str, int] = {}
        self.imported_directories: dict[str, int] = {}
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.success = False
        logger.error(msg)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "imported_tables": self.imported_tables,
            "imported_files": self.imported_files,
            "imported_directories": self.imported_directories,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class AstrBotImporter:
    """AstrBot 数据导入器

    导入备份文件中的所有数据，包括：
    - 主数据库所有表
    - 知识库元数据和文档
    - 配置文件
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
        kb_root_dir: str = KB_PATH,
    ):
        self.main_db = main_db
        self.kb_manager = kb_manager
        self.config_path = config_path
        self.kb_root_dir = kb_root_dir

    def pre_check(self, zip_path: str) -> ImportPreCheckResult:
        """预检查备份文件

        在实际导入前检查备份文件的有效性和版本兼容性。
        返回检查结果供前端显示确认对话框。

        Args:
            zip_path: ZIP 备份文件路径

        Returns:
            ImportPreCheckResult: 预检查结果
        """
        result = ImportPreCheckResult()
        result.current_version = VERSION

        if not os.path.exists(zip_path):
            result.error = f"备份文件不存在: {zip_path}"
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 读取 manifest
                try:
                    manifest_data = zf.read("manifest.json")
                    manifest = json.loads(manifest_data)
                except KeyError:
                    result.error = "备份文件缺少 manifest.json，不是有效的 AstrBot 备份"
                    return result
                except json.JSONDecodeError as e:
                    result.error = f"manifest.json 格式错误: {e}"
                    return result

                # 提取基本信息
                result.backup_version = manifest.get("astrbot_version", "未知")
                result.backup_time = manifest.get("exported_at", "未知")
                result.valid = True

                # 构建备份摘要
                result.backup_summary = {
                    "tables": list(manifest.get("tables", {}).keys()),
                    "has_knowledge_bases": manifest.get("has_knowledge_bases", False),
                    "has_config": manifest.get("has_config", False),
                    "directories": manifest.get("directories", []),
                }

                # 检查版本兼容性
                version_check = self._check_version_compatibility(result.backup_version)
                result.version_status = version_check["status"]
                result.can_import = version_check["can_import"]

                # 版本信息由前端根据 version_status 和 i18n 生成显示
                # 不再将版本消息添加到 warnings 列表中，避免中文硬编码
                # warnings 列表保留用于其他非版本相关的警告

                return result

        except zipfile.BadZipFile:
            result.error = "无效的 ZIP 文件"
            return result
        except Exception as e:
            result.error = f"检查备份文件失败: {e}"
            return result

    def _check_version_compatibility(self, backup_version: str) -> dict:
        """检查版本兼容性

        规则：
        - 主版本（前两位，如 4.9）必须一致，否则拒绝
        - 小版本（第三位，如 4.9.1 vs 4.9.2）不同时，警告但允许导入

        Returns:
            dict: {status, can_import, message}
        """
        if not backup_version:
            return {
                "status": "major_diff",
                "can_import": False,
                "message": "备份文件缺少版本信息",
            }

        # 提取主版本（前两位）进行比较
        backup_major = _get_major_version(backup_version)
        current_major = _get_major_version(VERSION)

        # 比较主版本
        if VersionComparator.compare_version(backup_major, current_major) != 0:
            return {
                "status": "major_diff",
                "can_import": False,
                "message": (
                    f"主版本不兼容: 备份版本 {backup_version}, 当前版本 {VERSION}。"
                    f"跨主版本导入可能导致数据损坏，请使用相同主版本的 AstrBot。"
                ),
            }

        # 比较完整版本
        version_cmp = VersionComparator.compare_version(backup_version, VERSION)
        if version_cmp != 0:
            return {
                "status": "minor_diff",
                "can_import": True,
                "message": (
                    f"小版本差异: 备份版本 {backup_version}, 当前版本 {VERSION}。"
                ),
            }

        return {
            "status": "match",
            "can_import": True,
            "message": "版本匹配",
        }

    async def import_all(
        self,
        zip_path: str,
        mode: str = "replace",  # "replace" 清空后导入
        progress_callback: Any | None = None,
    ) -> ImportResult:
        """从 ZIP 文件导入所有数据

        Args:
            zip_path: ZIP 备份文件路径
            mode: 导入模式，目前仅支持 "replace"（清空后导入）
            progress_callback: 进度回调函数，接收参数 (stage, current, total, message)

        Returns:
            ImportResult: 导入结果
        """
        result = ImportResult()

        if not os.path.exists(zip_path):
            result.add_error(f"备份文件不存在: {zip_path}")
            return result

        logger.info(f"开始从 {zip_path} 导入备份")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # 1. 读取并验证 manifest
                if progress_callback:
                    await progress_callback("validate", 0, 100, "正在验证备份文件...")

                try:
                    manifest_data = zf.read("manifest.json")
                    manifest = json.loads(manifest_data)
                except KeyError:
                    result.add_error("备份文件缺少 manifest.json")
                    return result
                except json.JSONDecodeError as e:
                    result.add_error(f"manifest.json 格式错误: {e}")
                    return result

                # 版本校验
                try:
                    self._validate_version(manifest)
                except ValueError as e:
                    result.add_error(str(e))
                    return result

                if progress_callback:
                    await progress_callback("validate", 100, 100, "验证完成")

                # 2. 导入主数据库
                if progress_callback:
                    await progress_callback("main_db", 0, 100, "正在导入主数据库...")

                try:
                    main_data_content = zf.read("databases/main_db.json")
                    main_data = json.loads(main_data_content)

                    if mode == "replace":
                        await self._clear_main_db()

                    imported = await self._import_main_database(main_data)
                    result.imported_tables.update(imported)
                except Exception as e:
                    result.add_error(f"导入主数据库失败: {e}")
                    return result

                if progress_callback:
                    await progress_callback("main_db", 100, 100, "主数据库导入完成")

                # 3. 导入知识库
                if self.kb_manager and "databases/kb_metadata.json" in zf.namelist():
                    if progress_callback:
                        await progress_callback("kb", 0, 100, "正在导入知识库...")

                    try:
                        kb_meta_content = zf.read("databases/kb_metadata.json")
                        kb_meta_data = json.loads(kb_meta_content)

                        if mode == "replace":
                            await self._clear_kb_data()

                        await self._import_knowledge_bases(zf, kb_meta_data, result)
                    except Exception as e:
                        result.add_warning(f"导入知识库失败: {e}")

                    if progress_callback:
                        await progress_callback("kb", 100, 100, "知识库导入完成")

                # 4. 导入配置文件
                if progress_callback:
                    await progress_callback("config", 0, 100, "正在导入配置文件...")

                if "config/cmd_config.json" in zf.namelist():
                    try:
                        config_content = zf.read("config/cmd_config.json")
                        # 备份现有配置
                        if os.path.exists(self.config_path):
                            backup_path = f"{self.config_path}.bak"
                            shutil.copy2(self.config_path, backup_path)

                        with open(self.config_path, "wb") as f:
                            f.write(config_content)
                        result.imported_files["config"] = 1
                    except Exception as e:
                        result.add_warning(f"导入配置文件失败: {e}")

                if progress_callback:
                    await progress_callback("config", 100, 100, "配置文件导入完成")

                # 5. 导入附件文件
                if progress_callback:
                    await progress_callback("attachments", 0, 100, "正在导入附件...")

                attachment_count = await self._import_attachments(
                    zf, main_data.get("attachments", [])
                )
                result.imported_files["attachments"] = attachment_count

                if progress_callback:
                    await progress_callback("attachments", 100, 100, "附件导入完成")

                # 6. 导入插件和其他目录
                if progress_callback:
                    await progress_callback(
                        "directories", 0, 100, "正在导入插件和数据目录..."
                    )

                dir_stats = await self._import_directories(zf, manifest, result)
                result.imported_directories = dir_stats

                if progress_callback:
                    await progress_callback("directories", 100, 100, "目录导入完成")

            logger.info(f"备份导入完成: {result.to_dict()}")
            return result

        except zipfile.BadZipFile:
            result.add_error("无效的 ZIP 文件")
            return result
        except Exception as e:
            result.add_error(f"导入失败: {e}")
            return result

    def _validate_version(self, manifest: dict) -> None:
        """验证版本兼容性 - 仅允许相同主版本导入

        注意：此方法仅在 import_all 中调用，用于双重校验。
        前端应先调用 pre_check 获取详细的版本信息并让用户确认。
        """
        backup_version = manifest.get("astrbot_version")
        if not backup_version:
            raise ValueError("备份文件缺少版本信息")

        # 使用新的版本兼容性检查
        version_check = self._check_version_compatibility(backup_version)

        if version_check["status"] == "major_diff":
            raise ValueError(version_check["message"])

        # minor_diff 和 match 都允许导入
        if version_check["status"] == "minor_diff":
            logger.warning(f"版本差异警告: {version_check['message']}")

    async def _clear_main_db(self) -> None:
        """清空主数据库所有表"""
        async with self.main_db.get_db() as session:
            async with session.begin():
                for table_name, model_class in MAIN_DB_MODELS.items():
                    try:
                        await session.execute(delete(model_class))
                        logger.debug(f"已清空表 {table_name}")
                    except Exception as e:
                        logger.warning(f"清空表 {table_name} 失败: {e}")

    async def _clear_kb_data(self) -> None:
        """清空知识库数据"""
        if not self.kb_manager:
            return

        # 清空知识库元数据表
        async with self.kb_manager.kb_db.get_db() as session:
            async with session.begin():
                for table_name, model_class in KB_METADATA_MODELS.items():
                    try:
                        await session.execute(delete(model_class))
                        logger.debug(f"已清空知识库表 {table_name}")
                    except Exception as e:
                        logger.warning(f"清空知识库表 {table_name} 失败: {e}")

        # 删除知识库文件目录
        for kb_id in list(self.kb_manager.kb_insts.keys()):
            try:
                kb_helper = self.kb_manager.kb_insts[kb_id]
                await kb_helper.terminate()
                if kb_helper.kb_dir.exists():
                    shutil.rmtree(kb_helper.kb_dir)
            except Exception as e:
                logger.warning(f"清理知识库 {kb_id} 失败: {e}")

        self.kb_manager.kb_insts.clear()

    async def _import_main_database(
        self, data: dict[str, list[dict]]
    ) -> dict[str, int]:
        """导入主数据库数据"""
        imported: dict[str, int] = {}

        async with self.main_db.get_db() as session:
            async with session.begin():
                for table_name, rows in data.items():
                    model_class = MAIN_DB_MODELS.get(table_name)
                    if not model_class:
                        logger.warning(f"未知的表: {table_name}")
                        continue

                    count = 0
                    for row in rows:
                        try:
                            # 转换 datetime 字符串为 datetime 对象
                            row = self._convert_datetime_fields(row, model_class)
                            obj = model_class(**row)
                            session.add(obj)
                            count += 1
                        except Exception as e:
                            logger.warning(f"导入记录到 {table_name} 失败: {e}")

                    imported[table_name] = count
                    logger.debug(f"导入表 {table_name}: {count} 条记录")

        return imported

    async def _import_knowledge_bases(
        self,
        zf: zipfile.ZipFile,
        kb_meta_data: dict[str, list[dict]],
        result: ImportResult,
    ) -> None:
        """导入知识库数据"""
        if not self.kb_manager:
            return

        # 1. 导入知识库元数据
        async with self.kb_manager.kb_db.get_db() as session:
            async with session.begin():
                for table_name, rows in kb_meta_data.items():
                    model_class = KB_METADATA_MODELS.get(table_name)
                    if not model_class:
                        continue

                    count = 0
                    for row in rows:
                        try:
                            row = self._convert_datetime_fields(row, model_class)
                            obj = model_class(**row)
                            session.add(obj)
                            count += 1
                        except Exception as e:
                            logger.warning(f"导入知识库记录到 {table_name} 失败: {e}")

                    result.imported_tables[f"kb_{table_name}"] = count

        # 2. 导入每个知识库的文档和文件
        for kb_data in kb_meta_data.get("knowledge_bases", []):
            kb_id = kb_data.get("kb_id")
            if not kb_id:
                continue

            # 创建知识库目录
            kb_dir = Path(self.kb_root_dir) / kb_id
            kb_dir.mkdir(parents=True, exist_ok=True)

            # 导入文档数据
            doc_path = f"databases/kb_{kb_id}/documents.json"
            if doc_path in zf.namelist():
                try:
                    doc_content = zf.read(doc_path)
                    doc_data = json.loads(doc_content)

                    # 导入到文档存储数据库
                    await self._import_kb_documents(kb_id, doc_data)
                except Exception as e:
                    result.add_warning(f"导入知识库 {kb_id} 的文档失败: {e}")

            # 导入 FAISS 索引
            faiss_path = f"databases/kb_{kb_id}/index.faiss"
            if faiss_path in zf.namelist():
                try:
                    target_path = kb_dir / "index.faiss"
                    with zf.open(faiss_path) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())
                except Exception as e:
                    result.add_warning(f"导入知识库 {kb_id} 的 FAISS 索引失败: {e}")

            # 导入媒体文件
            media_prefix = f"files/kb_media/{kb_id}/"
            for name in zf.namelist():
                if name.startswith(media_prefix):
                    try:
                        rel_path = name[len(media_prefix) :]
                        target_path = kb_dir / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(name) as src, open(target_path, "wb") as dst:
                            dst.write(src.read())
                    except Exception as e:
                        result.add_warning(f"导入媒体文件 {name} 失败: {e}")

        # 3. 重新加载知识库实例
        await self.kb_manager.load_kbs()

    async def _import_kb_documents(self, kb_id: str, doc_data: dict) -> None:
        """导入知识库文档到向量数据库"""
        from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage

        kb_dir = Path(self.kb_root_dir) / kb_id
        doc_db_path = kb_dir / "doc.db"

        # 初始化文档存储
        doc_storage = DocumentStorage(str(doc_db_path))
        await doc_storage.initialize()

        try:
            documents = doc_data.get("documents", [])
            for doc in documents:
                try:
                    await doc_storage.insert_document(
                        doc_id=doc.get("doc_id", ""),
                        text=doc.get("text", ""),
                        metadata=json.loads(doc.get("metadata", "{}")),
                    )
                except Exception as e:
                    logger.warning(f"导入文档块失败: {e}")
        finally:
            await doc_storage.close()

    async def _import_attachments(
        self,
        zf: zipfile.ZipFile,
        attachments: list[dict],
    ) -> int:
        """导入附件文件"""
        count = 0

        attachments_dir = Path(self.config_path).parent / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        attachment_prefix = "files/attachments/"
        for name in zf.namelist():
            if name.startswith(attachment_prefix) and name != attachment_prefix:
                try:
                    # 从附件记录中找到原始路径
                    attachment_id = os.path.splitext(os.path.basename(name))[0]
                    original_path = None
                    for att in attachments:
                        if att.get("attachment_id") == attachment_id:
                            original_path = att.get("path")
                            break

                    if original_path:
                        target_path = Path(original_path)
                    else:
                        target_path = attachments_dir / os.path.basename(name)

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())
                    count += 1
                except Exception as e:
                    logger.warning(f"导入附件 {name} 失败: {e}")

        return count

    async def _import_directories(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
        result: ImportResult,
    ) -> dict[str, int]:
        """导入插件和其他数据目录

        Args:
            zf: ZIP 文件对象
            manifest: 备份清单
            result: 导入结果对象

        Returns:
            dict: 每个目录导入的文件数量
        """
        dir_stats: dict[str, int] = {}

        # 检查备份版本是否支持目录备份（需要版本 >= 1.1）
        backup_version = manifest.get("version", "1.0")
        if VersionComparator.compare_version(backup_version, "1.1") < 0:
            logger.info("备份版本不支持目录备份，跳过目录导入")
            return dir_stats

        backed_up_dirs = manifest.get("directories", [])
        backup_directories = get_backup_directories()

        for dir_name in backed_up_dirs:
            if dir_name not in backup_directories:
                result.add_warning(f"未知的目录类型: {dir_name}")
                continue

            target_dir = Path(backup_directories[dir_name])
            archive_prefix = f"directories/{dir_name}/"

            file_count = 0

            try:
                # 获取该目录下的所有文件
                dir_files = [
                    name
                    for name in zf.namelist()
                    if name.startswith(archive_prefix) and name != archive_prefix
                ]

                if not dir_files:
                    continue

                # 备份现有目录（如果存在）
                if target_dir.exists():
                    backup_path = Path(f"{target_dir}.bak")
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    shutil.move(str(target_dir), str(backup_path))
                    logger.debug(f"已备份现有目录 {target_dir} 到 {backup_path}")

                # 创建目标目录
                target_dir.mkdir(parents=True, exist_ok=True)

                # 解压文件
                for name in dir_files:
                    try:
                        # 计算相对路径
                        rel_path = name[len(archive_prefix) :]
                        if not rel_path:  # 跳过目录条目
                            continue

                        target_path = target_dir / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        with zf.open(name) as src, open(target_path, "wb") as dst:
                            dst.write(src.read())
                        file_count += 1
                    except Exception as e:
                        result.add_warning(f"导入文件 {name} 失败: {e}")

                dir_stats[dir_name] = file_count
                logger.debug(f"导入目录 {dir_name}: {file_count} 个文件")

            except Exception as e:
                result.add_warning(f"导入目录 {dir_name} 失败: {e}")
                dir_stats[dir_name] = 0

        return dir_stats

    def _convert_datetime_fields(self, row: dict, model_class: type) -> dict:
        """转换 datetime 字符串字段为 datetime 对象"""
        result = row.copy()

        # 获取模型的 datetime 字段
        from sqlalchemy import inspect as sa_inspect

        try:
            mapper = sa_inspect(model_class)
            for column in mapper.columns:
                if column.name in result and result[column.name] is not None:
                    # 检查是否是 datetime 类型的列
                    from sqlalchemy import DateTime

                    if isinstance(column.type, DateTime):
                        value = result[column.name]
                        if isinstance(value, str):
                            # 解析 ISO 格式的日期时间字符串
                            result[column.name] = datetime.fromisoformat(value)
        except Exception:
            pass

        return result
