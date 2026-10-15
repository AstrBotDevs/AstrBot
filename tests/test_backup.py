"""备份功能单元测试"""

import asyncio
import errno
import hashlib
import json
import os
import re
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.backup import (
    BACKUP_MANIFEST_VERSION,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    ImportPreCheckResult,
)
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import (
    PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT,
    AstrBotImporter,
    DatabaseClearError,
    ImportResult,
    _get_major_version,
)
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import (
    ConversationV2,
)
from astrbot.core.utils.upload import UploadTooLargeError
from astrbot.core.utils.version_comparator import VersionComparator
from astrbot.dashboard.services.backup_service import (
    CHUNK_SIZE,
    MAX_BACKUP_TOTAL_BYTES,
    BackupService,
    BackupServiceError,
    generate_unique_filename,
    secure_filename,
)


@pytest.fixture
def temp_backup_dir(tmp_path):
    """创建临时备份目录"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def temp_data_dir(tmp_path):
    """创建临时数据目录"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # 创建配置文件
    config_path = data_dir / "cmd_config.json"
    config_path.write_text(json.dumps({"test": "config"}))

    # 创建附件目录
    attachments_dir = data_dir / "attachments"
    attachments_dir.mkdir()

    return data_dir


@pytest.fixture
def mock_main_db():
    """创建模拟的主数据库"""
    db = MagicMock()

    # 模拟异步上下文管理器
    session = AsyncMock()
    db.get_db = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(return_value=session))
    )

    return db


@pytest.fixture
def mock_kb_manager():
    """创建模拟的知识库管理器"""
    kb_manager = MagicMock()
    kb_manager.kb_insts = {}

    # 模拟 kb_db
    kb_db = MagicMock()
    session = AsyncMock()
    kb_db.get_db = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(return_value=session))
    )
    kb_manager.kb_db = kb_db

    return kb_manager


class TestImportResult:
    """ImportResult 类测试"""

    def test_init(self):
        """测试初始化"""
        result = ImportResult()
        assert result.success is True
        assert result.imported_tables == {}
        assert result.imported_files == {}
        assert result.warnings == []
        assert result.errors == []

    def test_add_warning(self):
        """测试添加警告"""
        result = ImportResult()
        result.add_warning("test warning")
        assert "test warning" in result.warnings
        assert result.success is True  # 警告不影响成功状态

    def test_add_error(self):
        """测试添加错误"""
        result = ImportResult()
        result.add_error("test error")
        assert "test error" in result.errors
        assert result.success is False  # 错误会导致失败

    def test_to_dict(self):
        """测试转换为字典"""
        result = ImportResult()
        result.imported_tables = {"test_table": 10}
        result.add_warning("warning")

        d = result.to_dict()
        assert d["success"] is True
        assert d["imported_tables"] == {"test_table": 10}
        assert "warning" in d["warnings"]


class TestAstrBotExporter:
    """AstrBotExporter 类测试"""

    def test_init(self, mock_main_db, mock_kb_manager, temp_data_dir):
        """测试初始化"""
        exporter = AstrBotExporter(
            main_db=mock_main_db,
            kb_manager=mock_kb_manager,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        assert exporter.main_db is mock_main_db
        assert exporter.kb_manager is mock_kb_manager

    def test_model_to_dict_with_model_dump(self):
        """测试 _model_to_dict 使用 model_dump 方法"""
        exporter = AstrBotExporter(main_db=MagicMock())

        # 创建一个有 model_dump 方法的模拟对象
        mock_record = MagicMock()
        mock_record.model_dump.return_value = {"id": 1, "name": "test"}

        result = exporter._model_to_dict(mock_record)
        assert result == {"id": 1, "name": "test"}

    def test_model_to_dict_with_datetime(self):
        """测试 _model_to_dict 处理 datetime 字段"""
        exporter = AstrBotExporter(main_db=MagicMock())

        now = datetime.now()
        mock_record = MagicMock()
        mock_record.model_dump.return_value = {"id": 1, "created_at": now}

        result = exporter._model_to_dict(mock_record)
        assert result["created_at"] == now.isoformat()

    def test_add_checksum(self):
        """测试添加校验和"""
        exporter = AstrBotExporter(main_db=MagicMock())

        exporter._add_checksum("test.json", '{"test": "data"}')

        assert "test.json" in exporter._checksums
        assert exporter._checksums["test.json"].startswith("sha256:")

    def test_generate_manifest(self, mock_main_db, mock_kb_manager):
        """测试生成清单"""
        exporter = AstrBotExporter(
            main_db=mock_main_db,
            kb_manager=mock_kb_manager,
        )

        main_data = {
            "platform_stats": [{"id": 1}],
            "conversations": [],
            "attachments": [],
        }
        kb_meta_data = {
            "knowledge_bases": [],
            "kb_documents": [],
        }
        dir_stats = {
            "plugins": {"files": 10, "size": 1024},
            "plugin_data": {"files": 5, "size": 512},
        }

        manifest = exporter._generate_manifest(main_data, kb_meta_data, dir_stats)

        assert manifest["version"] == BACKUP_MANIFEST_VERSION
        assert manifest["astrbot_version"] == VERSION
        assert manifest["origin"] == "exported"  # 验证备份来源标记
        assert "exported_at" in manifest
        assert "tables" in manifest
        assert "statistics" in manifest
        assert "directories" in manifest
        assert manifest["statistics"]["main_db"]["platform_stats"] == 1
        assert manifest["statistics"]["directories"] == dir_stats

    @pytest.mark.asyncio
    async def test_export_all_creates_zip(
        self, mock_main_db, temp_backup_dir, temp_data_dir
    ):
        """测试导出创建 ZIP 文件"""
        # 设置模拟数据库返回空数据
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        mock_main_db.get_db.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )

        exporter = AstrBotExporter(
            main_db=mock_main_db,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )

        zip_path = await exporter.export_all(output_dir=str(temp_backup_dir))

        assert os.path.exists(zip_path)
        assert zip_path.endswith(".zip")
        assert "astrbot_backup_" in zip_path

        # 验证 ZIP 文件内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "databases/main_db.json" in namelist
            assert "config/cmd_config.json" in namelist


