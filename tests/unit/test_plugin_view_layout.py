"""Tests for plugin view directory discovery and its migration warnings."""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.star.star import StarMetadata
from astrbot.dashboard.services import plugin_page_service
from astrbot.dashboard.services.plugin_page_service import PluginPageService


@pytest.fixture(autouse=True)
def reset_warned_layouts():
    """Keep the once-per-plugin warning guard from leaking between tests."""
    plugin_page_service._WARNED_VIEW_LAYOUTS.clear()
    yield
    plugin_page_service._WARNED_VIEW_LAYOUTS.clear()


def build_service(plugin_root: Path) -> PluginPageService:
    manager = SimpleNamespace(
        plugin_store_path=str(plugin_root.parent),
        reserved_plugin_path=str(plugin_root.parent),
    )
    return PluginPageService(plugin_manager=manager)


def build_plugin(plugin_root: Path) -> StarMetadata:
    return StarMetadata(name=plugin_root.name, root_dir_name=plugin_root.name)


def make_plugin_dir(tmp_path: Path, name: str, *dir_names: str) -> Path:
    plugin_root = tmp_path / name
    for dir_name in dir_names:
        (plugin_root / dir_name / "settings").mkdir(parents=True)
        (plugin_root / dir_name / "settings" / "index.html").write_text(
            "<!doctype html>", encoding="utf-8"
        )
    plugin_root.mkdir(exist_ok=True)
    return plugin_root


@pytest.mark.asyncio
async def test_views_directory_alone_is_silent(tmp_path: Path, caplog):
    plugin_root = make_plugin_dir(tmp_path, "plugin_views_only", "views")

    with caplog.at_level(logging.WARNING):
        resolved = await build_service(plugin_root).resolve_plugin_pages_root(
            build_plugin(plugin_root)
        )

    assert resolved == plugin_root / "views"
    assert caplog.records == []


@pytest.mark.asyncio
async def test_pages_directory_is_reported_once(tmp_path: Path, caplog):
    plugin_root = make_plugin_dir(tmp_path, "plugin_pages_only", "pages")
    service = build_service(plugin_root)
    plugin = build_plugin(plugin_root)

    with caplog.at_level(logging.WARNING):
        assert await service.resolve_plugin_pages_root(plugin) == plugin_root / "pages"
        first_pass = [record.getMessage() for record in caplog.records]
        caplog.clear()
        assert await service.resolve_plugin_pages_root(plugin) == plugin_root / "pages"
        second_pass = [record.getMessage() for record in caplog.records]

    assert len(first_pass) == 1
    assert "pages/" in first_pass[0] and "views/" in first_pass[0]
    # Discovery runs on every plugin list request, so it must stay quiet after
    # the first report.
    assert second_pass == []


@pytest.mark.asyncio
async def test_shadowed_pages_directory_is_reported(tmp_path: Path, caplog):
    plugin_root = make_plugin_dir(tmp_path, "plugin_both_dirs", "views", "pages")

    with caplog.at_level(logging.WARNING):
        resolved = await build_service(plugin_root).resolve_plugin_pages_root(
            build_plugin(plugin_root)
        )
        messages = [record.getMessage() for record in caplog.records]

    assert resolved == plugin_root / "views"
    assert len(messages) == 1
    assert "ignored" in messages[0]
    assert "pages/" in messages[0]


@pytest.mark.asyncio
async def test_missing_view_directories_raise(tmp_path: Path):
    plugin_root = make_plugin_dir(tmp_path, "plugin_without_views")

    with pytest.raises(FileNotFoundError):
        await build_service(plugin_root).resolve_plugin_pages_root(
            build_plugin(plugin_root)
        )
