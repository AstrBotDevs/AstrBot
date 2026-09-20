"""AstrBot 数据导入器

负责从 ZIP 备份文件恢复所有数据。
导入时进行版本校验：
- 主版本（前两位）不同时直接拒绝导入
- 小版本（第三位）不同时提示警告，用户可选择强制导入
- 版本匹配时也需要用户确认
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
import zlib
from collections.abc import Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from astrbot.core.utils.io import ensure_dir
from astrbot.core.utils.version_comparator import VersionComparator

# 从共享常量模块导入
from .constants import (
    HARD_FAIL_COMPONENTS,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    component_of_entry,
    derive_component_states,
    get_backup_components,
    get_backup_directories,
)
from .resources import (
    MAX_JSON_RECORD_BYTES,
    BackupTableStream,
    backup_json_limit,
    backup_row_batches,
    open_backup,
    read_backup_json,
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


def _validate_path_within(target_path: Path, base_dir: Path) -> bool:
    """Validate that target_path is within base_dir after resolving symlinks.

    Prevents path traversal attacks (CWE-22) by ensuring the resolved
    target path is relative to the resolved base directory.
    """
    try:
        resolved = target_path.resolve(strict=False)
        base_resolved = base_dir.resolve(strict=False)
        return resolved.is_relative_to(base_resolved)
    except (OSError, ValueError):
        return False


CMD_CONFIG_FILE_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")
KB_PATH = get_astrbot_knowledge_base_path()
DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT = 5
PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV = (
    "ASTRBOT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT"
)


def _load_platform_stats_invalid_count_warn_limit() -> int:
    raw_value = os.getenv(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV)
    if raw_value is None:
        return DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT

    try:
        value = int(raw_value)
        if value < 0:
            raise ValueError("negative")
        return value
    except (TypeError, ValueError):
        logger.warning(
            "Invalid env %s=%r, fallback to default %d",
            PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV,
            raw_value,
            DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT,
        )
        return DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT


PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT = (
    _load_platform_stats_invalid_count_warn_limit()
)


class _InvalidCountWarnLimiter:
    """Rate-limit warnings for invalid platform_stats count values."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._count = 0
        self._suppression_logged = False

    def warn_invalid_count(self, value: Any, key_for_log: tuple[Any, ...]) -> None:
        if self.limit > 0:
            if self._count < self.limit:
                logger.warning(
                    "Invalid platform_stats count; using 0: value=%r, key=%s",
                    value,
                    key_for_log,
                )
                self._count += 1
                if self._count == self.limit and not self._suppression_logged:
                    logger.warning(
                        "Invalid platform_stats count warning limit reached (%d); suppressing further warnings",
                        self.limit,
                    )
                    self._suppression_logged = True
            return

        if not self._suppression_logged:
            # limit <= 0: emit only one suppression warning.
            logger.warning(
                "Invalid platform_stats count warning limit reached (%d); suppressing further warnings",
                self.limit,
            )
            self._suppression_logged = True


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
    # 可恢复的组件（声明且条目完整），按 ZIP 实际条目推导
    available_components: list[str] = field(default_factory=list)
    # 已声明但条目缺失的损坏组件（不可恢复，默认恢复遇之中止）
    broken_components: list[str] = field(default_factory=list)

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
            "available_components": self.available_components,
            "broken_components": self.broken_components,
        }


class ImportResult:
    """导入结果"""

    def __init__(self) -> None:
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


class DatabaseClearError(RuntimeError):
    """Raised when clearing the main database in replace mode fails."""


