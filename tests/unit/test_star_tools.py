from types import ModuleType

import pytest

from astrbot.core.star import star_tools
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_tools import StarTools


@pytest.fixture(autouse=True)
def restore_star_map():
    original_map = dict(star_map)
    star_map.clear()
    try:
        yield
    finally:
        star_map.clear()
        star_map.update(original_map)


def make_module(name: str, file_path: str | None = None) -> ModuleType:
    module = ModuleType(name)
    if file_path:
        module.__file__ = file_path
    return module


def set_caller_module(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    monkeypatch.setattr(star_tools.inspect, "getmodule", lambda _frame: module)


def test_get_data_dir_resolves_registered_plugin_submodule(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    monkeypatch.setattr(star_tools, "get_astrbot_data_path", lambda: str(data_path))
    set_caller_module(
        monkeypatch,
        make_module("data.plugins.demo_plugin.services.cache"),
    )
    star_map["data.plugins.demo_plugin.main"] = StarMetadata(
        name="demo",
        module_path="data.plugins.demo_plugin.main",
        root_dir_name="demo_plugin",
    )

    data_dir = StarTools.get_data_dir()

    assert data_dir == (data_path / "plugin_data" / "demo").resolve()


def test_get_data_dir_resolves_debug_module_from_plugin_path(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    plugin_root = tmp_path / "plugins"
    debug_file = plugin_root / "demo_plugin" / "scripts" / "debug.py"
    debug_file.parent.mkdir(parents=True)
    debug_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(star_tools, "get_astrbot_data_path", lambda: str(data_path))
    monkeypatch.setattr(star_tools, "get_astrbot_plugin_path", lambda: str(plugin_root))
    monkeypatch.setattr(star_tools, "get_astrbot_path", lambda: str(tmp_path / "src"))
    set_caller_module(monkeypatch, make_module("__main__", str(debug_file)))
    star_map["data.plugins.demo_plugin.main"] = StarMetadata(
        name="demo",
        module_path="data.plugins.demo_plugin.main",
        root_dir_name="demo_plugin",
    )

    data_dir = StarTools.get_data_dir()

    assert data_dir == (data_path / "plugin_data" / "demo").resolve()


def test_get_data_dir_keeps_unknown_module_failure(monkeypatch, tmp_path):
    data_path = tmp_path / "data"
    monkeypatch.setattr(star_tools, "get_astrbot_data_path", lambda: str(data_path))
    set_caller_module(monkeypatch, make_module("external.module"))

    with pytest.raises(RuntimeError, match="无法获取模块 external.module 的元数据信息"):
        StarTools.get_data_dir()

    assert not (data_path / "plugin_data" / "unknown_plugin").exists()
