"""
Tests for first-layer modules under astrbot_sdk.
"""

from __future__ import annotations

import importlib
import runpy
import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import astrbot_sdk
import astrbot_sdk.compat as compat_module
import astrbot_sdk.runtime as runtime_module
import pytest
from click.testing import CliRunner

from astrbot_sdk._legacy_api import (
    CommandComponent,
    LegacyContext,
    LegacyConversationManager,
)
from astrbot_sdk.cli import cli, setup_logger
from astrbot_sdk.context import Context
from astrbot_sdk.decorators import on_command
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.runtime.capability_router import CapabilityRouter, StreamExecution
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.peer import Peer
from astrbot_sdk.runtime.transport import (
    MessageHandler,
    StdioTransport,
    Transport,
    WebSocketClientTransport,
    WebSocketServerTransport,
)
from astrbot_sdk.star import Star
from astrbot_sdk.testing import _PluginLoadError

REPO_ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_MODULES = [
    "astrbot_sdk",
    "astrbot_sdk._legacy_api",
    "astrbot_sdk.cli",
    "astrbot_sdk.compat",
    "astrbot_sdk.context",
    "astrbot_sdk.decorators",
    "astrbot_sdk.errors",
    "astrbot_sdk.events",
    "astrbot_sdk.runtime",
    "astrbot_sdk.star",
    "astrbot_sdk.testing",
]


class TestTopLevelImports:
    """Tests for package first-layer module imports and exports."""

    @pytest.mark.parametrize("module_name", TOP_LEVEL_MODULES)
    def test_first_layer_modules_are_importable(self, module_name: str):
        """All first-layer modules should be importable directly."""
        assert importlib.import_module(module_name) is not None

    def test_package_reexports_expected_symbols(self):
        """astrbot_sdk package should re-export the public API surface."""
        assert astrbot_sdk.AstrBotError is AstrBotError
        assert astrbot_sdk.Context is Context
        assert astrbot_sdk.MessageEvent is MessageEvent
        assert astrbot_sdk.Star is Star
        assert astrbot_sdk.on_command is not None
        assert astrbot_sdk.on_event is not None
        assert astrbot_sdk.on_message is not None
        assert astrbot_sdk.on_schedule is not None
        assert astrbot_sdk.provide_capability is not None
        assert astrbot_sdk.require_admin is not None

    def test_package_all_matches_public_exports(self):
        """astrbot_sdk.__all__ should stay aligned with top-level exports."""
        assert astrbot_sdk.__all__ == [
            "AstrBotError",
            "Context",
            "MessageEvent",
            "Star",
            "on_command",
            "on_event",
            "on_message",
            "on_schedule",
            "provide_capability",
            "require_admin",
        ]

    def test_compat_module_reexports_legacy_symbols(self):
        """compat module should proxy legacy compatibility types."""
        assert compat_module.CommandComponent is CommandComponent
        assert compat_module.Context is LegacyContext
        assert compat_module.LegacyContext is LegacyContext
        assert compat_module.LegacyConversationManager is LegacyConversationManager
        assert compat_module.__all__ == [
            "CommandComponent",
            "Context",
            "LegacyContext",
            "LegacyConversationManager",
        ]

    def test_runtime_module_reexports_advanced_runtime_primitives(self):
        """runtime module should expose only the small advanced runtime surface."""
        assert runtime_module.Peer is Peer
        assert runtime_module.CapabilityRouter is CapabilityRouter
        assert runtime_module.HandlerDispatcher is HandlerDispatcher
        assert runtime_module.Transport is Transport
        assert runtime_module.MessageHandler is MessageHandler
        assert runtime_module.StdioTransport is StdioTransport
        assert runtime_module.WebSocketClientTransport is WebSocketClientTransport
        assert runtime_module.WebSocketServerTransport is WebSocketServerTransport
        assert runtime_module.StreamExecution is StreamExecution

    def test_runtime_module_does_not_reexport_loader_or_bootstrap_details(self):
        """runtime root should not expose loader/bootstrap internals as stable API."""
        assert not hasattr(runtime_module, "PluginEnvironmentManager")
        assert not hasattr(runtime_module, "PluginWorkerRuntime")
        assert not hasattr(runtime_module, "SupervisorRuntime")
        assert not hasattr(runtime_module, "WorkerSession")
        assert not hasattr(runtime_module, "LoadedPlugin")
        assert not hasattr(runtime_module, "run_supervisor")

    def test_runtime_module_all_matches_narrow_public_surface(self):
        """runtime.__all__ should stay aligned with the narrowed advanced API."""
        assert runtime_module.__all__ == [
            "CapabilityRouter",
            "HandlerDispatcher",
            "MessageHandler",
            "Peer",
            "StdioTransport",
            "StreamExecution",
            "Transport",
            "WebSocketClientTransport",
            "WebSocketServerTransport",
        ]


