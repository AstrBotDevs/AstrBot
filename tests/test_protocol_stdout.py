from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

from click.testing import CliRunner

from astrbot_sdk import cli


class _FakeStream(io.StringIO):
    def __init__(self, *, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_resolve_protocol_stdout_defaults_to_silent_on_tty(monkeypatch) -> None:
    fake_stdout = _FakeStream(is_tty=True)
    monkeypatch.setattr("sys.stdout", fake_stdout)

    transport_stdout, opened_stdout = cli._resolve_protocol_stdout(None)

    assert opened_stdout is not None
    assert transport_stdout is opened_stdout
    assert getattr(transport_stdout, "name", None) == os.devnull
    opened_stdout.close()


def test_resolve_protocol_stdout_defaults_to_console_when_stdout_is_piped(
    monkeypatch,
) -> None:
    fake_stdout = _FakeStream(is_tty=False)
    monkeypatch.setattr("sys.stdout", fake_stdout)

    transport_stdout, opened_stdout = cli._resolve_protocol_stdout(None)

    assert transport_stdout is fake_stdout
    assert opened_stdout is None


def test_resolve_protocol_stdout_supports_file_path(
    monkeypatch, tmp_path: Path
) -> None:
    fake_stdout = _FakeStream(is_tty=True)
    output_path = tmp_path / "protocol.log"
    monkeypatch.setattr("sys.stdout", fake_stdout)

    transport_stdout, opened_stdout = cli._resolve_protocol_stdout(str(output_path))

    assert opened_stdout is not None
    assert transport_stdout is opened_stdout
    assert getattr(transport_stdout, "name", None) == str(output_path)
    opened_stdout.close()


def test_run_command_resolves_protocol_stdout_to_stream(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_supervisor(*, plugins_dir: Path, stdout=None, **_) -> None:
        captured["plugins_dir"] = plugins_dir
        captured["stdout_name"] = getattr(stdout, "name", None)

    def fake_run_async_entrypoint(entrypoint, **_) -> None:
        asyncio.run(entrypoint)

    monkeypatch.setattr(cli, "run_supervisor", fake_run_supervisor)
    monkeypatch.setattr(cli, "_run_async_entrypoint", fake_run_async_entrypoint)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["run", "--plugins-dir", str(tmp_path), "--protocol-stdout", "silent"],
    )

    assert result.exit_code == 0
    assert captured == {
        "plugins_dir": tmp_path,
        "stdout_name": os.devnull,
    }


def test_worker_command_resolves_protocol_stdout_to_stream(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    output_path = tmp_path / "worker-protocol.log"

    async def fake_run_plugin_worker(
        *,
        plugin_dir: Path | None = None,
        group_metadata: Path | None = None,
        stdout=None,
        **_,
    ) -> None:
        captured["plugin_dir"] = plugin_dir
        captured["group_metadata"] = group_metadata
        captured["stdout_name"] = getattr(stdout, "name", None)

    def fake_run_async_entrypoint(entrypoint, **_) -> None:
        asyncio.run(entrypoint)

    monkeypatch.setattr(cli, "run_plugin_worker", fake_run_plugin_worker)
    monkeypatch.setattr(cli, "_run_async_entrypoint", fake_run_async_entrypoint)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "worker",
            "--plugin-dir",
            str(plugin_dir),
            "--protocol-stdout",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "plugin_dir": plugin_dir,
        "group_metadata": None,
        "stdout_name": str(output_path),
    }
