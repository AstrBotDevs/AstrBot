"""Exercise reloads through real imports, decorators and plugin lifecycle methods."""

import asyncio
import importlib
import logging
import os
import py_compile
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.star import star_manager as core


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    # Keep the actual registries shared by Star and the registration decorators.
    saved_stars = list(core.star_registry)
    saved_map = dict(core.star_map)
    saved_handlers = list(core.star_handlers_registry)
    saved_tools = list(core.llm_tools.func_list)
    saved_root_handlers = list(logging.root.handlers)
    roots = ("data.plugins.cache_subject", "data.plugins.cache_subject_neighbor")

    def owned(name):
        return any(name == root or name.startswith(root + ".") for root in roots)

    saved_modules = {
        name: module for name, module in sys.modules.items() if owned(name)
    }
    for name in saved_modules:
        sys.modules.pop(name)
    core.star_registry.clear()
    core.star_map.clear()
    core.star_handlers_registry.clear()
    core.llm_tools.func_list.clear()
    package = tmp_path / "data" / "plugins"
    package.mkdir(parents=True)
    data = ModuleType("data")
    data.__path__ = [str(package.parent)]
    plugins = ModuleType("data.plugins")
    plugins.__path__ = [str(package)]
    data.plugins = plugins
    monkeypatch.setitem(sys.modules, "data", data)
    monkeypatch.setitem(sys.modules, "data.plugins", plugins)
    preferences = {
        "inactivated_plugins": [],
        "inactivated_llm_tools": [],
        "alter_cmd": {},
    }

    async def get(key, default=None):
        return preferences.get(key, default)

    async def put(key, value):
        preferences[key] = value

    monkeypatch.setattr(core.sp, "global_get", get)
    monkeypatch.setattr(core.sp, "global_put", put)
    monkeypatch.setattr(core, "sync_command_configs", AsyncMock())
    events = []
    context = SimpleNamespace(
        events=events,
        get_registered_star=lambda name: next(
            (m for m in core.star_registry if m.name == name), None
        ),
    )
    manager = core.PluginManager.__new__(core.PluginManager)
    manager.context = context
    manager.config = {}
    manager.plugin_store_path = str(package)
    manager.plugin_config_path = str(tmp_path / "config")
    manager.reserved_plugin_path = str(tmp_path / "builtin")
    manager.conf_schema_fname = "_conf_schema.json"
    manager.logo_fname = "logo.png"
    manager._pm_lock = asyncio.Lock()
    manager.failed_plugin_dict = {}
    manager.failed_plugin_info = ""

    def write(root="cache_subject", version="old", broken=False):
        folder = package / root
        folder.mkdir(exist_ok=True)
        (folder / "__init__.py").write_text("", encoding="utf-8")
        (folder / "child.py").write_text(f"VERSION = {version!r}\n", encoding="utf-8")
        (folder / "hooks.py").write_text(
            "from astrbot.api.event import filter\n"
            f"@filter.command({root + '_subcommand'!r})\n"
            "async def subcommand(event):\n"
            f"    return {version!r}\n",
            encoding="utf-8",
        )
        name = "registered_" + root
        (folder / "metadata.yaml").write_text(
            f"name: {name}\nauthor: synthetic\ndesc: Cache regression\nversion: 1.0.0\n",
            encoding="utf-8",
        )
        (folder / "main.py").write_text(
            "from astrbot.api.star import Star\n"
            "from astrbot.api.event import filter\n"
            "from .child import VERSION\n"
            "from . import hooks\n"
            f"MAIN_VERSION = {version!r}\n"
            "class Main(Star):\n"
            "    def __init__(self, context):\n"
            "        self.context = context\n"
            "        self.version = MAIN_VERSION + ':' + VERSION\n"
            f"        context.events.append(('construct', {name!r}))\n"
            "    async def initialize(self):\n"
            f"        self.context.events.append(('initialize', {name!r}))\n"
            "    async def terminate(self):\n"
            f"        self.context.events.append(('terminate', {name!r}))\n"
            f"    @filter.llm_tool(name={root + '_query'!r})\n"
            "    async def query(self, event):\n"
            '        """Return the loaded version."""\n'
            "        return self.version\n"
            f"    @filter.llm_tool(name={root + '_private'!r})\n"
            "    async def private(self, event):\n"
            '        """Return the loaded version for an explicitly disabled tool."""\n'
            "        return self.version\n"
            f"    @filter.command({root + '_command'!r})\n"
            "    async def command(self, event):\n"
            "        return self.version\n"
            + ("raise RuntimeError('synthetic import failure')\n" if broken else ""),
            encoding="utf-8",
        )
        importlib.invalidate_caches()
        return name

    def tools(root="cache_subject"):
        return {
            tool.name: tool
            for tool in core.llm_tools.func_list
            if tool.handler_module_path == f"data.plugins.{root}.main"
        }

    try:
        yield SimpleNamespace(
            manager=manager,
            context=context,
            events=events,
            preferences=preferences,
            write=write,
            tools=tools,
            package=package,
        )
    finally:
        for name in list(sys.modules):
            if owned(name):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        logging.root.handlers[:] = saved_root_handlers
        core.star_registry[:] = saved_stars
        core.star_map.clear()
        core.star_map.update(saved_map)
        core.star_handlers_registry.clear()
        for handler in saved_handlers:
            core.star_handlers_registry.append(handler)
        core.llm_tools.func_list[:] = saved_tools


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled_reload", [False, True])
async def test_disabled_reload_reimports_source_and_preserves_tool_preferences(
    runtime, disabled_reload
):
    r = runtime
    name = r.write()
    neighbor = r.write("cache_subject_neighbor")
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    assert await r.manager.load(specified_dir_name="cache_subject_neighbor") == (
        True,
        None,
    )
    first = r.context.get_registered_star(name).star_cls
    neighbor_metadata = r.context.get_registered_star(neighbor)
    neighbor_modules = {
        k: v
        for k, v in sys.modules.items()
        if k.startswith("data.plugins.cache_subject_neighbor")
    }
    neighbor_tools = r.tools("cache_subject_neighbor")
    neighbor_handlers = [
        h
        for h in core.star_handlers_registry
        if h.handler_module_path == neighbor_metadata.module_path
    ]
    r.preferences["inactivated_llm_tools"] = ["cache_subject_private"]
    await r.manager.turn_off_plugin(name)
    r.write(version="updated")
    if disabled_reload:
        assert await r.manager.reload(name) == (True, None)
        metadata = r.context.get_registered_star(name)
        assert not metadata.activated and metadata.star_cls is None
        assert set(r.tools()) == {"cache_subject_query", "cache_subject_private"}
        assert all(not tool.active for tool in r.tools().values())
        assert metadata.module.MAIN_VERSION == "updated"
        assert sys.modules["data.plugins.cache_subject.child"].VERSION == "updated"
    await r.manager.turn_on_plugin(name)
    current = r.context.get_registered_star(name)
    assert current.star_cls is not first
    assert current.star_cls.version == "updated:updated"
    assert await r.tools()["cache_subject_query"].handler(None) == "updated:updated"
    assert r.tools()["cache_subject_query"].active
    assert not r.tools()["cache_subject_private"].active
    for _ in range(2):
        assert await r.manager.reload(name) == (True, None)
    assert len([m for m in core.star_registry if m.name == name]) == 1
    assert len(r.tools()) == 2
    handlers = [
        h
        for h in core.star_handlers_registry
        if h.handler_module_path == current.module_path
    ]
    assert len(handlers) == 3
    assert (
        await next(h for h in handlers if h.handler_name == "command").handler(None)
        == "updated:updated"
    )
    subhandlers = [
        h
        for h in core.star_handlers_registry
        if h.handler_module_path == "data.plugins.cache_subject.hooks"
    ]
    assert len(subhandlers) == 1
    assert await subhandlers[0].handler(None) == "updated"
    assert r.context.get_registered_star(neighbor) is neighbor_metadata
    assert all(sys.modules[k] is v for k, v in neighbor_modules.items())
    assert all(
        r.tools("cache_subject_neighbor")[k] is v for k, v in neighbor_tools.items()
    )
    assert all(
        any(h is old for h in core.star_handlers_registry) for old in neighbor_handlers
    )
    assert r.events.count(("terminate", name)) == 3
    assert r.events.count(("construct", name)) == 4
    assert r.events.count(("initialize", name)) == 4
    assert ("terminate", neighbor) not in r.events