class AstrBotImporter:
    """Restore selected database, configuration, attachment, and extension data.

    Attachments include legacy WebChat images in data/webchat/imgs; upload
    fragments in data/webchat/.chunks are excluded.
    """

    def __init__(
        self,
        main_db: BaseDatabase,
        kb_manager: "KnowledgeBaseManager | None" = None,
        config_path: str = CMD_CONFIG_FILE_PATH,
        kb_root_dir: str = KB_PATH,
    ) -> None:
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
            result.error = f"Backup file does not exist: {zip_path}"
            return result

        try:
            with open_backup(zip_path) as zf:
                # 读取 manifest
                try:
                    manifest = read_backup_json(zf, "manifest.json")
                except KeyError:
                    result.error = "Invalid AstrBot backup: manifest.json is missing"
                    return result
                except json.JSONDecodeError as e:
                    result.error = f"Invalid manifest.json: {e}"
                    return result

                # 提取基本信息
                result.backup_version = manifest.get("astrbot_version", "未知")
                result.backup_time = manifest.get("exported_at", "未知")
                result.valid = True

                # 构建备份摘要：只信 ZIP 实际条目，不信 manifest 自报字段
                namelist = zf.namelist()
                result.backup_summary = {
                    "tables": list(manifest.get("tables", {}).keys()),
                    "has_knowledge_bases": "databases/kb_metadata.json" in namelist,
                    "has_config": "config/cmd_config.json" in namelist,
                    "directories": manifest.get("directories", []),
                }

                # 三态推导可用/损坏组件
                available, broken = derive_component_states(manifest, namelist)
                result.available_components = available
                result.broken_components = broken
                if any(n.startswith("directories/webchat/.chunks/") for n in namelist):
                    result.warnings.append(
                        "WebChat upload fragments cannot restore upload sessions and will be ignored."
                    )
                if not available and not broken:
                    result.warnings.append("This backup contains no restorable data.")

                # 检查版本兼容性
                version_check = self._check_version_compatibility(result.backup_version)
                result.version_status = version_check["status"]
                result.can_import = version_check["can_import"]

                # 版本信息由前端根据 version_status 和 i18n 生成显示
                # 不再将版本消息添加到 warnings 列表中，避免中文硬编码
                # warnings 列表保留用于其他非版本相关的警告

                return result

        except zipfile.BadZipFile:
            result.error = "Invalid ZIP file"
            return result
        except Exception as e:
            result.error = f"Failed to inspect backup file: {e}"
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
                "message": "Backup is missing version information",
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
                    f"Incompatible major version: backup={backup_version}, current={VERSION}. "
                    f"Importing across major versions may corrupt data; use the same AstrBot major version."
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
        components: list[str] | None = None,
    ) -> ImportResult:
        """从 ZIP 文件导入选定组件的数据

        两阶段执行：阶段一全量预检（条目 hash、聚合 hash、JSON 结构干跑，
        零修改），阶段二落盘（临时文件原子替换、主库单事务）。

        Args:
            zip_path: ZIP 备份文件路径
            mode: 导入模式，目前仅支持 "replace"（清空后导入）
            progress_callback: 进度回调函数，接收参数 (stage, current, total, message)
            components: 要恢复的组件 id 列表。None 恢复全部可用组件
                （遇 broken 组件中止）；空列表直接拒绝。

        Returns:
            ImportResult: 导入结果
        """
        result = ImportResult()

        if not os.path.exists(zip_path):
            result.add_error(f"Backup file does not exist: {zip_path}")
            return result

        logger.info(f"Starting backup import from {zip_path}")

        try:
            with open_backup(zip_path) as zf:
                # 1. 读取并验证 manifest
                if progress_callback:
                    await progress_callback("validate", 0, 100, "正在验证备份文件...")

                try:
                    manifest = read_backup_json(zf, "manifest.json")
                except KeyError:
                    result.add_error("Backup is missing manifest.json")
                    return result
                except json.JSONDecodeError as e:
                    result.add_error(f"Invalid manifest.json: {e}")
                    return result

                # 版本校验
                try:
                    self._validate_version(manifest)
                except ValueError as e:
                    result.add_error(str(e))
                    return result

                namelist = zf.namelist()
                available, broken = derive_component_states(manifest, namelist)

                selected = self._resolve_selection(
                    components, available, broken, result
                )
                if selected is None:
                    return result

                # Validate every selected component before making any changes.
                precheck = await self._run_pre_verify(
                    zf, manifest, namelist, selected, result, progress_callback
                )
                if precheck is None:
                    return result

                if progress_callback:
                    await progress_callback("validate", 100, 100, "验证完成")

                skip_components = precheck["skip_components"]
                bad_entries = precheck["bad_entries"]

                attachment_rows = []
                attachment_paths = (
                    {
                        Path(name).stem: None
                        for name in namelist
                        if name.startswith("files/attachments/")
                        and not name.endswith("/")
                    }
                    if "attachments" in selected
                    and "attachments" not in skip_components
                    else None
                )

                # ========== 阶段二：落盘 ==========

                # 2. 导入主数据库
                if "database" in selected:
                    if progress_callback:
                        await progress_callback(
                            "main_db", 0, 100, "正在导入主数据库..."
                        )

                    try:
                        main_data = precheck["json"].pop("main_db")
                        imported = await self._import_main_database(
                            main_data,
                            clear=(mode == "replace"),
                            attachment_paths=attachment_paths,
                        )
                        attachment_rows = (
                            {"attachment_id": key, "path": value}
                            for key, value in (attachment_paths or {}).items()
                            if value is not None
                        )
                        del main_data
                        result.imported_tables.update(imported)
                    except DatabaseClearError as e:
                        result.add_error(f"Failed to clear main database: {e}")
                        return result
                    except Exception as e:
                        result.add_error(
                            f"Main database import failed (transaction rolled back): {e}"
                        )
                        return result

                    if progress_callback:
                        await progress_callback("main_db", 100, 100, "主数据库导入完成")

                # 3. 导入知识库
                if "knowledge_base" in selected and self.kb_manager:
                    if progress_callback:
                        await progress_callback("kb", 0, 100, "正在导入知识库...")

                    try:
                        await self._import_knowledge_bases(
                            zf,
                            precheck["json"].pop("kb_metadata"),
                            result,
                            clear=(mode == "replace"),
                            json_ctx=precheck["json"],
                            bad_entries=bad_entries.get("knowledge_base", []),
                        )
                    except Exception as e:
                        result.add_warning(f"Knowledge base import failed: {e}")

                    if progress_callback:
                        await progress_callback("kb", 100, 100, "知识库导入完成")

                # 4. 导入配置文件
                if "cmd_config" in selected:
                    if progress_callback:
                        await progress_callback("config", 0, 100, "正在导入配置文件...")

                    try:
                        # 备份现有配置
                        if os.path.exists(self.config_path):
                            backup_path = f"{self.config_path}.bak"
                            shutil.copy2(self.config_path, backup_path)

                        # 阶段一已验证 hash 与结构，经临时文件原子替换
                        self._write_entry_safe(
                            zf, "config/cmd_config.json", Path(self.config_path)
                        )
                        result.imported_files["config"] = 1
                    except Exception as e:
                        result.add_warning(f"Configuration import failed: {e}")

                    if progress_callback:
                        await progress_callback("config", 100, 100, "配置文件导入完成")

                # 5. 导入附件文件
                if "attachments" in selected and "attachments" not in skip_components:
                    if progress_callback:
                        await progress_callback(
                            "attachments", 0, 100, "正在导入附件..."
                        )

                    # 附件原始路径来自主库 attachments 表；未恢复主库时仅作
                    # 路径提示读取（路径仍强制校验在附件目录内）。
                    if (
                        "database" not in selected
                        and attachment_paths
                        and "databases/main_db.json" in namelist
                    ):
                        try:
                            hint_data = read_backup_json(zf, "databases/main_db.json")
                            attachment_rows = hint_data.get("attachments", [])
                            del hint_data
                        except Exception as exc:
                            result.add_warning(f"Attachment path hints skipped: {exc}")
                            attachment_rows = []

                    attachment_count = await self._import_attachments(
                        zf, attachment_rows, bad_entries.get("attachments", [])
                    )
                    result.imported_files["attachments"] = attachment_count

                    if progress_callback:
                        await progress_callback("attachments", 100, 100, "附件导入完成")

                # 6. 导入插件和其他目录
                selected_dirs = [
                    d
                    for d in get_backup_directories()
                    if ("attachments" if d == "webchat" else d) in selected
                    and ("attachments" if d == "webchat" else d) not in skip_components
                ]
                if selected_dirs:
                    if progress_callback:
                        await progress_callback(
                            "directories", 0, 100, "正在导入插件和数据目录..."
                        )

                    dir_stats = await self._import_directories(
                        zf,
                        manifest,
                        result,
                        selected_dirs=selected_dirs,
                        bad_entries=bad_entries,
                    )
                    result.imported_directories = dir_stats

                    if progress_callback:
                        await progress_callback("directories", 100, 100, "目录导入完成")

            logger.info(
                "Backup import finished: success=%s, warnings=%d, errors=%d",
                result.success,
                len(result.warnings),
                len(result.errors),
            )
            return result

        except zipfile.BadZipFile:
            result.add_error("Invalid ZIP file")
            return result
        except Exception as e:
            result.add_error(f"Backup import failed: {e}")
            return result

    def _resolve_selection(
        self,
        components: list[str] | None,
        available: list[str],
        broken: list[str],
        result: ImportResult,
    ) -> set[str] | None:
        """Resolve the requested component selection.

        Broken components are checked FIRST so an explicitly requested broken
        component is never downgraded to a plain "unavailable" skip.

        Args:
            components: Requested ids, or None for the default restore.
            available: Components whose required entries exist.
            broken: Declared-but-missing components.
            result: Import result collecting warnings/errors.

        Returns:
            The effective component set, or None when the import must not
            start (error already recorded, nothing modified).
        """
        if components is not None and len(components) == 0:
            result.add_error(
                "No components selected for restoration (components is empty)"
            )
            return None

        if components is None:
            # Default restore must not silently drop corrupted components.
            if broken:
                result.add_error(
                    f"Declared components have missing entries: {sorted(broken)}. "
                    "Default restoration cannot skip broken components; explicitly select available components to restore."
                )
                return None
            if not available:
                result.add_error("This backup contains no restorable data")
                return None
            return set(available)

        requested = set(components)
        unknown = requested - set(get_backup_components())
        if unknown:
            result.add_warning(f"Ignoring unknown component ids: {sorted(unknown)}")
            requested -= unknown

        # Explicit selection legitimately excludes broken components, but
        # the exclusion is always noted — never silent.
        excluded_broken = set(broken) - requested
        if excluded_broken:
            result.add_warning(
                f"Declared components have missing entries; excluded from this restore: {sorted(excluded_broken)}"
            )

        broken_req = requested & set(broken)
        hard_broken = broken_req & HARD_FAIL_COMPONENTS
        if hard_broken:
            result.add_error(
                f"Requested declared components have missing entries: {sorted(hard_broken)}; import aborted"
            )
            return None
        for comp in broken_req - HARD_FAIL_COMPONENTS:
            result.add_error(
                f"Requested declared component {comp} has missing entries; skipped"
            )
        requested -= broken_req

        unavailable = requested - set(available)
        if unavailable:
            result.add_warning(
                f"Skipping components absent from the backup: {sorted(unavailable)}"
            )
            requested -= unavailable

        if not requested:
            result.add_error("None of the requested components can be restored")
            return None
        return requested

    def _hash_entry(self, zf: zipfile.ZipFile, name: str) -> str:
        """Stream an entry and return its hex sha256 (constant memory)."""
        hasher = hashlib.sha256()
        with zf.open(name) as src:
            while chunk := src.read(1 << 20):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _load_json_entry(
        self, zf: zipfile.ZipFile, name: str, result: ImportResult
    ) -> Any | None:
        """Read and parse a JSON entry, recording an error on failure.

        A literal "null" payload is structurally invalid for every JSON
        entry consumed here and is rejected explicitly — never confused
        with a valid empty dump or a parse failure.
        """
        try:
            value = read_backup_json(zf, name)
        except (KeyError, ValueError) as e:
            result.add_error(f"Failed to parse JSON entry {name}: {e}")
            return None
        if value is None:
            result.add_error(f"JSON entry is null: {name}")
            return None
        return value

    def _dry_run_table_dump(
        self,
        data: Any,
        models: dict[str, type],
        label: str,
        result: ImportResult,
        preprocess: bool = False,
    ) -> bool:
        """Validate a table dump: root dict[str, list[dict]] plus per-row checks.

        Every row goes through the same normalization as the real import
        (strict datetime conversion — conversion failures are errors here,
        not swallowed) followed by explicit model_validate(). Note that the
        plain SQLModel constructor bypasses pydantic validation for table
        models, so only model_validate can reject bad values.
        """
        if not isinstance(data, (dict, BackupTableStream)):
            result.add_error(f"Invalid {label} structure: root must be an object")
            return False
        for table_name, rows in data.items():
            model_class = models.get(table_name)
            if model_class is None:
                continue  # unknown tables are skipped at import with a warning
            if not isinstance(data, BackupTableStream) and not isinstance(rows, list):
                result.add_error(
                    f"Invalid {label} structure: table {table_name} must be an array"
                )
                return False
            if preprocess:
                rows = self._preprocess_main_table_rows(table_name, rows)
            # Apply the same normalized byte budget as the write phase before
            # any component can clear existing data.
            for row in (row for batch in backup_row_batches(rows) for row in batch):
                if not isinstance(row, dict):
                    result.add_error(
                        f"Invalid {label} structure: table {table_name} contains a non-object record"
                    )
                    return False
                try:
                    row = self._convert_datetime_fields(row, model_class, strict=True)
                    model_class.model_validate(row)
                except Exception as e:
                    result.add_error(
                        f"Record validation failed in {label} table {table_name}: {e}"
                    )
                    return False
        return True

    def _dry_run_documents(self, data: Any, name: str, result: ImportResult) -> bool:
        """Validate a KB documents.json payload structure."""
        if isinstance(data, BackupTableStream):
            found = False
            for table, rows in data.items():
                if table == "documents":
                    found = True
                    for row in (
                        row for batch in backup_row_batches(rows) for row in batch
                    ):
                        if not self._dry_run_documents(
                            {"documents": [row]}, name, result
                        ):
                            return False
            if not found:
                result.add_error(
                    f"Invalid {name} structure: documents array is missing"
                )
            return found
        if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
            result.add_error(f"Invalid {name} structure: documents array is missing")
            return False
        for doc in data["documents"]:
            if not isinstance(doc, dict) or "doc_id" not in doc or "text" not in doc:
                result.add_error(
                    f"Invalid {name} structure: document is missing doc_id/text"
                )
                return False
            try:
                json.loads(doc.get("metadata", "{}"))
            except (TypeError, json.JSONDecodeError):
                result.add_error(
                    f"Invalid {name} structure: metadata is not valid JSON"
                )
                return False
        return True

    async def _run_pre_verify(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
        namelist: list[str],
        selected: set[str],
        result: ImportResult,
        progress_callback: Any | None = None,
    ) -> dict | None:
        """Verify all selected components before restoring any data.

        Import is a maintenance operation and may block the event loop. Keeping
        verification here also ensures cancellation cannot close the archive
        while a worker is still reading it.

        Returns:
            A context dict for phase two, or None when a hard-fail component
            failed verification — nothing has been modified.
        """
        # Check type-specific limits before hashing or making any changes.
        # Database dumps are replayable streams, so no total JSON cache is needed.
        json_entries = [
            entry
            for entry in zf.infolist()
            if component_of_entry(entry.filename) in selected
            and (
                entry.filename
                in {
                    "databases/main_db.json",
                    "databases/kb_metadata.json",
                    "config/cmd_config.json",
                }
                or (
                    entry.filename.startswith("databases/kb_")
                    and entry.filename.endswith("/documents.json")
                )
            )
        ]
        if any(
            entry.file_size > backup_json_limit(entry.filename)
            for entry in json_entries
        ):
            result.add_error("Backup JSON exceeds the size limit for its entry type")
            return None

        checksums: dict[str, str] = manifest.get("checksums", {})
        comp_checksums: dict[str, str] = manifest.get("component_checksums", {})
        # v1.2 format = declared via the components field OR the manifest
        # version itself; both enforce full checksum coverage. A manifest
        # claiming version 1.2 without the components field is malformed
        # and must not fall into the legacy degradation path.
        is_v12 = (
            "components" in manifest
            or VersionComparator.compare_version(
                str(manifest.get("version", "1.0")), "1.2"
            )
            >= 0
        )

        ctx: dict[str, Any] = {
            "json": {},
            "bad_entries": {},
            "skip_components": set(),
            "unverified_counts": {},
        }

        comps = sorted(selected)
        for i, comp in enumerate(comps):
            if progress_callback:
                await progress_callback(
                    "validate", i, len(comps), f"正在校验组件 {comp}..."
                )
            ok = self._pre_verify_component(
                zf,
                comp,
                checksums=checksums,
                comp_checksums=comp_checksums,
                is_v12=is_v12,
                namelist=namelist,
                result=result,
                ctx=ctx,
            )
            if not ok:
                return None

        for comp, count in ctx["unverified_counts"].items():
            if count:
                result.add_warning(
                    f"Component {comp}: {count} entries have no checksum; verification skipped (legacy backup)"
                )

        return ctx

    def _pre_verify_component(
        self,
        zf: zipfile.ZipFile,
        comp: str,
        *,
        checksums: dict[str, str],
        comp_checksums: dict[str, str],
        is_v12: bool,
        namelist: list[str],
        result: ImportResult,
        ctx: dict[str, Any],
    ) -> bool:
        """Verify one component's entries before restoration.

        Entry hash checks, component aggregate check and JSON structural
        dry-runs, before anything is modified. Hard-fail components abort
        the import on any failure; soft-fail components record corrupted
        entries (skipped individually) or manifest-level errors (whole
        component skipped).

        Returns:
            False when a hard failure aborts the import (nothing has been
            modified). Soft-fail issues are recorded in ctx/result.
        """
        hard = comp in HARD_FAIL_COMPONENTS
        entries = [
            n for n in namelist if component_of_entry(n) == comp and not n.endswith("/")
        ]
        # Missing entries are structural errors, even if other files are corrupt.
        missing = sorted(
            {name for name in checksums if component_of_entry(name) == comp}
            - set(namelist)
        )
        if missing:
            result.add_error(
                f"Declared component {comp} has missing entries: {missing}"
            )
            if hard:
                return False
            ctx["skip_components"].add(comp)
            return True

        bad: list[str] = []
        hashes: dict[str, str] = {}
        unverified = 0

        for name in entries:
            expected = checksums.get(name)
            if expected is None:
                if is_v12:
                    # v1.2 requires full checksum coverage: this is a
                    # manifest-level (structural) format violation.
                    if hard:
                        result.add_error(
                            f"v1.2 backup entry is missing a checksum: {name}"
                        )
                        return False
                    result.add_error(
                        f"v1.2 backup entry is missing a checksum: {name}; skipping component {comp}"
                    )
                    ctx["skip_components"].add(comp)
                    return True
                unverified += 1
                continue
            try:
                actual = f"sha256:{self._hash_entry(zf, name)}"
            except (zipfile.BadZipFile, OSError, zlib.error) as e:
                # Entry-level read failure (e.g. CRC error): classify like a
                # checksum mismatch instead of failing the whole task.
                if hard:
                    result.add_error(f"Failed to read entry: {name} ({e})")
                    return False
                bad.append(name)
                continue
            if actual != expected:
                if hard:
                    result.add_error(f"Entry checksum verification failed: {name}")
                    return False
                bad.append(name)
                continue
            hashes[name] = actual

        # Component aggregate check (entry hashes already computed).
        expected_agg = comp_checksums.get(comp)
        if expected_agg is None:
            if is_v12:
                msg = f"v1.2 backup is missing the aggregate checksum for component {comp}"
                if hard:
                    result.add_error(msg)
                    return False
                result.add_error(f"{msg}; skipping component {comp}")
                ctx["skip_components"].add(comp)
                return True
        else:
            lines = sorted(f"{p}:{h}" for p, h in hashes.items())
            actual_agg = (
                "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
            )
            if actual_agg != expected_agg:
                if hard:
                    result.add_error(
                        f"Component {comp} aggregate verification failed (manifest does not match contents)"
                    )
                    return False
                if not bad:
                    # Entries all match but the aggregate does not:
                    # manifest structural error, not known corruption.
                    result.add_error(
                        f"Component {comp} aggregate verification failed (invalid manifest structure); skipping component"
                    )
                    ctx["skip_components"].add(comp)
                    return True
                # Known corrupted entries already explain the mismatch;
                # the entry-level warnings suffice, do not escalate.

        ctx["unverified_counts"][comp] = unverified
        if bad:
            ctx["bad_entries"][comp] = bad
            # Never silent: corrupted entries surface in the import result,
            # not only in per-file phase-two logs.
            result.add_warning(
                f"Component {comp}: verification failed or unreadable data for {len(bad)} entries; skipping these entries during import"
            )

        # JSON structural dry-run for hard-fail components.
        if comp == "database":
            data = self._load_json_entry(zf, "databases/main_db.json", result)
            if data is None or not self._dry_run_table_dump(
                data, MAIN_DB_MODELS, "main_db", result, preprocess=True
            ):
                return False
            ctx["json"]["main_db"] = data
        elif comp == "knowledge_base":
            meta = self._load_json_entry(zf, "databases/kb_metadata.json", result)
            if meta is None or not self._dry_run_table_dump(
                meta, KB_METADATA_MODELS, "kb_metadata", result
            ):
                return False
            ctx["json"]["kb_metadata"] = meta
            for name in entries:
                if name.startswith("databases/kb_") and name.endswith(
                    "/documents.json"
                ):
                    doc = self._load_json_entry(zf, name, result)
                    if doc is None or not self._dry_run_documents(doc, name, result):
                        return False
                    ctx["json"][name] = doc
        elif comp == "cmd_config":
            cfg = self._load_json_entry(zf, "config/cmd_config.json", result)
            if cfg is None:
                return False
            if not isinstance(cfg, dict):
                result.add_error(
                    "Invalid cmd_config.json structure: root must be a JSON object"
                )
                return False

        return True

    def _write_entry_safe(
        self, zf: zipfile.ZipFile, name: str, target_path: Path
    ) -> None:
        """Write a ZIP entry to target_path via a same-dir temp file.

        The entry was already verified in phase one, so no re-hashing here.
        The temp file is atomically moved into place with os.replace; on
        failure only the temp file is removed and the pre-existing target
        (if any) stays intact.
        """
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".restore-tmp",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as dst, zf.open(name) as src:
                shutil.copyfileobj(src, dst)
            os.replace(tmp_name, target_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _validate_version(self, manifest: dict) -> None:
        """验证版本兼容性 - 仅允许相同主版本导入

        注意：此方法仅在 import_all 中调用，用于双重校验。
        前端应先调用 pre_check 获取详细的版本信息并让用户确认。
        """
        backup_version = manifest.get("astrbot_version")
        if not backup_version:
            raise ValueError("Backup is missing version information")

        # 使用新的版本兼容性检查
        version_check = self._check_version_compatibility(backup_version)

        if version_check["status"] == "major_diff":
            raise ValueError(version_check["message"])

        # minor_diff 和 match 都允许导入
        if version_check["status"] == "minor_diff":
            logger.warning(
                "Backup version differs: backup=%s, current=%s", backup_version, VERSION
            )

    async def _clear_main_db(self) -> None:
        """清空主数据库所有表"""
        async with self.main_db.get_db() as session:
            async with session.begin():
                for table_name, model_class in MAIN_DB_MODELS.items():
                    try:
                        await session.execute(delete(model_class))
                        logger.debug(f"Cleared table {table_name}")
                    except Exception as e:
                        raise DatabaseClearError(
                            f"Failed to clear table {table_name}: {e}"
                        ) from e

    async def _clear_kb_data(self) -> None:
        """清空知识库文件目录与实例

        注意：元数据表的清理由 _import_knowledge_bases(clear=True) 在导入
        事务内完成，保证清表与插入原子性；此处只处理文件目录与内存实例。
        """
        if not self.kb_manager:
            return

        # 删除知识库文件目录
        for kb_id in list(self.kb_manager.kb_insts.keys()):
            try:
                kb_helper = self.kb_manager.kb_insts[kb_id]
                await kb_helper.terminate()
                if kb_helper.kb_dir.exists():
                    shutil.rmtree(kb_helper.kb_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up knowledge base {kb_id}: {e}")

        self.kb_manager.kb_insts.clear()

    async def _import_main_database(
        self,
        data: dict[str, list[dict]] | BackupTableStream,
        clear: bool = False,
        attachment_paths: dict[str, str | None] | None = None,
    ) -> dict[str, int]:
        """导入主数据库数据

        清表与插入在同一事务内执行：任何失败（包括逐条校验无法发现的
        记录间约束冲突）整体回滚，旧数据不丢失。

        Args:
            data: 表名到记录列表的映射
            clear: 是否在插入前清空所有主库表
            attachment_paths: Optional archive attachment ids mapped to path hints,
                filled during this pass with a bounded total path size.

        Returns:
            dict: 每个表导入的记录数

        Raises:
            DatabaseClearError: 清空表失败（事务回滚，旧数据保留）。
        """
        imported: dict[str, int] = {}
        hint_bytes = 0

        async with self.main_db.get_db() as session:
            async with session.begin():
                if clear:
                    for table_name, model_class in MAIN_DB_MODELS.items():
                        try:
                            await session.execute(delete(model_class))
                            logger.debug(f"Cleared table {table_name}")
                        except Exception as e:
                            raise DatabaseClearError(
                                f"Failed to clear table {table_name}: {e}"
                            ) from e

                for table_name, rows in data.items():
                    model_class = MAIN_DB_MODELS.get(table_name)
                    if not model_class:
                        logger.warning(f"Skipping unknown table: {table_name}")
                        continue
                    normalized_rows = self._preprocess_main_table_rows(table_name, rows)

                    count = 0
                    for batch in backup_row_batches(normalized_rows):
                        for row in batch:
                            try:
                                # 转换 datetime 字符串为 datetime 对象
                                row = self._convert_datetime_fields(row, model_class)
                                # 与预检一致：显式 model_validate，普通构造会
                                # 绕过 pydantic 校验
                                obj = model_class.model_validate(row)
                                session.add(obj)
                                count += 1
                                if table_name == "attachments" and attachment_paths:
                                    key, path = (
                                        row.get("attachment_id"),
                                        row.get("path"),
                                    )
                                    if (
                                        key in attachment_paths
                                        and attachment_paths[key] is None
                                        and isinstance(path, str)
                                    ):
                                        hint_bytes += len(path.encode("utf-8"))
                                        if hint_bytes <= MAX_JSON_RECORD_BYTES:
                                            attachment_paths[key] = path
                                        else:
                                            logger.warning(
                                                "Remaining attachment path hints exceed "
                                                "the memory budget and will be skipped"
                                            )
                                            # Keep the hints already collected, but
                                            # stop collecting through this local reference.
                                            attachment_paths = None
                            except Exception as e:
                                logger.warning(
                                    f"Failed to import record into {table_name}: {e}"
                                )
                                continue
                        # Flush without committing so failures roll back all rows.
                        await session.flush()

                    imported[table_name] = count
                    logger.debug(f"Imported table {table_name}: {count} records")

        return imported

    def _preprocess_main_table_rows(
        self, table_name: str, rows: Iterable[dict[str, Any]]
    ) -> Iterable[dict[str, Any]]:
        if table_name == "platform_stats":
            if not isinstance(rows, list):
                return self._merge_streamed_platform_stats(rows)
            normalized_rows = self._merge_platform_stats_rows(rows)
            duplicate_count = len(rows) - len(normalized_rows)
            if duplicate_count > 0:
                logger.warning(
                    "Merged duplicate rows before import: table=%s, duplicates=%d",
                    table_name,
                    duplicate_count,
                )
            return normalized_rows
        return rows

    def _merge_streamed_platform_stats(
        self, rows: Iterable[dict[str, Any]]
    ) -> Iterator[dict[str, Any]]:
        """Merge legacy statistics on disk without retaining all unique keys.

        Args:
            rows: Streamed statistics records in their original order.

        Yields:
            Normalized records in first-occurrence order, with duplicate counts summed.
        """
        limiter = _InvalidCountWarnLimiter(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT)
        # An empty SQLite filename creates a private temporary on-disk database
        # that is removed on close. It never touches the application's database.
        with closing(sqlite3.connect("")) as cache:
            cache.execute("PRAGMA cache_size = -2048")
            cache.execute(
                "CREATE TABLE merged (position INTEGER PRIMARY KEY, "
                "merge_key TEXT UNIQUE, payload TEXT NOT NULL)"
            )
            duplicates = 0
            for row in rows:
                normalized, timestamp, count = self._normalize_platform_stats_entry(
                    row, limiter
                )
                platform_id = normalized.get("platform_id")
                platform_type = normalized.get("platform_type")
                key = None
                if (
                    timestamp is not None
                    and isinstance(platform_id, str)
                    and isinstance(platform_type, str)
                ):
                    key = json.dumps((timestamp, platform_id, platform_type))
                    existing = cache.execute(
                        "SELECT payload FROM merged WHERE merge_key = ?", (key,)
                    ).fetchone()
                    if existing is not None:
                        first = json.loads(existing[0])
                        first["count"] += count
                        cache.execute(
                            "UPDATE merged SET payload = ? WHERE merge_key = ?",
                            (json.dumps(first), key),
                        )
                        duplicates += 1
                        continue
                cache.execute(
                    "INSERT INTO merged (merge_key, payload) VALUES (?, ?)",
                    (key, json.dumps(normalized)),
                )
            if duplicates:
                logger.warning(
                    f"Merged {duplicates} duplicate platform statistics rows"
                )
            for (payload,) in cache.execute(
                "SELECT payload FROM merged ORDER BY position"
            ):
                yield json.loads(payload)

    def _merge_platform_stats_rows(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge duplicate platform_stats rows by normalized timestamp/platform key.

        Note:
        - Invalid/empty timestamps are kept as distinct rows to avoid accidental merging.
        - Non-string platform_id/platform_type are kept as distinct rows.
        - Invalid count warnings are rate-limited per function invocation.
        """
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        result: list[dict[str, Any]] = []
        warn_limiter = _InvalidCountWarnLimiter(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT)

        for row in rows:
            normalized_row, normalized_timestamp, count = (
                self._normalize_platform_stats_entry(row, warn_limiter)
            )
            platform_id = normalized_row.get("platform_id")
            platform_type = normalized_row.get("platform_type")

            if (
                normalized_timestamp is None
                or not isinstance(platform_id, str)
                or not isinstance(platform_type, str)
            ):
                result.append(normalized_row)
                continue

            merge_key = (normalized_timestamp, platform_id, platform_type)
            existing = merged.get(merge_key)
            if existing is None:
                merged[merge_key] = normalized_row
                result.append(normalized_row)
            else:
                existing["count"] += count

        return result

    def _normalize_platform_stats_entry(
        self,
        row: dict[str, Any],
        warn_limiter: _InvalidCountWarnLimiter,
    ) -> tuple[dict[str, Any], str | None, int]:
        normalized_row = dict(row)
        raw_timestamp = normalized_row.get("timestamp")
        normalized_timestamp = self._normalize_platform_stats_timestamp(raw_timestamp)

        if normalized_timestamp is not None:
            normalized_row["timestamp"] = normalized_timestamp
        elif isinstance(raw_timestamp, str):
            normalized_row["timestamp"] = raw_timestamp.strip()
        elif raw_timestamp is None:
            normalized_row["timestamp"] = ""
        else:
            normalized_row["timestamp"] = str(raw_timestamp)

        raw_count = normalized_row.get("count", 0)
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            key_for_log = (
                normalized_row.get("timestamp"),
                repr(normalized_row.get("platform_id")),
                repr(normalized_row.get("platform_type")),
            )
            warn_limiter.warn_invalid_count(raw_count, key_for_log)
            count = 0

        normalized_row["count"] = count
        return normalized_row, normalized_timestamp, count

    def _normalize_platform_stats_timestamp(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat()
        if isinstance(value, str):
            timestamp = value.strip()
            if not timestamp:
                return None
            if timestamp.endswith("Z"):
                timestamp = f"{timestamp[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt.isoformat()
            except ValueError:
                return None
        return None

    async def _import_knowledge_bases(
        self,
        zf: zipfile.ZipFile,
        kb_meta_data: dict[str, list[dict]] | BackupTableStream,
        result: ImportResult,
        clear: bool = False,
        json_ctx: dict[str, Any] | None = None,
        bad_entries: list[str] | None = None,
    ) -> None:
        """导入知识库数据

        Args:
            zf: 打开的 ZIP 文件对象
            kb_meta_data: Validated KB metadata, replayed from the archive on demand.
            result: 导入结果对象
            clear: 是否在导入事务内先清空元数据表（清表与插入原子）
            json_ctx: Replayable JSON streams validated during phase one.
            bad_entries: 阶段一检出的损坏条目，逐条跳过
        """
        if not self.kb_manager:
            return

        if json_ctx is None:
            json_ctx = {}
        if bad_entries is None:
            bad_entries = []

        # 1. 导入知识库元数据（清表与插入在同一事务）
        imported = {}
        async with self.kb_manager.kb_db.get_db() as session:
            async with session.begin():
                if clear:
                    for table_name, model_class in KB_METADATA_MODELS.items():
                        try:
                            await session.execute(delete(model_class))
                            logger.debug(f"Cleared knowledge base table {table_name}")
                        except Exception as e:
                            raise DatabaseClearError(
                                f"Failed to clear knowledge base table {table_name}: {e}"
                            ) from e

                for table_name, rows in kb_meta_data.items():
                    model_class = KB_METADATA_MODELS.get(table_name)
                    if not model_class:
                        continue

                    count = 0
                    for batch in backup_row_batches(rows):
                        for row in batch:
                            try:
                                row = self._convert_datetime_fields(row, model_class)
                                obj = model_class.model_validate(row)
                                session.add(obj)
                                count += 1
                            except Exception as e:
                                logger.warning(
                                    f"Failed to import knowledge base record into {table_name}: {e}"
                                )
                                continue
                        await session.flush()

                    imported[f"kb_{table_name}"] = count

        result.imported_tables.update(imported)
        if clear:
            await self._clear_kb_data()

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
            if doc_path in zf.namelist() and doc_path not in bad_entries:
                try:
                    # Replay the validated entry without retaining its document list.
                    doc_data = json_ctx.pop(doc_path, None)
                    if doc_data is None:
                        doc_data = read_backup_json(zf, doc_path)

                    # 导入到文档存储数据库
                    await self._import_kb_documents(kb_id, doc_data)
                    del doc_data
                except Exception as e:
                    result.add_warning(
                        f"Failed to import documents for knowledge base {kb_id}: {e}"
                    )

            # 导入 FAISS 索引
            faiss_path = f"databases/kb_{kb_id}/index.faiss"
            if faiss_path in zf.namelist() and faiss_path not in bad_entries:
                try:
                    self._write_entry_safe(zf, faiss_path, kb_dir / "index.faiss")
                except Exception as e:
                    result.add_warning(
                        f"Failed to import FAISS index for knowledge base {kb_id}: {e}"
                    )

            # 导入媒体文件
            media_prefix = f"files/kb_media/{kb_id}/"
            for name in zf.namelist():
                if name.startswith(media_prefix) and name not in bad_entries:
                    try:
                        rel_path = name[len(media_prefix) :]
                        target_path = kb_dir / rel_path
                        # Validate path is within kb directory (CWE-22)
                        if not _validate_path_within(target_path, kb_dir):
                            logger.warning(
                                f"Skipping media file outside the knowledge base directory: {target_path}"
                            )
                            continue
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        self._write_entry_safe(zf, name, target_path)
                    except Exception as e:
                        result.add_warning(f"Failed to import media file {name}: {e}")

        # 3. 重新加载知识库实例
        await self.kb_manager.load_kbs()

    async def _import_kb_documents(
        self, kb_id: str, doc_data: dict | BackupTableStream
    ) -> None:
        """导入知识库文档到向量数据库"""
        from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage

        kb_dir = Path(self.kb_root_dir) / kb_id
        doc_db_path = kb_dir / "doc.db"

        # 初始化文档存储
        doc_storage = DocumentStorage(str(doc_db_path))
        await doc_storage.initialize()

        try:
            for batch in backup_row_batches(doc_data.get("documents", [])):
                await doc_storage.insert_documents_batch(
                    doc_ids=[doc.get("doc_id", "") for doc in batch],
                    texts=[doc.get("text", "") for doc in batch],
                    metadatas=[json.loads(doc.get("metadata", "{}")) for doc in batch],
                )
        finally:
            await doc_storage.close()

    async def _import_attachments(
        self,
        zf: zipfile.ZipFile,
        attachments: Iterable[dict],
        bad_entries: list[str] | None = None,
    ) -> int:
        """导入附件文件

        Args:
            zf: ZIP 文件对象
            attachments: 附件记录（用于恢复原始路径）
            bad_entries: 阶段一检出的损坏条目，逐条跳过

        Returns:
            int: 导入的附件数量
        """
        if bad_entries is None:
            bad_entries = []
        count = 0

        attachments_dir = Path(self.config_path).parent / "attachments"

        attachment_prefix = "files/attachments/"
        attachment_ids = {
            Path(name).stem
            for name in zf.namelist()
            if name.startswith(attachment_prefix) and not name.endswith("/")
        }
        if not attachment_ids:
            return 0
        attachments_dir.mkdir(parents=True, exist_ok=True)
        attachment_paths = {}
        hint_bytes = 0
        try:
            for attachment in attachments:
                attachment_id = attachment.get("attachment_id")
                path = attachment.get("path")
                if (
                    attachment_id in attachment_ids
                    and attachment_id not in attachment_paths
                    and isinstance(path, str)
                ):
                    hint_bytes += len(path.encode("utf-8"))
                    if hint_bytes > MAX_JSON_RECORD_BYTES:
                        raise ValueError(
                            "Attachment path hints exceed the memory budget"
                        )
                    attachment_paths[attachment_id] = path
        except Exception as exc:
            # Hints are optional; decoding failures must not discard attachments.
            logger.warning(f"Attachment path hints skipped: {exc}")
        for name in zf.namelist():
            if name.startswith(attachment_prefix) and name != attachment_prefix:
                if name in bad_entries:
                    # Phase one reported this entry as corrupted; skip it.
                    # The pre-existing target file (if any) is untouched.
                    logger.warning(
                        f"Skipping attachment with failed verification: {name}"
                    )
                    continue
                try:
                    # 从附件记录中找到原始路径
                    attachment_id = os.path.splitext(os.path.basename(name))[0]
                    original_path = attachment_paths.get(attachment_id)

                    if original_path:
                        target_path = Path(original_path)
                    else:
                        target_path = attachments_dir / os.path.basename(name)

                    # Validate path is within attachments directory (CWE-22)
                    if not _validate_path_within(target_path, attachments_dir):
                        logger.warning(
                            f"Skipping attachment outside the attachments directory: {target_path}"
                        )
                        continue

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    self._write_entry_safe(zf, name, target_path)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to import attachment {name}: {e}")

        return count

    async def _import_directories(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
        result: ImportResult,
        selected_dirs: list[str] | None = None,
        bad_entries: dict[str, list[str]] | None = None,
    ) -> dict[str, int]:
        """导入插件和其他数据目录

        Args:
            zf: ZIP 文件对象
            manifest: 备份清单
            result: 导入结果对象
            selected_dirs: 只导入这些目录键；None 导入清单中的全部目录
            bad_entries: 阶段一检出的损坏条目（按组件分组），逐文件跳过

        Returns:
            dict: 每个目录导入的文件数量
        """
        if bad_entries is None:
            bad_entries = {}
        dir_stats: dict[str, int] = {}

        # 检查备份版本是否支持目录备份（需要版本 >= 1.1）
        backup_version = manifest.get("version", "1.0")
        if VersionComparator.compare_version(backup_version, "1.1") < 0:
            logger.info(
                "Skipping directory import: backup version does not support directory backups"
            )
            return dir_stats

        backed_up_dirs = manifest.get("directories", [])
        backup_directories = get_backup_directories()

        for dir_name in backed_up_dirs:
            if dir_name not in backup_directories:
                result.add_warning(f"Unknown directory type: {dir_name}")
                continue
            if selected_dirs is not None and dir_name not in selected_dirs:
                continue

            target_dir = Path(backup_directories[dir_name])
            archive_prefix = f"directories/{dir_name}/"
            if dir_name == "webchat":
                # Preserve legacy filenames without replacing active upload data.
                target_dir = target_dir / "imgs"
                archive_prefix += "imgs/"
            bad_files = bad_entries.get(
                "attachments" if dir_name == "webchat" else dir_name, []
            )

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
                if dir_name == "webchat" and not any(
                    not name.endswith("/") and name not in bad_files
                    for name in dir_files
                ):
                    result.add_warning(
                        "No valid legacy WebChat images to restore; existing images were preserved."
                    )
                    continue

                # 备份现有目录（如果存在）
                if target_dir.exists():
                    backup_path = Path(f"{target_dir}.bak")
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    shutil.move(str(target_dir), str(backup_path))
                    logger.debug(
                        f"Backed up existing directory {target_dir} to {backup_path}"
                    )

                # 创建目标目录
                target_dir.mkdir(parents=True, exist_ok=True)

                # 解压文件
                for name in dir_files:
                    try:
                        if name in bad_files:
                            # Phase one reported this entry as corrupted;
                            # the old version stays recoverable in the .bak dir.
                            result.add_warning(
                                f"File {name} verification failed; skipped. "
                                f"The previous version can be recovered manually from {target_dir}.bak"
                            )
                            continue

                        # 计算相对路径
                        rel_path = name[len(archive_prefix) :]
                        if not rel_path:  # 跳过目录条目
                            continue

                        target_path = target_dir / rel_path
                        # Validate path is within target directory (CWE-22)
                        if not _validate_path_within(target_path, target_dir):
                            result.add_warning(
                                f"Skipping file outside the target directory: {name}"
                            )
                            continue

                        if zf.getinfo(name).is_dir():
                            ensure_dir(target_path)
                            continue

                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        self._write_entry_safe(zf, name, target_path)
                        file_count += 1
                    except Exception as e:
                        result.add_warning(f"Failed to import file {name}: {e}")

                dir_stats[dir_name] = file_count
                logger.debug(f"Imported directory {dir_name}: {file_count} files")

            except Exception as e:
                result.add_warning(f"Failed to import directory {dir_name}: {e}")
                dir_stats[dir_name] = 0

        return dir_stats

    def _convert_datetime_fields(
        self, row: dict, model_class: type, strict: bool = False
    ) -> dict:
        """转换 datetime 字符串字段为 datetime 对象

        Args:
            row: 记录字典
            model_class: 目标模型类
            strict: 严格模式（预检使用）：转换失败抛出异常而不是静默
                保留原值。导入路径保持宽松（默认 False），单条失败按
                warning 跳过。

        Returns:
            转换后的记录字典

        Raises:
            ValueError: strict 模式下 datetime 解析失败。
        """
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
                            try:
                                result[column.name] = datetime.fromisoformat(value)
                            except ValueError:
                                if strict:
                                    raise
        except ValueError:
            if strict:
                raise
        except Exception:
            if strict:
                raise

        return result
