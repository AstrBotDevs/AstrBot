"""
Tests for runtime/loader.py - Plugin loading utilities.
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.runtime.loader import (
    LoadedHandler,
    LoadedPlugin,
    PluginDiscoveryResult,
    PluginEnvironmentManager,
    PluginSpec,
    STATE_FILE_NAME,
    _create_legacy_context,
    _is_new_star_component,
    _iter_handler_names,
    _venv_python_path,
    discover_plugins,
    import_string,
    load_plugin,
    load_plugin_spec,
)


class TestVenvPythonPath:
    """Tests for _venv_python_path function."""

    def test_linux_path(self):
        """_venv_python_path should return correct Linux path."""
        # 使用 PurePath 进行路径拼接测试，避免跨平台问题
        from pathlib import PurePosixPath

        # 测试逻辑：posix 系统返回 bin/python
        with patch("os.name", "posix"):
            path = _venv_python_path(PurePosixPath("/home/user/.venv"))
            # 结果应该是字符串形式比较
            assert str(path) == "/home/user/.venv/bin/python"

    def test_windows_path(self):
        """_venv_python_path should return correct Windows path."""
        from pathlib import PureWindowsPath

        with patch("os.name", "nt"):
            path = _venv_python_path(PureWindowsPath("C:\\venv"))
            assert str(path) == "C:\\venv\\Scripts\\python.exe"


class TestPluginSpec:
    """Tests for PluginSpec dataclass."""

    def test_init(self):
        """PluginSpec should store all fields."""
        plugin_dir = Path("/tmp/plugin")
        manifest_path = plugin_dir / "plugin.yaml"
        requirements_path = plugin_dir / "requirements.txt"

        spec = PluginSpec(
            name="test_plugin",
            plugin_dir=plugin_dir,
            manifest_path=manifest_path,
            requirements_path=requirements_path,
            python_version="3.12",
            manifest_data={"name": "test_plugin"},
        )

        assert spec.name == "test_plugin"
        assert spec.plugin_dir == plugin_dir
        assert spec.manifest_path == manifest_path
        assert spec.requirements_path == requirements_path
        assert spec.python_version == "3.12"
        assert spec.manifest_data == {"name": "test_plugin"}


class TestPluginDiscoveryResult:
    """Tests for PluginDiscoveryResult dataclass."""

    def test_init(self):
        """PluginDiscoveryResult should store plugins and skipped."""
        spec = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )

        result = PluginDiscoveryResult(
            plugins=[spec],
            skipped_plugins={"bad_plugin": "missing requirements.txt"},
        )

        assert len(result.plugins) == 1
        assert result.skipped_plugins == {"bad_plugin": "missing requirements.txt"}


class TestLoadedHandler:
    """Tests for LoadedHandler dataclass."""

    def test_init(self):
        """LoadedHandler should store all fields."""
        descriptor = HandlerDescriptor(
            id="test.handler",
            trigger=CommandTrigger(command="hello"),
        )

        def handler_func():
            pass

        owner = MagicMock()

        loaded = LoadedHandler(
            descriptor=descriptor,
            callable=handler_func,
            owner=owner,
            legacy_context=None,
        )

        assert loaded.descriptor == descriptor
        assert loaded.callable == handler_func
        assert loaded.owner == owner
        assert loaded.legacy_context is None


class TestLoadedPlugin:
    """Tests for LoadedPlugin dataclass."""

    def test_init(self):
        """LoadedPlugin should store plugin and handlers."""
        spec = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )

        loaded = LoadedPlugin(plugin=spec, handlers=[], instances=[])

        assert loaded.plugin == spec
        assert loaded.handlers == []
        assert loaded.capabilities == []
        assert loaded.instances == []


class TestIsNewStarComponent:
    """Tests for _is_new_star_component function."""

    def test_non_class_returns_false(self):
        """_is_new_star_component should return False for non-class."""
        assert _is_new_star_component("not a class") is False
        assert _is_new_star_component(123) is False

    def test_non_star_subclass_returns_false(self):
        """_is_new_star_component should return False for non-Star class."""

        class NotAStar:
            pass

        assert _is_new_star_component(NotAStar) is False

    def test_star_without_marker_returns_true(self):
        """_is_new_star_component should return True for Star without marker."""
        from astrbot_sdk.star import Star

        class MyStar(Star):
            pass

        assert _is_new_star_component(MyStar) is True

    def test_star_with_false_marker_returns_false(self):
        """_is_new_star_component should return False if marker returns False."""
        from astrbot_sdk.star import Star

        class LegacyStar(Star):
            @classmethod
            def __astrbot_is_new_star__(cls):
                return False

        assert _is_new_star_component(LegacyStar) is False


class TestCreateLegacyContext:
    """Tests for _create_legacy_context function."""

    def test_with_factory_method(self):
        """_create_legacy_context should use factory method if available."""
        mock_context = MagicMock()

        class ComponentWithFactory:
            @classmethod
            def _astrbot_create_legacy_context(cls, plugin_name):
                return mock_context

        result = _create_legacy_context(ComponentWithFactory, "test_plugin")
        assert result == mock_context

    def test_without_factory_method(self):
        """_create_legacy_context should create default context."""
        # Without factory, it imports LegacyContext
        from astrbot_sdk.star import Star

        class PlainStar(Star):
            pass

        result = _create_legacy_context(PlainStar, "test_plugin")
        # Should return some context object
        assert result is not None


class TestIterHandlerNames:
    """Tests for _iter_handler_names function."""

    def test_with_handlers_attribute(self):
        """_iter_handler_names should use __handlers__ if available."""

        # 创建一个真实的类来测试，而不是 MagicMock
        class InstanceWithHandlers:
            __handlers__ = ("handler1", "handler2")

        instance = InstanceWithHandlers()
        names = _iter_handler_names(instance)
        assert names == ["handler1", "handler2"]

    def test_without_handlers_attribute(self):
        """_iter_handler_names should fall back to dir() if no __handlers__."""

        # 创建一个没有 __handlers__ 的真实类
        class InstanceWithoutHandlers:
            def method1(self):
                pass

            def method2(self):
                pass

        instance = InstanceWithoutHandlers()
        names = _iter_handler_names(instance)
        # 应该返回 dir(instance) 的结果
        assert "method1" in names
        assert "method2" in names


class TestLoadPluginSpec:
    """Tests for load_plugin_spec function."""

    def test_loads_manifest(self):
        """load_plugin_spec should load plugin.yaml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.11"},
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            assert spec.name == "test_plugin"
            assert spec.python_version == "3.11"
            assert spec.plugin_dir.resolve() == plugin_dir.resolve()

    def test_defaults_python_version(self):
        """load_plugin_spec should default python version to current."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump({"name": "test_plugin"}),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            expected = f"{sys.version_info.major}.{sys.version_info.minor}"
            assert spec.python_version == expected

    def test_defaults_name_to_dir_name(self):
        """load_plugin_spec should default name to directory name."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "my_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text("{}", encoding="utf-8")
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            assert spec.name == "my_plugin"


