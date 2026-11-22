"""Tests for scoped context retirement, live capability approval, dynamic tool discovery, UDS attach, and native Rust workers."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

import astrbot.core.message.components as core_comp
from astrbot.core.platform.message_type import MessageType as CoreMessageType
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.sdk_bridge.bridge import SDKPluginBridge, SDKPluginManager
from astrbot.core.star.sdk_bridge.uds_listener import ExternalUDSListener
from astrbot.core.star.star_handler import star_handlers_registry


class FakeKVStore:
    """In-memory plugin KV store test double."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str, str], object] = {}

    async def put_async(self, scope: str, plugin_id: str, key: str, value: object):
        self.data[(scope, plugin_id, key)] = value

    async def get_async(
        self,
        scope: str,
        plugin_id: str,
        key: str,
        default: object = None,
    ):
        return self.data.get((scope, plugin_id, key), default)

    async def remove_async(self, scope: str, plugin_id: str, key: str):
        self.data.pop((scope, plugin_id, key), None)


class FakeCoreEvent:
    """Minimal event double for invoking SDK bridge handlers."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.unified_msg_origin = "webchat:FriendMessage:user-1"
        self.platform_meta = SimpleNamespace(name="webchat", id="webchat")
        self.session_id = "user-1"
        self._extras: dict = {}
        self._result = None
        self._stopped = False
        self._has_send_oper = False
        self.role = "member"
        self.is_wake = True
        self.is_at_or_wake_command = True
        self.plugins_name = None
        self.message_str = text
        self.trace = MagicMock()
        self.message_obj = SimpleNamespace(
            message_id="m-1",
            self_id="bot-1",
            session_id="user-1",
            group_id="",
            sender=SimpleNamespace(user_id="user-1", nickname="Moon"),
            message=[core_comp.Plain(text)],
            timestamp=1700000000,
            raw_message=None,
        )

    def get_platform_name(self):
        return "webchat"

    def get_platform_id(self):
        return "webchat"

    def get_message_type(self):
        return CoreMessageType(self.unified_msg_origin.split(":", 2)[1])

    def get_messages(self):
        return [core_comp.Plain(self._text)]

    def get_message_str(self):
        return self._text

    def get_sender_id(self):
        return "user-1"

    def get_sender_name(self):
        return "Moon"

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_result(self, result):
        self._result = result

    def get_result(self):
        return self._result

    def clear_result(self):
        self._result = None

    def stop_event(self):
        self._stopped = True

    def is_stopped(self):
        return self._stopped


def _setup_sandbox_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    plugins_dir = tmp_path / "plugins"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_config_path",
        lambda: str(cfg_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    return plugins_dir


@pytest.mark.asyncio
async def test_scoped_invocation_context_retires_on_handler_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leaked InvocationContext must raise CallScopeRetired after handler exit."""
    plugins_dir = _setup_sandbox_paths(tmp_path, monkeypatch)
    plugin_dir = plugins_dir / "leak_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "test/leak_plugin",
                "name": "leak_plugin",
                "desc": "scope test",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:LeakPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": [{"id": "storage.kv"}]},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        """
import asyncio
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.errors import CallScopeRetired


class LeakPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self._gate = asyncio.Event()
        self._task = None

    @on.command("leak")
    async def leak(self, event: MessageEvent):
        captured = self.ctx

        async def _late():
            await self._gate.wait()
            try:
                await captured.storage.get("k")
                return "NO_ERROR"
            except CallScopeRetired as exc:
                return exc.code

        self._task = asyncio.create_task(_late())
        yield event.reply("scheduled")

    @on.command("check_leak")
    async def check_leak(self, event: MessageEvent):
        self._gate.set()
        assert self._task is not None
        code = await self._task
        yield event.reply(code)
""".strip(),
        encoding="utf-8",
    )

    manager = SDKPluginManager(MagicMock(), plugins_dir)
    try:
        assert await manager.load_all() == ["leak_plugin"]

        leak_h = star_handlers_registry.star_handlers_map["sdk_bridge.leak_plugin_leak"]
        ev1 = FakeCoreEvent("leak")
        out1 = []
        async for _ in leak_h.handler(ev1):
            if ev1.get_result():
                out1.append(ev1.get_result().chain[0].text)
            ev1.clear_result()
        assert out1 == ["scheduled"]

        check_h = star_handlers_registry.star_handlers_map[
            "sdk_bridge.leak_plugin_check_leak"
        ]
        ev2 = FakeCoreEvent("check_leak")
        out2 = []
        async for _ in check_h.handler(ev2):
            if ev2.get_result():
                out2.append(ev2.get_result().chain[0].text)
            ev2.clear_result()
        assert out2 == ["CALL_SCOPE_RETIRED"]
    finally:
        await manager.stop_all()


@pytest.mark.asyncio
async def test_capability_approval_store_and_live_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host approval intersection denies unapproved optional caps until update_capabilities grants them live."""
    plugins_dir = _setup_sandbox_paths(tmp_path, monkeypatch)
    plugin_dir = plugins_dir / "cap_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "test/cap_plugin",
                "name": "cap_plugin",
                "desc": "capability governance test",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:CapPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [{"id": "message.send"}],
                    "optional": [{"id": "storage.kv"}],
                },
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.errors import CapabilityDenied


