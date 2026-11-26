from __future__ import annotations

import asyncio
import base64
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrbot.core.star.sdk_bridge.bridge import SDKPluginManager
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def _build_wheel(target_dir: Path, pkg_name: str, version: str) -> Path:
    """Create a minimal pure-Python wheel exposing ``<pkg_name>.VALUE``."""
    dist = pkg_name.replace("_", "-")
    files = {
        f"{pkg_name}/__init__.py": f"VALUE = '{pkg_name}:{version}'\n",
        f"{dist}-{version}.dist-info/METADATA": (
            f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n"
        ),
        f"{dist}-{version}.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record_lines = []
    for name, content in files.items():
        data = content.encode("utf-8")
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        record_lines.append(f"{name},sha256={digest.decode()},{len(data)}")
    record_lines.append(f"{dist}-{version}.dist-info/RECORD,,")
    files[f"{dist}-{version}.dist-info/RECORD"] = "\n".join(record_lines) + "\n"

    wheel_path = target_dir / f"{pkg_name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return wheel_path


def _write_sdk_plugin(
    root: Path,
    name: str,
    reply_expr: str,
    *,
    isolation: str | None = None,
    dependencies: dict[str, str] | None = None,
    requirements: list[str] | None = None,
    service_name: str | None = None,
    extra_imports: str = "",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    isolation_line = f"\n  isolation: {isolation}" if isolation else ""
    deps_yaml = ""
    if dependencies:
        deps_yaml = "\ndependencies:\n" + "\n".join(
            f'  {k}: "{v}"' for k, v in dependencies.items()
        )
    (root / "metadata.yaml").write_text(
        f"""
schema_version: 2
name: {name}
desc: Group worker test plugin {name}
version: 0.1.0
author: test
runtime:
  api: sdk
  entrypoint: main:PluginImpl
  sdk_version: ">=0.1.0"{isolation_line}
capabilities:
  required: []
  optional:
    - id: storage.kv
    - id: plugin.inspect{deps_yaml}
""".strip(),
        encoding="utf-8",
    )
    if requirements:
        (root / "requirements.txt").write_text(
            "\n".join(requirements) + "\n", encoding="utf-8"
        )
    svc_block = (
        f'\n    @on.service("{service_name}")\n    async def svc(self, payload: dict) -> dict:\n        return {{"svc": "{name}", "in": payload}}\n'
        if service_name
        else ""
    )
    (root / "main.py").write_text(
        f"""
from __future__ import annotations

import os
from astrbot_sdk import MessageEvent, Plugin, on
{extra_imports}


class PluginImpl(Plugin[dict]):
    @on.command("{name}_cmd")
    async def cmd(self, event: MessageEvent) -> str:
        _ = event
        return {reply_expr}
{svc_block}""".strip(),
        encoding="utf-8",
    )


def _patch_bridge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _MemGlobalSP:
        def __init__(self) -> None:
            self._data: dict[str, object] = {}

        async def global_get(self, key: str, default=None):
            return self._data.get(key, default)

        async def global_put(self, key: str, value) -> None:
            self._data[key] = value

    data_dir = tmp_path / "data"
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.venv.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: data_dir / "sdk_assets",
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge.sp",
        _MemGlobalSP(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )


async def _run_command(plugin_dir: str, cmd: str) -> list[str]:
    handler = star_handlers_registry.star_handlers_map[
        f"sdk_bridge.{plugin_dir}_{cmd}"
    ]
    event = FakeCoreEvent(cmd)
    replies: list[str] = []
    async for _ in handler.handler(event):
        if event.get_result():
            replies.append(event.get_result().chain[0].text)
        event.clear_result()
    return replies


@pytest.mark.asyncio
async def test_group_worker_shares_pid_kv_and_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bridge_env(tmp_path, monkeypatch)
    store = tmp_path / "plugins"
    _write_sdk_plugin(
        store / "peer_a",
        "peer_a",
        "(await self.ctx.storage.set('shared_key', 'from_a') or f'a:{os.getpid()}')",
        service_name="hello",
    )
    _write_sdk_plugin(
        store / "caller_b",
        "caller_b",
        "f\"b:{os.getpid()}:{(await self.ctx.plugins.call_service('peer_a', 'hello', {'v': 1}))['svc']}\"",
        dependencies={"peer_a": ">=0.1.0"},
    )
    _write_sdk_plugin(
        store / "solo_c",
        "solo_c",
        "(await self.ctx.storage.set('shared_key', 'from_c') or f'c:{os.getpid()}')",
    )

    mgr = SDKPluginManager(MagicMock(), store)
    try:
        loaded = await mgr.load_all()
        assert set(loaded) == {"peer_a", "caller_b", "solo_c"}
        pids = {bridge.runner_pid for bridge in mgr.bridges.values()}
        assert len(pids) == 1
        shared_pid = next(iter(pids))
        assert shared_pid is not None and shared_pid > 0

        assert await _run_command("peer_a", "cmd") == [f"a:{shared_pid}"]
        assert await _run_command("caller_b", "cmd") == [f"b:{shared_pid}:peer_a"]
        assert await _run_command("solo_c", "cmd") == [f"c:{shared_pid}"]

        # Per-plugin KV scopes stay isolated even when sharing the same OS PID.
        kv_service_a = mgr.bridges["peer_a"]._services["storage.kv"]
        kv_service_c = mgr.bridges["solo_c"]._services["storage.kv"]
        assert (await kv_service_a.handle("get", {"key": "shared_key"}))["value"] == "from_a"
        assert (await kv_service_c.handle("get", {"key": "shared_key"}))["value"] == "from_c"
    finally:
        await mgr.stop_all()


@pytest.mark.asyncio
async def test_shared_compatible_venvs_conflict_split_and_dedicated_opt_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bridge_env(tmp_path, monkeypatch)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    whl_a1 = _build_wheel(wheels, "dep_a", "0.1")
    whl_b1 = _build_wheel(wheels, "dep_b", "0.1")
    whl_a2 = _build_wheel(wheels, "dep_a", "0.2")

    store = tmp_path / "plugins"
    # Compatible dep plugins merge into one shared group venv & PID.
    _write_sdk_plugin(
        store / "compat_one",
        "compat_one",
        "f'{dep_a.VALUE}:{os.getpid()}'",
        requirements=[f"dep-a @ {whl_a1.as_uri()}"],
        extra_imports="import dep_a",
    )
    _write_sdk_plugin(
        store / "compat_two",
        "compat_two",
        "f'{dep_b.VALUE}:{os.getpid()}'",
        requirements=[f"dep-b @ {whl_b1.as_uri()}"],
        extra_imports="import dep_b",
    )
    # Conflicting dep_a==0.2 splits into a second group venv & PID.
    _write_sdk_plugin(
        store / "conflict_three",
        "conflict_three",
        "f'{dep_a.VALUE}:{os.getpid()}'",
        requirements=[f"dep-a @ {whl_a2.as_uri()}"],
        extra_imports="import dep_a",
    )
    # Zero-dep plugin with isolation: dedicated gets its own dedicated PID.
    _write_sdk_plugin(
        store / "dedicated_four",
        "dedicated_four",
        "f'ded:{os.getpid()}'",
        isolation="dedicated",
    )

    mgr = SDKPluginManager(MagicMock(), store)
    try:
        loaded = await mgr.load_all()
        assert set(loaded) == {
            "compat_one",
            "compat_two",
            "conflict_three",
            "dedicated_four",
        }
        pid_c1 = mgr.bridges["compat_one"].runner_pid
        pid_c2 = mgr.bridges["compat_two"].runner_pid
        pid_conf = mgr.bridges["conflict_three"].runner_pid
        pid_ded = mgr.bridges["dedicated_four"].runner_pid

        assert pid_c1 == pid_c2
        assert pid_conf != pid_c1
        assert pid_ded not in {pid_c1, pid_conf}

        assert await _run_command("compat_one", "cmd") == [f"dep_a:0.1:{pid_c1}"]
        assert await _run_command("compat_two", "cmd") == [f"dep_b:0.1:{pid_c1}"]
        assert await _run_command("conflict_three", "cmd") == [
            f"dep_a:0.2:{pid_conf}"
        ]
        assert await _run_command("dedicated_four", "cmd") == [f"ded:{pid_ded}"]
    finally:
        await mgr.stop_all()


@pytest.mark.asyncio
async def test_group_worker_unload_reload_and_crash_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bridge_env(tmp_path, monkeypatch)
    from astrbot.core.star.sdk_bridge import supervisor as sup_mod

    orig_init = sup_mod.GroupRunnerSupervisor.__init__

    def _fast_init(self, plugin_root, **kwargs):
        kwargs.setdefault(
            "timing",
            sup_mod.SupervisorTiming(base_backoff=0.05, max_backoff=0.1),
        )
        orig_init(self, plugin_root, **kwargs)

    monkeypatch.setattr(sup_mod.GroupRunnerSupervisor, "__init__", _fast_init)

    store = tmp_path / "plugins"
    _write_sdk_plugin(store / "p_alpha", "p_alpha", "'alpha-v1'")
    _write_sdk_plugin(store / "p_beta", "p_beta", "'beta-v1'")

    mgr = SDKPluginManager(MagicMock(), store)
    try:
        await mgr.load_all()
        pid0 = mgr.bridges["p_alpha"].runner_pid
        assert pid0 is not None and pid0 == mgr.bridges["p_beta"].runner_pid

        # Unload p_alpha, edit on disk, and reload it onto the same worker PID.
        await mgr.unload("p_alpha")
        assert await _run_command("p_beta", "cmd") == ["beta-v1"]
        _write_sdk_plugin(store / "p_alpha", "p_alpha", "'alpha-v2-reloaded'")
        await mgr.load_all(specified_dir_name="p_alpha")
        assert mgr.bridges["p_alpha"].runner_pid == pid0
        assert await _run_command("p_alpha", "cmd") == ["alpha-v2-reloaded"]

        # Kill the shared Group Worker; both plugins recover onto ONE new PID.
        mgr.bridges["p_alpha"]._require_client().kill_process()
        for _ in range(80):
            await asyncio.sleep(0.05)
            p_a = mgr.bridges["p_alpha"].runner_pid
            p_b = mgr.bridges["p_beta"].runner_pid
            if p_a and p_b and p_a == p_b and p_a != pid0:
                c_a = getattr(mgr.bridges["p_alpha"]._supervisor, "_client", None)
                c_b = getattr(mgr.bridges["p_beta"]._supervisor, "_client", None)
                if c_a and c_b and c_a.is_running and c_b.is_running:
                    break
        new_pid_a = mgr.bridges["p_alpha"].runner_pid
        new_pid_b = mgr.bridges["p_beta"].runner_pid
        assert new_pid_a is not None and new_pid_a != pid0
        assert new_pid_a == new_pid_b
        assert await _run_command("p_alpha", "cmd") == ["alpha-v2-reloaded"]
        assert await _run_command("p_beta", "cmd") == ["beta-v1"]

        # Unloading all plugins tears down all pooled workers (0 idle processes).
        await mgr.unload("p_alpha")
        assert len(mgr.worker_pool._entries) == 1
        await mgr.unload("p_beta")
        assert len(mgr.worker_pool._entries) == 0
    finally:
        await mgr.stop_all()
