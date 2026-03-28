import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from astrbot_sdk.runtime.loader import load_plugin

from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from astrbot.core.star.star_manager import PluginDependencyInstallError, PluginManager
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.core.utils.requirements_utils import MissingRequirementsPlan

# --- Test Data & Helpers ---

TEST_PLUGIN_NAME = "helloworld"
TEST_PLUGIN_REPO = "https://github.com/AstrBotDevs/astrbot_plugin_helloworld"
TEST_PLUGIN_DIR = "helloworld"
TEST_SDK_PLUGIN_NAME = "sdk_demo"
TEST_SDK_PLUGIN_REPO = "https://github.com/AstrBotDevs/astrbot_plugin_sdk_demo"
TEST_SDK_TOOL_PLUGIN_NAME = "sdk_tool_demo"
TEST_SDK_TOOL_PLUGIN_REPO = (
    "https://github.com/AstrBotDevs/astrbot_plugin_sdk_tool_demo"
)


class MockStar:
    def __init__(self):
        self.root_dir_name = TEST_PLUGIN_DIR
        self.name = TEST_PLUGIN_NAME
        self.repo = TEST_PLUGIN_REPO
        self.reserved = False
        self.info = {"repo": TEST_PLUGIN_REPO, "readme": ""}


def _write_local_test_plugin(plugin_path: Path, repo_url: str):
    """Creates a minimal valid plugin structure."""
    plugin_path.mkdir(parents=True, exist_ok=True)
    metadata = {
        "name": TEST_PLUGIN_NAME,
        "repo": repo_url,
        "version": "1.0.0",
        "author": "AstrBot Team",
        "desc": "Local test plugin",
    }
    with open(plugin_path / "metadata.yaml", "w", encoding="utf-8") as f:
        yaml.dump(metadata, f)
    with open(plugin_path / "main.py", "w", encoding="utf-8") as f:
        f.write("from astrbot.api.star import Star, Context, StarManager\n")
        f.write("@StarManager.register\n")
        f.write("class HelloWorld(Star):\n")
        f.write("    def __init__(self, context: Context): ...\n")