class CapPlugin(Plugin):
    @on.command("probe")
    async def probe(self, event: MessageEvent):
        try:
            val = await self.ctx.storage.get("k", "empty")
            yield event.reply(f"OK:{val}")
        except CapabilityDenied:
            yield event.reply("DENIED")
""".strip(),
        encoding="utf-8",
    )

    manager = SDKPluginManager(MagicMock(), plugins_dir)
    await manager.approval_store.set_approved("astrbot/cap_plugin", ["message.send"])
    try:
        assert await manager.load_all() == ["cap_plugin"]
        bridge = manager.bridges["cap_plugin"]
        pid = bridge.runner_pid
        assert pid is not None

        h = star_handlers_registry.star_handlers_map["sdk_bridge.cap_plugin_probe"]
        ev1 = FakeCoreEvent("probe")
        res1 = []
        async for _ in h.handler(ev1):
            if ev1.get_result():
                res1.append(ev1.get_result().chain[0].text)
            ev1.clear_result()
        assert res1 == ["DENIED"]

        await bridge.update_capabilities(["message.send", "storage.kv"])
        assert bridge.runner_pid == pid

        ev2 = FakeCoreEvent("probe")
        res2 = []
        async for _ in h.handler(ev2):
            if ev2.get_result():
                res2.append(ev2.get_result().chain[0].text)
            ev2.clear_result()
        assert res2 == ["OK:empty"]
    finally:
        await manager.stop_all()


@pytest.mark.asyncio
async def test_tool_discovery_sync_and_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_discovered_tools registers @on.tool_discovery catalogs and replaces old entries on refresh."""
    plugins_dir = _setup_sandbox_paths(tmp_path, monkeypatch)
    plugin_dir = plugins_dir / "dyn_tools"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "test/dyn_tools",
                "name": "dyn_tools",
                "desc": "tool discovery test",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:DynPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": []},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.tools import ToolDefinition


class DynPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self._tool_name = "dyn_alpha"

    @on.command("bump")
    async def bump(self, event: MessageEvent):
        self._tool_name = "dyn_beta"
        yield event.reply("bumped")

    @on.tool_discovery
    async def discover(self) -> list[ToolDefinition]:
        async def _dyn(call, item: str = "x"):
            return f"{self._tool_name}:{item}"

        self.ctx._register_dynamic_tool(f"tool:{self._tool_name}", _dyn)
        return [
            ToolDefinition(name=self._tool_name, description="Dynamic tool")
        ]
""".strip(),
        encoding="utf-8",
    )

    manager = SDKPluginManager(MagicMock(), plugins_dir)
    try:
        assert await manager.load_all() == ["dyn_tools"]
        bridge = manager.bridges["dyn_tools"]
        assert llm_tools.get_func("dyn_alpha") is not None
        assert llm_tools.get_func("dyn_alpha").handler_module_path == bridge.module_path

        bump_h = star_handlers_registry.star_handlers_map["sdk_bridge.dyn_tools_bump"]
        ev = FakeCoreEvent("bump")
        async for _ in bump_h.handler(ev):
            ev.clear_result()

        refreshed = await bridge.sync_discovered_tools()
        assert refreshed == ["dyn_beta"]
        assert llm_tools.get_func("dyn_alpha") is None
        assert llm_tools.get_func("dyn_beta") is not None
    finally:
        await manager.stop_all()

    assert llm_tools.get_func("dyn_beta") is None


@pytest.mark.asyncio
async def test_external_uds_listener_enrolls_and_detaches_without_killing_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External UDS worker connects with 0600 credentials and bridge.stop() does not SIGKILL its OS process."""
    _setup_sandbox_paths(tmp_path, monkeypatch)
    plugin_dir = tmp_path / "ext_uds_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "ext/uds_test",
                "name": "ext_uds_plugin",
                "desc": "UDS external worker test",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:ExtPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {"required": []},
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on


class ExtPlugin(Plugin):
    @on.command("ping")
    async def ping(self, event: MessageEvent):
        yield event.reply("pong-uds")
