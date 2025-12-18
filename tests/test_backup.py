"""备份功能单元测试"""

import json
import os
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.backup.exporter import (
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    AstrBotExporter,
)
from astrbot.core.backup.importer import AstrBotImporter, ImportResult
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import (
    ConversationV2,
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
            attachments_dir=str(temp_data_dir / "attachments"),
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

        manifest = exporter._generate_manifest(main_data, kb_meta_data)

        assert manifest["version"] == "1.0"
        assert manifest["astrbot_version"] == VERSION
        assert "exported_at" in manifest
        assert "tables" in manifest
        assert "statistics" in manifest
        assert manifest["statistics"]["main_db"]["platform_stats"] == 1

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
            attachments_dir=str(temp_data_dir / "attachments"),
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
            attachments_dir=str(temp_data_dir / "attachments"),
        )
        assert importer.main_db is mock_main_db
        assert importer.kb_manager is mock_kb_manager

    def test_validate_version_match(self):
        """测试版本匹配验证"""
        importer = AstrBotImporter(main_db=MagicMock())

        manifest = {"astrbot_version": VERSION}
        # 不应该抛出异常
        importer._validate_version(manifest)

    def test_validate_version_mismatch(self):
        """测试版本不匹配验证"""
        importer = AstrBotImporter(main_db=MagicMock())

        manifest = {"astrbot_version": "0.0.1"}
        with pytest.raises(ValueError, match="版本不匹配"):
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
    async def test_import_version_mismatch(self, mock_main_db, tmp_path):
        """测试导入版本不匹配的备份"""
        # 创建一个版本不匹配的备份
        zip_path = tmp_path / "old_version.zip"
        manifest = {
            "version": "1.0",
            "astrbot_version": "0.0.1",  # 错误的版本
            "tables": {"main_db": []},
        }

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))

        importer = AstrBotImporter(main_db=mock_main_db)
        result = await importer.import_all(str(zip_path))

        assert result.success is False
        assert any("版本不匹配" in err for err in result.errors)


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
            attachments_dir=str(attachments_dir),
        )

        zip_path = await exporter.export_all(output_dir=str(backup_dir))
        assert os.path.exists(zip_path)

        # 验证 ZIP 内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 读取 manifest
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["astrbot_version"] == VERSION

            # 读取配置
            config = json.loads(zf.read("config/cmd_config.json"))
            assert config["setting"] == "value"

            # 读取主数据库
            main_db = json.loads(zf.read("databases/main_db.json"))
            assert "platform_stats" in main_db
