"""Unit tests for astrbot.core.star.star_manager.

Tests PluginManager initialization, load, install, and uninstall flows with
full mock isolation (no filesystem, no network).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from astrbot.core.star.star_manager import (
    PluginDependencyInstallError,
    PluginManager,
    PluginVersionIncompatibleError,
)


# ---------------------------------------------------------------------------
# PluginVersionIncompatibleError / PluginDependencyInstallError
# ---------------------------------------------------------------------------


class TestPluginExceptions:
    """Custom exception classes."""

    def test_version_incompatible_error(self):
        """PluginVersionIncompatibleError is a plain exception."""
        exc = PluginVersionIncompatibleError("bad version")
        assert isinstance(exc, Exception)
        assert str(exc) == "bad version"

    def test_dependency_install_error(self):
        """PluginDependencyInstallError wraps the original error."""
        inner = ValueError("pip failed")
        exc = PluginDependencyInstallError(
            plugin_label="my_plugin",
            requirements_path="/path/requirements.txt",
            error=inner,
        )
        assert exc.plugin_label == "my_plugin"
        assert exc.requirements_path == "/path/requirements.txt"
        assert exc.error is inner
        assert "pip failed" in str(exc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_context():
    """A fully mocked Context with required methods."""
    ctx = MagicMock()
    ctx.get_all_stars.return_value = []
    ctx.get_registered_star.return_value = None
    return ctx


@pytest.fixture
def mock_config():
    """A mock AstrBotConfig."""
    return MagicMock()


@pytest.fixture
def plugin_manager(mock_context, mock_config):
    """Create a PluginManager with all dependencies mocked."""
    with (
        patch(
            "astrbot.core.star.star_manager.get_astrbot_plugin_path",
            return_value="/mock/plugins",
        ),
        patch(
            "astrbot.core.star.star_manager.get_astrbot_config_path",
            return_value="/mock/config",
        ),
        patch(
            "astrbot.core.star.star_manager.get_astrbot_path",
            return_value="/mock/astrbot",
        ),
        patch(
            "astrbot.core.star.star_manager.PluginUpdator",
        ),
        patch(
            "astrbot.core.star.star_manager.StarTools",
        ),
    ):
        pm = PluginManager(mock_context, mock_config)
        # Disable hot-reload watcher
        pm.tasks = set()
        return pm


# ---------------------------------------------------------------------------
# Constructor / Init
# ---------------------------------------------------------------------------


class TestPluginManagerInit:
    """PluginManager constructor behavior."""

    def test_init_sets_paths(self, plugin_manager):
        """Constructor sets correct default paths."""
        assert plugin_manager.plugin_store_path == "/mock/plugins"
        assert plugin_manager.plugin_config_path == "/mock/config"
        assert "astrbot" in plugin_manager.reserved_plugin_path

    def test_init_sets_empty_failed_dict(self, plugin_manager):
        """Constructor initializes empty failed plugin tracking."""
        assert plugin_manager.failed_plugin_dict == {}
        assert plugin_manager.failed_plugin_info == ""

    def test_init_stores_context_and_config(self, plugin_manager, mock_context, mock_config):
        """Constructor stores the context and config references."""
        assert plugin_manager.context is mock_context
        assert plugin_manager.config is mock_config

    def test_init_sets_lock(self, plugin_manager):
        """Constructor creates an asyncio.Lock."""
        import asyncio

        assert isinstance(plugin_manager._pm_lock, asyncio.Lock)

    def test_init_starts_watcher_when_reload_env_set(self, mock_context, mock_config):
        """When ASTRBOT_RELOAD=1, the file watcher task is created."""
        with (
            patch(
                "astrbot.core.star.star_manager.get_astrbot_plugin_path",
                return_value="/mock/plugins",
            ),
            patch(
                "astrbot.core.star.star_manager.get_astrbot_config_path",
                return_value="/mock/config",
            ),
            patch(
                "astrbot.core.star.star_manager.get_astrbot_path",
                return_value="/mock",
            ),
            patch(
                "astrbot.core.star.star_manager.PluginUpdator",
            ),
            patch(
                "astrbot.core.star.star_manager.StarTools",
            ),
            patch.dict("os.environ", {"ASTRBOT_RELOAD": "1"}),
            patch(
                "astrbot.core.star.star_manager.asyncio.create_task",
            ) as mock_create_task,
        ):
            pm = PluginManager(mock_context, mock_config)
            # Clean up after init
            assert mock_create_task.called


# ---------------------------------------------------------------------------
# _get_classes / _get_modules / _get_plugin_modules (static helpers)
# ---------------------------------------------------------------------------


class TestGetClasses:
    """PluginManager._get_classes() static helper."""

    def test_returns_class_names_from_module(self):
        """_get_classes finds classes ending in 'plugin' or named 'main'."""
        import types

        module = types.ModuleType("test_module")
        exec(
            """