""".strip(),
        encoding="utf-8",
    )

    cred_dir = tmp_path / "creds"
    listener = ExternalUDSListener()
    proc: subprocess.Popen[str] | None = None
    repo_root = Path(__file__).resolve().parents[2]
    vendor_src = str(repo_root / "vendor" / "astrbot-sdk" / "src")

    await listener.start()
    bridge: SDKPluginBridge | None = None
    try:
        cred_path, queue = listener.enroll("astrbot/ext_uds_plugin", cred_dir)
        assert (cred_path.stat().st_mode & 0o777) == 0o600

        env = dict(os.environ)
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{vendor_src}:{existing_pp}" if existing_pp else vendor_src
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "astrbot_sdk.runtime",
                "--uds",
                str(cred_path),
                "--plugin-root",
                str(plugin_dir),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        bridge = SDKPluginBridge(
            plugin_dir,
            MagicMock(),
            external={
                "plugin_id": "astrbot/ext_uds_plugin",
                "name": "ext_uds_plugin",
                "capabilities": [],
                "config": {},
            },
            external_queue=queue,
            revoke_external=lambda: listener.revoke("astrbot/ext_uds_plugin"),
        )
        await asyncio.wait_for(bridge.start(), timeout=10.0)
        assert bridge.runner_pid is None

        ping_h = star_handlers_registry.star_handlers_map[
            "sdk_bridge.ext_uds_plugin_ping"
        ]
        ev = FakeCoreEvent("ping")
        outputs = []
        async for _ in ping_h.handler(ev):
            if ev.get_result():
                outputs.append(ev.get_result().chain[0].text)
            ev.clear_result()
        assert outputs == ["pong-uds"]

        await bridge.stop(reason="disabled")
        assert not cred_path.exists()
        assert proc.wait(timeout=5) == 0
    finally:
        if bridge is not None:
            await bridge.stop(reason="cleanup")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        await listener.stop()


@pytest.mark.asyncio
async def test_external_uds_listener_sanitizes_credential_filename(
    tmp_path: Path,
) -> None:
    """Credential enrollment confines filenames inside credential_dir with 0600 mode."""
    cred_dir = tmp_path / "creds"
    listener = ExternalUDSListener()
    try:
        cred_path, _queue = listener.enroll("../../escape\\id", cred_dir)
        assert cred_path.resolve().parent == cred_dir.resolve()
        if os.name == "posix":
            assert (cred_path.stat().st_mode & 0o777) == 0o600
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_native_rust_worker_plugin_json_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host loads compiled Rust Worker binary via plugin.json and runs command, tool, service, and live configure."""
    repo_root = Path(__file__).resolve().parents[2]
    rust_bin = (
        repo_root
        / ".worktrees"
        / "astrbot-sdk"
        / "target"
        / "debug"
        / "examples"
        / "rust_echo"
    )
    if not rust_bin.is_file():
        pytest.skip(f"compiled rust_echo binary not present at {rust_bin}")

    plugins_dir = _setup_sandbox_paths(tmp_path, monkeypatch)
    plugin_dir = plugins_dir / "rust_echo"
    bin_dir = plugin_dir / "bin"
    bin_dir.mkdir(parents=True)
    target_bin = bin_dir / "rust_echo"
    shutil.copy2(rust_bin, target_bin)
    target_bin.chmod(0o755)

    example_dir = repo_root / ".worktrees" / "astrbot-sdk" / "examples" / "rust_echo"
    shutil.copy2(example_dir / "plugin.json", plugin_dir / "plugin.json")
    shutil.copy2(
        example_dir / "config.schema.json",
        plugin_dir / "config.schema.json",
    )

    manager = SDKPluginManager(MagicMock(), plugins_dir)
    try:
        loaded = await manager.load_all()
        assert loaded == ["rust_echo"]
        bridge = manager.bridges["rust_echo"]
        initial_pid = bridge.runner_pid
        assert initial_pid is not None and initial_pid > 0

        # Live configure preserves native worker PID.
        await bridge.configure({"prefix": "[rs] "})
        assert bridge.runner_pid == initial_pid

        # Service invocation works natively.
        svc_res = await bridge.invoke_service("echo", {"text": "world"})
        assert svc_res == {"echo": "[rs] world"}

        # Registered tool executes in native worker.
        tool = llm_tools.get_func("rust_echo")
        assert tool is not None
        assert tool.handler is not None
        tool_res = await tool.handler(FakeCoreEvent("tool"), text="hi")
        assert tool_res == {"text": "[rs] hi"}

        # Registered command executes in native worker.
        cmd_h = star_handlers_registry.star_handlers_map[
            "sdk_bridge.rust_echo_command:echo"
        ]
        ev = FakeCoreEvent("echo hello")
        outputs = []
        async for _ in cmd_h.handler(ev):
            if ev.get_result():
                outputs.append(ev.get_result().chain[0].text)
            ev.clear_result()
        assert outputs == ["[rs] echo"]
    finally:
        await manager.stop_all()