@pytest.mark.asyncio
async def test_failed_import_cleans_target_and_preserves_neighbor(runtime):
    r = runtime
    name = r.write()
    neighbor = r.write("cache_subject_neighbor")
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    assert await r.manager.load(specified_dir_name="cache_subject_neighbor") == (
        True,
        None,
    )
    other = r.context.get_registered_star(neighbor)
    await r.manager.turn_off_plugin(name)
    r.write(version="broken_source", broken=True)
    with pytest.raises(Exception, match="synthetic import failure|启用失败|load"):
        await r.manager.turn_on_plugin(name)
    assert r.context.get_registered_star(name) is None
    assert not r.tools()
    assert not any(
        k == "data.plugins.cache_subject" or k.startswith("data.plugins.cache_subject.")
        for k in sys.modules
    )
    assert r.context.get_registered_star(neighbor) is other
    assert (
        await r.tools("cache_subject_neighbor")["cache_subject_neighbor_query"].handler(
            None
        )
        == "old:old"
    )


@pytest.mark.asyncio
async def test_reload_recompiles_same_size_same_timestamp_source(runtime):
    r = runtime
    name = r.write()
    for path in (r.package / "cache_subject").glob("*.py"):
        py_compile.compile(str(path), doraise=True)
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    await r.manager.turn_off_plugin(name)
    stamps = {p: p.stat() for p in (r.package / "cache_subject").glob("*.py")}
    r.write(version="new")
    for path, stat in stamps.items():
        assert path.stat().st_size == stat.st_size
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    await r.manager.turn_on_plugin(name)
    assert r.context.get_registered_star(name).star_cls.version == "new:new"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["missing", "", 42, [], "duplicate", "missing_module"])