class MyPlugin:
    pass

class NotAPlugin:
    pass
""",
            module.__dict__,
        )
        result = PluginManager._get_classes(module)
        assert "MyPlugin" in result
        assert "NotAPlugin" not in result

    def test_returns_main_class(self):
        """_get_classes includes a class named 'main' (case-insensitive)."""
        import types

        module = types.ModuleType("test_module")
        exec(
            """
class Main:
    pass
""",
            module.__dict__,
        )
        result = PluginManager._get_classes(module)
        assert "Main" in result

    def test_returns_empty_when_no_match(self):
        """_get_classes returns empty list when no matching classes exist."""
        import types

        module = types.ModuleType("test_module")
        exec(
            """
class Helper:
    pass
""",
            module.__dict__,
        )
        result = PluginManager._get_classes(module)
        assert result == []


class TestValidateImportableName:
    """PluginManager._validate_importable_name() static helper."""

    def test_valid_name_passes(self):
        """A valid Python identifier passes validation."""
        PluginManager._validate_importable_name("my_plugin")  # no raise

    def test_rejects_path_separator(self):
        """A name containing / raises ValueError."""
        with pytest.raises(ValueError, match="路径分隔符"):
            PluginManager._validate_importable_name("my/plugin")

    def test_rejects_invalid_identifier(self):
        """A name that is not a valid Python identifier raises Exception."""
        with pytest.raises(Exception, match="合法的模块名称"):
            PluginManager._validate_importable_name("123invalid")

    def test_rejects_keyword(self):
        """A name that is a Python keyword raises Exception."""
        with pytest.raises(Exception, match="合法的模块名称"):
            PluginManager._validate_importable_name("class")


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


class TestLoad:
    """PluginManager.load() behavior."""

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    async def test_load_returns_true_when_no_plugins(
        self, mock_sync, mock_sp_get, plugin_manager
    ):
        """load() returns (True, None) when no plugin modules exist."""
        mock_sp_get.return_value = []
        plugin_manager._get_plugin_modules = MagicMock(return_value=[])
        success, error = await plugin_manager.load()
        assert success is True
        assert error is None

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    async def test_load_returns_false_when_modules_is_none(
        self, mock_sync, mock_sp_get, plugin_manager
    ):
        """load() returns (False, msg) when _get_plugin_modules returns None."""
        mock_sp_get.return_value = []
        plugin_manager._get_plugin_modules = MagicMock(return_value=None)
        success, error = await plugin_manager.load()
        assert success is False
        assert "未找到" in error

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    async def test_load_handles_import_failure(
        self, mock_sync, mock_sp_get, plugin_manager
    ):
        """load() records failed plugins when import fails."""
        mock_sp_get.return_value = []
        plugin_manager._get_plugin_modules = MagicMock(
            return_value=[
                {
                    "pname": "broken_plugin",
                    "module": "main",
                    "module_path": "/mock/plugins/broken_plugin/main",
                    "reserved": False,
                }
            ]
        )
        plugin_manager._import_plugin_with_dependency_recovery = AsyncMock(
            side_effect=ImportError("Module not found")
        )
        plugin_manager._load_plugin_metadata = MagicMock(return_value=None)
        plugin_manager._build_failed_plugin_record = MagicMock(
            return_value={"name": "broken_plugin", "error": "Module not found"}
        )

        success, error = await plugin_manager.load()
        assert success is False
        assert "broken_plugin" in plugin_manager.failed_plugin_dict

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    async def test_load_calls_sync_command_configs(
        self, mock_sync, mock_sp_get, plugin_manager
    ):
        """load() calls sync_command_configs after processing plugins."""
        mock_sp_get.return_value = []
        plugin_manager._get_plugin_modules = MagicMock(return_value=[])
        await plugin_manager.load()
        mock_sync.assert_called_once()


# ---------------------------------------------------------------------------
# install_plugin
# ---------------------------------------------------------------------------


class TestInstallPlugin:
    """PluginManager.install_plugin() behavior."""

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    @patch("astrbot.core.star.star_manager.Metric")
    async def test_install_plugin_success(
        self, mock_metric, mock_sync, mock_sp_get, plugin_manager, mock_context
    ):
        """install_plugin installs and loads a plugin successfully."""
        mock_sp_get.return_value = []
        plugin_manager.updator.parse_github_url = MagicMock(
            return_value=("owner", "test_repo", "repo")
        )
        plugin_manager.updator.format_name = MagicMock(return_value="test_repo")

        # Mock the install to return a plugin path
        plugin_manager.updator.install = AsyncMock(
            return_value="/mock/plugins/test_repo"
        )
        plugin_manager._get_plugin_dir_name_from_metadata = MagicMock(
            return_value="test_repo"
        )
        plugin_manager._ensure_plugin_requirements = AsyncMock()
        plugin_manager.load = AsyncMock(return_value=(True, None))

        mock_plugin_meta = MagicMock()
        mock_plugin_meta.repo = "https://github.com/test/test_repo"
        mock_plugin_meta.name = "test_plugin"
        mock_context.get_registered_star.side_effect = lambda name: (
            mock_plugin_meta if name == "test_repo" else None
        )

        result = await plugin_manager.install_plugin(
            "https://github.com/test/test_repo"
        )
        assert result is not None
        assert result["repo"] == "https://github.com/test/test_repo"
        assert result["name"] == "test_plugin"

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    @patch("astrbot.core.star.star_manager.Metric")
    async def test_install_plugin_raises_when_load_fails(
        self, mock_metric, mock_sync, mock_sp_get, plugin_manager
    ):
        """install_plugin raises when load() returns failure."""
        mock_sp_get.return_value = []
        plugin_manager.updator.parse_github_url = MagicMock(
            return_value=("owner", "test_repo", "repo")
        )
        plugin_manager.updator.format_name = MagicMock(return_value="test_repo")
        plugin_manager.updator.install = AsyncMock(
            return_value="/mock/plugins/test_repo"
        )
        plugin_manager._get_plugin_dir_name_from_metadata = MagicMock(
            return_value="test_repo"
        )
        plugin_manager._ensure_plugin_requirements = AsyncMock()
        plugin_manager.load = AsyncMock(
            return_value=(False, "Version incompatible error")
        )

        with pytest.raises(Exception, match="Version incompatible error"):
            await plugin_manager.install_plugin(
                "https://github.com/test/test_repo"
            )

    @patch("astrbot.core.star.star_manager.sp.global_get")
    @patch("astrbot.core.star.star_manager.sync_command_configs", new_callable=AsyncMock)
    @patch("astrbot.core.star.star_manager.Metric")
    async def test_install_plugin_raises_when_dir_exists(
        self, mock_metric, mock_sync, mock_sp_get, plugin_manager
    ):
        """install_plugin raises when the target directory already exists."""
        mock_sp_get.return_value = []
        plugin_manager.updator.parse_github_url = MagicMock(
            return_value=("owner", "test_repo", "repo")
        )
        plugin_manager.updator.format_name = MagicMock(return_value="test_repo")

        with (
            patch("astrbot.core.star.star_manager.anyio.Path") as mock_path,
        ):
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_path_instance.exists = AsyncMock(return_value=True)

            with pytest.raises(Exception, match="已存在"):
                await plugin_manager.install_plugin(
                    "https://github.com/test/test_repo"
                )


# ---------------------------------------------------------------------------
# uninstall_plugin
# ---------------------------------------------------------------------------


class TestUninstallPlugin:
    """PluginManager.uninstall_plugin() behavior."""

    @patch("astrbot.core.star.star_manager.remove_dir")
    @patch("astrbot.core.star.star_manager.unregister_platform_adapters_by_module")
    async def test_uninstall_plugin_success(
        self,
        mock_unregister,
        mock_remove_dir,
        plugin_manager,
        mock_context,
    ):
        """uninstall_plugin terminates, unbinds, and removes plugin directory."""
        mock_plugin = MagicMock()
        mock_plugin.reserved = False
        mock_plugin.root_dir_name = "test_repo"
        mock_plugin.name = "test_plugin"
        mock_plugin.module_path = "data.plugins.test_repo.main"
        mock_context.get_registered_star.return_value = mock_plugin

        plugin_manager._terminate_plugin = AsyncMock()
        plugin_manager._unbind_plugin = AsyncMock()

        await plugin_manager.uninstall_plugin("test_plugin")

        plugin_manager._terminate_plugin.assert_called_once_with(mock_plugin)
        plugin_manager._unbind_plugin.assert_called_once_with(
            "test_plugin", "data.plugins.test_repo.main"
        )
        mock_remove_dir.assert_called_once()

    @patch("astrbot.core.star.star_manager.remove_dir")
    async def test_uninstall_plugin_raises_when_not_found(
        self, mock_remove_dir, plugin_manager, mock_context
    ):
        """uninstall_plugin raises when plugin is not registered."""
        mock_context.get_registered_star.return_value = None
        with pytest.raises(Exception, match="插件不存在"):
            await plugin_manager.uninstall_plugin("nonexistent")

    @patch("astrbot.core.star.star_manager.remove_dir")
    async def test_uninstall_plugin_raises_for_reserved(
        self, mock_remove_dir, plugin_manager, mock_context
    ):
        """uninstall_plugin raises when plugin is reserved."""
        mock_plugin = MagicMock()
        mock_plugin.reserved = True
        mock_context.get_registered_star.return_value = mock_plugin

        with pytest.raises(Exception, match="保留插件"):
            await plugin_manager.uninstall_plugin("reserved_plugin")


# ---------------------------------------------------------------------------
# _validate_astrbot_version_specifier
# ---------------------------------------------------------------------------


class TestValidateAstrbotVersion:
    """PluginManager._validate_astrbot_version_specifier() behavior."""

    def test_none_version_returns_valid(self):
        """None version specifier is valid."""
        valid, msg = PluginManager._validate_astrbot_version_specifier(None)
        assert valid is True
        assert msg is None

    @patch("astrbot.core.star.star_manager.VERSION", "4.16.0")
    def test_version_in_range(self):
        """A version specifier that includes the current version is valid."""
        valid, msg = PluginManager._validate_astrbot_version_specifier(">=4.16,<5")
        assert valid is True
        assert msg is None

    @patch("astrbot.core.star.star_manager.VERSION", "4.15.0")
    def test_version_out_of_range(self):
        """A version specifier that excludes the current version is invalid."""
        valid, msg = PluginManager._validate_astrbot_version_specifier(">=4.16,<5")
        assert valid is False
        assert "does not satisfy" in msg

    def test_invalid_specifier_returns_error(self):
        """An unparseable specifier returns invalid with error message."""
        valid, msg = PluginManager._validate_astrbot_version_specifier("not_a_version")
        assert valid is False
        assert "PEP 440" in msg


# ---------------------------------------------------------------------------
# _load_plugin_metadata
# ---------------------------------------------------------------------------


class TestLoadPluginMetadata:
    """PluginManager._load_plugin_metadata() behavior."""

    def test_raises_when_path_does_not_exist(self):
        """_load_plugin_metadata raises when plugin_path does not exist."""
        with patch("astrbot.core.star.star_manager.os.path.exists", return_value=False):
            with pytest.raises(Exception, match="插件不存在"):
                PluginManager._load_plugin_metadata("/nonexistent/path")


# ---------------------------------------------------------------------------
# reload_failed_plugin
# ---------------------------------------------------------------------------


class TestReloadFailedPlugin:
    """PluginManager.reload_failed_plugin() behavior."""

    async def test_returns_false_when_not_in_failed_dict(self, plugin_manager):
        """reload_failed_plugin returns (False, msg) when dir not in failed dict."""
        result = await plugin_manager.reload_failed_plugin("unknown")
        assert result == (False, "插件不存在于失败列表中")
