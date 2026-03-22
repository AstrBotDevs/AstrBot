# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install("jieba", {"cut": lambda text, *_a, **_k: text.split()})
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})
    install(
        "aiocqhttp",
        {
            "CQHttp": type("CQHttp", (), {}),
            "Event": type("Event", (), {}),
        },
    )
    install(
        "aiocqhttp.exceptions",
        {"ActionFailed": type("ActionFailed", (Exception,), {})},
    )


_install_optional_dependency_stubs()

from astrbot_sdk.clients.mcp import MCPServerRecord
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.runtime.loader import PluginSpec

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge
from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from tests.test_sdk.unit._mcp_contract import exercise_local_mcp_contract


class _FakeFunctionToolManager:
    def __init__(self) -> None:
        self.func_list: list[object] = []
        self._config = {"mcpServers": {}}
        self.mcp_server_runtime_view: dict[str, object] = {}

    def load_mcp_config(self) -> dict[str, object]:
        return json.loads(json.dumps(self._config))

    def save_mcp_config(self, config: dict[str, object]) -> bool:
        self._config = json.loads(json.dumps(config))
        return True

    async def enable_mcp_server(
        self,
        name: str,
        config: dict[str, object],
        *_,
        **__,
    ) -> None:
        tools = [
            SimpleNamespace(name=str(tool_name))
            for tool_name in config.get("mock_tools", [f"{name}_tool"])
        ]
        self.mcp_server_runtime_view[name] = SimpleNamespace(
            client=SimpleNamespace(tools=tools, server_errlogs=[]),
        )

    async def disable_mcp_server(self, name: str | None = None, **_kwargs) -> None:
        if name is None:
            self.mcp_server_runtime_view.clear()
            return
        self.mcp_server_runtime_view.pop(name, None)