class TestAstrBotImporter:
    """AstrBotImporter 类测试"""

    def test_init(self, mock_main_db, mock_kb_manager, temp_data_dir):
        """测试初始化"""
        importer = AstrBotImporter(
            main_db=mock_main_db,
            kb_manager=mock_kb_manager,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        assert importer.main_db is mock_main_db
        assert importer.kb_manager is mock_kb_manager

    def test_validate_version_match(self):
        """测试版本匹配验证"""
        importer = AstrBotImporter(main_db=MagicMock())

        manifest = {"astrbot_version": VERSION}
        # 不应该抛出异常
        importer._validate_version(manifest)

    def test_validate_version_major_diff_rejected(self):
        """测试主版本不同被拒绝"""
        importer = AstrBotImporter(main_db=MagicMock())

        # 使用一个明显不同的主版本
        manifest = {"astrbot_version": "0.0.1"}
        with pytest.raises(ValueError, match="主版本不兼容"):
            importer._validate_version(manifest)

    def test_validate_version_minor_diff_allowed(self):
        """测试小版本不同被允许（仅警告）"""
        importer = AstrBotImporter(main_db=MagicMock())

        # 获取当前主版本
        major_version = _get_major_version(VERSION)
        # 构造一个同主版本但小版本不同的版本
        minor_diff_version = f"{major_version}.999"
        manifest = {"astrbot_version": minor_diff_version}
        # 不应该抛出异常
        importer._validate_version(manifest)

    def test_validate_version_missing(self):
        """测试缺少版本信息"""
        importer = AstrBotImporter(main_db=MagicMock())

        manifest = {}
        with pytest.raises(ValueError, match="缺少版本信息"):
            importer._validate_version(manifest)

    def test_convert_datetime_fields(self):
        """测试 datetime 字段转换"""
        importer = AstrBotImporter(main_db=MagicMock())

        # 使用 ConversationV2 作为测试模型（它有 created_at 和 updated_at 字段）
        row = {
            "conversation_id": "test-123",
            "platform_id": "test",
            "user_id": "user1",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
        }

        result = importer._convert_datetime_fields(row, ConversationV2)

        # created_at 应该被转换为 datetime 对象
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)

    def test_merge_platform_stats_rows(self):
        """测试 platform_stats 重复键会在导入前聚合"""
        importer = AstrBotImporter(main_db=MagicMock())
        rows = [
            {
                "id": 1,
                "timestamp": "2025-12-13T20:00:00Z",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 14,
            },
            {
                "id": 80,
                "timestamp": "2025-12-13T20:00:00+00:00",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 3,
            },
            {
                "id": 81,
                "timestamp": "2025-12-13T20:00:00",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 2,
            },
            {
                "id": 2,
                "timestamp": "2025-12-13T21:00:00",
                "platform_id": "aiocqhttp",
                "platform_type": "unknown",
                "count": 1,
            },
        ]

        merged_rows = importer._merge_platform_stats_rows(rows)
        duplicate_count = len(rows) - len(merged_rows)

        assert duplicate_count == 2
        assert len(merged_rows) == 2
        webchat_row = next(
            (
                r
                for r in merged_rows
                if r.get("timestamp") == "2025-12-13T20:00:00+00:00"
                and r.get("platform_id") == "webchat"
                and r.get("platform_type") == "unknown"
            ),
            None,
        )
        assert webchat_row is not None
        assert webchat_row["timestamp"] == "2025-12-13T20:00:00+00:00"
        assert webchat_row["platform_id"] == "webchat"
        assert webchat_row["platform_type"] == "unknown"
        assert webchat_row["count"] == 19

        aiocq_row = next(
            (
                r
                for r in merged_rows
                if r.get("platform_id") == "aiocqhttp"
                and r.get("platform_type") == "unknown"
            ),
            None,
        )
        assert aiocq_row is not None
        assert aiocq_row["timestamp"] == "2025-12-13T21:00:00+00:00"

    def test_merge_platform_stats_rows_normalizes_naive_timestamp_to_utc(self):
        """测试 platform_stats 合并前会将 naive timestamp 标准化为 UTC 偏移"""
        importer = AstrBotImporter(main_db=MagicMock())

        rows = [
            {
                "timestamp": "2025-12-13T21:00:00",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 1,
            },
            {
                "timestamp": datetime(2025, 12, 13, 22, 0, 0),
                "platform_id": "telegram",
                "platform_type": "unknown",
                "count": 1,
            },
        ]

        merged_rows = importer._merge_platform_stats_rows(rows)
        assert len(merged_rows) == 2
        by_platform = {row["platform_id"]: row for row in merged_rows}
        assert by_platform["webchat"]["timestamp"] == "2025-12-13T21:00:00+00:00"
        assert by_platform["telegram"]["timestamp"] == "2025-12-13T22:00:00+00:00"

    def test_merge_platform_stats_rows_warns_on_invalid_count(self):
        """测试 platform_stats count 非法时会告警并按 0 处理（含上限）"""
        importer = AstrBotImporter(main_db=MagicMock())
        with patch("astrbot.core.backup.importer.logger.warning") as warning_mock:
            rows = [
                {
                    "timestamp": "2025-12-13T20:00:00+00:00",
                    "platform_id": "webchat",
                    "platform_type": "unknown",
                    "count": 5,
                },
                {
                    "timestamp": "2025-12-13T20:00:00Z",
                    "platform_id": "webchat",
                    "platform_type": "unknown",
                    "count": "bad-count",
                },
            ]
            merged_rows = importer._merge_platform_stats_rows(rows)
            duplicate_count = len(rows) - len(merged_rows)
            assert duplicate_count == 1
            assert len(merged_rows) == 1
            assert merged_rows[0]["count"] == 5
            assert warning_mock.call_count == 1

            warning_mock.reset_mock()

            rows_existing_invalid = [
                {
                    "timestamp": "2025-12-13T21:00:00+00:00",
                    "platform_id": "webchat",
                    "platform_type": "unknown",
                    "count": "bad-count",
                },
                {
                    "timestamp": "2025-12-13T21:00:00Z",
                    "platform_id": "webchat",
                    "platform_type": "unknown",
                    "count": 7,
                },
            ]
            merged_rows = importer._merge_platform_stats_rows(rows_existing_invalid)
            duplicate_count = len(rows_existing_invalid) - len(merged_rows)
            assert duplicate_count == 1
            assert len(merged_rows) == 1
            assert merged_rows[0]["count"] == 7
            assert warning_mock.call_count == 1

            warning_mock.reset_mock()

            many_invalid_rows = [
                {
                    "timestamp": "2025-12-13T22:00:00+00:00",
                    "platform_id": "webchat",
                    "platform_type": "unknown",
                    "count": 1,
                },
                *[
                    {
                        "timestamp": "2025-12-13T22:00:00Z",
                        "platform_id": "webchat",
                        "platform_type": "unknown",
                        "count": "bad-count",
                    }
                    for _ in range(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT + 5)
                ],
            ]
            importer._merge_platform_stats_rows(many_invalid_rows)
            assert (
                warning_mock.call_count == PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT + 1
            )
            assert any(
                "告警已达到上限" in str(call.args[0])
                for call in warning_mock.call_args_list
            )

            warning_mock.reset_mock()

            single_invalid_row = [
                {
                    "timestamp": "2025-12-13T23:00:00+00:00",
                    "platform_id": "telegram",
                    "platform_type": "unknown",
                    "count": "still-bad",
                },
            ]
            merged_rows = importer._merge_platform_stats_rows(single_invalid_row)
            duplicate_count = len(single_invalid_row) - len(merged_rows)
            assert duplicate_count == 0
            assert len(merged_rows) == 1
            assert merged_rows[0]["count"] == 0
            assert warning_mock.call_count == 1

    def test_merge_platform_stats_rows_keeps_invalid_timestamps_distinct(self):
        """测试空/非法 timestamp 不参与聚合，避免误合并"""
        importer = AstrBotImporter(main_db=MagicMock())
        rows = [
            {
                "timestamp": "",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 2,
            },
            {
                "timestamp": "not-a-datetime",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 3,
            },
            {
                "timestamp": "not-a-datetime",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 4,
            },
        ]

        merged_rows = importer._merge_platform_stats_rows(rows)
        duplicate_count = len(rows) - len(merged_rows)

        assert duplicate_count == 0
        assert len(merged_rows) == 3
        assert [row["count"] for row in merged_rows] == [2, 3, 4]

    def test_merge_platform_stats_rows_keeps_non_string_platform_keys_distinct(self):
        """测试非字符串 platform_id/platform_type 不参与聚合"""
        importer = AstrBotImporter(main_db=MagicMock())
        rows = [
            {
                "timestamp": "2025-12-13T20:00:00+00:00",
                "platform_id": None,
                "platform_type": "unknown",
                "count": 2,
            },
            {
                "timestamp": "2025-12-13T20:00:00Z",
                "platform_id": None,
                "platform_type": "unknown",
                "count": 3,
            },
            {
                "timestamp": "2025-12-13T20:00:00+00:00",
                "platform_id": "webchat",
                "platform_type": 1,
                "count": 4,
            },
            {
                "timestamp": "2025-12-13T20:00:00Z",
                "platform_id": "webchat",
                "platform_type": 1,
                "count": 5,
            },
        ]

        merged_rows = importer._merge_platform_stats_rows(rows)
        duplicate_count = len(rows) - len(merged_rows)

        assert duplicate_count == 0
        assert len(merged_rows) == 4

    def test_merge_platform_stats_rows_preserves_input_order(self):
        """测试 platform_stats 聚合后仍保持输入顺序（按首次出现位置）"""
        importer = AstrBotImporter(main_db=MagicMock())
        rows = [
            {
                "id": 1,
                "timestamp": "2025-12-13T20:00:00Z",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 2,
            },
            {
                "id": 2,
                "timestamp": "",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 3,
            },
            {
                "id": 3,
                "timestamp": "2025-12-13T20:00:00+00:00",
                "platform_id": "webchat",
                "platform_type": "unknown",
                "count": 5,
            },
            {
                "id": 4,
                "timestamp": "2025-12-13T21:00:00+00:00",
                "platform_id": "telegram",
                "platform_type": "unknown",
                "count": 7,
            },
        ]

        merged_rows = importer._merge_platform_stats_rows(rows)

        assert len(merged_rows) == 3
        assert [row["id"] for row in merged_rows] == [1, 2, 4]
        assert merged_rows[0]["count"] == 7

    @pytest.mark.asyncio
    async def test_import_file_not_exists(self, mock_main_db, tmp_path):
        """测试导入不存在的文件"""
        importer = AstrBotImporter(main_db=mock_main_db)

        result = await importer.import_all(str(tmp_path / "nonexistent.zip"))

        assert result.success is False
        assert any("不存在" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_invalid_zip(self, mock_main_db, tmp_path):
        """测试导入无效的 ZIP 文件"""
        # 创建一个无效的文件
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = await importer.import_all(str(invalid_zip))

        assert result.success is False
        assert any("无效" in err or "ZIP" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_missing_manifest(self, mock_main_db, tmp_path):
        """测试导入缺少 manifest 的 ZIP 文件"""
        # 创建一个没有 manifest 的 ZIP 文件
        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = await importer.import_all(str(zip_path))

        assert result.success is False
        assert any("manifest" in err.lower() for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_major_version_mismatch(self, mock_main_db, tmp_path):
        """测试导入主版本不匹配的备份"""
        # 创建一个主版本不匹配的备份
        zip_path = tmp_path / "old_version.zip"
        manifest = {
            "version": "1.0",
            "astrbot_version": "0.0.1",  # 主版本不同
            "tables": {"main_db": []},
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = await importer.import_all(str(zip_path))

        assert result.success is False
        assert any("主版本不兼容" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_replace_fails_when_clear_main_db_fails(
        self, mock_main_db, tmp_path
    ):
        """测试 replace 模式下主库清空失败会直接终止导入"""
        zip_path = tmp_path / "valid_backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": VERSION,
            "tables": {"platform_stats": 0},
        }
        main_data = {"platform_stats": []}
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("databases/main_db.json", json.dumps(main_data))

        importer = AstrBotImporter(main_db=mock_main_db)
        importer._clear_main_db = AsyncMock(
            side_effect=DatabaseClearError("清空表 platform_stats 失败: db locked")
        )
        importer._import_main_database = AsyncMock(return_value={})

        result = await importer.import_all(str(zip_path), mode="replace")

        assert result.success is False
        assert any("清空主数据库失败" in err for err in result.errors)
        assert any("清空表 platform_stats 失败" in err for err in result.errors)
        importer._import_main_database.assert_not_awaited()


class TestSecureFilename:
    """安全文件名函数测试"""

    def test_secure_filename_normal(self):
        """测试正常文件名"""
        assert secure_filename("backup.zip") == "backup.zip"
        assert secure_filename("my_backup_2024.zip") == "my_backup_2024.zip"

    def test_secure_filename_path_traversal(self):
        """测试路径遍历攻击"""
        assert ".." not in secure_filename("../../../etc/passwd")
        assert "/" not in secure_filename("/etc/passwd")
        assert "\\" not in secure_filename("..\\..\\windows\\system32")

    def test_secure_filename_with_path(self):
        """测试带路径的文件名"""
        result = secure_filename("/path/to/backup.zip")
        assert result == "backup.zip"

        result = secure_filename("C:\\Users\\test\\backup.zip")
        assert result == "backup.zip"

    def test_secure_filename_special_chars(self):
        """测试特殊字符"""
        result = secure_filename('backup<>:"|?*.zip')
        # 特殊字符应被替换为下划线
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_secure_filename_hidden_file(self):
        """测试隐藏文件（前导点）"""
        result = secure_filename(".hidden_backup.zip")
        assert not result.startswith(".")

    def test_secure_filename_empty(self):
        """测试空文件名"""
        assert secure_filename("") == "backup"
        assert secure_filename("...") == "backup"

    def test_generate_unique_filename(self):
        """测试生成唯一文件名"""
        result = generate_unique_filename("backup.zip")
        # 应包含原文件名和时间戳后缀
        assert result.startswith("backup_")
        assert result.endswith(".zip")
        # 应包含时间戳格式 YYYYMMDD_HHMMSS
        assert re.search(r"backup_\d{8}_\d{6}\.zip", result)

    def test_generate_unique_filename_with_complex_name(self):
        """测试复杂文件名生成唯一文件名"""
        result = generate_unique_filename("my_backup_file.zip")
        # 应在原文件名后添加时间戳
        assert result.startswith("my_backup_file_")
        assert result.endswith(".zip")
        assert re.search(r"my_backup_file_\d{8}_\d{6}\.zip", result)


class TestVersionComparison:
    """版本比较函数测试 - 使用 VersionComparator"""

    def test_get_major_version_simple(self):
        """测试提取简单主版本号"""
        assert _get_major_version("1.0") == "1.0"
        assert _get_major_version("2.1") == "2.1"
        assert _get_major_version("4.9.1") == "4.9"

    def test_get_major_version_with_prefix(self):
        """测试带 v 前缀的版本号"""
        assert _get_major_version("v1.0") == "1.0"
        assert _get_major_version("V4.9.1") == "4.9"

    def test_get_major_version_with_prerelease(self):
        """测试带预发布标签的版本号"""
        assert _get_major_version("4.9.1-beta") == "4.9"
        assert _get_major_version("4.9.1-alpha.1") == "4.9"
        assert _get_major_version("4.9.1+build123") == "4.9"

    def test_get_major_version_single_part(self):
        """测试单部分版本号"""
        assert _get_major_version("1") == "1.0"

    def test_get_major_version_empty(self):
        """测试空版本号"""
        assert _get_major_version("") == "0.0"

    def test_compare_versions_equal(self):
        """测试版本相等"""
        assert VersionComparator.compare_version("1.0", "1.0") == 0
        assert VersionComparator.compare_version("1.0.0", "1.0") == 0
        assert VersionComparator.compare_version("2.10", "2.10") == 0

    def test_compare_versions_less_than(self):
        """测试版本小于"""
        assert VersionComparator.compare_version("1.0", "1.1") == -1
        assert (
            VersionComparator.compare_version("1.9", "1.10") == -1
        )  # 关键测试：多位数版本比较
        assert VersionComparator.compare_version("1.2", "1.10") == -1
        assert VersionComparator.compare_version("1.0", "2.0") == -1

    def test_compare_versions_greater_than(self):
        """测试版本大于"""
        assert VersionComparator.compare_version("1.1", "1.0") == 1
        assert (
            VersionComparator.compare_version("1.10", "1.9") == 1
        )  # 关键测试：多位数版本比较
        assert VersionComparator.compare_version("1.10", "1.2") == 1
        assert VersionComparator.compare_version("2.0", "1.0") == 1

    def test_compare_versions_different_lengths(self):
        """测试不同长度版本比较"""
        assert VersionComparator.compare_version("1.0", "1.0.0") == 0
        assert VersionComparator.compare_version("1.0", "1.0.1") == -1
        assert VersionComparator.compare_version("1.0.1", "1.0") == 1

    def test_compare_versions_prerelease(self):
        """测试预发布版本比较"""
        # 预发布版本低于正式版本
        assert VersionComparator.compare_version("1.0.0-alpha", "1.0.0") == -1
        assert VersionComparator.compare_version("1.0.0", "1.0.0-beta") == 1
        # alpha < beta
        assert VersionComparator.compare_version("1.0.0-alpha", "1.0.0-beta") == -1


class TestImportPreCheckResult:
    """ImportPreCheckResult 类测试"""

    def test_init_default_values(self):
        """测试默认值初始化"""
        result = ImportPreCheckResult()
        assert result.valid is False
        assert result.can_import is False
        assert result.version_status == ""
        assert result.backup_version == ""
        assert result.current_version == VERSION
        assert result.confirm_message == ""
        assert result.warnings == []
        assert result.error == ""
        assert result.backup_summary == {}

    def test_to_dict(self):
        """测试转换为字典"""
        result = ImportPreCheckResult(
            valid=True,
            can_import=True,
            version_status="match",
            backup_version="4.9.0",
            confirm_message="确认导入？",
            warnings=["警告1"],
            backup_summary={"tables": ["table1"]},
        )

        d = result.to_dict()
        assert d["valid"] is True
        assert d["can_import"] is True
        assert d["version_status"] == "match"
        assert d["backup_version"] == "4.9.0"
        assert d["confirm_message"] == "确认导入？"
        assert "警告1" in d["warnings"]
        assert d["backup_summary"]["tables"] == ["table1"]


class TestPreCheck:
    """预检查功能测试"""

    def test_pre_check_file_not_exists(self, mock_main_db):
        """测试预检查不存在的文件"""
        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check("/nonexistent/file.zip")

        assert result.valid is False
        assert "不存在" in result.error

    def test_pre_check_invalid_zip(self, mock_main_db, tmp_path):
        """测试预检查无效的 ZIP 文件"""
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(invalid_zip))

        assert result.valid is False
        assert "ZIP" in result.error or "无效" in result.error

    def test_pre_check_missing_manifest(self, mock_main_db, tmp_path):
        """测试预检查缺少 manifest 的 ZIP 文件"""
        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "test content")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is False
        assert "manifest" in result.error.lower()

    def test_pre_check_version_match(self, mock_main_db, tmp_path):
        """测试预检查版本匹配"""
        zip_path = tmp_path / "backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": VERSION,
            "created_at": "2024-01-01T12:00:00",
            "tables": {"platform_stats": 1},
            "has_knowledge_bases": True,
            "has_config": True,
            "directories": ["plugins"],
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is True
        assert result.can_import is True
        assert result.version_status == "match"
        assert result.backup_version == VERSION
        # confirm_message 现在由前端生成，后端不再生成
        assert result.backup_summary["has_knowledge_bases"] is True

    def test_pre_check_minor_version_diff(self, mock_main_db, tmp_path):
        """测试预检查小版本差异"""
        # 构造一个同主版本但小版本不同的版本
        major_version = _get_major_version(VERSION)
        minor_diff_version = f"{major_version}.999"

        zip_path = tmp_path / "backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": minor_diff_version,
            "created_at": "2024-01-01T12:00:00",
            "tables": {},
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is True
        assert result.can_import is True
        assert result.version_status == "minor_diff"
        # 版本消息由前端 i18n 生成，后端 warnings 列表不再包含版本相关消息
        # warnings 列表保留用于其他非版本相关的警告

    def test_pre_check_major_version_diff(self, mock_main_db, tmp_path):
        """测试预检查主版本差异"""
        zip_path = tmp_path / "backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": "0.0.1",  # 主版本不同
            "created_at": "2024-01-01T12:00:00",
            "tables": {},
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is True  # 文件有效
        assert result.can_import is False  # 但不能导入
        assert result.version_status == "major_diff"
        # 版本消息由前端 i18n 生成，后端 warnings 列表不再包含版本相关消息


class TestVersionCompatibility:
    """版本兼容性检查测试"""

    def test_check_version_compatibility_match(self, mock_main_db):
        """测试版本完全匹配"""
        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer._check_version_compatibility(VERSION)

        assert result["status"] == "match"
        assert result["can_import"] is True

    def test_check_version_compatibility_minor_diff(self, mock_main_db):
        """测试小版本差异"""
        major_version = _get_major_version(VERSION)
        minor_diff_version = f"{major_version}.999"

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer._check_version_compatibility(minor_diff_version)

        assert result["status"] == "minor_diff"
        assert result["can_import"] is True

    def test_check_version_compatibility_major_diff(self, mock_main_db):
        """测试主版本差异"""
        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer._check_version_compatibility("0.0.1")

        assert result["status"] == "major_diff"
        assert result["can_import"] is False

    def test_check_version_compatibility_empty_version(self, mock_main_db):
        """测试空版本号"""
        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer._check_version_compatibility("")

        assert result["status"] == "major_diff"
        assert result["can_import"] is False


class TestModelMappings:
    """测试模型映射配置"""

    def test_main_db_models_not_empty(self):
        """测试主数据库模型映射非空"""
        assert len(MAIN_DB_MODELS) > 0

    def test_main_db_models_contain_expected_tables(self):
        """测试主数据库模型映射包含预期的表"""
        expected_tables = [
            "platform_stats",
            "conversations",
            "personas",
            "preferences",
            "chatui_projects",
            "session_project_relations",
            "attachments",
        ]
        for table in expected_tables:
            assert table in MAIN_DB_MODELS, f"Missing table: {table}"

    def test_kb_metadata_models_not_empty(self):
        """测试知识库元数据模型映射非空"""
        assert len(KB_METADATA_MODELS) > 0

    def test_kb_metadata_models_contain_expected_tables(self):
        """测试知识库元数据模型映射包含预期的表"""
        expected_tables = [
            "knowledge_bases",
            "kb_documents",
            "kb_media",
        ]
        for table in expected_tables:
            assert table in KB_METADATA_MODELS, f"Missing table: {table}"


class TestBackupIntegration:
    """备份集成测试"""

    @pytest.mark.asyncio
    async def test_export_import_roundtrip(self, tmp_path):
        """测试导出-导入往返"""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config_path = data_dir / "cmd_config.json"
        config_path.write_text(json.dumps({"setting": "value"}))

        attachments_dir = data_dir / "attachments"
        attachments_dir.mkdir()

        # 创建模拟数据库
        mock_db = MagicMock()
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        mock_db.get_db.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )

        # 导出
        exporter = AstrBotExporter(
            main_db=mock_db,
            kb_manager=None,
            config_path=str(config_path),
        )

        zip_path = await exporter.export_all(output_dir=str(backup_dir))
        assert os.path.exists(zip_path)

        # 验证 ZIP 内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 读取 manifest
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["astrbot_version"] == VERSION
            assert manifest["origin"] == "exported"  # 验证备份来源标记

            # 读取配置
            config = json.loads(zf.read("config/cmd_config.json"))
            assert config["setting"] == "value"

            # 读取主数据库
            main_db = json.loads(zf.read("databases/main_db.json"))
            assert "platform_stats" in main_db


class _StubUploadFile:
    """模拟 adapter 风格 save() 契约的上传文件对象"""

    def __init__(self, data: bytes):
        self._data = data

    async def save(self, destination, *, max_bytes=None) -> int:
        if max_bytes is not None and len(self._data) > max_bytes:
            raise UploadTooLargeError(max_bytes)
        Path(destination).write_bytes(self._data)
        return len(self._data)


class TestBackupUploadLimits:
    """备份上传大小限制测试"""

    @pytest.fixture
    def backup_service(self, tmp_path):
        """创建使用临时目录的 BackupService"""
        service = BackupService(db=MagicMock(), core_lifecycle=MagicMock())
        service.backup_dir = str(tmp_path / "backups")
        service.chunks_dir = str(tmp_path / "backups" / ".chunks")
        service.chunked_uploads.chunks_root = Path(service.chunks_dir)
        return service

    def test_upload_init_rejects_oversized_total(self, backup_service):
        """声明总大小超过上限时拒绝初始化"""
        with pytest.raises(BackupServiceError, match="size limit"):
            backup_service.upload_init(
                {"filename": "b.zip", "total_size": MAX_BACKUP_TOTAL_BYTES + 1},
                owner="tester",
            )

    @pytest.mark.asyncio
    async def test_upload_chunk_rejects_oversized_chunk(self, backup_service):
        """超过 CHUNK_SIZE 的分片被拒绝且不产生残留文件"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": CHUNK_SIZE}, owner="tester"
        )
        big_chunk = _StubUploadFile(b"x" * (CHUNK_SIZE + 1))

        with pytest.raises(BackupServiceError, match="Chunk exceeds the size limit"):
            await backup_service.upload_chunk(
                upload_id=session["upload_id"],
                chunk_index_str="0",
                chunk_file=big_chunk,
                owner="tester",
            )

        await backup_service.cleanup_upload_session(session["upload_id"])

    @pytest.mark.asyncio
    async def test_upload_chunk_accepts_small_chunk(self, backup_service):
        """正常大小的分片可以上传"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="tester"
        )
        result = await backup_service.upload_chunk(
            upload_id=session["upload_id"],
            chunk_index_str="0",
            chunk_file=_StubUploadFile(b"x" * 100),
            owner="tester",
        )
        assert result["received"] == 1
        assert result["total"] == 1

        await backup_service.cleanup_upload_session(session["upload_id"])

    @pytest.mark.asyncio
    async def test_upload_complete_rejects_size_mismatch(self, backup_service):
        """合并后大小与声明大小不一致时拒绝完成（分片带外损坏的兜底）"""
        declared = CHUNK_SIZE + 100
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": declared}, owner="tester"
        )
        await backup_service.upload_chunk(
            upload_id=session["upload_id"],
            chunk_index_str="0",
            chunk_file=_StubUploadFile(b"x" * CHUNK_SIZE),
            owner="tester",
        )
        await backup_service.upload_chunk(
            upload_id=session["upload_id"],
            chunk_index_str="1",
            chunk_file=_StubUploadFile(b"x" * 100),
            owner="tester",
        )
        # 传片时的字节数校验已拦截短写；此处绕过保存路径直接篡改磁盘上的
        # 分片（模拟带外损坏），验证合并时的大小复核仍然兜底
        chunk_path = (
            backup_service.chunked_uploads.chunks_root / session["upload_id"] / "1.part"
        )
        chunk_path.write_bytes(b"x" * 50)

        with pytest.raises(BackupServiceError, match="does not match"):
            await backup_service.upload_complete(
                {"upload_id": session["upload_id"]}, owner="tester"
            )

        await backup_service.cleanup_upload_session(session["upload_id"])

    @pytest.mark.asyncio
    async def test_session_rejects_other_owner(self, backup_service):
        """会话绑定创建者，其他用户无法传片、合并或取消"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )

        with pytest.raises(BackupServiceError, match="not found or expired"):
            await backup_service.upload_chunk(
                upload_id=session["upload_id"],
                chunk_index_str="0",
                chunk_file=_StubUploadFile(b"x" * 100),
                owner="mallory",
            )
        with pytest.raises(BackupServiceError, match="not found or expired"):
            await backup_service.upload_complete(
                {"upload_id": session["upload_id"]}, owner="mallory"
            )
        with pytest.raises(BackupServiceError, match="not found or expired"):
            await backup_service.upload_abort(
                {"upload_id": session["upload_id"]}, owner="mallory"
            )

        # 会话在攻击后仍然存活，真正的主人可以正常使用
        result = await backup_service.upload_chunk(
            upload_id=session["upload_id"],
            chunk_index_str="0",
            chunk_file=_StubUploadFile(b"x" * 100),
            owner="alice",
        )
        assert result["received"] == 1

        await backup_service.cleanup_upload_session(session["upload_id"])

    @pytest.mark.asyncio
    async def test_upload_status_reports_progress(self, backup_service):
        """状态查询返回已收分片，支持乱序后的续传定位"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": CHUNK_SIZE * 2}, owner="tester"
        )
        # 故意乱序：只传第 1 片（索引 1）
        await backup_service.upload_chunk(
            upload_id=session["upload_id"],
            chunk_index_str="1",
            chunk_file=_StubUploadFile(b"x" * CHUNK_SIZE),
            owner="tester",
        )

        status = backup_service.upload_status(
            {"upload_id": session["upload_id"]}, owner="tester"
        )
        assert status["received_chunks"] == [1]
        assert status["total_chunks"] == 2
        assert status["chunk_size"] == CHUNK_SIZE
        assert 0 < status["expires_in"] <= 3600

        await backup_service.cleanup_upload_session(session["upload_id"])

    def test_upload_status_bound_to_owner(self, backup_service):
        """状态查询同样绑定 owner，且不能探测他人会话"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )

        with pytest.raises(BackupServiceError, match="not found or expired"):
            backup_service.upload_status(
                {"upload_id": session["upload_id"]}, owner="mallory"
            )
        with pytest.raises(BackupServiceError, match="not found or expired"):
            backup_service.upload_status({"upload_id": "no-such-id"}, owner="alice")

    def test_upload_status_does_not_extend_lifetime(self, backup_service):
        """查询状态不得刷新 last_activity，否则轮询会让会话永不过期"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        inner = backup_service.chunked_uploads.get_session(
            session["upload_id"], owner="alice"
        )
        inner.last_activity -= 100  # 模拟会话已经闲置了 100 秒

        status = backup_service.upload_status(
            {"upload_id": session["upload_id"]}, owner="alice"
        )
        assert status["expires_in"] <= 3600 - 100 + 1
        assert (
            backup_service.chunked_uploads.get_session(
                session["upload_id"], owner="alice"
            ).last_activity
            == inner.last_activity
        )

    @pytest.mark.asyncio
    async def test_failed_chunk_retry_preserves_received_chunk(self, backup_service):
        """同索引重传失败不得破坏已收到的分片"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]
        good = b"x" * 100
        await backup_service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubUploadFile(good),
            owner="alice",
        )

        # 同索引用超大分片重试：必须报错，且已收到的分片原样保留
        with pytest.raises(BackupServiceError, match="size limit"):
            await backup_service.upload_chunk(
                upload_id=upload_id,
                chunk_index_str="0",
                chunk_file=_StubUploadFile(b"y" * (CHUNK_SIZE + 1)),
                owner="alice",
            )

        result = await backup_service.upload_complete(
            {"upload_id": upload_id}, owner="alice"
        )
        assert result["size"] == 100
        merged = Path(backup_service.backup_dir) / result["filename"]
        assert merged.read_bytes() == good

    @pytest.mark.asyncio
    async def test_chunk_publish_failure_cleans_temp(self, backup_service, monkeypatch):
        """原子改名失败时临时文件必须清理，已收分片不受影响"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": CHUNK_SIZE + 100}, owner="alice"
        )
        upload_id = session["upload_id"]
        await backup_service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubUploadFile(b"x" * CHUNK_SIZE),
            owner="alice",
        )

        def _boom(*args, **kwargs):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(
            "astrbot.dashboard.services.chunked_upload_service.os.replace", _boom
        )
        with pytest.raises(OSError, match="simulated rename failure"):
            await backup_service.upload_chunk(
                upload_id=upload_id,
                chunk_index_str="1",
                chunk_file=_StubUploadFile(b"y" * 100),
                owner="alice",
            )

        chunk_dir = backup_service.chunked_uploads.chunks_root / upload_id
        assert not list(chunk_dir.glob("*.tmp"))
        # 改名失败的分片未登记，已收到的第 0 片完好
        status = backup_service.upload_status({"upload_id": upload_id}, owner="alice")
        assert status["received_chunks"] == [0]
        assert (chunk_dir / "0.part").read_bytes() == b"x" * CHUNK_SIZE

        await backup_service.cleanup_upload_session(upload_id)

    @pytest.mark.asyncio
    async def test_expired_session_is_rejected_and_abortable(self, backup_service):
        """过期会话不可用（get_session 强制过期），但 abort 清理仍有效"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]
        inner = backup_service.chunked_uploads.get_session(upload_id, owner="alice")
        inner.last_activity -= 7200  # 闲置两小时，已过 1 小时过期线

        with pytest.raises(BackupServiceError, match="not found or expired"):
            backup_service.upload_status({"upload_id": upload_id}, owner="alice")
        with pytest.raises(BackupServiceError, match="not found or expired"):
            await backup_service.upload_chunk(
                upload_id=upload_id,
                chunk_index_str="0",
                chunk_file=_StubUploadFile(b"x" * 100),
                owner="alice",
            )

        # abort 是清理路径，对过期会话仍然有效
        await backup_service.upload_abort({"upload_id": upload_id}, owner="alice")
        assert upload_id not in backup_service.chunked_uploads.sessions

    @pytest.mark.asyncio
    async def test_upload_init_starts_cleanup_task(self, backup_service):
        """备份上传初始化必须启动过期清理任务"""
        backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        task = backup_service.chunked_uploads._cleanup_task
        assert task is not None and not task.done()
        task.cancel()

    @pytest.mark.asyncio
    async def test_cleanup_failure_keeps_session_for_retry(
        self, backup_service, monkeypatch
    ):
        """目录删除失败时会话保持注册，看门狗可重试，成功后正常摘除"""
        import shutil

        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]

        calls = {"n": 0}
        real_rmtree = shutil.rmtree

        def _flaky(path, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transient fs error")
            return real_rmtree(path, *args, **kwargs)

        monkeypatch.setattr(
            "astrbot.dashboard.services.chunked_upload_service.shutil.rmtree", _flaky
        )
        await backup_service.chunked_uploads.cleanup_session(upload_id)
        assert upload_id in backup_service.chunked_uploads.sessions

        await backup_service.chunked_uploads.cleanup_session(upload_id)
        assert upload_id not in backup_service.chunked_uploads.sessions

    @pytest.mark.asyncio
    async def test_short_write_chunk_is_rejected(self, backup_service):
        """save() 落盘字节数不足时不得发布分片，且不留临时文件"""
        session = backup_service.upload_init(
            {"filename": "b.zip", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]

        with pytest.raises(BackupServiceError, match="size mismatch"):
            await backup_service.upload_chunk(
                upload_id=upload_id,
                chunk_index_str="0",
                chunk_file=_StubUploadFile(b"x" * 50),
                owner="alice",
            )

        # 分片未发布、无临时文件残留；补传完整数据后正常完成
        chunk_dir = backup_service.chunked_uploads.chunks_root / upload_id
        assert not list(chunk_dir.glob("*.tmp"))
        status = backup_service.upload_status({"upload_id": upload_id}, owner="alice")
        assert status["received_chunks"] == []

        await backup_service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubUploadFile(b"y" * 100),
            owner="alice",
        )
        result = await backup_service.upload_complete(
            {"upload_id": upload_id}, owner="alice"
        )
        assert result["size"] == 100


class TestBackupExportDoesNotBlockEventLoop:
    """测试备份导出不会阻塞事件循环（归档操作在专用工作线程中执行）"""

    @staticmethod
    def _make_exporter(data_dir: Path) -> AstrBotExporter:
        """构造一个不访问真实用户数据的导出器

        Args:
            data_dir: 作为备份数据源的临时数据目录

        Returns:
            AstrBotExporter: 只依赖 mock 数据库与临时配置目录的导出器实例
        """
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        mock_db = MagicMock()
        mock_db.get_db.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
        return AstrBotExporter(
            main_db=mock_db,
            kb_manager=None,
            config_path=str(data_dir / "cmd_config.json"),
        )

    @staticmethod
    def _make_compressible_plugin_dir(data_dir: Path, blob_count: int = 4) -> Path:
        """创建不可压缩的大文件目录，保证 DEFLATE 有可测量的计算量

        Args:
            data_dir: 作为备份数据源的临时数据目录
            blob_count: 生成的随机数据文件数量，每个 16 MiB

        Returns:
            Path: 插件目录路径
        """
        plugin_dir = data_dir / "plugins"
        plugin_dir.mkdir(exist_ok=True)
        for index in range(blob_count):
            (plugin_dir / f"blob_{index}.bin").write_bytes(os.urandom(16 * 1024 * 1024))
        return plugin_dir

    @staticmethod
    async def _watch_event_loop_gaps(gaps: list[float], stop: asyncio.Event) -> None:
        """以 5ms 心跳采样事件循环停顿，写入 ``gaps``

        Args:
            gaps: 每次心跳实际间隔的收集列表
            stop: 置位后心跳退出
        """
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.005)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    @pytest.mark.asyncio
    async def test_archive_writes_leave_event_loop_thread(self, tmp_path, monkeypatch):
        """归档写入必须发生在非事件循环线程中（线程守卫回归测试）"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = data_dir / "plugins"
        plugin_dir.mkdir()
        for index in range(5):
            (plugin_dir / f"plugin_{index}.txt").write_text(f"content-{index}" * 100)
        (plugin_dir / "nested").mkdir()
        (plugin_dir / "nested" / "deep.txt").write_text("deep content" * 100)

        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        write_threads: set[int] = set()
        real_write = zipfile.ZipFile.write
        real_writestr = zipfile.ZipFile.writestr

        def spy_write(*args, **kwargs):
            write_threads.add(threading.get_ident())
            return real_write(*args, **kwargs)

        def spy_writestr(*args, **kwargs):
            write_threads.add(threading.get_ident())
            return real_writestr(*args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", spy_write)
        monkeypatch.setattr(zipfile.ZipFile, "writestr", spy_writestr)

        loop_thread_id = threading.get_ident()
        zip_path = await exporter.export_all(output_dir=str(backup_dir))

        assert os.path.exists(zip_path)
        # 归档写入确实发生过，且全部离开了事件循环线程
        assert write_threads
        assert loop_thread_id not in write_threads

        # 产物仍然完整可读
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.json" in namelist
            assert "directories/plugins/plugin_0.txt" in namelist
            assert "directories/plugins/nested/deep.txt" in namelist

    @pytest.mark.asyncio
    async def test_event_loop_stays_responsive_during_export(
        self, tmp_path, monkeypatch
    ):
        """导出压缩期间事件循环心跳既要有足够采样、也不能长时间停顿

        采样数量断言是回归守卫的核心：未修复的实现会把事件循环整段冻结，心跳任务
        一次都跑不到，只在导出结束后才采样到一两段间隔。没有这条断言时，空采样集
        会让下面的停顿断言退化成恒真。
        """
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = self._make_compressible_plugin_dir(data_dir)

        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        gaps: list[float] = []
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._watch_event_loop_gaps(gaps, stop_heartbeat)
        )

        started = time.monotonic()
        try:
            zip_path = await exporter.export_all(output_dir=str(backup_dir))
        finally:
            # 采样窗口包含导出结束后的收尾阶段，因此覆盖的是整段导出墙钟时间
            wall_time = time.monotonic() - started
            stop_heartbeat.set()
            await heartbeat_task

        assert os.path.exists(zip_path)

        # 事件循环必须真的被调度过：阻塞式实现下心跳一次都跑不到
        assert len(gaps) >= 20, f"事件循环仅采样到 {len(gaps)} 次心跳，导出期间被冻结"
        covered = sum(gaps)
        assert covered > wall_time * 0.8, (
            f"心跳仅覆盖 {covered:.3f}s / 导出墙钟 {wall_time:.3f}s"
        )

        max_gap = max(gaps)
        assert max_gap < 0.5, f"事件循环最长停顿 {max_gap:.3f}s"

    @pytest.mark.asyncio
    async def test_export_failure_shuts_down_executor_and_cleans_zip(
        self, tmp_path, monkeypatch
    ):
        """导出失败时异常向上抛出、执行器被回收且不留残缺 ZIP"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = data_dir / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.txt").write_text("content")

        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        def boom(zf):
            raise RuntimeError("simulated directory export failure")

        monkeypatch.setattr(
            "astrbot.core.backup.exporter._write_backup_directories", boom
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        with pytest.raises(RuntimeError, match="simulated directory export failure"):
            await exporter.export_all(output_dir=str(backup_dir))

        # 执行器已释放，且失败路径清理了残缺 ZIP
        assert exporter._archive_executor is None
        assert list(backup_dir.glob("*.zip")) == []

    @pytest.mark.asyncio
    async def test_archive_helper_requires_active_executor(self):
        """未处于 export_all 中时归档转发必须显式报错，而非回退到默认线程池"""
        exporter = AstrBotExporter(main_db=MagicMock())

        with pytest.raises(RuntimeError, match="export_all"):
            await exporter._run_in_archive_thread(lambda: None)

    @pytest.mark.asyncio
    async def test_concurrent_export_on_same_instance_is_rejected(
        self, tmp_path, monkeypatch
    ):
        """同一实例上的并发导出必须立即失败，且不影响首个导出"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = self._make_compressible_plugin_dir(data_dir, blob_count=1)

        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        # 让首个导出停在归档线程里，保证第二个调用确实与之并发
        write_started = threading.Event()
        release_write = threading.Event()
        real_write = zipfile.ZipFile.write

        def blocking_write(*args, **kwargs):
            write_started.set()
            release_write.wait(timeout=30)
            return real_write(*args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", blocking_write)

        first_task = asyncio.create_task(
            exporter.export_all(output_dir=str(backup_dir))
        )
        try:
            assert await asyncio.to_thread(write_started.wait, 30)

            with pytest.raises(RuntimeError, match="already running"):
                await exporter.export_all(output_dir=str(backup_dir))

            # 拒绝发生在动用实例状态之前：首个导出的执行器仍然有效
            assert exporter._archive_executor is not None
        finally:
            release_write.set()

        zip_path = await first_task
        assert os.path.exists(zip_path)
        assert exporter._archive_executor is None

        # 只有首个导出产物，被拒绝的调用没有留下残缺 ZIP
        assert [path.name for path in backup_dir.glob("*.zip")] == [
            os.path.basename(zip_path)
        ]
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None

    @pytest.mark.asyncio
    async def test_cancellation_closes_archive_and_keeps_loop_responsive(
        self, tmp_path, monkeypatch
    ):
        """导出中途取消：归档被正确关闭、不留残缺 ZIP、事件循环不被拖住"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = self._make_compressible_plugin_dir(data_dir, blob_count=1)

        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        write_started = asyncio.Event()
        real_write = zipfile.ZipFile.write

        def signalling_write(*args, **kwargs):
            write_started.set()
            return real_write(*args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", signalling_write)

        gaps: list[float] = []
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._watch_event_loop_gaps(gaps, stop_heartbeat)
        )

        export_task = asyncio.create_task(
            exporter.export_all(output_dir=str(backup_dir))
        )
        try:
            await asyncio.wait_for(write_started.wait(), timeout=30)
            gaps.clear()

            export_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await export_task
            cancelled_gaps = list(gaps)
        finally:
            stop_heartbeat.set()
            await heartbeat_task

        # 取消后的收尾不能把事件循环拖住（旧实现会同步等待压缩结束）
        assert cancelled_gaps
        assert max(cancelled_gaps) < 0.5, (
            f"取消期间事件循环最长停顿 {max(cancelled_gaps):.3f}s"
        )

        # 残缺 ZIP 已被清理，不会留下看似可读的损坏文件
        assert list(backup_dir.glob("*.zip")) == []
        assert exporter._archive_executor is None
        assert not [
            thread
            for thread in threading.enumerate()
            if thread.name.startswith("astrbot-backup-zip")
        ]

        # 同一数据目录上的新实例仍能正常导出
        retry_exporter = self._make_exporter(data_dir)
        zip_path = await retry_exporter.export_all(output_dir=str(backup_dir))
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None
            assert "manifest.json" in zf.namelist()

    @pytest.mark.asyncio
    async def test_export_structure_is_stable(self, tmp_path, monkeypatch):
        """归档结构稳定：成员清单一致、校验和与内容匹配、目录统计正确"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = data_dir / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.txt").write_text("content" * 10)
        (plugin_dir / "nested").mkdir()
        (plugin_dir / "nested" / "deep.txt").write_text("deep" * 10)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(plugin_dir)},
        )

        first_dir = tmp_path / "backups-a"
        second_dir = tmp_path / "backups-b"
        first_zip = await self._make_exporter(data_dir).export_all(
            output_dir=str(first_dir)
        )
        second_zip = await self._make_exporter(data_dir).export_all(
            output_dir=str(second_dir)
        )

        with (
            zipfile.ZipFile(first_zip) as first,
            zipfile.ZipFile(second_zip) as second,
        ):
            # 归档完整可用，且同一份数据的两次导出结构完全一致
            assert first.testzip() is None
            assert second.testzip() is None
            assert first.namelist() == second.namelist()
            assert set(first.namelist()) == {
                "databases/main_db.json",
                "config/cmd_config.json",
                "directories/plugins/plugin.txt",
                "directories/plugins/nested/deep.txt",
                "manifest.json",
            }

            first_manifest = json.loads(first.read("manifest.json"))
            second_manifest = json.loads(second.read("manifest.json"))
            # exported_at 每次不同，其余结构必须逐字节一致
            first_manifest.pop("exported_at")
            second_manifest.pop("exported_at")
            assert first_manifest == second_manifest

            # manifest 中的校验和与归档内实际内容逐项一致
            assert first_manifest["checksums"]
            for path, checksum in first_manifest["checksums"].items():
                assert path in first.namelist()
                digest = hashlib.sha256(first.read(path)).hexdigest()
                assert checksum == f"sha256:{digest}"

            assert first_manifest["statistics"]["directories"] == {
                "plugins": {"files": 2, "size": 110}
            }