class TestDiscoverPlugins:
    """Tests for discover_plugins function."""

    def test_empty_directory(self):
        """discover_plugins should return empty for non-existent directory."""
        result = discover_plugins(Path("/nonexistent"))
        assert result.plugins == []
        assert result.skipped_plugins == {}

    def test_skips_dot_directories(self):
        """discover_plugins should skip directories starting with dot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            # Create .hidden directory
            hidden_dir = plugins_dir / ".hidden"
            hidden_dir.mkdir()
            (hidden_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "hidden",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "test:Test"}],
                    }
                ),
                encoding="utf-8",
            )
            (hidden_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert result.plugins == []

    def test_skips_missing_manifest(self):
        """discover_plugins should skip directories without plugin.yaml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            plugin_dir = plugins_dir / "no_manifest"
            plugin_dir.mkdir()
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert result.plugins == []

    def test_skips_missing_requirements(self):
        """discover_plugins should skip directories without requirements.txt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            plugin_dir = plugins_dir / "no_requirements"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump({"name": "test"}),
                encoding="utf-8",
            )

            result = discover_plugins(plugins_dir)

            assert "no_requirements" in result.skipped_plugins
            assert "requirements.txt" in result.skipped_plugins["no_requirements"]

    def test_validates_required_fields(self):
        """discover_plugins should validate required manifest fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            # Missing name
            plugin_dir = plugins_dir / "missing_name"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "test:Test"}],
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert "missing_name" in result.skipped_plugins
            assert "name" in result.skipped_plugins["missing_name"]

    def test_detects_duplicate_names(self):
        """discover_plugins should detect duplicate plugin names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            for i, dirname in enumerate(["plugin1", "plugin2"]):
                plugin_dir = plugins_dir / dirname
                plugin_dir.mkdir()
                (plugin_dir / "plugin.yaml").write_text(
                    yaml.dump(
                        {
                            "name": "duplicate_name",  # Same name
                            "runtime": {"python": "3.12"},
                            "components": [{"class": "test:Test"}],
                        }
                    ),
                    encoding="utf-8",
                )
                (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            # First one should succeed, second should be skipped
            assert len(result.plugins) == 1
            assert "duplicate_name" in result.skipped_plugins

    def test_validates_components_list(self):
        """discover_plugins should validate components is a list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            plugin_dir = plugins_dir / "bad_components"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "test",
                        "runtime": {"python": "3.12"},
                        "components": "not_a_list",
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert "test" in result.skipped_plugins
            assert "components" in result.skipped_plugins["test"]

    def test_allows_empty_components_list(self):
        """discover_plugins should allow plugins without components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            plugin_dir = plugins_dir / "empty_components"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "empty_components",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert [plugin.name for plugin in result.plugins] == ["empty_components"]
            assert result.skipped_plugins == {}

    def test_discovers_valid_plugin(self):
        """discover_plugins should discover valid plugin."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)

            plugin_dir = plugins_dir / "valid_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.yaml").write_text(
                yaml.dump(
                    {
                        "name": "valid_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "module:Class"}],
                    }
                ),
                encoding="utf-8",
            )
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

            result = discover_plugins(plugins_dir)

            assert len(result.plugins) == 1
            assert result.plugins[0].name == "valid_plugin"

    def test_discovers_legacy_main_plugin_without_manifest(self):
        """discover_plugins should accept legacy plugins with main.py."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir)
            plugin_dir = plugins_dir / "legacy_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "main.py").write_text(
                "from astrbot_sdk.api.star import Star\n\nclass LegacyPlugin(Star):\n    pass\n",
                encoding="utf-8",
            )
            (plugin_dir / "metadata.yaml").write_text(
                yaml.dump({"name": "legacy_plugin", "author": "tester"}),
                encoding="utf-8",
            )

            result = discover_plugins(plugins_dir)

            assert [plugin.name for plugin in result.plugins] == ["legacy_plugin"]
            assert result.skipped_plugins == {}


class TestPluginEnvironmentManager:
    """Tests for PluginEnvironmentManager class."""

    def test_init(self):
        """PluginEnvironmentManager should initialize with repo root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PluginEnvironmentManager(Path(temp_dir))
            assert manager.repo_root == Path(temp_dir).resolve()
            assert manager.cache_dir == Path(temp_dir).resolve() / ".uv-cache"

    def test_uv_binary_detection(self):
        """PluginEnvironmentManager should detect uv binary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("shutil.which", return_value="/usr/bin/uv"):
                manager = PluginEnvironmentManager(Path(temp_dir))
                assert manager.uv_binary == "/usr/bin/uv"

    def test_prepare_environment_without_uv_raises(self):
        """prepare_environment should raise if uv not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建 requirements.txt，否则 _fingerprint 会失败
            requirements_path = Path(temp_dir) / "requirements.txt"
            requirements_path.write_text("", encoding="utf-8")

            # Mock shutil.which 在 loader 模块中返回 None，确保 uv_binary 为 None
            with patch("astrbot_sdk.runtime.loader.shutil.which", return_value=None):
                manager = PluginEnvironmentManager(Path(temp_dir), uv_binary=None)
                assert manager.uv_binary is None

                spec = PluginSpec(
                    name="test",
                    plugin_dir=Path(temp_dir),
                    manifest_path=Path(temp_dir) / "plugin.yaml",
                    requirements_path=requirements_path,
                    python_version="3.12",
                    manifest_data={},
                )

                with pytest.raises(RuntimeError, match="uv"):
                    manager.prepare_environment(spec)

    def test_fingerprint(self):
        """_fingerprint should create consistent fingerprint."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            requirements = plugin_dir / "requirements.txt"
            requirements.write_text("astrbot-sdk\n", encoding="utf-8")

            spec = PluginSpec(
                name="test",
                plugin_dir=plugin_dir,
                manifest_path=plugin_dir / "plugin.yaml",
                requirements_path=requirements,
                python_version="3.12",
                manifest_data={},
            )

            fingerprint = PluginEnvironmentManager._fingerprint(spec)

            assert "python_version" in fingerprint
            assert "3.12" in fingerprint
            assert "requirements" in fingerprint

    def test_load_state_missing_file(self):
        """_load_state should return empty dict for missing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state = PluginEnvironmentManager._load_state(
                Path(temp_dir) / "missing.json"
            )
            assert state == {}

    def test_load_state_invalid_json(self):
        """_load_state should return empty dict for invalid JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text("not valid json", encoding="utf-8")

            state = PluginEnvironmentManager._load_state(state_path)
            assert state == {}

    def test_write_state(self):
        """_write_state should write state file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            spec = PluginSpec(
                name="test",
                plugin_dir=Path(temp_dir),
                manifest_path=Path(temp_dir) / "plugin.yaml",
                requirements_path=Path(temp_dir) / "requirements.txt",
                python_version="3.12",
                manifest_data={},
            )

            PluginEnvironmentManager._write_state(state_path, spec, "test_fingerprint")

            import json

            state = json.loads(state_path.read_text(encoding="utf-8"))

            assert state["plugin"] == "test"
            assert state["fingerprint"] == "test_fingerprint"