def _write_local_sdk_plugin(
    plugin_path: Path,
    *,
    plugin_name: str = TEST_SDK_PLUGIN_NAME,
):
    """Creates a minimal valid SDK plugin structure."""
    plugin_path.mkdir(parents=True, exist_ok=True)
    (plugin_path / "plugin.yaml").write_text(
        "\n".join(
            [
                f"name: {plugin_name}",
                "version: 1.0.0",
                "author: AstrBot Team",
                f"repo: {plugin_name}",
                'description: "Local SDK test plugin"',
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:DemoPlugin",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text(
        "\n".join(
            [
                "class DemoPlugin:",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_path / "README.md").write_text(
        "# SDK Demo\n",
        encoding="utf-8",
    )


def _write_local_sdk_tool_plugin(
    plugin_path: Path,
    *,
    plugin_name: str = TEST_SDK_TOOL_PLUGIN_NAME,
    tool_name: str = "sdk_lookup_note",
):
    """Creates a minimal SDK plugin that registers one LLM tool."""
    plugin_path.mkdir(parents=True, exist_ok=True)
    (plugin_path / "plugin.yaml").write_text(
        "\n".join(
            [
                f"name: {plugin_name}",
                "display_name: SDK Tool Demo",
                "version: 1.0.0",
                "author: AstrBot Team",
                f"repo: {plugin_name}",
                'desc: "SDK tool demo plugin"',
                "runtime:",
                '  python: "3.11"',
                "components:",
                "  - class: main:DemoToolPlugin",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text(
        "\n".join(
            [
                "from astrbot_sdk import Star",
                "from astrbot_sdk.decorators import register_llm_tool",
                "",
                "class DemoToolPlugin(Star):",
                f'    @register_llm_tool("{tool_name}", description="Lookup demo note")',
                "    async def lookup(self, keyword: str) -> str:",
                '        """Return a deterministic note lookup result."""',
                '        return f"note:{keyword}"',
            ]
        ),
        encoding="utf-8",
    )
    (plugin_path / "README.md").write_text(
        "# SDK Tool Demo\n",
        encoding="utf-8",
    )


def _write_requirements(plugin_path: Path):
    """Creates a requirements.txt file."""
    with open(plugin_path / "requirements.txt", "w", encoding="utf-8") as f:
        f.write("networkx\n")


def _clear_module_cache():
    """Clear test-specific modules from sys.modules to allow reloading."""
    import sys

    to_del = [m for m in sys.modules if m.startswith("data.plugins.helloworld")]
    for m in to_del:
        del sys.modules[m]


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
    fallback_reason: str | None = None,
):
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
        lambda requirements_path: MissingRequirementsPlan(
            missing_names=frozenset(missing_names),
            install_lines=tuple(install_lines),
            fallback_reason=fallback_reason,
        ),
    )


def _mock_precheck_fails(monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
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


@pytest.fixture
def plugin_manager_pm(tmp_path, monkeypatch):
    """Provides a fully isolated PluginManager instance for testing."""
    # Clear module cache before setup to ensure isolation
    _clear_module_cache()

    plugin_dir = tmp_path / "astrbot_root" / "data" / "plugins"
    data_dir = plugin_dir.parent
    plugin_dir.mkdir(parents=True, exist_ok=True)

    class MockContext:
        def __init__(self):
            self.stars = []
            self.sdk_plugin_bridge = None

        def get_all_stars(self):
            return self.stars

        def get_registered_star(self, name):
            for s in self.stars:
                if s.root_dir_name == name or s.name == name:
                    return s
            return None

    mock_context = MockContext()
    mock_config = {}
    pm = PluginManager(cast(Any, mock_context), cast(Any, mock_config))

    # Patch paths to use tmp_path
    monkeypatch.setattr(pm, "plugin_store_path", str(plugin_dir))
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.get_astrbot_plugin_path",
        lambda: str(plugin_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    sdk_plugins_dir = data_dir / "sdk_plugins"
    sdk_plugins_dir.mkdir(parents=True, exist_ok=True)

    async def _noop_metric_upload(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "astrbot.core.star.star_manager.Metric.upload",
        _noop_metric_upload,
    )

    return pm


@pytest.fixture
def local_updator(plugin_manager_pm):
    """Helper to setup a local plugin directory simulating a download."""
    path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    _write_local_test_plugin(path, TEST_PLUGIN_REPO)
    return path


# --- Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_install_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager, monkeypatch, dependency_install_fails: bool
):
    plugin_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install(repo_url: str, proxy=""):
        assert repo_url == TEST_PLUGIN_REPO
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)
        assert len(events) == 1
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=plugin_path / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)
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

    monkeypatch.setattr(plugin_manager_pm.updator, "unzip_file", mock_unzip_file)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.install_plugin_from_file(str(zip_file_path))
        assert any(e[0] == "deps" for e in events)
    else:
        await plugin_manager_pm.install_plugin_from_file(str(zip_file_path))
        assert any(e[0] == "deps" for e in events)
        assert ("load", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_reload_failed_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    dependency_install_fails: bool,
):
    _write_requirements(local_updator)
    plugin_manager_pm.failed_plugin_dict[TEST_PLUGIN_DIR] = {"error": "init fail"}
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.reload_failed_plugin(TEST_PLUGIN_DIR)
        assert len(events) == 1
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.reload_failed_plugin(TEST_PLUGIN_DIR)
        assert len(events) == 2
        _assert_dependency_install_event_matches(
            events[0],
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
        assert events[1] == ("load", TEST_PLUGIN_DIR)


@pytest.mark.asyncio
async def test_ensure_plugin_requirements_reraises_cancelled_error(
    plugin_manager_pm: PluginManager, local_updator: Path, monkeypatch
):
    _write_requirements(local_updator)
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_install_requirements(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        mock_install_requirements,
    )

    with pytest.raises(asyncio.CancelledError):
        await plugin_manager_pm._ensure_plugin_requirements(
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
        "astrbot.core.star.star_manager.pip_installer.install",
        mock_install_requirements,
    )

    with pytest.raises(PluginDependencyInstallError, match="pip failed") as exc_info:
        await plugin_manager_pm._ensure_plugin_requirements(
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
        "astrbot.core.star.star_manager.pip_installer.install",
        mock_install_requirements,
    )

    with pytest.raises(
        PluginDependencyInstallError, match="install failed"
    ) as exc_info:
        await plugin_manager_pm._ensure_plugin_requirements(
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
        "astrbot.core.star.star_manager.pip_installer.install",
        mock_install_requirements,
    )
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.logger.info",
        lambda line, *args: logged_lines.append(line % args if args else line),
    )

    await plugin_manager_pm._ensure_plugin_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert any("按 requirements.txt 安装" in line for line in logged_lines)


@pytest.mark.asyncio
@pytest.mark.parametrize("dependency_install_fails", [False, True])
async def test_update_plugin_dependency_install_flow(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
    dependency_install_fails: bool,
):
    mock_star = MockStar()
    cast(Any, plugin_manager_pm.context).stars.append(mock_star)

    _write_requirements(local_updator)
    events = []
    _mock_missing_requirements(monkeypatch, {"networkx"})

    async def mock_update(plugin, proxy=""):
        del proxy
        events.append(("update", plugin.name))

    monkeypatch.setattr(plugin_manager_pm.updator, "update", mock_update)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, dependency_install_fails),
    )
    monkeypatch.setattr(plugin_manager_pm, "reload", _build_reload_mock(events))

    if dependency_install_fails:
        with pytest.raises(PluginDependencyInstallError, match="pip failed"):
            await plugin_manager_pm.update_plugin(TEST_PLUGIN_NAME)
        dep_event = next(event for event in events if event[0] == "deps")
        _assert_dependency_install_event_matches(
            dep_event,
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
    else:
        await plugin_manager_pm.update_plugin(TEST_PLUGIN_NAME)
        dep_event = next(event for event in events if event[0] == "deps")
        _assert_dependency_install_event_matches(
            dep_event,
            expected_original_path=local_updator / "requirements.txt",
            expected_content="networkx\n",
        )
        assert ("reload", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_update_plugin_migrates_legacy_plugin_to_sdk_runtime(
    plugin_manager_pm: PluginManager,
    local_updator: Path,
    monkeypatch,
):
    legacy_plugin = SimpleNamespace(
        root_dir_name=TEST_PLUGIN_DIR,
        name=TEST_PLUGIN_NAME,
        repo=TEST_PLUGIN_REPO,
        reserved=False,
        activated=False,
        module_path=f"data.plugins.{TEST_PLUGIN_DIR}.main",
    )
    cast(Any, plugin_manager_pm.context).stars.append(legacy_plugin)
    events = []

    class MockSdkBridge:
        async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
            events.append(("sdk_reload_all", reset_restart_budget))

        async def turn_off_plugin(self, plugin_id: str) -> None:
            events.append(("sdk_turn_off", plugin_id))

    cast(Any, plugin_manager_pm.context).sdk_plugin_bridge = MockSdkBridge()

    async def mock_update(plugin, proxy=""):
        del proxy
        assert plugin is legacy_plugin
        for path in local_updator.iterdir():
            if path.is_file():
                path.unlink()
        _write_local_sdk_plugin(
            local_updator,
            plugin_name="astrbot_plugin_helloworld_sdk",
        )

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy reload/dependency path should not be used")

    async def mock_terminate(plugin):
        events.append(("terminate", plugin.name))

    async def mock_unbind(plugin_name: str, module_path: str) -> None:
        events.append(("unbind", plugin_name, module_path))

    monkeypatch.setattr(plugin_manager_pm.updator, "update", mock_update)
    monkeypatch.setattr(
        plugin_manager_pm, "_ensure_plugin_requirements", fail_if_called
    )
    monkeypatch.setattr(plugin_manager_pm, "reload", fail_if_called)
    monkeypatch.setattr(plugin_manager_pm, "_terminate_plugin", mock_terminate)
    monkeypatch.setattr(plugin_manager_pm, "_unbind_plugin", mock_unbind)

    await plugin_manager_pm.update_plugin(TEST_PLUGIN_NAME)

    sdk_plugin_dir = (
        Path(plugin_manager_pm.plugin_store_path).parent
        / "sdk_plugins"
        / "astrbot_plugin_helloworld_sdk"
    )
    assert not local_updator.exists()
    assert (sdk_plugin_dir / "plugin.yaml").exists()
    assert ("terminate", TEST_PLUGIN_NAME) in events
    assert ("unbind", TEST_PLUGIN_NAME, legacy_plugin.module_path) in events
    assert ("sdk_reload_all", True) in events
    assert ("sdk_turn_off", "astrbot_plugin_helloworld_sdk") in events


@pytest.mark.asyncio
async def test_install_plugin_skips_dependency_install_when_no_requirements_missing(
    plugin_manager_pm: PluginManager, monkeypatch
):
    plugin_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    events = []
    _mock_missing_requirements(monkeypatch, set())

    async def mock_install(repo_url: str, proxy=""):
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, False),
    )

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)

    assert "deps" not in [e[0] for e in events]
    assert ("load", TEST_PLUGIN_DIR) in events


@pytest.mark.asyncio
async def test_install_plugin_runs_dependency_install_when_precheck_fails(
    plugin_manager_pm: PluginManager, monkeypatch
):
    plugin_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    events = []

    async def mock_install(repo_url: str, proxy=""):
        _write_local_test_plugin(plugin_path, repo_url)
        _write_requirements(plugin_path)
        return str(plugin_path)

    _mock_precheck_fails(monkeypatch)
    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, False),
    )

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)

    dep_event = next(event for event in events if event[0] == "deps")
    _assert_dependency_install_event_matches(
        dep_event,
        expected_original_path=plugin_path / "requirements.txt",
    )
    assert ("load", TEST_PLUGIN_DIR) in events


