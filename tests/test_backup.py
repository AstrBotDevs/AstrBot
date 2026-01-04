"""备份功能单元测试"""

import json
import os
import re
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.backup import (
    BACKUP_MANIFEST_VERSION,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    ImportPreCheckResult,
)
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import (
    AstrBotImporter,
    ImportResult,
    _get_major_version,
)
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import (
    ConversationV2,
)
from astrbot.core.utils.version_comparator import VersionComparator
from astrbot.dashboard.routes.backup import (
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