class TestImportString:
    """Tests for import_string function."""

    def test_imports_module_attribute(self):
        """import_string should import module and get attribute."""
        result = import_string("os:path")
        assert result is not None

    def test_raises_for_missing_module(self):
        """import_string should raise for missing module."""
        with pytest.raises(ImportError):
            import_string("nonexistent_module:attr")

    def test_raises_for_missing_attribute(self):
        """import_string should raise for missing attribute."""
        with pytest.raises(AttributeError):
            import_string("os:nonexistent_attr")

    def test_raises_for_invalid_format(self):
        """import_string should raise for invalid format."""
        with pytest.raises(ValueError):
            import_string("no_colon")

    def test_plugin_dir_isolates_same_top_level_package(self):
        """import_string should evict conflicting cached top-level plugin packages."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_plugin = root / "plugin_one"
            second_plugin = root / "plugin_two"

            for plugin_dir, marker in (
                (first_plugin, "first"),
                (second_plugin, "second"),
            ):
                commands_dir = plugin_dir / "commands"
                commands_dir.mkdir(parents=True)
                (commands_dir / "__init__.py").write_text("", encoding="utf-8")
                (commands_dir / "sample.py").write_text(
                    f"VALUE = {marker!r}\n",
                    encoding="utf-8",
                )

            try:
                first_module = import_string(
                    "commands.sample:VALUE",
                    plugin_dir=first_plugin,
                )
                second_module = import_string(
                    "commands.sample:VALUE",
                    plugin_dir=second_plugin,
                )
            finally:
                for module_name in list(sys.modules):
                    if module_name == "commands" or module_name.startswith("commands."):
                        sys.modules.pop(module_name, None)
                for plugin_dir in (first_plugin, second_plugin):
                    plugin_path = str(plugin_dir)
                    if plugin_path in sys.path:
                        sys.path.remove(plugin_path)

            assert first_module == "first"
            assert second_module == "second"


class TestLoadPlugin:
    """Tests for load_plugin function."""

    def test_loads_component_and_handlers(self):
        """load_plugin should load component class and find handlers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            # Create module
            module_dir = plugin_dir / "mymodule"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "component.py").write_text(
                textwrap.dedent("""
                    from astrbot_sdk import Star, on_command

                    class MyComponent(Star):
                        @on_command("hello")
                        async def hello_handler(self):
                            pass
                """),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "mymodule.component:MyComponent"}],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            # Add plugin dir to sys.path for import
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            try:
                loaded = load_plugin(spec)

                assert loaded.plugin.name == "test_plugin"
                assert len(loaded.instances) == 1
                assert len(loaded.handlers) >= 1
            finally:
                if str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))
                for module_name in list(sys.modules):
                    if module_name == "mymodule" or module_name.startswith("mymodule."):
                        sys.modules.pop(module_name, None)

    def test_preserves_legacy_handler_declaration_order(self):
        """load_plugin should keep legacy handler order instead of sorting by dir()."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            commands_dir = plugin_dir / "commands"
            commands_dir.mkdir()
            (commands_dir / "__init__.py").write_text("", encoding="utf-8")
            (commands_dir / "component.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot_sdk.api.components.command import CommandComponent
                    from astrbot_sdk.api.event import AstrMessageEvent, filter
                    from astrbot_sdk.api.event.filter import EventMessageType
                    from astrbot_sdk.api.star.context import Context


                    class OrderedCommand(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context

                        @filter.command("hello")
                        async def hello(self, event: AstrMessageEvent):
                            yield event.plain_result("hello")

                        @filter.regex(r"^ping.*")
                        async def ping(self, event: AstrMessageEvent):
                            yield event.plain_result("ping")

                        @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
                        async def group_only(self, event: AstrMessageEvent):
                            yield event.plain_result("group")
                    """
                ),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "ordered_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "commands.component:OrderedCommand"}],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)
            try:
                loaded = load_plugin(spec)

                trigger_order = [
                    getattr(handler.descriptor.trigger, "command", None)
                    or getattr(handler.descriptor.trigger, "regex", None)
                    or ",".join(
                        getattr(handler.descriptor.trigger, "message_types", ())
                    )
                    for handler in loaded.handlers
                ]

                assert trigger_order[:3] == ["hello", r"^ping.*", "group"]
            finally:
                plugin_path = str(plugin_dir)
                if plugin_path in sys.path:
                    sys.path.remove(plugin_path)
                for module_name in list(sys.modules):
                    if module_name == "commands" or module_name.startswith("commands."):
                        sys.modules.pop(module_name, None)

    def test_loads_component_capabilities(self):
        """load_plugin should discover plugin-provided capabilities separately from handlers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            module_dir = plugin_dir / "capmodule"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "component.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot_sdk import Star, provide_capability


                    class MyComponent(Star):
                        @provide_capability(
                            "demo.echo",
                            description="Echo text",
                            input_schema={
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                            },
                            output_schema={
                                "type": "object",
                                "properties": {"echo": {"type": "string"}},
                            },
                        )
                        async def echo(self, payload):
                            return {"echo": payload["text"]}
                    """
                ),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "cap_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "capmodule.component:MyComponent"}],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            try:
                loaded = load_plugin(spec)
                assert [item.descriptor.name for item in loaded.capabilities] == [
                    "demo.echo"
                ]
                assert len(loaded.handlers) == 0
            finally:
                if str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))

    def test_ignores_non_handler_descriptors_without_triggering_properties(self):
        """load_plugin should not access unrelated properties during handler discovery."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            module_dir = plugin_dir / "mymodule"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "component.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot_sdk import Star, on_command


                    class MyComponent(Star):
                        @property
                        def explode(self):
                            raise RuntimeError("property should not be touched")

                        @on_command("hello")
                        async def hello_handler(self):
                            pass
                    """
                ),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "safe_loader_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [{"class": "mymodule.component:MyComponent"}],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            try:
                loaded = load_plugin(spec)
                assert len(loaded.instances) == 1
                assert [handler.descriptor.id for handler in loaded.handlers]
            finally:
                if str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))

    @pytest.mark.asyncio
    async def test_load_plugin_shares_legacy_context_between_components(self):
        """Legacy components in one plugin should share the same LegacyContext."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "test_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"
            module_dir = plugin_dir / "legacy_pkg"
            module_dir.mkdir()
            (module_dir / "__init__.py").write_text("", encoding="utf-8")
            (module_dir / "components.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot_sdk.api.components.command import CommandComponent
                    from astrbot_sdk.api.star.context import Context


                    class FirstComponent(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context
                            context._register_component(self)

                        def echo(self, text: str) -> str:
                            return f"first:{text}"


                    class SecondComponent(CommandComponent):
                        def __init__(self, context: Context):
                            self.context = context
                    """
                ),
                encoding="utf-8",
            )

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [
                            {"class": "legacy_pkg.components:FirstComponent"},
                            {"class": "legacy_pkg.components:SecondComponent"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            spec = load_plugin_spec(plugin_dir)

            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            try:
                loaded = load_plugin(spec)

                assert len(loaded.instances) == 2
                assert loaded.instances[0].context is loaded.instances[1].context
                result = await loaded.instances[1].context.call_context_function(
                    "FirstComponent.echo",
                    {"text": "hi"},
                )
                assert result == {"data": "first:hi"}
            finally:
                if str(plugin_dir) in sys.path:
                    sys.path.remove(str(plugin_dir))

    def test_load_plugin_supports_legacy_main_and_config_schema(self):
        """load_plugin should auto-discover main.py legacy stars and inject config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "legacy_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "main.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot_sdk.api.event import AstrMessageEvent, filter
                    from astrbot_sdk.api.star import Context, Star


                    class LegacyPlugin(Star):
                        def __init__(self, context: Context, config):
                            super().__init__(context, config)

                        @filter.command("hello")
                        async def hello(self, event: AstrMessageEvent):
                            yield event.plain_result(self.config["token"])
                    """
                ),
                encoding="utf-8",
            )
            (plugin_dir / "metadata.yaml").write_text(
                yaml.dump({"name": "legacy_plugin", "version": "1.0.0"}),
                encoding="utf-8",
            )
            (plugin_dir / "_conf_schema.json").write_text(
                json.dumps(
                    {
                        "token": {
                            "type": "string",
                            "default": "demo-token",
                        },
                        "nested": {
                            "type": "object",
                            "items": {
                                "enabled": {
                                    "type": "bool",
                                    "default": True,
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            spec = load_plugin_spec(plugin_dir)
            loaded = load_plugin(spec)

            assert len(loaded.instances) == 1
            instance = loaded.instances[0]
            assert instance.context.plugin_id == "legacy_plugin"
            assert instance.config["token"] == "demo-token"
            assert instance.config["nested"] == {"enabled": True}

            config_path = plugin_dir / "data" / "config" / "legacy_plugin_config.json"
            assert config_path.exists()

            instance.config["token"] = "changed"
            instance.config.save_config()
            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            assert persisted["token"] == "changed"

    def test_load_plugin_supports_legacy_astrbot_imports_relative_modules_and_groups(
        self,
    ):
        """load_plugin should support real legacy package imports and command groups."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir) / "legacy_plugin"
            plugin_dir.mkdir()
            (plugin_dir / "src").mkdir()
            (plugin_dir / "src" / "helper.py").write_text(
                'HELP_TEXT = "legacy-ok"\n',
                encoding="utf-8",
            )
            (plugin_dir / "main.py").write_text(
                textwrap.dedent(
                    """\
                    from astrbot.api.event import MessageChain, AstrMessageEvent, filter
                    from astrbot.api.star import Context, Star, StarTools, register
                    from astrbot.api import AstrBotConfig, logger

                    from .src.helper import HELP_TEXT


                    @register("legacy_alias_demo", "tester", "demo", "1.0.0")
                    class LegacyPlugin(Star):
                        def __init__(self, context: Context, config: AstrBotConfig):
                            super().__init__(context, config)
                            self.data_dir = str(StarTools.get_data_dir())
                            logger.info(HELP_TEXT)

                        @filter.command("hello")
                        async def hello(self, event: AstrMessageEvent):
                            yield event.plain_result(HELP_TEXT)

                        @filter.command_group("ccl")
                        def ccl(self):
                            pass

                        @ccl.command("子命令")
                        async def sub(self, event: AstrMessageEvent):
                            yield MessageChain().message("sub")
                    """
                ),
                encoding="utf-8",
            )
            (plugin_dir / "metadata.yaml").write_text(
                yaml.dump({"name": "legacy_alias_demo", "version": "1.0.0"}),
                encoding="utf-8",
            )

            spec = load_plugin_spec(plugin_dir)
            loaded = load_plugin(spec)

            assert len(loaded.instances) == 1
            instance = loaded.instances[0]
            assert Path(instance.data_dir) == plugin_dir / "data"

            commands = [
                handler.descriptor.trigger.command
                for handler in loaded.handlers
                if isinstance(handler.descriptor.trigger, CommandTrigger)
            ]
            assert commands == ["hello", "ccl 子命令"]


class TestStateFileConstant:
    """Tests for STATE_FILE_NAME constant."""

    def test_value(self):
        """STATE_FILE_NAME should be correct."""
        assert STATE_FILE_NAME == ".astrbot-worker-state.json"