def test_detect_plugin_type_identifies_sdk_plugin(
    plugin_manager_pm: PluginManager, tmp_path
):
    plugin_path = tmp_path / "sdk_plugin"
    _write_local_sdk_plugin(plugin_path)

    plugin_type, plugin_name = plugin_manager_pm._detect_plugin_type(str(plugin_path))

    assert plugin_type == "sdk"
    assert plugin_name == TEST_SDK_PLUGIN_NAME


def test_detect_plugin_type_identifies_legacy_plugin(
    plugin_manager_pm: PluginManager, tmp_path
):
    plugin_path = tmp_path / "legacy_plugin"
    _write_local_test_plugin(plugin_path, TEST_PLUGIN_REPO)

    plugin_type, plugin_name = plugin_manager_pm._detect_plugin_type(str(plugin_path))

    assert plugin_type == "legacy"
    assert plugin_name == TEST_PLUGIN_NAME


@pytest.mark.asyncio
async def test_install_plugin_routes_sdk_plugin_to_sdk_plugins_directory(
    plugin_manager_pm: PluginManager, monkeypatch
):
    download_path = Path(plugin_manager_pm.plugin_store_path) / "sdk_download_dir"
    events = []

    class MockSdkBridge:
        async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
            events.append(("sdk_reload_all", reset_restart_budget))

    cast(Any, plugin_manager_pm.context).sdk_plugin_bridge = MockSdkBridge()

    async def mock_install(repo_url: str, proxy=""):
        assert repo_url == TEST_SDK_PLUGIN_REPO
        del proxy
        _write_local_sdk_plugin(download_path)
        return str(download_path)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy loader path should not be used for SDK plugins")

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(plugin_manager_pm, "load", fail_if_called)
    monkeypatch.setattr(
        plugin_manager_pm, "_ensure_plugin_requirements", fail_if_called
    )

    plugin_info = await plugin_manager_pm.install_plugin(TEST_SDK_PLUGIN_REPO)

    sdk_plugin_dir = Path(plugin_manager_pm.plugin_store_path).parent / "sdk_plugins"
    assert not download_path.exists()
    assert (sdk_plugin_dir / TEST_SDK_PLUGIN_NAME / "plugin.yaml").exists()
    assert events == [("sdk_reload_all", True)]
    assert plugin_info == {
        "repo": TEST_SDK_PLUGIN_REPO,
        "readme": "# SDK Demo\n",
        "name": TEST_SDK_PLUGIN_NAME,
        "type": "sdk",
    }