class TestCliModule:
    """Tests for cli.py and __main__.py."""

    @pytest.mark.parametrize(
        ("verbose", "expected_level"),
        [
            (False, "INFO"),
            (True, "DEBUG"),
        ],
    )
    def test_setup_logger_configures_level(self, verbose: bool, expected_level: str):
        """setup_logger() should rebuild loguru handlers with the expected level."""
        mock_logger = Mock()

        with patch("astrbot_sdk.cli.logger", mock_logger):
            setup_logger(verbose=verbose)

        mock_logger.remove.assert_called_once_with()
        mock_logger.add.assert_called_once()
        assert mock_logger.add.call_args.args[0] is sys.stderr
        assert mock_logger.add.call_args.kwargs["level"] == expected_level
        assert mock_logger.add.call_args.kwargs["colorize"] is True

    def test_cli_group_sets_up_logging_from_verbose_flag(self):
        """cli group should pass the verbose flag through to setup_logger()."""
        runner = CliRunner()

        with (
            patch("astrbot_sdk.cli.setup_logger") as setup_logger_mock,
            patch("astrbot_sdk.cli.run_supervisor", new=Mock(return_value=object())),
            patch("astrbot_sdk.cli.asyncio.run"),
        ):
            result = runner.invoke(cli, ["--verbose", "run"])

        assert result.exit_code == 0
        setup_logger_mock.assert_called_once_with(True)

    @pytest.mark.parametrize(
        ("args", "target", "kwargs"),
        [
            (
                ["run", "--plugins-dir", "plugins-dev"],
                "run_supervisor",
                {"plugins_dir": Path("plugins-dev")},
            ),
            (
                ["worker", "--plugin-dir", "plugins/demo"],
                "run_plugin_worker",
                {"plugin_dir": Path("plugins/demo")},
            ),
            (
                ["websocket", "--port", "9000"],
                "run_websocket_server",
                {"port": 9000},
            ),
        ],
    )
    def test_cli_commands_delegate_to_bootstrap_functions(
        self, args, target: str, kwargs
    ):
        """Each CLI command should pass normalized arguments to its bootstrap entrypoint."""
        runner = CliRunner()
        sentinel = object()

        with (
            patch(
                f"astrbot_sdk.cli.{target}",
                new=Mock(return_value=sentinel),
            ) as entrypoint_mock,
            patch("astrbot_sdk.cli.asyncio.run") as asyncio_run_mock,
        ):
            result = runner.invoke(cli, args)

        assert result.exit_code == 0
        entrypoint_mock.assert_called_once_with(**kwargs)
        asyncio_run_mock.assert_called_once_with(sentinel)

    def test_dev_command_delegates_to_local_runtime(self):
        """dev --local should delegate to the local harness entrypoint."""
        runner = CliRunner()
        sentinel = object()

        with (
            patch(
                "astrbot_sdk.cli._run_local_dev",
                new=Mock(return_value=sentinel),
            ) as dev_mock,
            patch("astrbot_sdk.cli.asyncio.run") as asyncio_run_mock,
        ):
            result = runner.invoke(
                cli,
                [
                    "dev",
                    "--plugin-dir",
                    "test_plugin/new",
                    "--local",
                    "--event-text",
                    "hello",
                ],
            )

        assert result.exit_code == 0
        dev_mock.assert_called_once_with(
            plugin_dir=Path("test_plugin/new"),
            event_text="hello",
            interactive=False,
            session_id="local-session",
            user_id="local-user",
            platform="test",
            group_id=None,
            event_type="message",
        )
        asyncio_run_mock.assert_called_once_with(sentinel)

    def test_dev_command_requires_local_mode(self):
        """dev should reject invocations that do not opt into local mode."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            [
                "dev",
                "--plugin-dir",
                "test_plugin/new",
                "--event-text",
                "hello",
            ],
        )

        assert result.exit_code == 2
        assert "--local/--standalone" in result.output

    def test_dev_command_maps_plugin_load_errors_to_exit_code_3(self):
        """Known plugin load failures should render a friendly error and exit code 3."""
        runner = CliRunner()

        async def fail(*args, **kwargs):
            raise _PluginLoadError("missing plugin")

        with patch("astrbot_sdk.cli._run_local_dev", new=fail):
            result = runner.invoke(
                cli,
                [
                    "dev",
                    "--plugin-dir",
                    "missing-plugin",
                    "--local",
                    "--event-text",
                    "hello",
                ],
            )

        assert result.exit_code == 3
        assert "Error[plugin_load_error]" in result.output
        assert "Suggestion:" in result.output

    def test_init_command_creates_plugin_skeleton(self):
        """init should generate a loader-compatible plugin skeleton."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init", "demo-plugin"])

            plugin_dir = Path("astrbot_plugin_demo_plugin")
            manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
            main_file = (plugin_dir / "main.py").read_text(encoding="utf-8")
            test_file = (plugin_dir / "tests" / "test_plugin.py").read_text(
                encoding="utf-8"
            )

        assert result.exit_code == 0
        assert "已创建插件骨架" in result.output
        assert "name: astrbot_plugin_demo_plugin" in manifest
        assert 'display_name: "demo-plugin"' in manifest
        assert 'author: ""' in manifest
        assert 'version: "1.0.0"' in manifest
        assert 'python: "3.12"' in manifest
        assert "class AstrbotPluginDemoPlugin(Star):" in main_file
        assert "MockContext" in test_file
        assert "MockMessageEvent" in test_file

    def test_init_command_normalizes_spaces_to_underscores(self):
        """init should normalize spaces in the generated directory and manifest name."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init", "demo plugin"])

            plugin_dir = Path("astrbot_plugin_demo_plugin")
            manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
            assert plugin_dir.is_dir()

        assert result.exit_code == 0
        assert "name: astrbot_plugin_demo_plugin" in manifest
        assert 'display_name: "demo plugin"' in manifest

    def test_init_command_converts_legacy_prefix_to_underscore_prefix(self):
        """init should translate the legacy astrbot-plugin prefix to astrbot_plugin."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init", "astrbot-plugin-demo"])

            plugin_dir = Path("astrbot_plugin_demo")
            manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
            assert plugin_dir.is_dir()

        assert result.exit_code == 0
        assert "name: astrbot_plugin_demo" in manifest

    def test_init_command_enters_interactive_mode_without_name(self):
        """init without a name should prompt for plugin metadata interactively."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                ["init"],
                input="hello world\nalice\n2.3.4\n",
            )

            plugin_dir = Path("astrbot_plugin_hello_world")
            manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
            assert plugin_dir.is_dir()

        assert result.exit_code == 0
        assert "插件名字" in result.output
        assert "作者名字" in result.output
        assert "版本" in result.output
        assert "name: astrbot_plugin_hello_world" in manifest
        assert 'display_name: "hello world"' in manifest
        assert 'author: "alice"' in manifest
        assert 'version: "2.3.4"' in manifest
        assert 'python: "3.12"' in manifest

    def test_init_command_reprompts_for_empty_interactive_name(self):
        """init interactive mode should reject an empty plugin name and keep prompting."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                ["init"],
                input="\nhello world\n\n\n",
            )

            plugin_dir = Path("astrbot_plugin_hello_world")
            manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
            assert plugin_dir.is_dir()

        assert result.exit_code == 0
        assert "插件名字不能为空" in result.output
        assert 'author: ""' in manifest
        assert 'version: "1.0.0"' in manifest

    def test_validate_command_checks_real_plugin_fixture(self):
        """validate should reuse loader-based discovery against a real v4 fixture."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            [
                "validate",
                "--plugin-dir",
                str(REPO_ROOT / "test_plugin" / "new"),
            ],
        )

        assert result.exit_code == 0
        assert "校验通过：astrbot_plugin_v4demo" in result.output
        assert "handlers:" in result.output
        assert "capabilities:" in result.output

    def test_validate_command_maps_invalid_component_to_exit_code_3(self):
        """validate should fail with a friendly plugin-load error on broken manifests."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            plugin_dir = Path("broken-plugin")
            plugin_dir.mkdir()
            (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
            (plugin_dir / "plugin.yaml").write_text(
                "\n".join(
                    [
                        "name: broken_plugin",
                        "runtime:",
                        '  python: "3.12"',
                        "components:",
                        "  - class: broken",
                    ]
                ),
                encoding="utf-8",
            )

            result = runner.invoke(cli, ["validate", "--plugin-dir", str(plugin_dir)])

        assert result.exit_code == 3
        assert "Error[plugin_load_error]" in result.output
        assert "components[0].class" in result.output

    def test_build_command_creates_zip_artifact(self):
        """build should validate first and then package the plugin directory into a zip."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            init_result = runner.invoke(cli, ["init", "buildable-plugin"])
            assert init_result.exit_code == 0

            result = runner.invoke(
                cli,
                [
                    "build",
                    "--plugin-dir",
                    "astrbot_plugin_buildable_plugin",
                ],
            )

            artifact_dir = Path("astrbot_plugin_buildable_plugin") / "dist"
            artifacts = sorted(artifact_dir.glob("*.zip"))
            assert len(artifacts) == 1
            with zipfile.ZipFile(artifacts[0]) as archive:
                names = set(archive.namelist())

        assert result.exit_code == 0
        assert "构建完成：" in result.output
        assert "plugin.yaml" in names
        assert "main.py" in names
        assert "requirements.txt" in names
        assert "tests/test_plugin.py" in names

    def test_main_module_invokes_cli_entrypoint(self):
        """Running astrbot_sdk.__main__ as a script should call cli()."""
        cli_mock = Mock()

        with patch("astrbot_sdk.cli.cli", cli_mock):
            runpy.run_module("astrbot_sdk.__main__", run_name="__main__")

        cli_mock.assert_called_once_with()


class TestErrorsModule:
    """Tests for errors.py."""

    @pytest.mark.parametrize(
        ("factory", "args", "expected"),
        [
            (
                AstrBotError.cancelled,
                (),
                {
                    "code": "cancelled",
                    "message": "调用被取消",
                    "hint": "",
                    "retryable": False,
                },
            ),
            (
                AstrBotError.capability_not_found,
                ("memory.save",),
                {
                    "code": "capability_not_found",
                    "message": "未找到能力：memory.save",
                    "hint": "请确认 AstrBot Core 是否已注册该 capability",
                    "retryable": False,
                },
            ),
            (
                AstrBotError.invalid_input,
                ("bad payload",),
                {
                    "code": "invalid_input",
                    "message": "bad payload",
                    "hint": "请检查调用参数",
                    "retryable": False,
                },
            ),
        ],
    )
    def test_error_factories_build_expected_payloads(self, factory, args, expected):
        """Factory helpers should populate stable error payloads."""
        error = factory(*args)

        assert str(error) == expected["message"]
        assert error.to_payload() == expected

    def test_from_payload_applies_defaults_for_missing_fields(self):
        """from_payload() should fill in the documented fallback values."""
        error = AstrBotError.from_payload({"message": "boom", "retryable": 1})

        assert error.code == ErrorCodes.UNKNOWN_ERROR
        assert error.message == "boom"
        assert error.hint == ""
        assert error.retryable is True

    def test_error_code_constants_match_factory_outputs(self):
        """核心工厂方法应复用统一错误码常量。"""
        assert AstrBotError.cancelled().code == ErrorCodes.CANCELLED
        assert (
            AstrBotError.capability_not_found("memory.get").code
            == ErrorCodes.CAPABILITY_NOT_FOUND
        )
        assert AstrBotError.invalid_input("bad").code == ErrorCodes.INVALID_INPUT
        assert (
            AstrBotError.protocol_version_mismatch("bad").code
            == ErrorCodes.PROTOCOL_VERSION_MISMATCH
        )


class TestStarModule:
    """Tests for star.py."""

    def test_handlers_collect_across_inheritance(self):
        """Star subclasses should inherit decorated handlers from base classes."""

        class BasePlugin(Star):
            @on_command("base")
            async def base(self):
                return None

        class ChildPlugin(BasePlugin):
            @on_command("child")
            async def child(self):
                return None

        assert ChildPlugin.__handlers__ == ("base", "child")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "expected_reply"),
        [
            (
                AstrBotError(code="retryable", message="later", retryable=True),
                "请求失败，请稍后重试",
            ),
            (AstrBotError.invalid_input("bad payload"), "请检查调用参数"),
            (AstrBotError(code="plain", message="plain failure"), "plain failure"),
            (RuntimeError("boom"), "出了点问题，请联系插件作者"),
        ],
    )
    async def test_on_error_replies_with_expected_message(
        self, error, expected_reply: str
    ):
        """on_error() should translate failures into the expected user-facing reply."""
        event = AsyncMock()
        event.reply = AsyncMock()
        star = Star()

        with patch("astrbot_sdk.star.logger.error") as log_error:
            await star.on_error(error, event, ctx=None)

        event.reply.assert_awaited_once_with(expected_reply)
        log_error.assert_called_once()
