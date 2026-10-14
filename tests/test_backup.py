"""备份功能单元测试"""

import hashlib
import json
import os
import re
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path, PureWindowsPath
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
        stream = MagicMock()
        stream.mappings.return_value.__aiter__.return_value = []
        stream.close = AsyncMock()
        session.stream = AsyncMock(return_value=stream)

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
        with pytest.raises(ValueError, match="Incompatible major version"):
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
        with pytest.raises(ValueError, match="missing version information"):
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
                "warning limit reached" in str(call.args[0])
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
        assert any("does not exist" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_invalid_zip(self, mock_main_db, tmp_path):
        """测试导入无效的 ZIP 文件"""
        # 创建一个无效的文件
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = await importer.import_all(str(invalid_zip))

        assert result.success is False
        assert any("Invalid" in err or "ZIP" in err for err in result.errors)

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
        assert any("Incompatible major version" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_import_replace_fails_when_clear_main_db_fails(
        self, mock_main_db, tmp_path
    ):
        """测试 replace 模式下主库清空失败会直接终止导入

        清表已并入 _import_main_database 的导入事务（原子性），因此
        DatabaseClearError 现在从 _import_main_database 抛出。
        """
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
        importer._import_main_database = AsyncMock(
            side_effect=DatabaseClearError(
                "Failed to clear table platform_stats: db locked"
            )
        )

        result = await importer.import_all(str(zip_path), mode="replace")

        assert result.success is False
        assert any("Failed to clear main database" in err for err in result.errors)
        assert any(
            "Failed to clear table platform_stats" in err for err in result.errors
        )


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
        assert "does not exist" in result.error

    def test_pre_check_invalid_zip(self, mock_main_db, tmp_path):
        """测试预检查无效的 ZIP 文件"""
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(invalid_zip))

        assert result.valid is False
        assert "ZIP" in result.error or "Invalid" in result.error

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
        """测试预检查版本匹配

        摘要字段按 ZIP 实际条目推导（has_knowledge_bases / has_config
        不再是 manifest 自报字段），因此 zip 内需要放入对应条目。
        """
        zip_path = tmp_path / "backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": VERSION,
            "created_at": "2024-01-01T12:00:00",
            "tables": {"platform_stats": 1},
            "directories": ["plugins"],
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("databases/kb_metadata.json", json.dumps({}))
            zf.writestr("config/cmd_config.json", json.dumps({}))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is True
        assert result.can_import is True
        assert result.version_status == "match"
        assert result.backup_version == VERSION
        # confirm_message 现在由前端生成，后端不再生成
        assert result.backup_summary["has_knowledge_bases"] is True
        assert result.backup_summary["has_config"] is True

    def test_pre_check_summary_derived_from_real_entries(self, mock_main_db, tmp_path):
        """摘要只信实际条目：manifest 自报布尔字段不被采信（幽灵字段回归）"""
        zip_path = tmp_path / "backup.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": VERSION,
            "tables": {},
            "has_knowledge_bases": True,  # 自报字段：不应影响推导结果
            "has_config": True,
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = importer.pre_check(str(zip_path))

        assert result.valid is True
        # zip 中没有 KB/配置条目，即使 manifest 自报也为 False
        assert result.backup_summary["has_knowledge_bases"] is False
        assert result.backup_summary["has_config"] is False

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
        stream = MagicMock()
        stream.mappings.return_value.__aiter__.return_value = []
        stream.close = AsyncMock()
        session.stream = AsyncMock(return_value=stream)

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


def _make_working_mock_db():
    """Mock DB whose get_db()/session.begin() support the async CM protocol."""
    session = AsyncMock()
    session.begin = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    db = MagicMock()
    db.get_db = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return db, session


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _component_checksum(entries: dict[str, str]) -> str:
    """Replicate the exporter's per-component digest for hand-built zips."""
    lines = sorted(f"{p}:{h}" for p, h in entries.items())
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


class TestSelectiveExport:
    """选择性导出测试"""

    @pytest.mark.parametrize(
        ("source", "relative_name", "archive_prefix"),
        [
            ("webchat", "imgs/legacy.png", "directories/webchat"),
            ("plugins", "example/main.py", "directories/plugins"),
            ("kb_media", "media/image.png", "files/kb_media/kb1"),
        ],
    )
    def test_windows_archive_paths_match_checksums(
        self, tmp_path, monkeypatch, source, relative_name, archive_prefix
    ):
        """Keep ZIP names and checksum keys portable for Windows source paths."""
        root = tmp_path / source
        file_path = root / relative_name
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"backup-content")
        exporter = AstrBotExporter(main_db=MagicMock())
        monkeypatch.setattr(
            "astrbot.core.backup.exporter.get_backup_directories",
            lambda: {source: root},
        )
        archive = tmp_path / "backup.zip"
        relative_to = Path.relative_to
        with zipfile.ZipFile(archive, "w") as zf, monkeypatch.context() as context:
            # Simulate Windows separators while retaining real local file I/O.
            context.setattr(
                Path,
                "relative_to",
                lambda path, *other: PureWindowsPath(*relative_to(path, *other).parts),
            )
            if source == "kb_media":
                helper = MagicMock(kb_dir=root, kb_medias_dir=root / "media")
                exporter._export_kb_media_files(zf, helper, "kb1")
            else:
                exporter._export_directories(zf, [source])

        entry = f"{archive_prefix}/{relative_name}"
        with zipfile.ZipFile(archive) as zf:
            assert zf.namelist() == [entry]
            assert exporter._checksums == {entry: _sha256(zf.read(entry))}

    @pytest.mark.asyncio
    async def test_export_selective_components(self, temp_backup_dir, temp_data_dir):
        """只导出勾选组件，manifest 记录实际写入的组件与聚合 hash"""
        db, _ = _make_working_mock_db()
        exporter = AstrBotExporter(
            main_db=db,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )

        zip_path = await exporter.export_all(
            output_dir=str(temp_backup_dir), components=["cmd_config"]
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            manifest = json.loads(zf.read("manifest.json"))

        assert "databases/main_db.json" not in namelist
        assert "config/cmd_config.json" in namelist
        assert manifest["components"] == ["cmd_config"]
        assert set(manifest["component_checksums"]) == {"cmd_config"}
        assert "config/cmd_config.json" in manifest["checksums"]
        assert manifest["version"] == "1.2"
        assert exporter.exported_components == ["cmd_config"]

    @pytest.mark.asyncio
    async def test_export_invalid_components_rejected(
        self, temp_backup_dir, temp_data_dir
    ):
        """空列表或全无效组件 id 被拒绝"""
        exporter = AstrBotExporter(
            main_db=MagicMock(),
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        with pytest.raises(ValueError):
            await exporter.export_all(output_dir=str(temp_backup_dir), components=[])
        with pytest.raises(ValueError):
            await exporter.export_all(
                output_dir=str(temp_backup_dir), components=["nope"]
            )

    @pytest.mark.asyncio
    async def test_export_mid_write_failure_cleans_up_zip(
        self, temp_backup_dir, temp_data_dir
    ):
        """回归：条目写入中途失败 -> 整个导出失败，半成品 ZIP 被清理"""
        src = temp_data_dir / "att.bin"
        src.write_bytes(b"x" * (2 << 20))

        db, _ = _make_working_mock_db()
        exporter = AstrBotExporter(
            main_db=db,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        exporter._export_attachment_records = AsyncMock(
            return_value=[{"path": str(src), "attachment_id": "x"}]
        )

        real_open = zipfile.ZipFile.open

        class _Boom:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, data):
                raise OSError("disk on fire")

        def fake_open(zf, name, mode="r", *args, **kwargs):
            if mode == "w":
                return _Boom()
            return real_open(zf, name, mode, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "open", fake_open):
            with pytest.raises(RuntimeError, match="mid-write"):
                await exporter.export_all(
                    output_dir=str(temp_backup_dir), components=["attachments"]
                )

        # 半成品 ZIP 已被清理，不留无法通过完整性校验的产物
        assert list(temp_backup_dir.glob("*.zip")) == []


class TestSelectiveImport:
    """选择性导入与两阶段预检测试"""

    async def _full_backup(self, tmp_path, temp_data_dir):
        """用真实 exporter 造一份 database + cmd_config 备份"""
        db, _ = _make_working_mock_db()
        exporter = AstrBotExporter(
            main_db=db,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        exporter._export_main_database = AsyncMock(
            return_value={"platform_stats": [], "conversations": [], "attachments": []}
        )
        return await exporter.export_all(
            output_dir=str(tmp_path / "bk"), components=["database", "cmd_config"]
        )

    @pytest.mark.asyncio
    async def test_import_selective_restore_only_selected(
        self, tmp_path, temp_data_dir
    ):
        """只恢复勾选组件：配置被替换，主库完全不被触碰"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)

        target = tmp_path / "restore_cfg.json"
        target.write_text(json.dumps({"old": "config"}))
        db, session = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None, config_path=str(target))

        result = await importer.import_all(zip_path, components=["cmd_config"])

        assert result.success, result.errors
        assert json.loads(target.read_text()) == {"test": "config"}
        assert result.imported_files.get("config") == 1
        session.execute.assert_not_awaited()  # 主库未被触碰

    @pytest.mark.asyncio
    async def test_import_empty_components_rejected(self, tmp_path, temp_data_dir):
        """components=[] 显式拒绝（与 None 的全量语义区分）"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)
        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        result = await importer.import_all(zip_path, components=[])
        assert result.success is False
        assert result.errors

    @pytest.mark.asyncio
    async def test_import_all_invalid_components_rejected(
        self, tmp_path, temp_data_dir
    ):
        """请求的组件全部无效时报错且不执行任何修改"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)
        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        result = await importer.import_all(zip_path, components=["nope1", "nope2"])
        assert result.success is False
        assert any(
            "None of the requested components can be restored" in e
            for e in result.errors
        )

    @pytest.mark.asyncio
    async def test_import_corrupt_config_aborts_zero_modification(
        self, tmp_path, temp_data_dir
    ):
        """配置条目 hash 不匹配（硬失败）-> 中止，已有文件零改动"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)
        bad = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(bad, "w") as zout:
            for item in zin.namelist():
                data = zin.read(item)
                if item == "config/cmd_config.json":
                    data = b'{"tampered": true}'
                zout.writestr(item, data)

        victim = tmp_path / "victim.json"
        victim.write_text(json.dumps({"precious": "data"}))
        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None, config_path=str(victim))

        result = await importer.import_all(str(bad), components=["cmd_config"])
        assert result.success is False
        assert any("checksum" in e for e in result.errors)
        assert json.loads(victim.read_text()) == {"precious": "data"}

    async def _legacy_zip(self, tmp_path, main_data: dict) -> str:
        """造一份无 checksum 的旧格式（v1.1）备份"""
        zip_path = tmp_path / "legacy.zip"
        manifest = {
            "version": "1.1",
            "astrbot_version": VERSION,
            "tables": {"main_db": list(main_data.keys())},
        }
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("databases/main_db.json", json.dumps(main_data))
        return str(zip_path)

    @pytest.mark.asyncio
    async def test_import_invalid_datetime_aborts_before_modification(self, tmp_path):
        """非法日期：严格归一化 + model_validate 在清库前拦截（零修改）"""
        zip_path = await self._legacy_zip(
            tmp_path,
            {
                "conversations": [
                    {
                        "conversation_id": "c1",
                        "platform_id": "p",
                        "user_id": "u",
                        "created_at": "not-a-date",
                    }
                ]
            },
        )
        db, session = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        result = await importer.import_all(zip_path, components=["database"])
        assert result.success is False
        assert any("Record validation failed" in e for e in result.errors)
        session.execute.assert_not_awaited()  # 清库未发生

    @pytest.mark.asyncio
    async def test_import_missing_required_field_aborts(self, tmp_path):
        """缺必需字段：普通构造能过、model_validate 拒绝（零修改）"""
        zip_path = await self._legacy_zip(tmp_path, {"conversations": [{}]})
        db, session = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        result = await importer.import_all(zip_path, components=["database"])
        assert result.success is False
        assert any("Record validation failed" in e for e in result.errors)
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_import_broken_component_three_states(self, tmp_path, temp_data_dir):
        """回归：UI 排除 broken 后返回 warning；默认恢复与显式选中 broken 中止"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)
        # 删掉 main_db.json 条目，制造"已声明但损坏"的 database
        broken_zip = tmp_path / "broken.zip"
        with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(broken_zip, "w") as zout:
            for item in zin.namelist():
                if item == "databases/main_db.json":
                    continue
                zout.writestr(item, zin.read(item))

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db,
            kb_manager=None,
            config_path=str(tmp_path / "cfg.json"),
        )

        # 默认恢复：遇 broken 中止
        result = await importer.import_all(str(broken_zip))
        assert result.success is False
        assert any("missing entries" in e for e in result.errors)

        # 显式排除 broken：恢复可用组件，result 带 warning 注明（不静默）
        result = await importer.import_all(str(broken_zip), components=["cmd_config"])
        assert result.success, result.errors
        assert any("excluded from this restore" in w for w in result.warnings)

        # 显式选中 broken 硬失败组件：修改前中止，不允许降格跳过
        result = await importer.import_all(
            str(broken_zip), components=["database", "cmd_config"]
        )
        assert result.success is False
        assert any("missing entries" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_import_legacy_roundtrip_from_real_export(
        self, tmp_path, temp_data_dir
    ):
        """真实 exporter 产物降级为旧格式后仍可恢复（缺失 checksum 走降级警告）"""
        zip_path = await self._full_backup(tmp_path, temp_data_dir)

        # 把 v1.2 manifest 降级成 v1.1：去掉新字段和 checksums
        legacy = tmp_path / "legacy_full.zip"
        with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(legacy, "w") as zout:
            for item in zin.namelist():
                data = zin.read(item)
                if item == "manifest.json":
                    manifest = json.loads(data)
                    manifest["version"] = "1.1"
                    for key in ("components", "component_checksums", "checksums"):
                        manifest.pop(key, None)
                    data = json.dumps(manifest).encode()
                zout.writestr(item, data)

        target = tmp_path / "restore.json"
        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None, config_path=str(target))

        result = await importer.import_all(str(legacy))
        assert result.success, result.errors
        assert json.loads(target.read_text()) == {"test": "config"}
        assert result.imported_files.get("config") == 1
        # 旧格式降级有聚合警告，不静默
        assert any("no checksum" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_import_main_db_single_transaction(self):
        """清表与插入在同一 session.begin() 事务内（原子性结构验证）"""
        db, session = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        await importer._import_main_database({"platform_stats": []}, clear=True)

        assert session.begin.call_count == 1
        # 13 张表各一次 delete，空数据无插入
        assert session.execute.await_count == len(MAIN_DB_MODELS)
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_main_db_clear_failure_raises_clear_error(self):
        """清表失败抛 DatabaseClearError（事务回滚，旧数据保留）"""
        db, session = _make_working_mock_db()
        session.execute = AsyncMock(side_effect=Exception("db locked"))
        importer = AstrBotImporter(main_db=db, kb_manager=None)

        with pytest.raises(DatabaseClearError):
            await importer._import_main_database({"platform_stats": []}, clear=True)

    @pytest.mark.asyncio
    async def test_import_corrupt_attachment_preserves_existing(
        self, tmp_path, temp_data_dir
    ):
        """坏附件（软失败）：跳过且结果带 warning，恢复前的原文件不受损"""
        attachments_dir = temp_data_dir / "attachments"
        victim = attachments_dir / "abc.jpg"
        victim.write_bytes(b"original-bytes")

        zip_path = tmp_path / "att.zip"
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["attachments"],
            "checksums": {"files/attachments/abc.jpg": "sha256:wrong"},
            "component_checksums": {"attachments": "sha256:whatever"},
            "directories": [],
        }
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("files/attachments/abc.jpg", b"tampered-bytes")

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )

        result = await importer.import_all(str(zip_path), components=["attachments"])
        assert result.success, result.errors
        assert any("verification failed" in w for w in result.warnings)
        # 原文件未被覆盖、未被删除
        assert victim.read_bytes() == b"original-bytes"

    @pytest.mark.asyncio
    async def test_v12_missing_checksum_soft_component_skipped(self, tmp_path):
        """v1.2 软失败组件条目缺 checksum（清单级错误）-> 整个组件跳过并记 error"""
        zip_path = tmp_path / "v12_bad.zip"
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["attachments"],
            "checksums": {},  # 条目缺 checksum：v1.2 不允许降级
            "component_checksums": {},
            "directories": [],
        }
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("files/attachments/a.jpg", b"data")

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db,
            kb_manager=None,
            config_path=str(tmp_path / "cfg.json"),
        )

        result = await importer.import_all(str(zip_path), components=["attachments"])
        assert result.success is False
        assert any("checksum" in e for e in result.errors)


class TestImportTaskResultRetention:
    """服务层：失败任务保留完整结果"""

    @pytest.fixture
    def backup_service(self, tmp_path):
        service = BackupService(db=MagicMock(), core_lifecycle=MagicMock())
        service.backup_dir = str(tmp_path / "backups")
        service.data_dir = str(tmp_path / "data")
        return service

    @pytest.mark.asyncio
    async def test_failed_import_task_keeps_full_result(self, backup_service, tmp_path):
        """导入失败时 result（含 warnings/errors）完整保留，可通过进度接口查询"""
        zip_path = tmp_path / "broken.zip"
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["database"],  # 声明了 database 但条目缺失
            "checksums": {},
            "component_checksums": {},
            "directories": [],
        }
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        backup_service._init_task("t1", "import")
        await backup_service.background_import_task("t1", str(zip_path))

        progress = backup_service.get_progress("t1")
        assert progress["status"] == "failed"
        # 完整 result 保留：errors 说明中止原因
        assert progress["result"] is not None
        assert any("missing entries" in e for e in progress["result"]["errors"])
        assert progress["error"]


class TestPreVerifyEdgeCases:
    """预检边界情况回归测试（评审修正 2/3/4/5）"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_entry", ["files/attachments/a.bin", "config/cmd_config.json"]
    )
    async def test_deflate_error_classified_by_component(self, tmp_path, bad_entry):
        """Preserve existing files and apply the component policy to broken DEFLATE."""
        entries = {
            "files/attachments/a.bin": b"attachment data" * 20,
            "config/cmd_config.json": b'{"restored": true}',
        }
        checksums = {name: _sha256(content) for name, content in entries.items()}
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["attachments", "cmd_config"],
            "checksums": checksums,
            "component_checksums": {
                "attachments": _component_checksum(
                    {"files/attachments/a.bin": checksums["files/attachments/a.bin"]}
                ),
                "cmd_config": _component_checksum(
                    {"config/cmd_config.json": checksums["config/cmd_config.json"]}
                ),
            },
        }
        zip_path = tmp_path / "deflate.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            for name, content in entries.items():
                zf.writestr(name, content)
            header_offset = zf.getinfo(bad_entry).header_offset

        archive = bytearray(zip_path.read_bytes())
        name_size, extra_size = struct.unpack_from("<HH", archive, header_offset + 26)
        data_offset = header_offset + 30 + name_size + extra_size
        # Set DEFLATE's block type to the reserved value without changing ZIP metadata.
        archive[data_offset] = (archive[data_offset] & 0xF8) | 0x07
        zip_path.write_bytes(archive)
        with zipfile.ZipFile(zip_path) as zf, pytest.raises(zlib.error):
            zf.read(bad_entry)

        config = tmp_path / "cmd_config.json"
        config.write_bytes(b'{"old": true}')
        attachments_dir = tmp_path / "attachments"
        attachments_dir.mkdir()
        attachment = attachments_dir / "a.bin"
        attachment.write_bytes(b"old attachment")
        importer = AstrBotImporter(main_db=MagicMock(), config_path=str(config))

        result = await importer.import_all(
            str(zip_path), components=manifest["components"]
        )

        assert attachment.read_bytes() == b"old attachment"
        if bad_entry.startswith("files/"):
            assert result.success, result.errors
            assert result.warnings
            assert config.read_bytes() == entries["config/cmd_config.json"]
        else:
            assert not result.success
            assert any(bad_entry in error for error in result.errors)
            assert config.read_bytes() == b'{"old": true}'

    @pytest.mark.asyncio
    async def test_missing_entry_with_corruption_preserves_directory(self, tmp_path):
        """Skip an incomplete directory before moving it, even with another bad file."""
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "existing.py").write_bytes(b"existing plugin")
        checksums = {
            "directories/plugins/a.py": _sha256(b"original a"),
            "directories/plugins/b.py": _sha256(b"original b"),
        }
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["plugins"],
            "directories": ["plugins"],
            "checksums": checksums,
            "component_checksums": {"plugins": _component_checksum(checksums)},
        }
        zip_path = tmp_path / "incomplete.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("directories/plugins/a.py", b"corrupted a")

        importer = AstrBotImporter(main_db=MagicMock())
        with patch(
            "astrbot.core.backup.importer.get_backup_directories",
            return_value={"plugins": str(plugins)},
        ):
            result = await importer.import_all(str(zip_path), components=["plugins"])

        assert not result.success
        assert any("directories/plugins/b.py" in error for error in result.errors)
        assert result.imported_directories == {}
        assert (plugins / "existing.py").read_bytes() == b"existing plugin"
        assert list(plugins.iterdir()) == [plugins / "existing.py"]
        assert not (tmp_path / "plugins.bak").exists()

    @pytest.mark.asyncio
    async def test_entry_read_error_classified_by_component(
        self, tmp_path, temp_data_dir
    ):
        """回归：条目读取错误（如 CRC）按组件分类，软失败不拖垮整个任务"""
        att_content = b"att-bytes"
        cfg_content = json.dumps({"k": "v"}).encode()
        att_hash = _sha256(att_content)
        cfg_hash = _sha256(cfg_content)
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["attachments", "cmd_config"],
            "checksums": {
                "files/attachments/abc.jpg": att_hash,
                "config/cmd_config.json": cfg_hash,
            },
            "component_checksums": {
                "attachments": _component_checksum(
                    {"files/attachments/abc.jpg": att_hash}
                ),
                "cmd_config": _component_checksum({"config/cmd_config.json": cfg_hash}),
            },
            "directories": [],
        }
        zip_path = tmp_path / "att_crc.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("files/attachments/abc.jpg", att_content)
            zf.writestr("config/cmd_config.json", cfg_content)

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db, kb_manager=None, config_path=str(tmp_path / "cfg.json")
        )

        real_hash = AstrBotImporter._hash_entry

        def flaky_hash(self, zf, name):
            if name.startswith("files/attachments/"):
                raise zipfile.BadZipFile("Bad CRC-32")
            return real_hash(self, zf, name)

        with patch.object(AstrBotImporter, "_hash_entry", flaky_hash):
            result = await importer.import_all(
                str(zip_path), components=["attachments", "cmd_config"]
            )

        # 软失败组件跳过并告警，正常组件不受影响
        assert result.success, result.errors
        assert any("attachments" in w for w in result.warnings)
        assert result.imported_files.get("config") == 1

    @pytest.mark.asyncio
    async def test_entry_read_error_hard_component_aborts(self, tmp_path):
        """条目读取错误落在硬失败组件上时中止导入"""
        cfg_content = json.dumps({"k": "v"}).encode()
        cfg_hash = _sha256(cfg_content)
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["cmd_config"],
            "checksums": {"config/cmd_config.json": cfg_hash},
            "component_checksums": {
                "cmd_config": _component_checksum({"config/cmd_config.json": cfg_hash})
            },
            "directories": [],
        }
        zip_path = tmp_path / "cfg_crc.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("config/cmd_config.json", cfg_content)

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db, kb_manager=None, config_path=str(tmp_path / "cfg.json")
        )
        with patch.object(
            AstrBotImporter,
            "_hash_entry",
            side_effect=zipfile.BadZipFile("Bad CRC-32"),
        ):
            result = await importer.import_all(str(zip_path), components=["cmd_config"])

        assert result.success is False
        assert any("Failed to read entry" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_v12_version_without_components_rejected(self, tmp_path):
        """回归：version=1.2 但缺 components/checksums 的备份不得走旧格式降级"""
        cfg_content = json.dumps({"k": "v"}).encode()
        manifest = {
            "version": "1.2",  # 声明 1.2 但缺 components/checksums 字段
            "astrbot_version": VERSION,
            "directories": [],
        }
        zip_path = tmp_path / "v12_malformed.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("config/cmd_config.json", cfg_content)

        victim = tmp_path / "victim.json"
        victim.write_text(json.dumps({"precious": "data"}))
        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(main_db=db, kb_manager=None, config_path=str(victim))

        result = await importer.import_all(str(zip_path), components=["cmd_config"])
        assert result.success is False
        assert any("checksum" in e for e in result.errors)
        # 零修改
        assert json.loads(victim.read_text()) == {"precious": "data"}

    @pytest.mark.asyncio
    async def test_null_json_config_rejected(self, tmp_path):
        """回归：JSON 内容为 null 明确报错，不得返回无警告的成功"""
        cfg_content = b"null"
        cfg_hash = _sha256(cfg_content)
        manifest = {
            "version": "1.2",
            "astrbot_version": VERSION,
            "components": ["cmd_config"],
            "checksums": {"config/cmd_config.json": cfg_hash},
            "component_checksums": {
                "cmd_config": _component_checksum({"config/cmd_config.json": cfg_hash})
            },
            "directories": [],
        }
        zip_path = tmp_path / "null_cfg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("config/cmd_config.json", cfg_content)

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db, kb_manager=None, config_path=str(tmp_path / "cfg.json")
        )

        result = await importer.import_all(str(zip_path), components=["cmd_config"])
        assert result.success is False
        assert any("null" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_pre_verify_reports_per_component_progress(
        self, tmp_path, temp_data_dir
    ):
        """预检在工作线程逐组件执行并向 UI 回报进度"""
        db0, _ = _make_working_mock_db()
        exporter = AstrBotExporter(
            main_db=db0,
            kb_manager=None,
            config_path=str(temp_data_dir / "cmd_config.json"),
        )
        exporter._export_main_database = AsyncMock(
            return_value={"platform_stats": [], "conversations": [], "attachments": []}
        )
        zip_path = await exporter.export_all(
            output_dir=str(tmp_path / "bk"), components=["database", "cmd_config"]
        )

        db, _ = _make_working_mock_db()
        importer = AstrBotImporter(
            main_db=db, kb_manager=None, config_path=str(tmp_path / "cfg.json")
        )

        calls = []

        async def record(stage, current, total, message):
            calls.append((stage, message))

        result = await importer.import_all(
            zip_path,
            components=["cmd_config", "database"],
            progress_callback=record,
        )
        assert result.success, result.errors
        validate_msgs = [m for s, m in calls if s == "validate"]
        assert any("正在校验组件" in m for m in validate_msgs)


def _write_webchat_backup(path, entries, *, version="1.2", checksums=None):
    """Write a legacy WebChat archive for restoration tests.

    Args:
        path: Destination ZIP path.
        entries: Archive entry names mapped to file bytes.
        version: Backup manifest format version.
        checksums: Optional expected hashes, including missing or corrupt entries.
    """
    manifest = {
        "version": version,
        "astrbot_version": VERSION,
        "directories": ["webchat"],
    }
    if version == "1.2":
        hashes = (
            checksums
            if checksums is not None
            else {name: _sha256(data) for name, data in entries.items()}
        )
        manifest.update(
            components=["attachments"],
            checksums=hashes,
            component_checksums={
                "attachments": _component_checksum(
                    {
                        name: value
                        for name, value in hashes.items()
                        if name.startswith(
                            ("files/attachments/", "directories/webchat/imgs/")
                        )
                    }
                )
            },
        )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, data in entries.items():
            zf.writestr(name, data)


class TestLegacyWebChatAttachments:
    """Keep legacy images restorable without copying upload sessions."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_regular_attachment", [False, True])
    async def test_export_and_restore_images_without_upload_fragments(
        self,
        tmp_path,
        temp_data_dir,
        temp_backup_dir,
        monkeypatch,
        with_regular_attachment,
    ):
        """Export both file sources while keeping fragments out of the archive."""
        webchat = temp_data_dir / "webchat"
        (webchat / "imgs").mkdir(parents=True)
        image = webchat / "imgs" / "legacy.png"
        image.write_bytes(b"legacy-image")
        (webchat / ".chunks").mkdir()
        fragment = webchat / ".chunks" / "live.part"
        fragment.write_bytes(b"active-upload")
        (webchat / "other.txt").write_bytes(b"unrelated-data")
        monkeypatch.setattr(
            "astrbot.core.backup.constants.get_astrbot_webchat_path",
            lambda: str(webchat),
        )
        regular = temp_data_dir / "attachments" / "regular.txt"
        regular.write_bytes(b"regular-file")
        rows = (
            [{"attachment_id": "regular", "path": str(regular)}]
            if with_regular_attachment
            else []
        )
        exporter = AstrBotExporter(
            MagicMock(), config_path=str(temp_data_dir / "cmd_config.json")
        )
        exporter._export_attachment_records = AsyncMock(return_value=rows)
        archive = await exporter.export_all(
            output_dir=str(temp_backup_dir), components=["attachments"]
        )
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            assert "directories/webchat/imgs/legacy.png" in names
            assert not any(".chunks/" in name for name in names)
            assert "directories/webchat/other.txt" not in names
            assert ("files/attachments/regular.txt" in names) == with_regular_attachment
        importer = AstrBotImporter(
            MagicMock(), config_path=str(temp_data_dir / "cmd_config.json")
        )
        check = importer.pre_check(archive)
        assert check.available_components == ["attachments"]
        image.write_bytes(b"current-image")
        regular.unlink()
        result = await importer.import_all(
            archive, components=check.available_components
        )
        assert result.success, result.errors
        assert image.read_bytes() == b"legacy-image"
        assert fragment.read_bytes() == b"active-upload"
        assert (webchat / "other.txt").read_bytes() == b"unrelated-data"
        if with_regular_attachment:
            assert regular.read_bytes() == b"regular-file"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("version", ["1.1", "1.2"])
    async def test_restore_images_ignores_upload_fragments(
        self, tmp_path, monkeypatch, version
    ):
        """Published legacy and current formats restore images without upload state."""
        webchat = tmp_path / "webchat"
        (webchat / "imgs").mkdir(parents=True)
        (webchat / "imgs" / "previous.png").write_bytes(b"previous")
        (webchat / ".chunks").mkdir()
        (webchat / ".chunks" / "active.part").write_bytes(b"active")
        monkeypatch.setattr(
            "astrbot.core.backup.constants.get_astrbot_webchat_path",
            lambda: str(webchat),
        )
        archive = tmp_path / "old.zip"
        _write_webchat_backup(
            archive,
            {
                "directories/webchat/imgs/old.png": b"old-image",
                "directories/webchat/.chunks/saved.part": b"obsolete-upload",
            },
            version=version,
        )
        importer = AstrBotImporter(MagicMock())
        check = importer.pre_check(str(archive))
        assert check.available_components == ["attachments"]
        assert any("upload fragments" in warning for warning in check.warnings)
        result = await importer.import_all(str(archive), components=["attachments"])
        assert result.success, result.errors
        assert (webchat / "imgs" / "old.png").read_bytes() == b"old-image"
        assert (webchat / "imgs.bak" / "previous.png").read_bytes() == b"previous"
        assert (webchat / ".chunks" / "active.part").read_bytes() == b"active"
        assert not (webchat / ".chunks" / "saved.part").exists()
        assert not webchat.with_suffix(".bak").exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("selection", [None, ["attachments"]])
    async def test_fragments_only_never_clear_images(
        self, tmp_path, monkeypatch, selection
    ):
        """An upload-only backup has no restorable component and changes no files."""
        webchat = tmp_path / "webchat"
        (webchat / "imgs").mkdir(parents=True)
        image = webchat / "imgs" / "keep.png"
        image.write_bytes(b"keep")
        monkeypatch.setattr(
            "astrbot.core.backup.constants.get_astrbot_webchat_path",
            lambda: str(webchat),
        )
        archive = tmp_path / "fragments.zip"
        _write_webchat_backup(
            archive,
            {
                "directories/webchat/.chunks/saved.part": b"obsolete-upload",
            },
            version="1.1",
        )
        importer = AstrBotImporter(MagicMock())
        check = importer.pre_check(str(archive))
        assert check.available_components == []
        assert check.broken_components == []
        assert any("no restorable data" in warning for warning in check.warnings)
        result = await importer.import_all(str(archive), components=selection)
        assert not result.success
        assert image.read_bytes() == b"keep"
        assert not (webchat / "imgs.bak").exists()

    @pytest.mark.asyncio
    async def test_missing_declared_image_is_still_broken(self, tmp_path, monkeypatch):
        """Fragments cannot disguise an image removed from a declared component."""
        webchat = tmp_path / "webchat"
        monkeypatch.setattr(
            "astrbot.core.backup.constants.get_astrbot_webchat_path",
            lambda: str(webchat),
        )
        archive = tmp_path / "missing.zip"
        fragment = "directories/webchat/.chunks/saved.part"
        _write_webchat_backup(
            archive,
            {fragment: b"fragment"},
            checksums={
                fragment: _sha256(b"fragment"),
                "directories/webchat/imgs/missing.png": _sha256(b"missing"),
            },
        )
        importer = AstrBotImporter(MagicMock())
        check = importer.pre_check(str(archive))
        assert check.available_components == []
        assert check.broken_components == ["attachments"]
        result = await importer.import_all(str(archive))
        assert not result.success
        assert not webchat.exists()

    @pytest.mark.asyncio
    async def test_corrupt_images_preserve_existing_directory(
        self, tmp_path, monkeypatch
    ):
        """A wholly corrupt image set does not replace existing legacy images."""
        webchat = tmp_path / "webchat"
        (webchat / "imgs").mkdir(parents=True)
        image = webchat / "imgs" / "keep.png"
        image.write_bytes(b"keep")
        monkeypatch.setattr(
            "astrbot.core.backup.constants.get_astrbot_webchat_path",
            lambda: str(webchat),
        )
        archive = tmp_path / "corrupt.zip"
        name = "directories/webchat/imgs/keep.png"
        _write_webchat_backup(
            archive, {name: b"tampered"}, checksums={name: _sha256(b"expected")}
        )
        result = await AstrBotImporter(MagicMock()).import_all(str(archive))
        assert any("verification failed" in warning for warning in result.warnings)
        assert any(
            "existing images were preserved" in warning for warning in result.warnings
        )
        assert image.read_bytes() == b"keep"
        assert not (webchat / "imgs.bak").exists()