class _FakeCorePluginBridge:
    def __init__(self, *, acknowledge_global_mcp_risk: bool = False) -> None:
        self._acknowledge_global_mcp_risk = acknowledge_global_mcp_risk
        self._local_servers = {
            "sdk-demo": {
                "demo": {
                    "name": "demo",
                    "scope": "local",
                    "active": True,
                    "running": True,
                    "config": {"mock_tools": ["lookup"]},
                    "tools": ["lookup"],
                    "errlogs": [],
                    "last_error": None,
                }
            }
        }
        self._temporary_sessions: dict[str, dict[str, object]] = {}

    def resolve_request_plugin_id(self, _request_id: str) -> str:
        return "sdk-demo"

    def resolve_request_session(self, _request_id: str):
        return None

    def acknowledges_global_mcp_risk(self, plugin_id: str) -> bool:
        return plugin_id == "sdk-demo" and self._acknowledge_global_mcp_risk

    def get_local_mcp_server(self, plugin_id: str, name: str):
        return self._local_servers.get(plugin_id, {}).get(name)

    def list_local_mcp_servers(self, plugin_id: str):
        return list(self._local_servers.get(plugin_id, {}).values())

    async def enable_local_mcp_server(
        self, plugin_id: str, name: str, *, timeout: float
    ):
        server = dict(self._local_servers[plugin_id][name])
        if float(server["config"].get("mock_connect_delay", 0.0)) > timeout:
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        server["active"] = True
        server["running"] = True
        self._local_servers[plugin_id][name] = server
        return server

    async def disable_local_mcp_server(self, plugin_id: str, name: str):
        server = dict(self._local_servers[plugin_id][name])
        server["active"] = False
        server["running"] = False
        self._local_servers[plugin_id][name] = server
        return server

    async def wait_for_local_mcp_server(
        self, plugin_id: str, name: str, *, timeout: float
    ):
        server = self._local_servers[plugin_id][name]
        delay = float(server["config"].get("mock_connect_delay", 0.0))
        if delay > timeout:
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        server = dict(server)
        server["running"] = True
        self._local_servers[plugin_id][name] = server
        return server

    async def open_temporary_mcp_session(
        self,
        plugin_id: str,
        *,
        name: str,
        config: dict[str, object],
        timeout: float,
    ) -> tuple[str, list[str]]:
        delay = float(config.get("mock_connect_delay", 0.0))
        if delay > timeout:
            raise TimeoutError(f"MCP session '{name}' failed to connect in time")
        session_id = f"{plugin_id}:session-1"
        tools = [str(item) for item in config.get("mock_tools", [f"{name}_tool"])]
        self._temporary_sessions[session_id] = {
            "plugin_id": plugin_id,
            "name": name,
            "tools": tools,
            "results": dict(config.get("mock_tool_results", {})),
        }
        return session_id, tools

    def get_temporary_mcp_session_tools(
        self, plugin_id: str, session_id: str
    ) -> list[str]:
        session = self._temporary_sessions.get(session_id)
        if session is None or session["plugin_id"] != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        return list(session["tools"])

    async def call_temporary_mcp_tool(
        self,
        plugin_id: str,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        session = self._temporary_sessions.get(session_id)
        if session is None or session["plugin_id"] != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        result = session["results"].get(tool_name)
        if isinstance(result, dict):
            return dict(result)
        return {"content": f"mock:{tool_name}", "arguments": dict(arguments)}

    async def close_temporary_mcp_session(
        self, plugin_id: str, session_id: str
    ) -> None:
        session = self._temporary_sessions.get(session_id)
        if session is None or session["plugin_id"] != plugin_id:
            return
        self._temporary_sessions.pop(session_id, None)

    async def execute_local_mcp_tool(
        self,
        plugin_id: str,
        *,
        server_name: str,
        tool_name: str,
        tool_args: dict[str, object],
        timeout_seconds: int = 60,
    ) -> dict[str, object]:
        return {
            "content": f"{plugin_id}:{server_name}:{tool_name}:{timeout_seconds}:{tool_args}",
            "success": True,
        }

    def get_request_tool_specs(self, plugin_id: str) -> list[LLMToolSpec]:
        server = self._local_servers[plugin_id]["demo"]
        return [
            LLMToolSpec.create(
                name=f"mcp.{server['name']}.lookup",
                description="demo lookup",
                parameters_schema={"type": "object", "properties": {}},
                handler_ref='{"server_name":"demo","tool_name":"lookup"}',
                handler_capability="internal.mcp.local.execute",
            )
        ]


class _CoreMCPBackend:
    def __init__(self, bridge: CoreCapabilityBridge) -> None:
        self._bridge = bridge

    async def get_server(self, name: str):
        output = await self._bridge._mcp_local_get("req-local", {"name": name}, None)
        return MCPServerRecord.from_payload(output["server"])

    async def list_servers(self):
        output = await self._bridge._mcp_local_list("req-local", {}, None)
        return [
            record
            for record in (
                MCPServerRecord.from_payload(item) for item in output["servers"]
            )
            if record is not None
        ]

    async def enable_server(self, name: str):
        output = await self._bridge._mcp_local_enable(
            "req-local",
            {"name": name, "timeout": 0.2},
            None,
        )
        return MCPServerRecord.from_payload(output["server"])

    async def disable_server(self, name: str):
        output = await self._bridge._mcp_local_disable(
            "req-local", {"name": name}, None
        )
        return MCPServerRecord.from_payload(output["server"])

    async def wait_until_ready(self, name: str, *, timeout: float):
        output = await self._bridge._mcp_local_wait_until_ready(
            "req-local",
            {"name": name, "timeout": timeout},
            None,
        )
        return MCPServerRecord.from_payload(output["server"])


def _build_core_bridge(
    *,
    acknowledge_global_mcp_risk: bool = False,
    func_tool_manager: _FakeFunctionToolManager | None = None,
    plugin_bridge: _FakeCorePluginBridge | None = None,
) -> CoreCapabilityBridge:
    tool_manager = func_tool_manager or _FakeFunctionToolManager()
    return CoreCapabilityBridge(
        star_context=SimpleNamespace(
            get_llm_tool_manager=lambda: tool_manager,
            persona_manager=object(),
            conversation_manager=object(),
            kb_manager=object(),
            get_all_stars=lambda: [],
        ),
        plugin_bridge=plugin_bridge
        or _FakeCorePluginBridge(
            acknowledge_global_mcp_risk=acknowledge_global_mcp_risk
        ),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_local_mcp_contract() -> None:
    bridge = _build_core_bridge()
    await exercise_local_mcp_contract(_CoreMCPBackend(bridge))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_mcp_session_round_trip() -> None:
    bridge = _build_core_bridge()

    opened = await bridge._mcp_session_open(
        "req-local",
        {
            "name": "adhoc",
            "config": {
                "mock_tools": ["inspect"],
                "mock_tool_results": {"inspect": {"ok": True}},
            },
            "timeout": 0.2,
        },
        None,
    )
    session_id = opened["session_id"]
    assert opened["tools"] == ["inspect"]

    listed = await bridge._mcp_session_list_tools(
        "req-local",
        {"session_id": session_id},
        None,
    )
    assert listed["tools"] == ["inspect"]

    called = await bridge._mcp_session_call_tool(
        "req-local",
        {
            "session_id": session_id,
            "tool_name": "inspect",
            "args": {"q": "hello"},
        },
        None,
    )
    assert called["result"] == {"ok": True}

    closed = await bridge._mcp_session_close(
        "req-local",
        {"session_id": session_id},
        None,
    )
    assert closed == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_global_mcp_requires_ack_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    func_tool_manager = _FakeFunctionToolManager()
    bridge = _build_core_bridge(
        acknowledge_global_mcp_risk=False,
        func_tool_manager=func_tool_manager,
    )

    with pytest.raises(PermissionError):
        await bridge._mcp_global_register(
            "req-local",
            {
                "name": "global-demo",
                "config": {"mock_tools": ["inspect"]},
                "timeout": 0.2,
            },
            None,
        )
    with pytest.raises(PermissionError):
        await bridge._mcp_global_list("req-local", {}, None)
    with pytest.raises(PermissionError):
        await bridge._mcp_global_get("req-local", {"name": "global-demo"}, None)

    bridge = _build_core_bridge(
        acknowledge_global_mcp_risk=True,
        func_tool_manager=func_tool_manager,
    )
    actions: list[dict[str, str]] = []
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.mcp.logger.info",
        lambda _message, payload: actions.append(dict(payload)),
    )

    registered = await bridge._mcp_global_register(
        "req-local",
        {
            "name": "global-demo",
            "config": {"mock_tools": ["inspect"]},
            "timeout": 0.2,
        },
        None,
    )
    assert registered["server"]["running"] is True
    listed = await bridge._mcp_global_list("req-local", {}, None)
    assert [item["name"] for item in listed["servers"]] == ["global-demo"]
    fetched = await bridge._mcp_global_get(
        "req-local",
        {"name": "global-demo"},
        None,
    )
    assert fetched["server"]["name"] == "global-demo"

    disabled = await bridge._mcp_global_disable(
        "req-local",
        {"name": "global-demo"},
        None,
    )
    assert disabled["server"]["active"] is False

    enabled = await bridge._mcp_global_enable(
        "req-local",
        {"name": "global-demo", "timeout": 0.2},
        None,
    )
    assert enabled["server"]["running"] is True

    removed = await bridge._mcp_global_unregister(
        "req-local",
        {"name": "global-demo"},
        None,
    )
    assert removed["server"]["name"] == "global-demo"
    assert [item["action"] for item in actions] == [
        "register",
        "disable",
        "enable",
        "unregister",
    ]


class _FakeWorkerSession:
    bridge: SdkPluginBridge | None = None

    def __init__(self, *, plugin: PluginSpec, on_closed=None, **_kwargs) -> None:
        self.plugin = plugin
        self.on_closed = on_closed
        self.handlers = []
        self.llm_tools = []
        self.agents = []
        self.issues = []
        self.peer = None
        self._start_assertions: list[bool] = []

    async def start(self) -> None:
        bridge = self.__class__.bridge
        if bridge is not None:
            record = bridge._records[self.plugin.name]
            self._start_assertions.append(
                all(
                    not runtime.running for runtime in record.local_mcp_servers.values()
                )
            )
        else:
            self._start_assertions.append(True)
        self.peer = SimpleNamespace(
            remote_metadata={"acknowledge_global_mcp_risk": False}
        )

    def start_close_watch(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FakeMCPClient:
    created: list[_FakeMCPClient] = []

    def __init__(self) -> None:
        self.name: str | None = None
        self.tools = [
            SimpleNamespace(
                name="lookup",
                description="Lookup item",
                inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
        ]
        self.server_errlogs: list[str] = []
        self.process_pid = 4242
        self.cleaned = False
        _FakeMCPClient.created.append(self)

    async def connect_to_server(self, _config: dict[str, object], _name: str) -> None:
        return None

    async def list_tools_and_save(self):
        return SimpleNamespace(tools=self.tools)

    async def cleanup(self) -> None:
        self.cleaned = True

    async def call_tool_with_reconnect(
        self, tool_name: str, arguments: dict[str, object], **_kwargs
    ):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"{tool_name}:{arguments}")],
            isError=False,
        )


