from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.cli.commands import cmd_run


def _write_cmd_config(tmp_path, content: str) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "cmd_config.json").write_text(content, encoding="utf-8-sig")


def test_dashboard_enabled_reads_false_from_config(tmp_path):
    _write_cmd_config(tmp_path, '{"dashboard":{"enable":false}}')
    assert cmd_run._dashboard_enabled(tmp_path) is False


def test_dashboard_enabled_defaults_to_true_when_key_missing(tmp_path):
    _write_cmd_config(tmp_path, "{}")
    assert cmd_run._dashboard_enabled(tmp_path) is True


def test_dashboard_enabled_falls_back_to_true_on_invalid_json(tmp_path):
    _write_cmd_config(tmp_path, "{invalid json")
    assert cmd_run._dashboard_enabled(tmp_path) is True


def test_dashboard_enabled_falls_back_to_true_when_config_missing(tmp_path):
    assert cmd_run._dashboard_enabled(tmp_path) is True


def test_dashboard_enabled_falls_back_to_true_when_root_is_not_object(tmp_path):
    _write_cmd_config(tmp_path, "[]")
    assert cmd_run._dashboard_enabled(tmp_path) is True


@pytest.mark.asyncio
async def test_check_dashboard_if_enabled_skips_when_disabled(monkeypatch, tmp_path):
    _write_cmd_config(tmp_path, '{"dashboard":{"enable":false}}')
    mock_check_dashboard = AsyncMock()
    mock_echo = MagicMock()

    monkeypatch.setattr(cmd_run, "check_dashboard", mock_check_dashboard)
    monkeypatch.setattr(cmd_run.click, "echo", mock_echo)

    await cmd_run._check_dashboard_if_enabled(tmp_path)

    mock_check_dashboard.assert_not_called()
    mock_echo.assert_called_once()


@pytest.mark.asyncio
async def test_check_dashboard_if_enabled_checks_when_enabled(monkeypatch, tmp_path):
    _write_cmd_config(tmp_path, '{"dashboard":{"enable":true}}')
    mock_check_dashboard = AsyncMock()
    mock_echo = MagicMock()

    monkeypatch.setattr(cmd_run, "check_dashboard", mock_check_dashboard)
    monkeypatch.setattr(cmd_run.click, "echo", mock_echo)

    await cmd_run._check_dashboard_if_enabled(tmp_path)

    mock_check_dashboard.assert_awaited_once_with(tmp_path / "data")
    mock_echo.assert_not_called()