@pytest.mark.asyncio
async def test_install_plugin_routes_legacy_plugin_to_plugins_directory(
    plugin_manager_pm: PluginManager, monkeypatch
):
    download_path = Path(plugin_manager_pm.plugin_store_path) / "legacy_repo_dir"
    events = []

    async def mock_install(repo_url: str, proxy=""):
        assert repo_url == TEST_PLUGIN_REPO
        del proxy
        _write_local_test_plugin(download_path, repo_url)
        return str(download_path)

    async def mock_ensure_requirements(plugin_path: str, plugin_label: str) -> None:
        events.append(("deps", plugin_label, plugin_path))

    def mock_load_and_register(*args, **kwargs):
        cast(Any, plugin_manager_pm.context).stars.append(MockStar())
        return _build_load_mock(events)(*args, **kwargs)

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(
        plugin_manager_pm,
        "_ensure_plugin_requirements",
        mock_ensure_requirements,
    )
    monkeypatch.setattr(plugin_manager_pm, "load", mock_load_and_register)

    plugin_info = await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)

    target_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR
    assert not download_path.exists()
    assert target_path.exists()
    assert ("load", TEST_PLUGIN_DIR) in events
    assert any(event[0] == "deps" for event in events)
    assert plugin_info == {
        "repo": TEST_PLUGIN_REPO,
        "readme": None,
        "name": TEST_PLUGIN_NAME,
        "type": "legacy",
    }