class _TeardownInterrupt(BaseException):
    """模拟 KeyboardInterrupt/SystemExit 这类不继承 Exception 的收尾中断"""


class TestBackupExportTeardown:
    """导出收尾语义：归档收尾失败与取消都不得掩盖真正的导出错误"""

    @staticmethod
    def _make_exporter(data_dir: Path) -> AstrBotExporter:
        """构造一个不访问真实用户数据的导出器

        Args:
            data_dir: 作为备份数据源的临时数据目录

        Returns:
            AstrBotExporter: 只依赖 mock 数据库与临时配置目录的导出器实例
        """
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        mock_db = MagicMock()
        mock_db.get_db.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
        return AstrBotExporter(
            main_db=mock_db,
            kb_manager=None,
            config_path=str(data_dir / "cmd_config.json"),
        )

    @staticmethod
    def _make_data_dir(tmp_path: Path) -> Path:
        """创建带配置文件与插件目录的临时数据目录

        Args:
            tmp_path: pytest 提供的临时目录

        Returns:
            Path: 已填充的数据目录
        """
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cmd_config.json").write_text(json.dumps({"test": "config"}))
        plugin_dir = data_dir / "plugins"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.txt").write_text("content")
        return data_dir

    @staticmethod
    def _fail_end_record(*args, **kwargs):
        """模拟中央目录写入失败，即 ENOSPC/EIO/配额耗尽真正暴露的位置"""
        raise OSError(errno.ENOSPC, "No space left on device")

    @pytest.mark.asyncio
    async def test_close_failure_is_reported_as_export_failure(
        self, tmp_path, monkeypatch
    ):
        """收尾失败时 export_all 必须抛异常、清理残缺 ZIP 并释放执行器

        修复前该失败只被记成日志：export_all 正常返回路径，磁盘上留下一个
        无法打开的 ZIP，调用方据此上报“备份成功”，用户在导入时才发现损坏。
        """
        data_dir = self._make_data_dir(tmp_path)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(data_dir / "plugins")},
        )
        monkeypatch.setattr(zipfile.ZipFile, "_write_end_record", self._fail_end_record)

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        with pytest.raises(OSError) as excinfo:
            await exporter.export_all(output_dir=str(backup_dir))

        assert excinfo.value.errno == errno.ENOSPC
        # 残缺 ZIP 不得留在输出目录，否则调用方会拿它当成功产物上报
        assert list(backup_dir.glob("*.zip")) == []
        # 实例必须仍然可用，不能因为收尾失败而永远卡在“already running”
        # 即：正常结束时执行器已被释放，再入保护不会拒绝后续调用
        with monkeypatch.context() as retry_finalisation:
            retry_finalisation.setattr(
                zipfile.ZipFile, "_write_end_record", self._fail_end_record
            )
            with pytest.raises(OSError) as retry_excinfo:
                await exporter.export_all(output_dir=str(backup_dir))
        assert retry_excinfo.value.errno == errno.ENOSPC
        assert list(backup_dir.glob("*.zip")) == []

    @pytest.mark.asyncio
    async def test_close_failure_keeps_original_error_as_cause(
        self, tmp_path, monkeypatch
    ):
        """导出本身出错且收尾也失败时，两个错误都要能追溯"""
        data_dir = self._make_data_dir(tmp_path)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(data_dir / "plugins")},
        )

        def boom(zf):
            raise RuntimeError("simulated directory export failure")

        monkeypatch.setattr(
            "astrbot.core.backup.exporter._write_backup_directories", boom
        )
        monkeypatch.setattr(zipfile.ZipFile, "_write_end_record", self._fail_end_record)

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        with pytest.raises(OSError) as excinfo:
            await exporter.export_all(output_dir=str(backup_dir))

        assert excinfo.value.errno == errno.ENOSPC
        assert isinstance(excinfo.value.__cause__, RuntimeError)
        assert "simulated directory export failure" in str(excinfo.value.__cause__)
        assert list(backup_dir.glob("*.zip")) == []

    @pytest.mark.asyncio
    async def test_base_exception_in_teardown_still_releases_instance(
        self, tmp_path, monkeypatch
    ):
        """收尾抛出 BaseException 时执行器仍必须释放，实例不能被永久锁死

        修复前收尾只捕获 Exception：BaseException（KeyboardInterrupt/SystemExit）
        会直接冲出 finally，跳过 ``self._archive_executor = None``，此后同一实例上的
        每次 export_all 都会以“already running”被拒绝。
        """
        data_dir = self._make_data_dir(tmp_path)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(data_dir / "plugins")},
        )

        def interrupt_end_record(*args, **kwargs):
            raise _TeardownInterrupt("simulated interrupt while finalising the archive")

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        # 只在首次导出注入故障，之后要验证同一实例可以继续工作
        with monkeypatch.context() as failing_finalisation:
            failing_finalisation.setattr(
                zipfile.ZipFile, "_write_end_record", interrupt_end_record
            )
            with pytest.raises(_TeardownInterrupt):
                await exporter.export_all(output_dir=str(backup_dir))

        # 执行器必须已释放：这正是再入保护检查的状态
        assert exporter._archive_executor is None

        # 同一实例仍然可用，而不是从此永远抛 "already running"
        zip_path = await exporter.export_all(output_dir=str(backup_dir))
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None

    @pytest.mark.asyncio
    async def test_successful_export_still_returns_usable_archive(
        self, tmp_path, monkeypatch
    ):
        """成功路径不受影响：仍然返回路径，且归档完整可读"""
        data_dir = self._make_data_dir(tmp_path)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(data_dir / "plugins")},
        )

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        zip_path = await exporter.export_all(output_dir=str(backup_dir))

        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None
            assert "manifest.json" in zf.namelist()

        # 导出器释放了归档执行器：同一实例可以立刻再导出一份完整备份
        second_zip_path = await exporter.export_all(output_dir=str(backup_dir))
        assert os.path.exists(second_zip_path)
        with zipfile.ZipFile(second_zip_path) as zf:
            assert zf.testzip() is None
            assert "manifest.json" in zf.namelist()

    @pytest.mark.asyncio
    async def test_real_error_wins_over_cancellation_during_teardown(
        self, tmp_path, monkeypatch
    ):
        """收尾期间被取消时，真正的导出错误必须胜出

        修复前收尾无条件重抛 CancelledError：调用方的 ``except Exception`` 看不到
        真正的失败原因，任务会一直停在 processing。
        """
        data_dir = self._make_data_dir(tmp_path)
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {"plugins": str(data_dir / "plugins")},
        )

        # 本用例需要收尾的 close 停在归档线程里，以便在收尾期间投递取消
        close_started = threading.Event()
        release_close = threading.Event()
        real_close = zipfile.ZipFile.close

        # 记录本次导出自己的归档实例。按位置取出（当且仅当本次导出真的调用过它，
        # 出口才有值），因此取值前后都不需要额外的时序假设。
        archive_holder: list[zipfile.ZipFile] = []

        def boom(zf):
            # 这里拿到的就是本次导出自己打开的归档实例，先记下来
            # （即收尾 close 的同步时机），再抛出真正的导出错误
            archive_holder.append(zf)
            raise RuntimeError("simulated directory export failure")

        # 同步必须锚定「本次导出的那个归档实例」：``close`` 是类级补丁，而
        # ``ZipFile.__del__`` 同样会调用它——同批次先跑完的用例留下的归档一旦被 gc
        # 回收，就会替真正的收尾把 ``close_started`` 提前置位（实测这正是修复前
        # ~67s = 两个 30s 超时的来源：一次陈旧 close、一次真正的 close）。取消因此
        # 打在 ``await asyncio.shield(open_task)`` 这个「打开」等待上，而那时还没有
        # 任何导出错误，收尾只能重抛 CancelledError，用例随之失败。
        # 因此这里只对本次导出的归档阻塞并置位，其余实例一律直接透传给真实 close，
        # 不发信号也不阻塞：同步点唯一，且不依赖 gc 时机或用例顺序。
        def blocking_close(zf_self):
            if not archive_holder or zf_self is not archive_holder[0]:
                return real_close(zf_self)
            close_started.set()
            release_close.wait(timeout=10)
            return real_close(zf_self)

        monkeypatch.setattr(zipfile.ZipFile, "close", blocking_close)

        exporter = self._make_exporter(data_dir)
        backup_dir = tmp_path / "backups"

        # 只在首次导出注入故障，之后要验证同一实例可以继续工作
        with monkeypatch.context() as failing_export:
            failing_export.setattr(
                "astrbot.core.backup.exporter._write_backup_directories", boom
            )

            export_task = asyncio.create_task(
                exporter.export_all(output_dir=str(backup_dir))
            )
            try:
                # 本地临时目录导出只需数秒，10s 足够；不再各花 30s 死等
                assert await asyncio.to_thread(close_started.wait, 10)
                export_task.cancel()
            finally:
                release_close.set()

            # 真正的失败必须原样上报，而不是被收尾吸收的取消顶替
            with pytest.raises(RuntimeError, match="simulated directory export failure"):
                await export_task

        # 残留 ZIP 必须被清理
        assert list(backup_dir.glob("*.zip")) == []

        # 执行器必须已释放：这正是再入保护检查的状态
        assert exporter._archive_executor is None

        # 可观测证据：同一实例的后续导出立刻成功，而不是永远抛 "already running"
        zip_path = await exporter.export_all(output_dir=str(backup_dir))
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None
            assert "manifest.json" in zf.namelist()