async def test_invalid_named_reload_does_not_touch_plugins(runtime, name):
    r = runtime
    registered = r.write()
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    if name == "duplicate":
        core.star_registry.extend(
            [
                core.StarMetadata(name=name, module_path="data.plugins.a.main"),
                core.StarMetadata(name=name, module_path="data.plugins.b.main"),
            ]
        )
    elif name == "missing_module":
        core.star_registry.append(core.StarMetadata(name=name))
    before = r.context.get_registered_star(registered)
    events = list(r.events)
    success, error = await r.manager.reload(name)
    assert not success and error
    assert r.context.get_registered_star(registered) is before
    assert r.events == events


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["reload", "enable"])
async def test_bytecode_permission_failure_preserves_disabled_runtime(
    runtime, monkeypatch, operation
):
    r = runtime
    name = r.write()
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    await r.manager.turn_off_plugin(name)
    metadata = r.context.get_registered_star(name)
    tools = r.tools()
    modules = {
        k: v
        for k, v in sys.modules.items()
        if k == "data.plugins.cache_subject"
        or k.startswith("data.plugins.cache_subject.")
    }
    events = list(r.events)
    unlink = Path.unlink

    def deny_bytecode(path, *args, **kwargs):
        if path.suffix == ".pyc" and path.is_relative_to(r.package):
            raise PermissionError("synthetic read-only bytecode")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_bytecode)
    if operation == "reload":
        success, error = await r.manager.reload(name)
        assert not success and "bytecode" in error
    else:
        with pytest.raises(PermissionError, match="read-only bytecode"):
            await r.manager.turn_on_plugin(name)
    assert r.context.get_registered_star(name) is metadata
    assert not metadata.activated
    assert metadata.module_path in r.preferences["inactivated_plugins"]
    assert all(r.tools()[k] is tool and not tool.active for k, tool in tools.items())
    assert all(sys.modules[k] is module for k, module in modules.items())
    assert r.events == events


@pytest.mark.asyncio
async def test_enable_preflights_once_under_same_lock_as_reload(runtime, monkeypatch):
    r = runtime
    name = r.write()
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    await r.manager.turn_off_plugin(name)
    original = r.manager._clear_plugin_bytecode
    calls = []

    def preflight(metadata):
        assert r.manager._pm_lock.locked()
        calls.append(metadata)
        if len(calls) > 1:
            raise PermissionError("second preflight must not occur")
        original(metadata)

    monkeypatch.setattr(r.manager, "_clear_plugin_bytecode", preflight)
    await asyncio.wait_for(r.manager.turn_on_plugin(name), timeout=2)
    assert len(calls) == 1
    assert r.context.get_registered_star(name).activated
    assert r.tools()["cache_subject_query"].active


@pytest.mark.asyncio
async def test_enable_and_disable_are_serialized(runtime, monkeypatch):
    r = runtime
    name = r.write()
    assert await r.manager.load(specified_dir_name="cache_subject") == (True, None)
    await r.manager.turn_off_plugin(name)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = core.sp.global_put

    async def paused_put(key, value):
        if key == "inactivated_plugins" and not value and not entered.is_set():
            entered.set()
            await release.wait()
        await original(key, value)

    monkeypatch.setattr(core.sp, "global_put", paused_put)
    enabling = asyncio.create_task(r.manager.turn_on_plugin(name))
    disabling = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert r.manager._pm_lock.locked()
        disabling = asyncio.create_task(r.manager.turn_off_plugin(name))
        await asyncio.sleep(0)
        assert not disabling.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(enabling, disabling), timeout=2)
        metadata = r.context.get_registered_star(name)
        assert not metadata.activated
        assert metadata.module_path in r.preferences["inactivated_plugins"]
        assert all(not tool.active for tool in r.tools().values())
    finally:
        release.set()
        for task in (enabling, disabling):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
