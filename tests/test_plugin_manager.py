import sys
from asyncio import Queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.context import Context
from astrbot.core.star.star import star_map, star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.star_manager import PluginManager


def _clear_module_cache() -> None:
    """Clear module cache for data module tree to ensure test isolation."""
    modules_to_remove = [
        key for key in sys.modules if key == "data" or key.startswith("data.")
    ]
    for key in modules_to_remove:
        del sys.modules[key]


def _clear_registry(plugin_name: str) -> None:
    """Clear plugin from global registries."""
    # Clear star_registry (list)
    star_registry[:] = [md for md in star_registry if md.name != plugin_name]
    # Clear star_map (dict)
    keys_to_remove = [
        key for key, md in star_map.items() if md.name == plugin_name
    ]
    for key in keys_to_remove:
        del star_map[key]
    # Clear star_handlers_registry (StarHandlerRegistry)
    for handler in list(star_handlers_registry):
        if plugin_name in (handler.handler_module_path or ""):
            star_handlers_registry.remove(handler)

TEST_PLUGIN_REPO = "https://github.com/Soulter/helloworld"
TEST_PLUGIN_DIR = "helloworld"
TEST_PLUGIN_NAME = "helloworld"


def _write_local_test_plugin(plugin_dir: Path, repo_url: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "metadata.yaml").write_text(
        "\n".join(
            [
                f"name: {TEST_PLUGIN_NAME}",
                "author: AstrBot Team",
                "desc: Local test plugin",
                "version: 1.0.0",
                f"repo: {repo_url}",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot.api import star",
                "",
                "class Main(star.Star):",
                "    pass",
                "",
            ],
        ),
        encoding="utf-8",
    )


@pytest_asyncio.fixture
async def plugin_manager_pm(tmp_path, monkeypatch):
    """Provides a fully isolated PluginManager instance for testing."""
    # Clear module cache before setup to ensure isolation
    _clear_module_cache()

    test_root = tmp_path / "astrbot_root"
    data_dir = test_root / "data"
    plugin_dir = data_dir / "plugins"
    config_dir = data_dir / "config"
    temp_dir = data_dir / "temp"
    for path in (plugin_dir, config_dir, temp_dir):
        path.mkdir(parents=True, exist_ok=True)

    # Ensure `import data.plugins.<plugin>.main` resolves to this temp root.
    (data_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")

    # Use monkeypatch for both env var and sys.path to ensure proper cleanup
    monkeypatch.setenv("ASTRBOT_ROOT", str(test_root))
    monkeypatch.syspath_prepend(str(test_root))

    # Create fresh, isolated instances for the context
    event_queue = Queue()
    config = AstrBotConfig()
    db = SQLiteDatabase(str(data_dir / "test_db.db"))
    config.plugin_store_path = str(plugin_dir)

    provider_manager = MagicMock()
    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    persona_manager.personas_v3 = []
    astrbot_config_mgr = MagicMock()
    knowledge_base_manager = MagicMock()
    cron_manager = MagicMock()

    star_context = Context(
        event_queue=event_queue,
        config=config,
        db=db,
        provider_manager=provider_manager,
        platform_manager=platform_manager,
        conversation_manager=conversation_manager,
        message_history_manager=message_history_manager,
        persona_manager=persona_manager,
        astrbot_config_mgr=astrbot_config_mgr,
        knowledge_base_manager=knowledge_base_manager,
        cron_manager=cron_manager,
        subagent_orchestrator=None,
    )

    manager = PluginManager(star_context, config)
    try:
        yield manager
    finally:
        # Cleanup global registries and module cache
        _clear_registry(TEST_PLUGIN_NAME)
        _clear_module_cache()
        await db.engine.dispose()


@pytest.fixture
def local_updator(plugin_manager_pm: PluginManager, monkeypatch):
    plugin_path = Path(plugin_manager_pm.plugin_store_path) / TEST_PLUGIN_DIR

    async def mock_install(repo_url: str, proxy=""):  # noqa: ARG001
        if repo_url != TEST_PLUGIN_REPO:
            raise Exception("Repo not found")
        _write_local_test_plugin(plugin_path, repo_url)
        return str(plugin_path)

    async def mock_update(plugin, proxy=""):  # noqa: ARG001
        if plugin.name != TEST_PLUGIN_NAME:
            raise Exception("Plugin not found")
        if not plugin_path.exists():
            raise Exception("Plugin path missing")
        (plugin_path / ".updated").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(plugin_manager_pm.updator, "install", mock_install)
    monkeypatch.setattr(plugin_manager_pm.updator, "update", mock_update)
    return plugin_path


@pytest.mark.asyncio
async def test_plugin_manager_initialization(plugin_manager_pm: PluginManager):
    assert plugin_manager_pm is not None
    assert plugin_manager_pm.context is not None
    assert plugin_manager_pm.config is not None


@pytest.mark.asyncio
async def test_plugin_manager_reload(plugin_manager_pm: PluginManager):
    success, err_message = await plugin_manager_pm.reload()
    assert success is True
    assert err_message is None


@pytest.mark.asyncio
async def test_install_plugin(plugin_manager_pm: PluginManager, local_updator: Path):
    """Tests successful plugin installation without external network."""
    plugin_info = await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)
    assert plugin_info is not None
    assert plugin_info["name"] == TEST_PLUGIN_NAME
    assert local_updator.exists()
    assert any(md.name == TEST_PLUGIN_NAME for md in star_registry)


@pytest.mark.asyncio
async def test_install_nonexistent_plugin(
    plugin_manager_pm: PluginManager, local_updator
):
    """Tests that installing a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.install_plugin(
            "https://github.com/Soulter/non_existent_repo"
        )


@pytest.mark.asyncio
async def test_update_plugin(plugin_manager_pm: PluginManager, local_updator: Path):
    """Tests updating an existing plugin without external network."""
    plugin_info = await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)
    assert plugin_info is not None
    plugin_name = plugin_info["name"]
    await plugin_manager_pm.update_plugin(plugin_name)
    assert (local_updator / ".updated").exists()


@pytest.mark.asyncio
async def test_update_nonexistent_plugin(
    plugin_manager_pm: PluginManager, local_updator
):
    """Tests that updating a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.update_plugin("non_existent_plugin")


@pytest.mark.asyncio
async def test_uninstall_plugin(plugin_manager_pm: PluginManager, local_updator: Path):
    """Tests successful plugin uninstallation."""
    plugin_info = await plugin_manager_pm.install_plugin(TEST_PLUGIN_REPO)
    assert plugin_info is not None
    plugin_name = plugin_info["name"]
    assert local_updator.exists()

    await plugin_manager_pm.uninstall_plugin(plugin_name)

    assert not local_updator.exists()
    assert not any(md.name == TEST_PLUGIN_NAME for md in star_registry)
    assert not any(
        TEST_PLUGIN_NAME in md.handler_module_path for md in star_handlers_registry
    )


@pytest.mark.asyncio
async def test_uninstall_nonexistent_plugin(plugin_manager_pm: PluginManager):
    """Tests that uninstalling a non-existent plugin raises an exception."""
    with pytest.raises(Exception):
        await plugin_manager_pm.uninstall_plugin("non_existent_plugin")
