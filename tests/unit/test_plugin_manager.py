import asyncio
import functools
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import yaml
from pydantic import BaseModel, ConfigDict

from astrbot.core.agent.handoff import FunctionTool
from astrbot.core.command import CommandEngine, CommandResolutionKind
from astrbot.core.platform.catalog import PlatformAdapterDescriptor
from astrbot.core.provider.catalog import ProviderAdapterDescriptor
from astrbot.core.provider.entities import ProviderType
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star import plugin_runtime_common as runtime_common_module
from astrbot.core.star import plugin_runtime_loader as loader_module
from astrbot.core.star import star_manager as star_manager_module
from astrbot.core.star.dashboard_extension import (
    DashboardExtensionAccess,
    DashboardExtensionRegistry,
    DashboardJsonAction,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.plugin_extension_coordinator import PluginExtensionCoordinator
from astrbot.core.star.plugin_lifecycle import PluginLifecycle
from astrbot.core.star.plugin_runtime_common import PluginDependencyInstallError
from astrbot.core.star.plugin_runtime_loader import PluginRuntimeLoader
from astrbot.core.star.star import StarDeclaration, StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
)
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.core.utils.requirements_utils import MissingRequirementsPlan
from astrbot.core.utils.task_utils import cancel_tracked_tasks

# --- Test Data & Helpers ---

TEST_PLUGIN_NAME = "helloworld"
TEST_PLUGIN_REPO = "https://github.com/AstrBotDevs/astrbot_plugin_helloworld"
TEST_PLUGIN_DIR = "helloworld"


class MockStar:
    def __init__(self):
        self.root_dir_name = TEST_PLUGIN_DIR
        self.name = TEST_PLUGIN_NAME
        self.repo = TEST_PLUGIN_REPO
        self.reserved = False
        self.module_path = f"data.plugins.{TEST_PLUGIN_DIR}.main"
        self.activated = True
        self.star_cls = None
        self.star_cls_type = None
        self.info = {"repo": TEST_PLUGIN_REPO, "readme": ""}


class _DashboardEmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _DashboardResult(BaseModel):
    ok: bool


@pytest.mark.asyncio
async def test_plugin_lifecycle_refreshes_only_its_injected_platform_port() -> None:
    command_catalog = MagicMock()
    refresh_platform_commands = AsyncMock()
    lifecycle = PluginLifecycle(
        refresh_platform_commands=refresh_platform_commands,
        catalog=command_catalog,
        loader=MagicMock(),
        packages=MagicMock(),
        extensions=MagicMock(),
        preferences=MagicMock(),
        plugin_store_path="plugins",
        reserved_plugin_path="builtin_stars",
        background_tasks=set(),
    )

    await lifecycle._refresh_command_surfaces()

    command_catalog.refresh_command_catalogs.assert_called_once_with()
    refresh_platform_commands.assert_awaited_once_with()


def _write_local_test_plugin(plugin_path: Path, repo_url: str, version: str = "1.0.0"):
    """Creates a minimal valid plugin structure."""
    plugin_path.mkdir(parents=True, exist_ok=True)
    metadata = {
        "name": TEST_PLUGIN_NAME,
        "repo": repo_url,
        "version": version,
        "author": "AstrBot Team",
        "desc": "Local test plugin",
        "short_desc": "Local test short description",
    }
    with open(plugin_path / "metadata.yaml", "w", encoding="utf-8") as f:
        yaml.dump(metadata, f)
    with open(plugin_path / "main.py", "w", encoding="utf-8") as f:
        f.write("from astrbot.api.star import PluginContext, Star\n")
        f.write("class HelloWorld(Star):\n")
        f.write("    def __init__(self, context: PluginContext): ...\n")


def _write_requirements(plugin_path: Path):
    """Creates a requirements.txt file."""
    with open(plugin_path / "requirements.txt", "w", encoding="utf-8") as f:
        f.write("networkx\n")


