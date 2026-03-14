from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_env() -> dict[str, str]:
    env = os.environ.copy()
    src_new = str(_repo_root() / "src-new")
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_new}{os.pathsep}{current}" if current else src_new
    return env


def test_testing_module_importable() -> None:
    from astrbot_sdk import testing

    assert testing.PluginHarness is not None
    assert testing.MockContext is not None


def test_cli_help_works_from_source_tree() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "astrbot_sdk", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_source_env(),
    )

    assert process.returncode == 0, process.stderr
    assert "Usage" in process.stdout


@pytest.mark.asyncio
async def test_plugin_harness_dispatches_sample_plugin() -> None:
    from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness

    plugin_dir = _repo_root() / "test_plugin" / "new"

    async with PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir)) as harness:
        records = await harness.dispatch_text("hello")

    assert any(record.text == "Echo: hello" for record in records)


@pytest.mark.asyncio
async def test_plugin_harness_supports_metadata_and_http_commands() -> None:
    from astrbot_sdk.testing import LocalRuntimeConfig, PluginHarness

    plugin_dir = _repo_root() / "test_plugin" / "new"

    async with PluginHarness(LocalRuntimeConfig(plugin_dir=plugin_dir)) as harness:
        plugin_records = await harness.dispatch_text("plugins")
        api_records = await harness.dispatch_text("register_api")

    assert any(
        "astrbot_plugin_v4demo" in (record.text or "") for record in plugin_records
    )
    assert any(
        "已注册 API，当前共 1 个" in (record.text or "") for record in api_records
    )
