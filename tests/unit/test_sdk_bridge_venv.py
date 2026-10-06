from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.venv import (
    ensure_plugin_venv,
    resolve_dependency_source,
)
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


async def _empty_snapshot(_context):
    """Stub out the legacy host-state snapshot for MagicMock contexts."""
    return {}


def fabricate_wheel(target_dir: Path) -> Path:
    """Build a tiny offline wheel exposing fake_legacy_dep.VALUE = 42."""
    files = {
        "fake_legacy_dep/__init__.py": "VALUE = 42\n",
        "fake_legacy_dep-0.1.dist-info/METADATA": (
            "Metadata-Version: 2.1\nName: fake-legacy-dep\nVersion: 0.1\n"
        ),
        "fake_legacy_dep-0.1.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record_lines = []
    for name, content in files.items():
        data = content.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        record_lines.append(f"{name},sha256={digest.decode()},{len(data)}")
    record_lines.append("fake_legacy_dep-0.1.dist-info/RECORD,,")
    files["fake_legacy_dep-0.1.dist-info/RECORD"] = "\n".join(record_lines) + "\n"

    wheel_path = target_dir / "fake_legacy_dep-0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return wheel_path


def test_resolve_dependency_source(tmp_path: Path) -> None:
    plugin = tmp_path / "p1"
    plugin.mkdir()
    assert resolve_dependency_source(plugin) is None

    (plugin / "requirements.txt").write_text("aiohttp\n", "utf-8")
    assert resolve_dependency_source(plugin) == plugin / "requirements.txt"

    (plugin / "pyproject.toml").write_text(
        '[project]\nname = "p1"\nversion = "0.1"\ndependencies = ["aiohttp"]\n',
        "utf-8",
    )
    assert resolve_dependency_source(plugin) == plugin / "pyproject.toml"

    (plugin / "pyproject.toml").write_text(
        '[project]\nname = "p1"\nversion = "0.1"\ndynamic = ["dependencies"]\n',
        "utf-8",
    )
    with pytest.raises(ValueError, match="dynamic dependencies"):
        resolve_dependency_source(plugin)


@pytest.mark.asyncio
async def test_venv_installs_declared_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = fabricate_wheel(tmp_path)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.venv.get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )

    plugin = tmp_path / "dep_plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text(f"{wheel}\n", "utf-8")

    python = await ensure_plugin_venv(plugin, MagicMock())
    assert python is not None and python.is_file()

    process = await asyncio.create_subprocess_exec(
        str(python),
        "-c",
        "import fake_legacy_dep; print(fake_legacy_dep.VALUE)",
        stdout=asyncio.subprocess.PIPE,
    )
    output, _ = await process.communicate()
    assert output.decode().strip() == "42"
    # The core environment itself stays clean.
    assert not any(
        (Path(sys.prefix) / "lib").glob("*/site-packages/fake_legacy_dep"),
    )

    # Second call with a matching fingerprint skips reinstallation (the
    # wheel file being gone would otherwise fail the install).
    wheel.unlink()
    python_again = await ensure_plugin_venv(plugin, MagicMock())
    assert python_again == python


@pytest.mark.asyncio
async def test_venv_pyproject_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = fabricate_wheel(tmp_path)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.venv.get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )

    plugin = tmp_path / "pyproject_plugin"
    plugin.mkdir()
    (plugin / "pyproject.toml").write_text(
        '[project]\nname = "pyproject-plugin"\nversion = "0.1"\n'
        f'dependencies = ["fake-legacy-dep @ file://{wheel}"]\n',
        "utf-8",
    )

    python = await ensure_plugin_venv(plugin, MagicMock())
    assert python is not None
    marker = json.loads(
        (
            tmp_path
            / "data"
            / "plugin_venvs"
            / "pyproject_plugin"
            / ".astrbot-deps.json"
        ).read_text(
            "utf-8",
        ),
    )
    assert marker["source"] == "pyproject.toml"


def write_isolated_legacy_dep_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "legacy_dep_e2e",
                "desc": "venv e2e plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {"isolated": True},
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from fake_legacy_dep import VALUE


class LegacyDepPlugin(Star):
    @filter.command("depvalue")
    async def depvalue(self, event: AstrMessageEvent):
        yield event.plain_result(f"value={VALUE}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_runs_legacy_plugin_in_its_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = fabricate_wheel(tmp_path)
    plugin_root = tmp_path / "legacy_dep_e2e"
    write_isolated_legacy_dep_plugin(plugin_root)
    (plugin_root / "requirements.txt").write_text(f"{wheel}\n", "utf-8")

    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.venv.get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge.build_legacy_snapshot",
        _empty_snapshot,
    )
    context = MagicMock()
    bridge = SDKPluginBridge(plugin_root, context, legacy=True)
    full_name = f"sdk_bridge.{plugin_root.name}_depvalue"
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[full_name]
        event = FakeCoreEvent("depvalue")
        replies = []
        async for _ in handler.handler(event):
            if event.get_result():
                replies.append(event.get_result().chain[0].text)
            event.clear_result()
        assert replies == ["value=42"]
    finally:
        await bridge.stop()

    assert full_name not in star_handlers_registry.star_handlers_map