def _write_dashboard_extension_metadata(plugin_path: Path, plugin_name: str) -> None:
    module_path = "pages/settings/app.js"
    module_content = b"export const plugin = true;\n"
    module_file = plugin_path / module_path
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_bytes(module_content)
    assets_manifest = plugin_path / "pages/settings/assets.v1.json"
    assets_manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "files": [
                    {
                        "path": module_path,
                        "sha256": hashlib.sha256(module_content).hexdigest(),
                        "size": len(module_content),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (plugin_path / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": plugin_name,
                "author": "AstrBot Team",
                "desc": "Dashboard extension integration test",
                "version": "1.0.0",
                "requires": {"dashboard_extension": 1},
                "dashboard": {
                    "extension_id": f"io.github.example.{plugin_name.replace('_', '-')}",
                    "pages": [
                        {
                            "id": "settings",
                            "title": "Settings",
                            "module": module_path,
                            "assets_manifest": "pages/settings/assets.v1.json",
                            "actions": ["config.read"],
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_load_plugin_i18n_reads_supported_locale_files(tmp_path: Path):
    plugin_path = tmp_path / "plugin"
    i18n_path = plugin_path / ".astrbot-plugin" / "i18n"
    i18n_path.mkdir(parents=True)
    (i18n_path / "zh-CN.json").write_text(
        json.dumps({"metadata": {"desc": "中文描述"}}, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    (i18n_path / "en-US.json").write_text(
        json.dumps({"metadata": {"desc": "English description"}}),
        encoding="utf-8",
    )
    (i18n_path / "ru-RU.json").write_text(
        json.dumps({"metadata": {"desc": "Russian description"}}),
        encoding="utf-8",
    )
    (i18n_path / "README.md").write_text("ignored", encoding="utf-8")

    assert PluginRuntimeLoader.load_i18n(str(plugin_path)) == {
        "zh-CN": {"metadata": {"desc": "中文描述"}},
        "en-US": {"metadata": {"desc": "English description"}},
    }


@pytest.mark.asyncio
async def test_load_plugin_schema_accepts_utf8_bom(
    plugin_manager_pm: PluginManager, tmp_path: Path, monkeypatch
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "bom_schema_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir()
    (plugin_path / "_conf_schema.json").write_text(
        json.dumps({"enabled": {"type": "bool", "default": True}}),
        encoding="utf-8-sig",
    )

    class SchemaPlugin:
        def __init__(self, context, config=None):
            self.context = context
            self.config = config

    metadata = StarMetadata(
        name=plugin_name,
        author="AstrBot Team",
        desc="BOM schema test plugin",
        version="1.0.0",
        root_dir_name=plugin_name,
        module_path=module_path,
    )

    async def mock_global_get(_key, default=None):
        return default

    async def mock_import_plugin_with_dependency_recovery(**_kwargs):
        return ModuleType(module_path)

    async def mock_sync_command_configs(*_args):
        return None

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_get", mock_global_get
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "discover_modules",
        lambda: [{"pname": plugin_name, "module": "main"}],
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "import_with_dependency_recovery",
        mock_import_plugin_with_dependency_recovery,
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "load_metadata",
        lambda **_kwargs: metadata,
    )
    monkeypatch.setattr(
        loader_module, "sync_command_configs", mock_sync_command_configs
    )
    _mock_star_declaration(monkeypatch, module_path, SchemaPlugin)
    config_path = tmp_path / "config"
    config_path.mkdir()
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "_plugin_config_path",
        str(config_path),
    )

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name
        )
        registered = plugin_manager_pm.catalog.runtime_catalogs.plugins.get_by_module(
            module_path
        )
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)

    assert success is True
    assert error is None
    assert registered is not None
    assert registered.config is not None


def test_load_plugin_i18n_ignores_legacy_directories(tmp_path: Path):
    plugin_path = tmp_path / "plugin"
    hidden_legacy_i18n_path = plugin_path / ".i18n"
    legacy_i18n_path = plugin_path / "i18n"
    hidden_legacy_i18n_path.mkdir(parents=True)
    legacy_i18n_path.mkdir()
    (hidden_legacy_i18n_path / "zh-CN.json").write_text(
        json.dumps({"metadata": {"desc": "隐藏旧目录"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (legacy_i18n_path / "zh-CN.json").write_text(
        json.dumps({"metadata": {"desc": "中文描述"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert PluginRuntimeLoader.load_i18n(str(plugin_path)) == {}


def test_load_plugin_metadata_includes_i18n(tmp_path: Path):
    plugin_path = tmp_path / "helloworld"
    _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)
    i18n_path = plugin_path / ".astrbot-plugin" / "i18n"
    i18n_path.mkdir(parents=True)
    (i18n_path / "zh-CN.json").write_text(
        json.dumps({"metadata": {"display_name": "你好世界"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    metadata = PluginRuntimeLoader.load_metadata(str(plugin_path))

    assert metadata is not None
    assert metadata.short_desc == "Local test short description"
    assert metadata.i18n == {"zh-CN": {"metadata": {"display_name": "你好世界"}}}


def test_load_plugin_metadata_rejects_top_level_pages(tmp_path: Path):
    plugin_path = tmp_path / "helloworld"
    _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)
    metadata_path = plugin_path / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    metadata["pages"] = [{"name": "dashboard", "title": "Dashboard"}]
    metadata_path.write_text(yaml.dump(metadata), encoding="utf-8")

    with pytest.raises(Exception, match="top-level pages is unsupported"):
        PluginRuntimeLoader.load_metadata(str(plugin_path))


def test_load_plugin_metadata_raises_without_metadata_yaml(tmp_path: Path):
    plugin_path = tmp_path / "legacy_plugin"
    plugin_path.mkdir(parents=True, exist_ok=True)
    (plugin_path / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(Exception, match="未找到 metadata.yaml"):
        PluginRuntimeLoader.load_metadata(str(plugin_path))


def test_load_plugin_metadata_rejects_description_alias(tmp_path: Path):
    plugin_path = tmp_path / "legacy_plugin"
    plugin_path.mkdir(parents=True, exist_ok=True)
    (plugin_path / "metadata.yaml").write_text(
        yaml.dump(
            {
                "name": TEST_PLUGIN_NAME,
                "repo": TEST_PLUGIN_REPO,
                "version": "1.0.0",
                "author": "AstrBot Team",
                "description": "Legacy alias description",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="插件元数据信息不完整"):
        PluginRuntimeLoader.load_metadata(str(plugin_path))


@pytest.mark.asyncio
async def test_plugin_initialize_commits_dashboard_registration_atomically(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "dashboard_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir()
    _write_dashboard_extension_metadata(plugin_path, plugin_name)

    class DashboardPlugin:
        def __init__(self, context):
            self.context = context

        async def initialize(self):
            registrar = self.context.dashboard_extensions.for_plugin(self)
            registrar.register_json(
                DashboardJsonAction(
                    name="config.read",
                    input_model=_DashboardEmptyRequest,
                    output_model=_DashboardResult,
                ),
                self.read_config,
            )

        async def read_config(self, _payload, _context):
            return _DashboardResult(ok=True)

    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "discover_modules",
        lambda: [{"pname": plugin_name, "module": "main"}],
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "import_with_dependency_recovery",
        AsyncMock(return_value=ModuleType(module_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences,
        "global_get",
        AsyncMock(side_effect=lambda _key, default=None: default),
    )
    monkeypatch.setattr(
        loader_module,
        "sync_command_configs",
        AsyncMock(),
    )
    _mock_star_declaration(monkeypatch, module_path, DashboardPlugin)

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name
        )
        snapshots = plugin_manager_pm.extensions.registry.snapshots()
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)

    assert success is True
    assert error is None
    assert len(snapshots) == 1
    assert snapshots[0].plugin_name == plugin_name
    assert list(snapshots[0].actions) == ["config.read"]


@pytest.mark.asyncio
async def test_plugin_initialize_failure_rolls_back_dashboard_registration(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "dashboard_plugin_failure"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir()
    _write_dashboard_extension_metadata(plugin_path, plugin_name)

    class DashboardPlugin:
        def __init__(self, context):
            self.context = context

        async def initialize(self):
            registrar = self.context.dashboard_extensions.for_plugin(self)
            registrar.register_json(
                DashboardJsonAction(
                    name="config.read",
                    input_model=_DashboardEmptyRequest,
                    output_model=_DashboardResult,
                ),
                self.read_config,
            )
            raise RuntimeError("initialize failed")

        async def read_config(self, _payload, _context):
            return _DashboardResult(ok=True)

    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "discover_modules",
        lambda: [{"pname": plugin_name, "module": "main"}],
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "import_with_dependency_recovery",
        AsyncMock(return_value=ModuleType(module_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences,
        "global_get",
        AsyncMock(side_effect=lambda _key, default=None: default),
    )
    monkeypatch.setattr(loader_module, "sync_command_configs", AsyncMock())
    _mock_star_declaration(monkeypatch, module_path, DashboardPlugin)

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name
        )
        snapshots = plugin_manager_pm.extensions.registry.snapshots()
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)

    assert success is False
    assert "initialize failed" in str(error)
    assert snapshots == ()


@pytest.mark.asyncio
async def test_plugin_constructor_cannot_register_dashboard_action(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "dashboard_constructor_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir()
    _write_dashboard_extension_metadata(plugin_path, plugin_name)

    class DashboardPlugin:
        def __init__(self, context):
            context.dashboard_extensions.for_plugin(self)

    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "discover_modules",
        lambda: [{"pname": plugin_name, "module": "main"}],
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "import_with_dependency_recovery",
        AsyncMock(return_value=ModuleType(module_path)),
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences,
        "global_get",
        AsyncMock(side_effect=lambda _key, default=None: default),
    )
    monkeypatch.setattr(loader_module, "sync_command_configs", AsyncMock())
    _mock_star_declaration(monkeypatch, module_path, DashboardPlugin)

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name
        )
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)

    assert success is False
    assert "during initialize" in str(error)
    assert plugin_manager_pm.extensions.registry.snapshots() == ()


@pytest.mark.asyncio
async def test_install_validates_dashboard_manifest_before_dependencies(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_name = "invalid_dashboard_install"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    ensure_requirements = AsyncMock()

    async def mock_install(_repo_url, _proxy):
        plugin_path.mkdir()
        _write_dashboard_extension_metadata(plugin_path, plugin_name)
        metadata_path = plugin_path / "metadata.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        metadata["dashboard"]["pages"][0]["module"] = "../outside.js"
        metadata_path.write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        return str(plugin_path)

    monkeypatch.setattr(
        plugin_manager_pm.packages._updator,
        "parse_github_url",
        lambda _url: ("owner", plugin_name, ""),
    )
    monkeypatch.setattr(
        plugin_manager_pm.packages._updator,
        "format_name",
        lambda name: name,
    )
    monkeypatch.setattr(plugin_manager_pm.packages._updator, "install", mock_install)
    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "ensure_requirements",
        ensure_requirements,
    )

    with pytest.raises(
        Exception, match="Invalid asset path segment|escapes plugin root"
    ):
        await plugin_manager_pm.lifecycle.install_plugin(
            "https://example.invalid/plugin.git"
        )

    ensure_requirements.assert_not_awaited()


def test_get_modules_ignores_directory_name_entrypoint(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "legacy_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "legacy_plugin.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert PluginRuntimeLoader.get_modules(str(plugin_root)) == []


def test_loaded_metadata_can_copy_i18n_into_existing_star_metadata(tmp_path: Path):
    plugin_path = tmp_path / "helloworld"
    _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)
    i18n_path = plugin_path / ".astrbot-plugin" / "i18n"
    i18n_path.mkdir(parents=True)
    (i18n_path / "zh-CN.json").write_text(
        json.dumps({"metadata": {"desc": "中文描述"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    existing_metadata = StarMetadata(name="old")
    loaded_metadata = PluginRuntimeLoader.load_metadata(str(plugin_path))

    assert loaded_metadata is not None
    existing_metadata.i18n = loaded_metadata.i18n
    assert existing_metadata.i18n == {"zh-CN": {"metadata": {"desc": "中文描述"}}}


def _clear_module_cache():
    """Clear test-specific modules from sys.modules to allow reloading."""
    import sys

    to_del = [
        m
        for m in sys.modules
        if m.startswith("data.plugins.helloworld")
        or m.startswith("data.plugins.broken_plugin")
    ]
    for m in to_del:
        del sys.modules[m]


def _clear_plugin_runtime_state(catalogs: RuntimeCatalogs) -> None:
    """Clear registrations owned by one test runtime."""
    catalogs.handlers.clear()
    catalogs.tools.func_list.clear()
    catalogs.plugins.clear()


def _mock_star_declaration(
    monkeypatch: pytest.MonkeyPatch,
    module_path: str,
    star_cls_type: type,
) -> None:
    """Make an imported test module expose one static Star declaration."""
    declaration = StarDeclaration(
        star_cls_type=cast(Any, star_cls_type),
        module_path=module_path,
    )
    monkeypatch.setattr(
        loader_module,
        "collect_star_declaration",
        lambda _module: declaration,
    )


def test_bind_plugin_handlers_is_idempotent(
    plugin_manager_pm: PluginManager,
) -> None:
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    module_path = "data.plugins.test_plugin.main"
    plugin_instance = object()
    metadata = StarMetadata(
        name="test_plugin",
        module_path=module_path,
        star_cls=cast(Any, plugin_instance),
    )

    async def raw_event_handler(plugin, event):
        return plugin, event

    async def raw_tool_handler(plugin, query):
        return plugin, query

    raw_event_handler.__module__ = module_path
    raw_tool_handler.__module__ = module_path
    event_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.raw_event_handler",
        handler_name="raw_event_handler",
        handler_module_path=module_path,
        handler=raw_event_handler,
        event_filters=[],
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(metadata)
    plugin_manager_pm.catalog.runtime_catalogs.handlers.append(event_handler)

    tool = FunctionTool(
        name="test_plugin_tool",
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler=raw_tool_handler,
        handler_module_path=module_path,
    )
    plugin_manager_pm.catalog.runtime_catalogs.tools.func_list = [tool]

    try:
        plugin_manager_pm.loader.bind_handlers(metadata, [])
        plugin_manager_pm.loader.bind_handlers(metadata, [])

        assert isinstance(event_handler.handler, functools.partial)
        assert event_handler.handler.func is raw_event_handler
        assert event_handler.handler.args == (plugin_instance,)
        assert isinstance(tool.handler, functools.partial)
        assert tool.handler.func is raw_tool_handler
        assert tool.handler.args == (plugin_instance,)

        metadata.star_cls = None
        plugin_manager_pm.loader.bind_handlers(metadata, [])
        assert event_handler.handler is raw_event_handler
        assert tool.handler is raw_tool_handler
        assert tool.active is False
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


def _build_load_mock(events):
    async def mock_load(specified_dir_name=None, ignore_version_check=False):
        del ignore_version_check
        events.append(("load", specified_dir_name or TEST_PLUGIN_DIR))
        return True, ""

    return mock_load


def _build_reload_mock(events):
    async def mock_reload(specified_dir_name=None):
        events.append(("reload", specified_dir_name or TEST_PLUGIN_DIR))
        return True, ""

    return mock_reload


def _build_dependency_install_mock(
    events,
    fail: bool,
    *,
    capture_content: bool = False,
):
    async def mock_install_requirements(
        *,
        requirements_path: str | None = None,
        package_name: str | None = None,
        **kwargs,
    ):
        del kwargs
        if requirements_path:
            path = Path(requirements_path)
            event = ("deps", str(path))
            if capture_content:
                event = (*event, path.read_text(encoding="utf-8"))
            events.append(event)
        if package_name:
            events.append(("deps_pkg", package_name))
        if fail:
            raise Exception("pip failed")

    return mock_install_requirements


def _mock_missing_requirements(monkeypatch, missing: set[str]):
    _mock_missing_requirements_plan(monkeypatch, missing, sorted(missing))


def _mock_missing_requirements_plan(
    monkeypatch,
    missing_names,
    install_lines,
    *,
    version_mismatch_names=(),
    fallback_reason: str | None = None,
):
    monkeypatch.setattr(
        runtime_common_module,
        "plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset(missing_names),
            version_mismatch_names=frozenset(version_mismatch_names),
            install_lines=tuple(install_lines),
            fallback_reason=fallback_reason,
        ),
    )


def _mock_precheck_fails(monkeypatch):
    monkeypatch.setattr(
        runtime_common_module,
        "plan_missing_requirements_install",
        lambda requirements_path: None,
    )


def _assert_dependency_install_event_matches(
    event,
    *,
    expected_original_path: Path,
    expected_content: str | None = None,
    expect_filtered_tempfile: bool | None = None,
):
    assert event[0] == "deps"
    used_path = Path(event[1])
    should_be_filtered = expected_content is not None
    if expect_filtered_tempfile is not None:
        should_be_filtered = expect_filtered_tempfile

    if not should_be_filtered:
        assert used_path == expected_original_path
    else:
        assert used_path != expected_original_path
        assert used_path.name.endswith("_plugin_requirements.txt")
    if expected_content is not None:
        if len(event) >= 3:
            assert event[2] == expected_content


# --- Fixtures ---


@pytest_asyncio.fixture
async def plugin_manager_pm(tmp_path, monkeypatch):
    """Provides a fully isolated PluginManager instance for testing."""
    # Clear module cache before setup to ensure isolation
    _clear_module_cache()

    runtime_root = tmp_path / "astrbot_root"
    plugin_dir = runtime_root / "data" / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_config_dir = runtime_root / "data" / "config"
    plugin_config_dir.mkdir(parents=True, exist_ok=True)
    (runtime_root / "astrbot" / "builtin_stars").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_plugin_path",
        lambda: str(plugin_dir),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_config_path",
        lambda: str(plugin_config_dir),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_path",
        lambda: str(runtime_root),
    )

    class MockContext:
        def __init__(self, catalogs: RuntimeCatalogs):
            self.catalogs = catalogs
            self._db = MagicMock()
            self._db.get_command_configs = AsyncMock(return_value=[])
            self.database = self._db
            self._config = {}
            self.provider_manager = MagicMock()
            self.preferences = MagicMock()
            self.astrbot_config_mgr = MagicMock()
            self.conversation_manager = MagicMock()
            self.persona_manager = MagicMock()
            self.cron_manager = MagicMock()
            self.kb_manager = MagicMock()
            self.html_renderer = MagicMock()
            self.file_token_service = MagicMock()
            self.metrics = SimpleNamespace(upload=AsyncMock())
            self.demo_mode = False
            self.dashboard_extension_registry = DashboardExtensionRegistry()
            self.dashboard_extensions = DashboardExtensionAccess(
                self.dashboard_extension_registry,
            )
            self._platform_manager = MagicMock()
            self._platform_manager.refresh_registered_commands = AsyncMock()

        def get_all_stars(self):
            return list(self.catalogs.plugins)

        def get_registered_star(self, name):
            return self.catalogs.plugins.get_by_name(name)

        async def refresh_platform_commands(self):
            await self._platform_manager.refresh_registered_commands()

    catalogs = RuntimeCatalogs()
    mock_context = MockContext(catalogs)
    mock_config = {}
    pm = PluginManager(
        cast(Any, mock_context),
        cast(Any, mock_config),
        AsyncMock(),
        MagicMock(),
        catalogs,
    )
    try:
        yield pm
    finally:
        await cancel_tracked_tasks(pm.lifecycle._background_tasks)


def test_plugin_manager_atomically_replaces_owned_command_catalog(
    plugin_manager_pm: PluginManager,
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    module_path = "plugin.catalog_demo"
    plugin = StarMetadata(
        name="catalog_demo",
        module_path=module_path,
        activated=True,
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(plugin)

    async def handler(self, event, value: str) -> None: ...

    metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.catalog_demo_handler",
        handler_name="handler",
        handler_module_path=module_path,
        handler=handler,
        event_filters=[],
    )
    command_filter = CommandFilter("demo")
    command_filter.init_handler_md(metadata)
    metadata.event_filters.append(command_filter)
    plugin_manager_pm.catalog.runtime_catalogs.handlers.append(metadata)

    try:
        store = plugin_manager_pm.catalog.get_command_catalog("default", None)
        first_snapshot = store.snapshot
        assert CommandEngine(first_snapshot).resolve("demo value").invocation.argv == (
            "value",
        )

        command_filter.command_name = "renamed"
        command_filter._cmpl_cmd_names = None
        plugin_manager_pm.catalog.refresh_command_catalogs()

        assert plugin_manager_pm.catalog.get_command_catalog("default", None) is store
        assert store.snapshot is not first_snapshot
        assert (
            CommandEngine(store.snapshot).resolve("demo value").resolution.kind
            is CommandResolutionKind.UNKNOWN_ROOT
        )
        assert CommandEngine(store.snapshot).resolve(
            "renamed value"
        ).invocation.argv == ("value",)
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


def test_plugin_manager_runtime_catalogs_are_isolated(
    plugin_manager_pm: PluginManager,
) -> None:
    """Registrations from one PluginManager runtime never leak into another."""
    catalogs = plugin_manager_pm.catalog.runtime_catalogs
    other_catalogs = RuntimeCatalogs()
    _clear_plugin_runtime_state(catalogs)
    try:
        module_path = "data.plugins.isolated.main"
        plugin = StarMetadata(name="isolated", module_path=module_path)
        other_plugin = StarMetadata(name="isolated", module_path=module_path)
        catalogs.plugins.publish(plugin)
        other_catalogs.plugins.publish(other_plugin)

        async def handler(*_args):
            return None

        handler_metadata = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=f"{module_path}.handler",
            handler_name="handler",
            handler_module_path=module_path,
            handler=handler,
            event_filters=[],
        )
        other_handler_metadata = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=f"{module_path}.other_handler",
            handler_name="other_handler",
            handler_module_path=module_path,
            handler=handler,
            event_filters=[],
        )
        catalogs.handlers.append(handler_metadata)
        other_catalogs.handlers.append(other_handler_metadata)
        tool = FunctionTool(
            name="isolated_tool",
            description="test tool",
            parameters={"type": "object", "properties": {}},
            handler_module_path=f"{module_path}.tools.search",
        )
        other_tool = FunctionTool(
            name="other_isolated_tool",
            description="test tool",
            parameters={"type": "object", "properties": {}},
            handler_module_path=f"{module_path}.tools.search",
        )
        catalogs.tools.func_list.append(tool)
        other_catalogs.tools.func_list.append(other_tool)

        _clear_plugin_runtime_state(catalogs)

        assert other_catalogs.plugins.get_by_module(module_path) is other_plugin
        assert list(other_catalogs.handlers) == [other_handler_metadata]
        assert other_catalogs.tools.func_list == [other_tool]
    finally:
        _clear_plugin_runtime_state(catalogs)
        _clear_plugin_runtime_state(other_catalogs)


@pytest.fixture
def local_updator(plugin_manager_pm):
    """Helper to setup a local plugin directory simulating a download."""
    path = Path(plugin_manager_pm.packages.store_path) / TEST_PLUGIN_DIR
    _write_local_test_plugin(path, TEST_PLUGIN_REPO)
    return path


# --- Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_install_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager, monkeypatch, dependency_install_fails: bool
):
    plugin_path = Path(plugin_manager_pm.packages.store_path) / TEST_PLUGIN_DIR
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install(repo_url: str, proxy=""):
        assert repo_url == TEST_PLUGIN_REPO
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    monkeypatch.setattr(plugin_manager_pm.packages._updator, "install", mock_install)
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
            cast(StarMetadata, MockStar())
        )
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_load_unlocked", mock_load_and_register
    )

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.lifecycle.install_plugin(TEST_PLUGIN_REPO)
        assert len(events) == 1
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=plugin_path / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.lifecycle.install_plugin(TEST_PLUGIN_REPO)
        assert len(events) == 2
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=plugin_path / "requirements.txt",
            expected_content="networkx\n",
        )
        assert events[1] == ("load", TEST_PLUGIN_DIR)


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_install_plugin_from_file_dependency_install_flow(
    plugin_manager_pm: PluginManager,
    monkeypatch,
    tmp_path,
    dependency_install_fails: bool,
):
    zip_file_path = tmp_path / f"{TEST_PLUGIN_DIR}.zip"
    zip_file_path.write_text("placeholder", encoding="utf-8")
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    def mock_unzip_file(zip_path: str, target_dir: str) -> None:
        assert zip_path == str(zip_file_path)
        plugin_path = Path(target_dir)
        _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)
        _write_requirements(plugin_path)

    monkeypatch.setattr(
        plugin_manager_pm.packages._updator, "unzip_file", mock_unzip_file
    )
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
            cast(StarMetadata, MockStar())
        )
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_load_unlocked", mock_load_and_register
    )

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.lifecycle.install_plugin_from_file(
                str(zip_file_path)
            )
        assert any(e[0] == "deps" for e in events)
    else:
        await plugin_manager_pm.lifecycle.install_plugin_from_file(str(zip_file_path))
        assert any(e[0] == "deps" for e in events)
        assert ("load", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_install_plugin_from_file_conflict_keeps_failed_plugins_clean(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    tmp_path: Path,
):
    zip_file_path = tmp_path / "plugin_upload_helloworld_v2.zip"
    zip_file_path.write_text("placeholder", encoding="utf-8")
    plugin_store_path = Path(plugin_manager_pm.packages.store_path)
    existing_upload_dirs = set(plugin_store_path.glob("plugin_upload_*"))

    def mock_unzip_file(zip_path: str, target_dir: str) -> None:
        assert zip_path == str(zip_file_path)
        _write_local_test_plugin(
            Path(target_dir),
            TEST_PLUGIN_REPO,
            version="2.0.0",
        )

    assert local_updator.is_dir()
    monkeypatch.setattr(
        plugin_manager_pm.packages._updator, "unzip_file", mock_unzip_file
    )

    with pytest.raises(Exception, match=f"安装失败：目录 {TEST_PLUGIN_DIR} 已存在。"):
        await plugin_manager_pm.lifecycle.install_plugin_from_file(str(zip_file_path))

    new_upload_dirs = [
        upload_dir
        for upload_dir in plugin_store_path.glob("plugin_upload_*")
        if upload_dir not in existing_upload_dirs
    ]
    assert plugin_manager_pm.loader._failed_plugins == {}
    assert new_upload_dirs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_reload_failed_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    dependency_install_fails: bool,
):
    _write_requirements(local_updator)
    plugin_manager_pm.loader._failed_plugins[TEST_PLUGIN_DIR] = {"error": "init fail"}
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
            cast(StarMetadata, MockStar())
        )
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_load_unlocked", mock_load_and_register
    )

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.lifecycle.reload_failed_plugin(TEST_PLUGIN_DIR)
        assert len(events) == 1
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.lifecycle.reload_failed_plugin(TEST_PLUGIN_DIR)
        assert len(events) == 2
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
        assert events[1] == ("load", TEST_PLUGIN_DIR)


@pytest.mark.asyncio
async def test_failed_reload_keeps_live_plugin_catalog_and_extension_generation(
    plugin_manager_pm: PluginManager, monkeypatch
):
    """A failed staged reload must leave the published generation executable."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "staged_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    metadata = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    catalogs = plugin_manager_pm.catalog.runtime_catalogs
    catalogs.plugins.publish(metadata)

    async def handler(*_args: object) -> None:
        return None

    handler_metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.handler",
        handler_name="handler",
        handler_module_path=module_path,
        handler=handler,
        event_filters=[],
    )
    catalogs.handlers.append(handler_metadata)
    tool = FunctionTool(
        name="staged_plugin_tool",
        description="test tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path=f"{module_path}.tools.test",
    )
    catalogs.tools.func_list.append(tool)

    class ExistingProvider:
        pass

    ExistingProvider.__module__ = f"{module_path}.provider"
    catalogs.providers.register(
        ProviderAdapterDescriptor.create(
            type="staged-plugin-provider",
            desc="existing provider",
            provider_type=ProviderType.CHAT_COMPLETION,
            default_config_tmpl=None,
            provider_display_name=None,
        ),
        ExistingProvider,
        module_path=ExistingProvider.__module__,
    )

    class ExistingPlatform:
        pass

    ExistingPlatform.__module__ = f"{module_path}.platform"
    catalogs.platforms.register(
        PlatformAdapterDescriptor.create(
            name="staged-plugin-platform",
            description="existing platform",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
        ),
        ExistingPlatform,
        module_path=ExistingPlatform.__module__,
    )

    staged_sync_flags: list[bool] = []

    async def failed_staged_load(self, **kwargs):
        staged_sync_flags.append(kwargs["sync_command_configs_after_load"])
        replacement = StarMetadata(
            name=plugin_name,
            root_dir_name=plugin_name,
            module_path=module_path,
        )
        self._catalog.plugins.publish(replacement)
        self._catalog.runtime_catalogs.handlers.append(
            StarHandlerMetadata(
                event_type=EventType.AdapterMessageEvent,
                handler_full_name=f"{module_path}.replacement",
                handler_name="replacement",
                handler_module_path=module_path,
                handler=handler,
                event_filters=[],
            )
        )
        self._catalog.runtime_catalogs.tools.func_list.append(
            FunctionTool(
                name="replacement_tool",
                description="replacement tool",
                parameters={"type": "object", "properties": {}},
                handler_module_path=module_path,
            )
        )
        return False, "replacement initialize failed"

    terminate_plugin = AsyncMock()
    promote_extension = AsyncMock()
    monkeypatch.setattr(PluginRuntimeLoader, "load", failed_staged_load)
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "terminate_plugin", terminate_plugin
    )
    monkeypatch.setattr(
        type(plugin_manager_pm.extensions),
        "promote_staged_generation",
        promote_extension,
    )

    try:
        success, error = await plugin_manager_pm.lifecycle.reload(plugin_name)

        assert success is False
        assert error == "replacement initialize failed"
        assert catalogs.plugins.get_by_module(module_path) is metadata
        assert list(catalogs.handlers) == [handler_metadata]
        assert catalogs.tools.func_list == [tool]
        assert catalogs.providers.get("staged-plugin-provider") is not None
        assert catalogs.platforms.get("staged-plugin-platform") is not None
        assert staged_sync_flags == [False]
        terminate_plugin.assert_not_awaited()
        promote_extension.assert_not_awaited()
    finally:
        catalogs.providers.unregister_module(ExistingProvider.__module__)
        catalogs.platforms.unregister_module(ExistingPlatform.__module__)
        _clear_plugin_runtime_state(catalogs)


@pytest.mark.asyncio
async def test_turn_plugin_toggles_llm_tools_from_plugin_child_module(
    plugin_manager_pm: PluginManager,
    monkeypatch,
):
    plugin = StarMetadata(
        name="demo_plugin",
        root_dir_name="demo_plugin",
        module_path="data.plugins.demo_plugin.main",
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(plugin)
    plugin_tool = FunctionTool(
        name="plugin_search",
        description="plugin search",
        parameters={"type": "object", "properties": {}},
        handler_module_path="data.plugins.demo_plugin.main.tools.search",
    )
    other_tool = FunctionTool(
        name="other_search",
        description="other search",
        parameters={"type": "object", "properties": {}},
        handler_module_path="data.plugins.other_plugin.main.tools.search",
    )
    tool_manager = plugin_manager_pm.catalog.runtime_catalogs.tools
    original_func_list = tool_manager.func_list
    tool_manager.func_list = [plugin_tool, other_tool]
    preferences = {
        "inactivated_plugins": [],
        "inactivated_llm_tools": [],
    }

    async def mock_global_get(key, default=None):
        return preferences.get(key, default)

    async def mock_global_put(key, value):
        preferences[key] = value

    async def mock_terminate(star_metadata):
        assert star_metadata is plugin

    transition_order = []

    async def mock_deactivate(_coordinator, star_metadata, *, reason, release=False):
        assert star_metadata is plugin
        assert reason == "disable"
        assert release is False
        transition_order.append("drain")

    async def ordered_terminate(star_metadata):
        await mock_terminate(star_metadata)
        transition_order.append("terminate")

    async def mock_reload(plugin_name):
        assert plugin_name == plugin.root_dir_name
        return True, None

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_get", mock_global_get
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_put", mock_global_put
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "terminate_plugin",
        ordered_terminate,
    )
    monkeypatch.setattr(
        type(plugin_manager_pm.extensions),
        "deactivate",
        mock_deactivate,
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "_reload_unlocked",
        mock_reload,
    )

    try:
        await plugin_manager_pm.lifecycle.turn_off_plugin(plugin.root_dir_name)

        assert plugin_tool.active is False
        assert other_tool.active is True
        assert preferences["inactivated_plugins"] == [plugin.module_path]
        assert preferences["inactivated_llm_tools"] == [plugin_tool.name]
        assert plugin.activated is False
        assert transition_order == ["drain", "terminate"]
        cast(
            Any,
            plugin_manager_pm.loader._execution_context,
        )._platform_manager.refresh_registered_commands.assert_awaited_once()

        await plugin_manager_pm.lifecycle.turn_on_plugin(plugin.root_dir_name)

        assert plugin_tool.active is True
        assert other_tool.active is True
        assert preferences["inactivated_plugins"] == []
        assert preferences["inactivated_llm_tools"] == []
    finally:
        tool_manager.func_list = original_func_list
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


@pytest.mark.asyncio
async def test_load_reports_unregistered_plugin_without_index_error(
    plugin_manager_pm: PluginManager, monkeypatch
):
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_root = Path(plugin_manager_pm.packages.store_path).parents[1]
    plugin_name = "broken_plugin"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir(parents=True)
    (plugin_path / "metadata.yaml").write_text(
        yaml.dump(
            {
                "name": plugin_name,
                "author": "AstrBot Team",
                "desc": "Broken test plugin",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text("VALUE = 1\n", encoding="utf-8")

    async def mock_global_get(key, default=None):
        del key
        return default

    async def mock_sync_command_configs():
        return None

    monkeypatch.syspath_prepend(str(plugin_root))
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_get", mock_global_get
    )
    monkeypatch.setattr(
        loader_module, "sync_command_configs", mock_sync_command_configs
    )

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name
        )
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
        _clear_module_cache()

    assert success is False
    assert error is not None
    assert "未声明 Star 类" in error
    assert "继承自 Star 的插件主类" in error
    assert "list index out of range" not in error
    assert plugin_name in plugin_manager_pm.loader._failed_plugins


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_reraises_cancelled_error(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    _write_requirements(local_updator)
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install_requirements(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )

    with pytest.raises(asyncio.CancelledError):
        await plugin_manager_pm.packages.ensure_requirements(
            str(local_updator),
            TEST_PLUGIN_DIR,
        )


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_wraps_generic_dependency_install_failure(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    _write_requirements(local_updator)
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install_requirements(*args, **kwargs):
        raise RuntimeError("pip failed")

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )

    with pytest.raises(PluginDependencyInstallError, match="pip failed") as exc_info:
        await plugin_manager_pm.packages.ensure_requirements(
            str(local_updator),
            TEST_PLUGIN_DIR,
        )

    assert exc_info.value.plugin_label == TEST_PLUGIN_DIR
    assert exc_info.value.requirements_path == str(local_updator / "requirements.txt")
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_wraps_pip_install_error(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    _write_requirements(local_updator)
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install_requirements(*args, **kwargs):
        raise PipInstallError("install failed", code=2)

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )

    with pytest.raises(
        PluginDependencyInstallError, match="install failed"
    ) as exc_info:
        await plugin_manager_pm.packages.ensure_requirements(
            str(local_updator),
            TEST_PLUGIN_DIR,
        )

    assert isinstance(exc_info.value.__cause__, PipInstallError)


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_logs_requirements_file_install_for_missing_dependencies(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    _write_requirements(local_updator)
    _mock_missing_requirements(monkeypatch, {"networkx"})
    logged_lines = []

    async def mock_install_requirements(*args, **kwargs):
        return None

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )
    monkeypatch.setattr(
        runtime_common_module.logger,
        "info",
        lambda line, *args: logged_lines.append(line % args if args else line),
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert any("按 requirements.txt 安装" in line for line in logged_lines)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version_mismatch_names", "expected_allow_target_upgrade"),
    [
        (set(), False),
        ({"networkx"}, True),
    ],
)
async def test_ensure_plugin_requirements_sets_target_upgrade_based_on_version_mismatch(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    version_mismatch_names,
    expected_allow_target_upgrade: bool,
):
    _write_requirements(local_updator)
    _mock_missing_requirements_plan(
        monkeypatch,
        {"networkx"},
        ["networkx"],
        version_mismatch_names=version_mismatch_names,
    )
    observed_calls = []

    async def mock_install_requirements(*args, **kwargs):
        observed_calls.append(kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert len(observed_calls) == 1
    assert observed_calls[0]["allow_target_upgrade"] is expected_allow_target_upgrade


@pytest.mark.asyncio
async def test_import_plugin_prefers_installed_dependencies_before_first_import(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []
    sentinel_module = object()

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset(),
            install_lines=(),
            version_mismatch_names=frozenset(),
        ),
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="data.plugins.helloworld.main",
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert imported_module is sentinel_module
    assert events == [
        ("prefer", str(requirements_path)),
        ("import", "data.plugins.helloworld.main", ("main",)),
    ]


@pytest.mark.asyncio
async def test_import_reserved_plugin_skips_preloading_user_site_dependencies(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []
    sentinel_module = object()

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="astrbot.builtin_stars.web_searcher.main",
        module_str="main",
        root_dir_name="web_searcher",
        requirements_path=str(requirements_path),
        reserved=True,
    )

    assert imported_module is sentinel_module
    assert events == [
        ("import", "astrbot.builtin_stars.web_searcher.main", ("main",)),
    ]


@pytest.mark.asyncio
async def test_import_plugin_skips_preloading_when_requirements_version_mismatch_detected(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx>=3\n", encoding="utf-8")
    events = []
    sentinel_module = object()

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset({"networkx"}),
            install_lines=("networkx>=3",),
            version_mismatch_names=frozenset({"networkx"}),
        ),
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="data.plugins.helloworld.main",
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert imported_module is sentinel_module
    assert events == [
        ("import", "data.plugins.helloworld.main", ("main",)),
    ]


@pytest.mark.asyncio
async def test_import_plugin_reinstalls_when_version_mismatch_import_fails(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx>=3\n", encoding="utf-8")
    events = []
    sentinel_module = object()
    import_attempts = {"count": 0}

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset({"networkx"}),
            install_lines=("networkx>=3",),
            version_mismatch_names=frozenset({"networkx"}),
        ),
    )

    async def mock_ensure_requirements(_plugin_dir_path, plugin_label):
        events.append(("reinstall", plugin_label))

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "ensure_requirements",
        mock_ensure_requirements,
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        import_attempts["count"] += 1
        events.append(("import", name, tuple(fromlist), import_attempts["count"]))
        if import_attempts["count"] == 1:
            raise ModuleNotFoundError("networkx")
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="data.plugins.helloworld.main",
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert imported_module is sentinel_module
    assert events == [
        ("import", "data.plugins.helloworld.main", ("main",), 1),
        ("reinstall", TEST_PLUGIN_DIR),
        ("import", "data.plugins.helloworld.main", ("main",), 2),
    ]


@pytest.mark.asyncio
async def test_import_plugin_skips_preloading_when_requirement_precheck_is_unavailable(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []
    sentinel_module = object()

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: None,
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="data.plugins.helloworld.main",
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert imported_module is sentinel_module
    assert events == [
        ("import", "data.plugins.helloworld.main", ("main",)),
    ]


@pytest.mark.asyncio
async def test_import_plugin_attempts_dependency_recovery_when_precheck_is_unavailable(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []
    sentinel_module = object()
    import_attempts = {"count": 0}

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: None,
    )

    async def unexpected_check_plugin_dept_update(*args, **kwargs):
        raise AssertionError("dependency install fallback should not run")

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "ensure_requirements",
        unexpected_check_plugin_dept_update,
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        import_attempts["count"] += 1
        events.append(("import", name, tuple(fromlist), import_attempts["count"]))
        if import_attempts["count"] == 1:
            raise ModuleNotFoundError("networkx")
        return sentinel_module

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    imported_module = await plugin_manager_pm.loader.import_with_dependency_recovery(
        path="data.plugins.helloworld.main",
        module_str="main",
        root_dir_name=TEST_PLUGIN_DIR,
        requirements_path=str(requirements_path),
    )

    assert imported_module is sentinel_module
    assert events == [
        ("import", "data.plugins.helloworld.main", ("main",), 1),
        ("prefer", str(requirements_path)),
        ("import", "data.plugins.helloworld.main", ("main",), 2),
    ]


@pytest.mark.asyncio
async def test_import_plugin_does_not_recover_from_plain_import_error(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        lambda requirements_path: events.append(("prefer", requirements_path)),
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset(),
            install_lines=(),
            version_mismatch_names=frozenset(),
        ),
    )

    async def unexpected_check_plugin_dept_update(*args, **kwargs):
        raise AssertionError("dependency install fallback should not run")

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "ensure_requirements",
        unexpected_check_plugin_dept_update,
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        raise ImportError("plugin import error")

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    with pytest.raises(ImportError, match="plugin import error"):
        await plugin_manager_pm.loader.import_with_dependency_recovery(
            path="data.plugins.helloworld.main",
            module_str="main",
            root_dir_name=TEST_PLUGIN_DIR,
            requirements_path=str(requirements_path),
        )

    assert events == [
        ("prefer", str(requirements_path)),
        ("import", "data.plugins.helloworld.main", ("main",)),
    ]


@pytest.mark.asyncio
async def test_import_plugin_surfaces_unexpected_recovery_errors(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("networkx\n", encoding="utf-8")
    events = []

    def raising_prefer_installed_dependencies(requirements_path):
        events.append(("prefer", requirements_path))
        raise RuntimeError("unexpected recovery failure")

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "prefer_installed_dependencies",
        raising_prefer_installed_dependencies,
    )
    monkeypatch.setattr(
        loader_module,
        "plan_missing_requirements_install",
        lambda requirements_path: None,
    )

    async def unexpected_check_plugin_dept_update(*args, **kwargs):
        raise AssertionError("dependency install fallback should not run")

    monkeypatch.setattr(
        plugin_manager_pm.packages,
        "ensure_requirements",
        unexpected_check_plugin_dept_update,
    )

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        del globals, locals, level
        events.append(("import", name, tuple(fromlist)))
        raise ModuleNotFoundError("networkx")

    monkeypatch.setattr(loader_module, "import_module", fake_import)

    with pytest.raises(RuntimeError, match="unexpected recovery failure"):
        await plugin_manager_pm.loader.import_with_dependency_recovery(
            path="data.plugins.helloworld.main",
            module_str="main",
            root_dir_name=TEST_PLUGIN_DIR,
            requirements_path=str(requirements_path),
        )

    assert events == [
        ("import", "data.plugins.helloworld.main", ("main",)),
        ("prefer", str(requirements_path)),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_update_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    dependency_install_fails: bool,
):
    mock_star = MockStar()
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
        cast(StarMetadata, mock_star)
    )

    _write_requirements(local_updator)
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_update(plugin, proxy="", download_url=""):
        del proxy, download_url
        events.append(("update", plugin.name))

    monkeypatch.setattr(plugin_manager_pm.packages._updator, "update", mock_update)
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_reload_unlocked", _build_reload_mock(events)
    )

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.lifecycle.update_plugin(TEST_PLUGIN_NAME)
        dep_event = next(event for event in events if event[0] == "deps")
        _assert_dependency_install_event_matches(
            dep_event,
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.lifecycle.update_plugin(TEST_PLUGIN_NAME)
        dep_event = next(event for event in events if event[0] == "deps")
        _assert_dependency_install_event_matches(
            dep_event,
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
        assert ("reload", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_install_plugin_skips_dependency_install_when_no_requirements_missing(
    plugin_manager_pm: PluginManager, monkeypatch
):
    plugin_path = Path(plugin_manager_pm.packages.store_path) / TEST_PLUGIN_DIR
    events = []
    _mock_missing_requirements(monkeypatch, set())

    async def mock_install(repo_url: str, proxy=""):
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    monkeypatch.setattr(plugin_manager_pm.packages._updator, "install", mock_install)
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, False),
    )

    def mock_load_and_register(*args, **kwargs):
        plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
            cast(StarMetadata, MockStar())
        )
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_load_unlocked", mock_load_and_register
    )

    await plugin_manager_pm.lifecycle.install_plugin(TEST_PLUGIN_REPO)

    assert "deps" not in [e[0] for e in events]
    assert ("load", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_install_plugin_runs_dependency_install_when_precheck_fails(
    plugin_manager_pm: PluginManager, monkeypatch
):
    plugin_path = Path(plugin_manager_pm.packages.store_path) / TEST_PLUGIN_DIR
    events = []

    async def mock_install(repo_url: str, proxy=""):
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    _mock_precheck_fails(monkeypatch)
    monkeypatch.setattr(plugin_manager_pm.packages._updator, "install", mock_install)
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, False),
    )

    def mock_load_and_register(*args, **kwargs):
        plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
            cast(StarMetadata, MockStar())
        )
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "_load_unlocked", mock_load_and_register
    )

    await plugin_manager_pm.lifecycle.install_plugin(TEST_PLUGIN_REPO)

    dep_event = next(event for event in events if event[0] == "deps")
    _assert_dependency_install_event_matches(
        dep_event,
        expected_original_path=plugin_path / "requirements.txt",
    )
    assert ("load", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_installs_only_missing_requirement_lines(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text(
        "aiohttp>=3.0\nboto3==1.2\nbotocore\n",
        encoding="utf-8",
    )
    events = []
    _mock_missing_requirements_plan(
        monkeypatch, {"boto3", "botocore"}, ["boto3==1.2", "botocore"]
    )

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, False, capture_content=True),
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert len(events) == 1
    kind, used_path, content = events[0]
    assert kind == "deps"
    assert used_path != str(requirements_path)
    assert content == "boto3==1.2\nbotocore\n"
    assert not Path(used_path).exists()


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_creates_temp_dir_before_filtered_install(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch, tmp_path
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("boto3\n", encoding="utf-8")
    temp_dir = tmp_path / "missing-temp-dir"
    events = []
    _mock_missing_requirements_plan(monkeypatch, {"boto3"}, ["boto3"])

    monkeypatch.setattr(
        runtime_common_module,
        "get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, False, capture_content=True),
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert temp_dir.is_dir()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_falls_back_when_missing_names_have_no_install_lines(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("boto3\n", encoding="utf-8")
    events = []

    monkeypatch.setattr(
        runtime_common_module,
        "plan_missing_requirements_install",
        lambda path: MissingRequirementsPlan(
            missing_names=frozenset({"botocore"}),
            install_lines=(),
            fallback_reason="unmapped missing requirement names",
        ),
    )
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        _build_dependency_install_mock(events, False),
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert events == [("deps", str(requirements_path))]


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_fallback_full_install_keeps_upgrade_for_version_mismatch(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("boto3>=2\n", encoding="utf-8")
    observed_calls = []

    monkeypatch.setattr(
        runtime_common_module,
        "plan_missing_requirements_install",
        lambda path: MissingRequirementsPlan(
            missing_names=frozenset({"boto3"}),
            install_lines=(),
            version_mismatch_names=frozenset({"boto3"}),
            fallback_reason="unmapped missing requirement names",
        ),
    )

    async def mock_install_requirements(*args, **kwargs):
        observed_calls.append(kwargs)

    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )

    await plugin_manager_pm.packages.ensure_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert len(observed_calls) == 1
    assert observed_calls[0]["requirements_path"] == str(requirements_path)
    assert observed_calls[0]["allow_target_upgrade"] is True


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_does_not_mask_install_error_when_cleanup_fails(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch, tmp_path
):
    requirements_path = local_updator / "requirements.txt"
    requirements_path.write_text("boto3\n", encoding="utf-8")
    temp_dir = tmp_path / "cleanup-fails"
    _mock_missing_requirements_plan(monkeypatch, {"boto3"}, ["boto3"])
    warning_logs = []

    async def mock_install_requirements(
        *, requirements_path: str | None = None, **kwargs
    ):
        del kwargs, requirements_path
        raise RuntimeError("pip failed")

    original_remove = os.remove

    def flaky_remove(path):
        if str(path).endswith("_plugin_requirements.txt"):
            raise OSError("cleanup failed")
        return original_remove(path)

    monkeypatch.setattr(
        runtime_common_module,
        "get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        plugin_manager_pm.packages._pip_installer,
        "install",
        mock_install_requirements,
    )
    monkeypatch.setattr(runtime_common_module.os, "remove", flaky_remove)
    monkeypatch.setattr(
        runtime_common_module.logger,
        "warning",
        lambda line, *args: warning_logs.append(line % args if args else line),
    )

    with pytest.raises(PluginDependencyInstallError, match="pip failed"):
        await plugin_manager_pm.packages.ensure_requirements(
            str(local_updator),
            TEST_PLUGIN_DIR,
        )

    assert any("删除临时插件依赖文件失败" in log for log in warning_logs)


# --- Tests for plugin_id KV cleanup logic ---


@pytest.mark.asyncio
async def test_cleanup_plugin_optional_artifacts_clears_kv_when_plugin_id_present(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleared = []

    class MockDB:
        async def clear_preferences(self, scope, scope_id):
            cleared.append((scope, scope_id))

    monkeypatch.setattr(
        plugin_manager_pm.loader._execution_context,
        "database",
        MockDB(),
    )

    await plugin_manager_pm.packages.cleanup_optional_artifacts(
        root_dir_name="test_plugin",
        plugin_label="TestPlugin",
        plugin_id="test_author/test_plugin",
        delete_config=False,
        delete_data=True,
    )

    assert cleared == [("plugin", "test_author/test_plugin")]


@pytest.mark.asyncio
async def test_cleanup_plugin_optional_artifacts_skips_kv_when_plugin_id_none(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleared = []

    class MockDB:
        async def clear_preferences(self, scope, scope_id):
            cleared.append((scope, scope_id))

    monkeypatch.setattr(
        plugin_manager_pm.loader._execution_context,
        "get_db",
        MockDB,
        raising=False,
    )

    await plugin_manager_pm.packages.cleanup_optional_artifacts(
        root_dir_name="test_plugin",
        plugin_label="TestPlugin",
        plugin_id=None,
        delete_config=False,
        delete_data=True,
    )

    assert cleared == []


@pytest.mark.asyncio
async def test_uninstall_plugin_reads_plugin_id_from_metadata(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleanup_calls = []
    transition_order = []

    mock_star = MockStar()
    mock_star.root_dir_name = TEST_PLUGIN_DIR
    mock_star.name = TEST_PLUGIN_NAME
    mock_star.module_path = "data.plugins.helloworld.main"
    mock_star.reserved = False
    mock_star.star_cls = None
    mock_star.plugin_id = "mock_author/mock_name"

    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
        cast(StarMetadata, mock_star)
    )

    async def mock_deactivate(_coordinator, plugin, *, reason, release=False):
        assert plugin is mock_star
        assert reason == "uninstall"
        assert release is True
        transition_order.append("drain")

    async def mock_terminate(_plugin):
        transition_order.append("terminate")

    monkeypatch.setattr(plugin_manager_pm.lifecycle, "terminate_plugin", mock_terminate)
    monkeypatch.setattr(
        type(plugin_manager_pm.extensions),
        "deactivate",
        mock_deactivate,
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader, "unpublish_plugin", lambda _module_path: None
    )
    monkeypatch.setattr(
        "astrbot.core.star.plugin_lifecycle.remove_dir",
        lambda p: None,
    )

    async def mock_cleanup(
        *, root_dir_name, plugin_label, plugin_id, delete_config, delete_data
    ):
        cleanup_calls.append(
            {
                "root_dir_name": root_dir_name,
                "plugin_label": plugin_label,
                "plugin_id": plugin_id,
            }
        )

    monkeypatch.setattr(
        plugin_manager_pm.packages, "cleanup_optional_artifacts", mock_cleanup
    )

    await plugin_manager_pm.lifecycle.uninstall_plugin(
        TEST_PLUGIN_NAME, delete_config=False, delete_data=True
    )

    assert transition_order == ["drain", "terminate"]

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0]["plugin_id"] == "mock_author/mock_name"


@pytest.mark.asyncio
async def test_uninstall_plugin_handles_disabled_plugin_with_plugin_id(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleanup_calls = []

    mock_star = MockStar()
    mock_star.root_dir_name = TEST_PLUGIN_DIR
    mock_star.name = TEST_PLUGIN_NAME
    mock_star.module_path = "data.plugins.helloworld.main"
    mock_star.star_cls = None
    mock_star.plugin_id = "mock_author/mock_name"

    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(
        cast(StarMetadata, mock_star)
    )

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "terminate_plugin", lambda p: asyncio.sleep(0)
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader, "unpublish_plugin", lambda _module_path: None
    )
    monkeypatch.setattr(
        "astrbot.core.star.plugin_lifecycle.remove_dir",
        lambda p: None,
    )

    async def mock_cleanup(
        *, root_dir_name, plugin_label, plugin_id, delete_config, delete_data
    ):
        cleanup_calls.append(
            {
                "root_dir_name": root_dir_name,
                "plugin_label": plugin_label,
                "plugin_id": plugin_id,
            }
        )

    monkeypatch.setattr(
        plugin_manager_pm.packages, "cleanup_optional_artifacts", mock_cleanup
    )

    await plugin_manager_pm.lifecycle.uninstall_plugin(
        TEST_PLUGIN_NAME, delete_config=False, delete_data=True
    )

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0]["plugin_id"] == "mock_author/mock_name"


@pytest.mark.asyncio
async def test_uninstall_failed_plugin_passes_plugin_id_from_record(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleanup_calls = []

    plugin_manager_pm.loader._failed_plugins[TEST_PLUGIN_DIR] = {
        "name": TEST_PLUGIN_NAME,
        "display_name": "Hello World",
        "plugin_id": "astrbot_team/helloworld",
    }

    monkeypatch.setattr(
        "astrbot.core.star.plugin_lifecycle.remove_dir",
        lambda p: None,
    )

    async def mock_cleanup(
        *, root_dir_name, plugin_label, plugin_id, delete_config, delete_data
    ):
        cleanup_calls.append(
            {
                "root_dir_name": root_dir_name,
                "plugin_label": plugin_label,
                "plugin_id": plugin_id,
            }
        )

    monkeypatch.setattr(
        plugin_manager_pm.packages, "cleanup_optional_artifacts", mock_cleanup
    )

    await plugin_manager_pm.lifecycle.uninstall_failed_plugin(
        TEST_PLUGIN_DIR, delete_config=False, delete_data=True
    )

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0]["plugin_id"] == "astrbot_team/helloworld"


@pytest.mark.asyncio
async def test_uninstall_failed_plugin_without_plugin_id_in_record(
    plugin_manager_pm: PluginManager, monkeypatch
):
    cleanup_calls = []

    plugin_manager_pm.loader._failed_plugins[TEST_PLUGIN_DIR] = {
        "name": TEST_PLUGIN_NAME,
        "display_name": "Hello World",
    }

    monkeypatch.setattr(
        "astrbot.core.star.plugin_lifecycle.remove_dir",
        lambda p: None,
    )

    async def mock_cleanup(
        *, root_dir_name, plugin_label, plugin_id, delete_config, delete_data
    ):
        cleanup_calls.append(
            {
                "root_dir_name": root_dir_name,
                "plugin_label": plugin_label,
                "plugin_id": plugin_id,
            }
        )

    monkeypatch.setattr(
        plugin_manager_pm.packages, "cleanup_optional_artifacts", mock_cleanup
    )

    await plugin_manager_pm.lifecycle.uninstall_failed_plugin(
        TEST_PLUGIN_DIR, delete_config=False, delete_data=True
    )

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0]["plugin_id"] is None


# --- reload + deactivated plugin regression tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("inactivated_plugins", "expected_activated"),
    [
        ([], True),
        (["data.plugins.demo_plugin.main"], False),
    ],
)
async def test_load_syncs_existing_metadata_activation_from_preferences(
    plugin_manager_pm: PluginManager,
    monkeypatch,
    inactivated_plugins: list[str],
    expected_activated: bool,
):
    """Existing plugin metadata activation follows persisted preferences."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "demo_plugin"
    module_path = f"data.plugins.{plugin_name}.main"

    class DemoPlugin:
        def __init__(self, context):
            self.context = context

    preferences = {
        "inactivated_plugins": inactivated_plugins,
        "inactivated_llm_tools": [],
        "alter_cmd": {},
    }

    async def mock_global_get(key, default=None):
        return preferences.get(key, default)

    async def mock_import_plugin_with_dependency_recovery(
        path,
        module_str,
        root_dir_name,
        requirements_path,
        *,
        reserved=False,
    ):
        del module_str, root_dir_name, requirements_path, reserved
        assert path == module_path
        return ModuleType(module_path)

    async def mock_sync_command_configs(*_args):
        return None

    def mock_load_plugin_metadata(**_kwargs):
        return StarMetadata(
            name=plugin_name,
            author="AstrBot Team",
            desc="Demo plugin",
            version="1.0.0",
            root_dir_name=plugin_name,
            module_path=module_path,
            activated=False,
        )

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_get", mock_global_get
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "discover_modules",
        lambda: [{"pname": plugin_name, "module": "main"}],
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "import_with_dependency_recovery",
        mock_import_plugin_with_dependency_recovery,
    )
    monkeypatch.setattr(
        plugin_manager_pm.loader,
        "load_metadata",
        mock_load_plugin_metadata,
    )
    monkeypatch.setattr(
        loader_module,
        "sync_command_configs",
        mock_sync_command_configs,
    )
    _mock_star_declaration(monkeypatch, module_path, DemoPlugin)

    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_module_path=module_path,
        )
        registered = plugin_manager_pm.catalog.runtime_catalogs.plugins.get_by_module(
            module_path
        )

        assert success is True
        assert error is None
        assert registered is not None
        assert registered.activated is expected_activated
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


@pytest.mark.asyncio
async def test_failed_reload_deactivated_plugin_keeps_stale_tools(
    plugin_manager_pm: PluginManager, monkeypatch
):
    """A failed stage never removes tools from a disabled live generation."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "demo_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    metadata = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
        activated=False,
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(metadata)

    plugin_tool = FunctionTool(
        name="plugin_search",
        description="plugin search",
        parameters={"type": "object", "properties": {}},
        handler_module_path=f"data.plugins.{plugin_name}.main.tools.search",
    )
    tool_manager = plugin_manager_pm.catalog.runtime_catalogs.tools
    original_func_list = tool_manager.func_list
    tool_manager.func_list = [plugin_tool]

    try:
        success, _error = await plugin_manager_pm.lifecycle.reload(plugin_name)
        assert success is False
        assert tool_manager.func_list == [plugin_tool]
    finally:
        tool_manager.func_list = original_func_list
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


@pytest.mark.asyncio
async def test_failed_reload_does_not_unpublish_live_module(
    plugin_manager_pm: PluginManager, monkeypatch
):
    """Staging failure must not call the destructive live unpublish path."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "demo_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    metadata = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
        activated=True,
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(metadata)

    unbound = []

    def mock_unbind(path):
        unbound.append(path)

    monkeypatch.setattr(plugin_manager_pm.loader, "unpublish_plugin", mock_unbind)

    try:
        success, _error = await plugin_manager_pm.lifecycle.reload(plugin_name)
        assert success is False
        assert unbound == []
        assert (
            plugin_manager_pm.catalog.runtime_catalogs.plugins.get_by_module(
                module_path
            )
            is metadata
        )
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


@pytest.mark.asyncio
async def test_successful_staged_reload_replaces_live_catalog(
    plugin_manager_pm: PluginManager, monkeypatch
):
    """Successful promotion replaces only the old plugin-owned declarations."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "demo_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    current = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    catalogs = plugin_manager_pm.catalog.runtime_catalogs
    catalogs.plugins.publish(current)

    async def old_handler(*_args: object) -> None:
        return None

    old_handler_metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.old_handler",
        handler_name="old_handler",
        handler_module_path=module_path,
        handler=old_handler,
        event_filters=[],
    )
    catalogs.handlers.append(old_handler_metadata)
    old_tool = FunctionTool(
        name="demo_plugin_tool",
        description="old tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path=module_path,
    )
    catalogs.tools.func_list.append(old_tool)

    staged_catalogs = RuntimeCatalogs()
    staged_catalog = PluginCatalog(staged_catalogs)
    replacement = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    staged_catalogs.plugins.publish(replacement)

    async def replacement_handler(*_args: object) -> None:
        return None

    replacement_handler_metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.replacement_handler",
        handler_name="replacement_handler",
        handler_module_path=module_path,
        handler=replacement_handler,
        event_filters=[],
    )
    staged_catalogs.handlers.append(replacement_handler_metadata)
    replacement_tool = FunctionTool(
        name="demo_plugin_tool",
        description="replacement tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path=module_path,
    )
    staged_catalogs.tools.func_list.append(replacement_tool)

    context = SimpleNamespace(dashboard_extensions=None)
    context._rebind_runtime_catalogs = MagicMock()
    staged = SimpleNamespace(
        metadata=replacement,
        catalog=staged_catalog,
        extensions=PluginExtensionCoordinator(DashboardExtensionRegistry()),
        execution_context=SimpleNamespace(),
        plugin_context=context,
    )

    async def stage_generation(_current):
        return staged, None

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "_stage_reload_generation",
        stage_generation,
    )
    terminate_plugin = AsyncMock()
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle, "terminate_plugin", terminate_plugin
    )

    try:
        success, error = await plugin_manager_pm.lifecycle.reload(plugin_name)
        assert success is True
        assert error is None
        assert catalogs.plugins.get_by_module(module_path) is replacement
        assert list(catalogs.handlers) == [replacement_handler_metadata]
        assert catalogs.tools.func_list == [replacement_tool]
        terminate_plugin.assert_awaited_once_with(current)
        context._rebind_runtime_catalogs.assert_called_once_with(catalogs)
    finally:
        _clear_plugin_runtime_state(catalogs)


@pytest.mark.asyncio
async def test_staged_reload_keeps_live_module_published_during_initialize_await(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A staged initializer must never expose its module via ``sys.modules``."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "module_stage_isolation"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin_path = Path(plugin_manager_pm.packages.store_path) / plugin_name
    plugin_path.mkdir()
    (plugin_path / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": plugin_name,
                "author": "AstrBot Team",
                "desc": "module stage isolation",
                "short_desc": "module stage isolation",
                "version": "1.0.0",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text(
        "from astrbot.api.star import Star\n"
        "\n"
        "class LiveGeneration(Star):\n"
        "    pass\n",
        encoding="utf-8",
    )
    runtime_root = Path(plugin_manager_pm.packages.store_path).parents[1]
    monkeypatch.syspath_prepend(str(runtime_root))
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences,
        "global_get",
        AsyncMock(side_effect=lambda _key, default=None: default),
    )

    probe_name = "plugin_stage_isolation_probe"
    probe = ModuleType(probe_name)
    probe.entered = asyncio.Event()
    probe.release = asyncio.Event()
    monkeypatch.setitem(sys.modules, probe_name, probe)

    reload_task: asyncio.Task[tuple[bool, str | None]] | None = None
    try:
        success, error = await plugin_manager_pm.lifecycle.load(
            specified_dir_name=plugin_name,
        )
        assert success is True
        assert error is None
        original_module = sys.modules[module_path]
        original_metadata = plugin_manager_pm.catalog.plugins.get_by_module(module_path)

        (plugin_path / "main.py").write_text(
            "from astrbot.api.star import Star\n"
            f"from {probe_name} import entered, release\n"
            "\n"
            "class ReplacementGeneration(Star):\n"
            "    async def initialize(self):\n"
            "        entered.set()\n"
            "        await release.wait()\n"
            "\n"
            "# Deliberately changes the source size to invalidate timestamp pyc caches.\n",
            encoding="utf-8",
        )
        importlib.invalidate_caches()
        reload_task = asyncio.create_task(plugin_manager_pm.lifecycle.reload(plugin_name))
        await asyncio.wait_for(probe.entered.wait(), timeout=1)

        assert sys.modules[module_path] is original_module
        assert (
            plugin_manager_pm.catalog.plugins.get_by_module(module_path)
            is original_metadata
        )

        probe.release.set()
        success, error = await reload_task
        assert success is True
        assert error is None
        assert sys.modules[module_path] is not original_module
        assert (
            plugin_manager_pm.catalog.plugins.get_by_module(module_path)
            is not original_metadata
        )
    finally:
        if reload_task is not None and not reload_task.done():
            probe.release.set()
            await reload_task
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
        for name in tuple(sys.modules):
            if name == f"data.plugins.{plugin_name}" or name.startswith(
                f"data.plugins.{plugin_name}."
            ):
                sys.modules.pop(name, None)


@pytest.mark.asyncio
async def test_staged_reload_does_not_share_legacy_task_registrations(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed staging must not append deprecated tasks to the live context."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "staged_task_isolation"
    module_path = f"data.plugins.{plugin_name}.main"
    current = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    plugin_manager_pm.catalog.plugins.publish(current)
    live_context = plugin_manager_pm.loader._execution_context
    live_context._register_tasks = []
    live_context.background_tasks = set()
    registered_coroutine = None
    observed: list[bool] = []

    async def staged_load(self, **_kwargs):
        nonlocal registered_coroutine
        observed.extend(
            [
                self._execution_context._register_tasks
                is live_context._register_tasks,
                self._execution_context.background_tasks is live_context.background_tasks,
            ],
        )

        async def deprecated_task() -> None:
            await asyncio.Event().wait()

        registered_coroutine = deprecated_task()
        self._execution_context._register_tasks.append(registered_coroutine)
        self._catalog.plugins.publish(
            StarMetadata(
                name=plugin_name,
                root_dir_name=plugin_name,
                module_path=module_path,
            ),
        )
        return False, "staged initialization failed"

    monkeypatch.setattr(PluginRuntimeLoader, "load", staged_load)
    try:
        success, error = await plugin_manager_pm.lifecycle.reload(plugin_name)
        assert success is False
        assert error == "staged initialization failed"
        assert observed == [False, False]
        assert live_context._register_tasks == []
        assert live_context.background_tasks == set()
        assert registered_coroutine is not None
        assert registered_coroutine.cr_frame is None
    finally:
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)


def _make_staged_generation(
    plugin_name: str,
) -> tuple[StarMetadata, SimpleNamespace, StarHandlerMetadata, FunctionTool]:
    """Build a small staged package for reload transaction tests."""
    module_path = f"data.plugins.{plugin_name}.main"
    catalogs = RuntimeCatalogs()
    catalog = PluginCatalog(catalogs)
    replacement = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    catalogs.plugins.publish(replacement)

    async def replacement_handler(*_args: object) -> None:
        return None

    handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.replacement_handler",
        handler_name="replacement_handler",
        handler_module_path=module_path,
        handler=replacement_handler,
        event_filters=[],
    )
    catalogs.handlers.append(handler)
    tool = FunctionTool(
        name=f"{plugin_name}_tool",
        description="replacement tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path=module_path,
    )
    catalogs.tools.func_list.append(tool)
    context = SimpleNamespace(dashboard_extensions=None)
    context._rebind_runtime_catalogs = MagicMock()
    return (
        replacement,
        SimpleNamespace(
            metadata=replacement,
            catalog=catalog,
            extensions=PluginExtensionCoordinator(DashboardExtensionRegistry()),
            execution_context=SimpleNamespace(),
            plugin_context=context,
        ),
        handler,
        tool,
    )


@pytest.mark.asyncio
async def test_batch_reload_rolls_back_catalog_after_second_extension_promotion_fails(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure on the second promotion must restore the first package too."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    catalogs = plugin_manager_pm.catalog.runtime_catalogs
    original: list[tuple[StarMetadata, StarHandlerMetadata, FunctionTool]] = []
    staged: list[SimpleNamespace] = []
    for plugin_name in ("reload_batch_one", "reload_batch_two"):
        module_path = f"data.plugins.{plugin_name}.main"
        metadata = StarMetadata(
            name=plugin_name,
            root_dir_name=plugin_name,
            module_path=module_path,
        )
        catalogs.plugins.publish(metadata)

        async def old_handler(*_args: object) -> None:
            return None

        handler = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=f"{module_path}.old_handler",
            handler_name="old_handler",
            handler_module_path=module_path,
            handler=old_handler,
            event_filters=[],
        )
        catalogs.handlers.append(handler)
        tool = FunctionTool(
            name=f"{plugin_name}_tool",
            description="old tool",
            parameters={"type": "object", "properties": {}},
            handler_module_path=module_path,
        )
        catalogs.tools.func_list.append(tool)
        original.append((metadata, handler, tool))
        _replacement, generation, _handler, _tool = _make_staged_generation(
            plugin_name,
        )
        staged.append(generation)

    async def stage_generation(_current: StarMetadata):
        return staged.pop(0), None

    promotion_calls = 0

    async def fail_second_promotion(
        _coordinator,
        _staging,
        _current,
        _replacement,
        *,
        reason,
    ) -> None:
        del reason
        nonlocal promotion_calls
        promotion_calls += 1
        if promotion_calls == 2:
            raise RuntimeError("second extension promotion failed")

    terminate_plugin = AsyncMock()
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "_stage_reload_generation",
        stage_generation,
    )
    monkeypatch.setattr(
        type(plugin_manager_pm.extensions),
        "promote_staged_generation",
        fail_second_promotion,
    )
    monkeypatch.setattr(plugin_manager_pm.lifecycle, "terminate_plugin", terminate_plugin)
    try:
        success, error = await plugin_manager_pm.lifecycle.reload()
        assert success is False
        assert error == "second extension promotion failed"
        assert promotion_calls == 2
        assert [catalogs.plugins.get_by_module(item[0].module_path) for item in original] == [
            item[0] for item in original
        ]
        assert list(catalogs.handlers) == [item[1] for item in original]
        assert catalogs.tools.func_list == [item[2] for item in original]
        terminate_plugin.assert_not_awaited()
    finally:
        _clear_plugin_runtime_state(catalogs)


@pytest.mark.asyncio
async def test_reload_rolls_back_catalog_when_command_refresh_fails(
    plugin_manager_pm: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-promotion command refresh failure cannot leave new declarations live."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "reload_refresh_failure"
    module_path = f"data.plugins.{plugin_name}.main"
    catalogs = plugin_manager_pm.catalog.runtime_catalogs
    current = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
    )
    catalogs.plugins.publish(current)

    async def old_handler(*_args: object) -> None:
        return None

    old_metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module_path}.old_handler",
        handler_name="old_handler",
        handler_module_path=module_path,
        handler=old_handler,
        event_filters=[],
    )
    catalogs.handlers.append(old_metadata)
    old_tool = FunctionTool(
        name=f"{plugin_name}_tool",
        description="old tool",
        parameters={"type": "object", "properties": {}},
        handler_module_path=module_path,
    )
    catalogs.tools.func_list.append(old_tool)
    _replacement, staged, _replacement_handler, _replacement_tool = (
        _make_staged_generation(plugin_name)
    )

    async def stage_generation(_current: StarMetadata):
        return staged, None

    terminate_plugin = AsyncMock()
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "_stage_reload_generation",
        stage_generation,
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle,
        "_refresh_command_surfaces",
        AsyncMock(side_effect=[RuntimeError("command refresh failed"), None]),
    )
    monkeypatch.setattr(plugin_manager_pm.lifecycle, "terminate_plugin", terminate_plugin)
    try:
        success, error = await plugin_manager_pm.lifecycle.reload(plugin_name)
        assert success is False
        assert error == "command refresh failed"
        assert catalogs.plugins.get_by_module(module_path) is current
        assert list(catalogs.handlers) == [old_metadata]
        assert catalogs.tools.func_list == [old_tool]
        terminate_plugin.assert_not_awaited()
    finally:
        _clear_plugin_runtime_state(catalogs)


@pytest.mark.asyncio
async def test_turn_on_plugin_after_deactivated_reload_reactivates_tools(
    plugin_manager_pm: PluginManager, monkeypatch
):
    """turn_on_plugin reactivates tools after a deactivated plugin is reloaded."""
    _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
    plugin_name = "demo_plugin"
    module_path = f"data.plugins.{plugin_name}.main"
    plugin = StarMetadata(
        name=plugin_name,
        root_dir_name=plugin_name,
        module_path=module_path,
        activated=False,
    )
    plugin_manager_pm.catalog.runtime_catalogs.plugins.publish(plugin)

    plugin_tool = FunctionTool(
        name="plugin_search",
        description="plugin search",
        parameters={"type": "object", "properties": {}},
        handler_module_path=f"data.plugins.{plugin_name}.main.tools.search",
    )
    plugin_tool.active = False  # simulate deactivated state
    tool_manager = plugin_manager_pm.catalog.runtime_catalogs.tools
    original_func_list = tool_manager.func_list
    tool_manager.func_list = [plugin_tool]
    preferences = {
        "inactivated_plugins": [module_path],
        "inactivated_llm_tools": [plugin_tool.name],
    }

    async def mock_global_get(key, default=None):
        return preferences.get(key, default)

    async def mock_global_put(key, value):
        preferences[key] = value

    async def mock_terminate(smd):
        pass

    async def mock_reload(plugin_name_arg):
        assert plugin_name_arg == plugin_name
        return True, None

    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_get", mock_global_get
    )
    monkeypatch.setattr(
        plugin_manager_pm.lifecycle._preferences, "global_put", mock_global_put
    )
    monkeypatch.setattr(plugin_manager_pm.lifecycle, "terminate_plugin", mock_terminate)
    monkeypatch.setattr(plugin_manager_pm.lifecycle, "_reload_unlocked", mock_reload)

    try:
        await plugin_manager_pm.lifecycle.turn_on_plugin(plugin_name)
        assert plugin_tool.active is True
        assert module_path not in preferences["inactivated_plugins"]
        assert plugin.activated is True
    finally:
        tool_manager.func_list = original_func_list
        _clear_plugin_runtime_state(plugin_manager_pm.catalog.runtime_catalogs)
