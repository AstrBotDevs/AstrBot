from unittest.mock import MagicMock

import pytest

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter


@pytest.mark.asyncio
async def test_export_failure_removes_partial_archive(tmp_path):
    exporter = AstrBotExporter(
        main_db=MagicMock(),
        kb_manager=MagicMock(),
        config_path=str(tmp_path / "cmd_config.json"),
    )

    async def fail_stage(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    exporter._export_main_database_stage = fail_stage  # type: ignore[method-assign]
    output_dir = tmp_path / "backups"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await exporter.export_all(output_dir=str(output_dir))

    assert list(output_dir.glob("*.zip")) == []


@pytest.mark.asyncio
async def test_import_missing_archive_does_not_mutate_existing_config(tmp_path):
    config_path = tmp_path / "cmd_config.json"
    config_path.write_text('{"keep": true}', encoding="utf-8")
    importer = AstrBotImporter(
        main_db=MagicMock(),
        kb_manager=MagicMock(),
        config_path=str(config_path),
        kb_root_dir=str(tmp_path / "kb"),
    )

    result = await importer.import_all(str(tmp_path / "missing.zip"))

    assert result.success is False
    assert result.imported_tables == {}
    assert config_path.read_text(encoding="utf-8") == '{"keep": true}'