@pytest.mark.asyncio
async def test_install_plugin_from_file_routes_sdk_plugin_to_sdk_plugins_directory(
    plugin_manager_pm: PluginManager, monkeypatch, tmp_path
):
    zip_file_path = tmp_path / "sdk_demo.zip"
    zip_file_path.write_text("placeholder", encoding="utf-8")
    events = []

    class MockSdkBridge:
        async def reload_all(self, *, reset_restart_budget: bool = False) -> None:
            events.append(("sdk_reload_all", reset_restart_budget))

    cast(Any, plugin_manager_pm.context).sdk_plugin_bridge = MockSdkBridge()

    def mock_unzip_file(zip_path: str, target_dir: str) -> None:
        assert zip_path == str(zip_file_path)
        _write_local_sdk_plugin(Path(target_dir))

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy loader path should not be used for SDK plugins")

    monkeypatch.setattr(plugin_manager_pm.updator, "unzip_file", mock_unzip_file)
    monkeypatch.setattr(plugin_manager_pm, "load", fail_if_called)
    monkeypatch.setattr(
        plugin_manager_pm, "_ensure_plugin_requirements", fail_if_called
    )

    plugin_info = await plugin_manager_pm.install_plugin_from_file(str(zip_file_path))

    sdk_plugin_dir = Path(plugin_manager_pm.plugin_store_path).parent / "sdk_plugins"
    assert not zip_file_path.exists()
    assert (sdk_plugin_dir / TEST_SDK_PLUGIN_NAME / "plugin.yaml").exists()
    assert events == [("sdk_reload_all", True)]
    assert plugin_info == {
        "repo": None,
        "readme": "# SDK Demo\n",
        "name": TEST_SDK_PLUGIN_NAME,
        "type": "sdk",
    }


