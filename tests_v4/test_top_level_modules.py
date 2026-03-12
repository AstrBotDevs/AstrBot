"""
Tests for first-layer modules under astrbot_sdk.
"""

from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import astrbot_sdk
import astrbot_sdk.compat as compat_module
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
from astrbot_sdk.star import Star

TOP_LEVEL_MODULES = [
    "astrbot_sdk",
    "astrbot_sdk._legacy_api",
    "astrbot_sdk.cli",
    "astrbot_sdk.compat",
    "astrbot_sdk.context",
    "astrbot_sdk.decorators",
    "astrbot_sdk.errors",
    "astrbot_sdk.events",
    "astrbot_sdk.star",
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