def _plugin_spec(plugin_dir: Path, *, name: str = "sdk-demo") -> PluginSpec:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plugin_dir / "plugin.yaml"
    manifest_path.write_text(
        "name: sdk-demo\nauthor: tester\ndesc: demo\nversion: 0.1.0\nruntime:\n  python: '3.11'\ncomponents: []\n",
        encoding="utf-8",
    )
    requirements_path = plugin_dir / "requirements.txt"
    requirements_path.write_text("", encoding="utf-8")
    return PluginSpec(
        name=name,
        plugin_dir=plugin_dir,
        manifest_path=manifest_path,
        requirements_path=requirements_path,
        python_version="3.11",
        manifest_data={
            "name": name,
            "display_name": name,
            "author": "tester",
            "desc": "demo",
            "version": "0.1.0",
        },
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_plugin_bridge_loads_mcp_json_and_keeps_local_tools_plugin_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    plugin_data_root = data_root / "plugin_data"
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_plugin_data_path",
        lambda: str(plugin_data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.WorkerSession", _FakeWorkerSession
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.MCPClient", _FakeMCPClient
    )

    func_tool_manager = _FakeFunctionToolManager()
    bridge = SdkPluginBridge(
        SimpleNamespace(
            get_llm_tool_manager=lambda: func_tool_manager,
            get_all_stars=lambda: [],
        )
    )
    _FakeWorkerSession.bridge = bridge
    bridge._publish_plugin_skills = lambda _plugin_id: None
    bridge._persist_state_overrides = lambda: None

    async def _noop_register_schedule(_record) -> None:
        return None

    bridge._register_schedule_handlers = _noop_register_schedule

    plugin_a = _plugin_spec(tmp_path / "plugin-a", name="plugin-a")
    plugin_b = _plugin_spec(tmp_path / "plugin-b", name="plugin-b")
    (plugin_a.plugin_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"alpha": {"command": "uvx", "args": ["alpha"]}}}),
        encoding="utf-8",
    )
    (plugin_b.plugin_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"beta": {"command": "uvx", "args": ["beta"]}}}),
        encoding="utf-8",
    )

    await bridge._load_or_reload_plugin(
        plugin_a, load_order=0, reset_restart_budget=True
    )
    await bridge._load_or_reload_plugin(
        plugin_b, load_order=1, reset_restart_budget=True
    )

    record_a = bridge._records["plugin-a"]
    record_b = bridge._records["plugin-b"]
    assert record_a.session._start_assertions == [True]
    assert record_b.session._start_assertions == [True]
    assert record_a.local_mcp_servers["alpha"].running is True
    assert record_b.local_mcp_servers["beta"].running is True
    assert [item.name for item in bridge.get_request_tool_specs("plugin-a")] == [
        "mcp.alpha.lookup"
    ]
    assert [item.name for item in bridge.get_request_tool_specs("plugin-b")] == [
        "mcp.beta.lookup"
    ]
    assert func_tool_manager.func_list == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_plugin_bridge_worker_close_cleans_local_mcp_runtimes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeMCPClient.created.clear()
    data_root = tmp_path / "data"
    plugin_data_root = data_root / "plugin_data"
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_plugin_data_path",
        lambda: str(plugin_data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.WorkerSession", _FakeWorkerSession
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.MCPClient", _FakeMCPClient
    )

    bridge = SdkPluginBridge(
        SimpleNamespace(
            get_llm_tool_manager=lambda: _FakeFunctionToolManager(),
            get_all_stars=lambda: [],
        )
    )
    _FakeWorkerSession.bridge = bridge
    bridge._publish_plugin_skills = lambda _plugin_id: None
    bridge._persist_state_overrides = lambda: None

    async def _noop_register_schedule(_record) -> None:
        return None

    bridge._register_schedule_handlers = _noop_register_schedule

    plugin = _plugin_spec(tmp_path / "plugin-demo", name="plugin-demo")
    (plugin.plugin_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"demo": {"command": "uvx", "args": ["demo"]}}}),
        encoding="utf-8",
    )

    await bridge._load_or_reload_plugin(plugin, load_order=0, reset_restart_budget=True)
    bridge._records["plugin-demo"].restart_attempted = True
    await bridge._handle_worker_closed("plugin-demo")

    assert _FakeMCPClient.created
    assert all(client.cleaned for client in _FakeMCPClient.created)
    assert bridge._records["plugin-demo"].local_mcp_servers["demo"].running is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_plugin_bridge_start_sweeps_stale_mcp_leases_before_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    plugin_data_root = data_root / "plugin_data"
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_data_path",
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.get_astrbot_plugin_data_path",
        lambda: str(plugin_data_root),
    )
    lease_dir = plugin_data_root / "demo-plugin" / ".mcp_leases"
    lease_dir.mkdir(parents=True, exist_ok=True)
    lease_path = lease_dir / "demo.json"
    lease_path.write_text(
        json.dumps({"pid": 12345, "plugin_id": "demo-plugin", "server_name": "demo"}),
        encoding="utf-8",
    )
    killed: list[int] = []
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.os.kill",
        lambda pid, _sig: killed.append(pid),
    )

    bridge = SdkPluginBridge(
        SimpleNamespace(
            get_llm_tool_manager=lambda: _FakeFunctionToolManager(),
            get_all_stars=lambda: [],
        )
    )
    bridge._persist_state_overrides = lambda: None

    async def _fake_reload_all(*, reset_restart_budget: bool) -> None:
        assert reset_restart_budget is True

    bridge.reload_all = _fake_reload_all

    await bridge.start()

    assert killed == [12345]
    assert lease_path.exists() is False