@pytest.mark.asyncio
async def test_install_sdk_plugin_registers_sdk_tool_in_bridge_dashboard_view(
    plugin_manager_pm: PluginManager,
    monkeypatch,
):
    download_path = Path(plugin_manager_pm.plugin_store_path) / "sdk_tool_download_dir"
    data_root = Path(plugin_manager_pm.plugin_store_path).parent

    class _LoadingWorkerSession:
        def __init__(self, *, plugin, on_closed=None, **_kwargs) -> None:
            self.plugin = plugin
            self.on_closed = on_closed
            self.handlers = []
            self.llm_tools = []
            self.agents = []
            self.issues = []
            self.peer = None

        async def start(self) -> None:
            loaded_plugin = load_plugin(self.plugin)
            self.handlers = [
                item.descriptor.model_copy(deep=True) for item in loaded_plugin.handlers
            ]
            self.llm_tools = [
                item.spec.to_payload() for item in loaded_plugin.llm_tools
            ]
            self.agents = [item.spec.to_payload() for item in loaded_plugin.agents]
            self.peer = SimpleNamespace(remote_metadata={})

        def start_close_watch(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_plugin_data_path",
        lambda: str(data_root / "plugin_data"),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.WorkerSession",
        _LoadingWorkerSession,
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.SkillManager.prune_sdk_plugin_skills",
        lambda self, known: None,
    )

    sdk_bridge = SdkPluginBridge(cast(Any, plugin_manager_pm.context))
    sdk_bridge._publish_plugin_skills = lambda _plugin_id: None
    sdk_bridge._persist_state_overrides = lambda: None
    sdk_bridge.env_manager.plan = lambda _plugins: None

    async def _noop_register_schedule(_record) -> None:
        return None

    sdk_bridge._register_schedule_handlers = _noop_register_schedule
    cast(Any, plugin_manager_pm.context).sdk_plugin_bridge = sdk_bridge

    async def mock_install(repo_url: str, proxy=""):
        assert repo_url == TEST_SDK_TOOL_PLUGIN_REPO
        del proxy
        _write_local_sdk_tool_plugin(download_path)
        return str(download_path)

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)

    plugin_info = await plugin_manager_pm.install_plugin(TEST_SDK_TOOL_PLUGIN_REPO)

    dashboard_tools = sdk_bridge.list_dashboard_tools()
    assert plugin_info == {
        "repo": TEST_SDK_TOOL_PLUGIN_REPO,
        "readme": "# SDK Tool Demo\n",
        "name": TEST_SDK_TOOL_PLUGIN_NAME,
        "type": "sdk",
    }
    assert len(dashboard_tools) == 1
    assert dashboard_tools[0] == {
        "tool_key": f"sdk:{TEST_SDK_TOOL_PLUGIN_NAME}:sdk_lookup_note",
        "name": "sdk_lookup_note",
        "description": "Lookup demo note",
        "parameters": {
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
            "required": ["keyword"],
        },
        "active": True,
        "origin": "sdk_plugin",
        "origin_name": "SDK Tool Demo",
        "runtime_kind": "sdk",
        "plugin_id": TEST_SDK_TOOL_PLUGIN_NAME,
    }


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
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, False, capture_content=True),
    )

    await plugin_manager_pm._ensure_plugin_requirements(
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
        "astrbot.core.star.star_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, False, capture_content=True),
    )

    await plugin_manager_pm._ensure_plugin_requirements(
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
        "astrbot.core.star.star_manager.plan_missing_requirements_install",
        lambda path: MissingRequirementsPlan(
            missing_names=frozenset({"botocore"}),
            install_lines=(),
            fallback_reason="unmapped missing requirement names",
        ),
    )
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        _build_dependency_install_mock(events, False),
    )

    await plugin_manager_pm._ensure_plugin_requirements(
        str(local_updator),
        TEST_PLUGIN_DIR,
    )

    assert events == [("deps", str(requirements_path))]


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
        "astrbot.core.star.star_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.pip_installer.install",
        mock_install_requirements,
    )
    monkeypatch.setattr("astrbot.core.star.star_manager.os.remove", flaky_remove)
    monkeypatch.setattr(
        "astrbot.core.star.star_manager.logger.warning",
        lambda line, *args: warning_logs.append(line % args if args else line),
    )

    with pytest.raises(PluginDependencyInstallError, match="pip failed"):
        await plugin_manager_pm._ensure_plugin_requirements(
            str(local_updator),
            TEST_PLUGIN_DIR,
        )

    assert any("删除临时插件依赖文件失败" in log for log in warning_logs)
