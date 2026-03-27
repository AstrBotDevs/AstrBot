# ruff: noqa: E402
from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

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
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot_sdk.clients.mcp import MCPManagerClient
from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.capability_dispatcher import CapabilityDispatcher
from astrbot_sdk.runtime.loader import (
    load_plugin,
    load_plugin_spec,
    validate_plugin_spec,
)
from astrbot_sdk.runtime.supervisor import SupervisorRuntime

from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


class _DummyTransport:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, payload: str) -> None:
        del payload


class _BridgeBackedCapabilitySession:
    def __init__(self, runtime, plugin_dir: Path) -> None:
        plugin = load_plugin_spec(plugin_dir)
        validate_plugin_spec(plugin)
        self.plugin = plugin
        self.loaded_plugin = load_plugin(plugin)
        self.dispatcher = CapabilityDispatcher(
            plugin_id=plugin.name,
            peer=runtime.peer,
            capabilities=self.loaded_plugin.capabilities,
            llm_tools=self.loaded_plugin.llm_tools,
        )
        self.provided_capabilities = [
            item.descriptor.model_copy(deep=True)
            for item in self.loaded_plugin.capabilities
        ]
        self.capability_sources = {
            item.descriptor.name: plugin.name
            for item in self.loaded_plugin.capabilities
        }

    async def invoke_capability(
        self,
        capability_name: str,
        payload: dict[str, object],
        *,
        request_id: str,
    ) -> dict[str, object]:
        result = await self.dispatcher.invoke(
            InvokeMessage(
                id=request_id,
                capability=capability_name,
                input=dict(payload),
                stream=False,
            ),
            CancelToken(),
        )
        assert isinstance(result, dict)
        return result


def _fixture_plugin_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "sdk_plugins"
        / "dynamic_registration_probe"
    )


def _materialize_probe_plugin(
    tmp_path: Path,
    *,
    plugin_name: str,
    acknowledge_global_mcp_risk: bool = True,
) -> Path:
    plugin_dir = tmp_path / plugin_name
    shutil.copytree(_fixture_plugin_dir(), plugin_dir)
    plugin_yaml = plugin_dir / "plugin.yaml"
    plugin_yaml.write_text(
        plugin_yaml.read_text(encoding="utf-8").replace(
            "name: dynamic_registration_probe",
            f"name: {plugin_name}",
            1,
        ),
        encoding="utf-8",
    )
    main_py = plugin_dir / "main.py"
    main_py.write_text(
        main_py.read_text(encoding="utf-8").replace(
            '"dynamic_registration_probe.',
            f'"{plugin_name}.',
        ),
        encoding="utf-8",
    )
    if not acknowledge_global_mcp_risk:
        main_py.write_text(
            main_py.read_text(encoding="utf-8").replace(
                "@acknowledge_global_mcp_risk\n",
                "",
                1,
            ),
            encoding="utf-8",
        )
    return plugin_dir


def _plugin_capability_name(plugin_name: str, suffix: str) -> str:
    return f"{plugin_name}.{suffix}"


def _register_plugin_session(runtime, supervisor: SupervisorRuntime, session) -> None:
    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": session.plugin.name,
            "display_name": session.plugin.name,
            "description": "dynamic registration probe",
            "acknowledge_global_mcp_risk": any(
                bool(
                    getattr(
                        instance.__class__,
                        "__astrbot_acknowledge_global_mcp_risk__",
                        False,
                    )
                )
                for instance in session.loaded_plugin.instances
            ),
        }
    )
    for descriptor in session.provided_capabilities:
        supervisor._register_plugin_capability(  # noqa: SLF001
            descriptor,
            session,
            session.plugin.name,
        )


async def _execute_plugin_capability(
    supervisor: SupervisorRuntime,
    capability_name: str,
    payload: dict[str, object],
    *,
    request_id: str,
) -> dict[str, object]:
    result = await supervisor.capability_router.execute(
        capability_name,
        dict(payload),
        stream=False,
        cancel_token=CancelToken(),
        request_id=request_id,
    )
    assert isinstance(result, dict)
    return result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dynamic_skill_registration_round_trips_through_plugin_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    registered = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.register"),
        {
            "name": "dynamic_probe.runtime_probe",
            "description": "Runtime probe skill",
        },
        request_id="core-register-skill",
    )
    listed = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.list"),
        {},
        request_id="core-list-skill",
    )

    expected_skill_dir = plugin_dir / "skills" / "runtime_probe"
    expected_skill_path = expected_skill_dir / "SKILL.md"

    assert registered == {
        "name": "dynamic_probe.runtime_probe",
        "description": "Runtime probe skill",
        "path": str(expected_skill_path),
        "skill_dir": str(expected_skill_dir),
    }
    assert listed["skills"] == [registered]

    ctx = runtime.make_context(session.plugin.name)
    skills = await ctx.skills.list()
    assert len(skills) == 1
    assert skills[0].name == "dynamic_probe.runtime_probe"
    assert Path(skills[0].path) == expected_skill_path
    assert Path(skills[0].skill_dir) == expected_skill_dir


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dynamic_skill_unregister_and_plugin_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.register"),
        {"name": "dynamic_probe.runtime_probe"},
        request_id="core-register-skill",
    )

    owner_ctx = runtime.make_context(session.plugin.name)
    other_ctx = runtime.make_context("isolated-plugin")
    owner_skills = await owner_ctx.skills.list()
    other_skills = await other_ctx.skills.list()

    assert [item.name for item in owner_skills] == ["dynamic_probe.runtime_probe"]
    assert other_skills == []

    removed = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.unregister"),
        {"name": "dynamic_probe.runtime_probe"},
        request_id="core-unregister-skill",
    )
    listed_after = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.list"),
        {},
        request_id="core-list-skill-after-unregister",
    )
    removed_again = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.unregister"),
        {"name": "dynamic_probe.runtime_probe"},
        request_id="core-unregister-skill-again",
    )

    assert removed == {"removed": True}
    assert listed_after == {"skills": []}
    assert removed_again == {"removed": False}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dynamic_global_mcp_registration_lifecycle_and_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    actions: list[dict[str, str]] = []
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.mcp.logger.info",
        lambda _message, payload: actions.append(dict(payload)),
    )

    registered = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.register"),
        {
            "name": "probe-global",
            "config": {"mock_tools": ["inspect"]},
            "timeout": 0.2,
        },
        request_id="core-register-global-mcp",
    )
    fetched = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.get"),
        {"name": "probe-global"},
        request_id="core-get-global-mcp",
    )
    listed = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.list"),
        {},
        request_id="core-list-global-mcp",
    )
    disabled = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.disable"),
        {"name": "probe-global"},
        request_id="core-disable-global-mcp",
    )
    enabled = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.enable"),
        {"name": "probe-global", "timeout": 0.2},
        request_id="core-enable-global-mcp",
    )
    removed = await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.unregister"),
        {"name": "probe-global"},
        request_id="core-unregister-global-mcp",
    )

    ctx = runtime.make_context(session.plugin.name)
    assert registered["server"]["name"] == "probe-global"
    assert registered["server"]["scope"] == "global"
    assert registered["server"]["running"] is True
    assert fetched["server"]["name"] == "probe-global"
    assert [item["name"] for item in listed["servers"]] == ["probe-global"]
    assert disabled["server"]["active"] is False
    assert enabled["server"]["running"] is True
    assert removed["server"]["name"] == "probe-global"
    assert await ctx.mcp.list_global_servers() == []
    assert runtime.func_tool_manager.load_mcp_config()["mcpServers"] == {}
    assert runtime.func_tool_manager.mcp_server_runtime_view == {}
    assert [item["action"] for item in actions] == [
        "register",
        "disable",
        "enable",
        "unregister",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dynamic_global_mcp_requires_acknowledged_risk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe_noack"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
        acknowledge_global_mcp_risk=False,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    with pytest.raises(PermissionError, match="@acknowledge_global_mcp_risk"):
        await _execute_plugin_capability(
            supervisor,
            _plugin_capability_name(plugin_name, "mcp.global.register"),
            {
                "name": "probe-global",
                "config": {"mock_tools": ["inspect"]},
                "timeout": 0.2,
            },
            request_id="core-register-global-mcp",
        )

    assert runtime.func_tool_manager.load_mcp_config()["mcpServers"] == {}
    assert runtime.func_tool_manager.mcp_server_runtime_view == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plugin_teardown_clears_dynamic_skill_and_leaves_no_global_mcp_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "skill.register"),
        {"name": "dynamic_probe.runtime_probe"},
        request_id="core-register-skill",
    )
    await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.register"),
        {
            "name": "probe-global",
            "config": {"mock_tools": ["inspect"]},
            "timeout": 0.2,
        },
        request_id="core-register-global-mcp",
    )
    await _execute_plugin_capability(
        supervisor,
        _plugin_capability_name(plugin_name, "mcp.global.unregister"),
        {"name": "probe-global"},
        request_id="core-unregister-global-mcp",
    )

    runtime.plugin_bridge.remove_plugin(session.plugin.name)

    remaining_skills = await runtime.make_context(session.plugin.name).skills.list()
    assert remaining_skills == []
    assert runtime.func_tool_manager.load_mcp_config()["mcpServers"] == {}
    assert runtime.func_tool_manager.mcp_server_runtime_view == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_local_mcp_dynamic_registration_is_currently_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    descriptor_names = {descriptor.name for descriptor in runtime.bridge.descriptors()}

    assert hasattr(MCPManagerClient, "register_local_server") is False
    assert hasattr(MCPManagerClient, "unregister_local_server") is False
    assert "mcp.local.register" not in descriptor_names
    assert "mcp.local.unregister" not in descriptor_names
    assert hasattr(SdkPluginBridge, "register_local_mcp_server") is False
    assert hasattr(SdkPluginBridge, "unregister_local_mcp_server") is False
    assert hasattr(SdkPluginBridge, "enable_local_mcp_server") is True
    assert hasattr(SdkPluginBridge, "disable_local_mcp_server") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plugin_provided_capability_descriptors_do_not_hot_register_after_handshake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_name = "dynamic_registration_probe"
    plugin_dir = _materialize_probe_plugin(
        tmp_path,
        plugin_name=plugin_name,
    )
    session = _BridgeBackedCapabilitySession(runtime, plugin_dir)
    supervisor = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=object(),  # type: ignore[arg-type]
    )
    _register_plugin_session(runtime, supervisor, session)

    descriptor_names = {
        item.name for item in supervisor.capability_router.descriptors()
    }
    assert _plugin_capability_name(plugin_name, "skill.register") in descriptor_names

    session.provided_capabilities.append(
        session.provided_capabilities[0].model_copy(
            update={"name": _plugin_capability_name(plugin_name, "skill.hot_added")}
        )
    )
    session.capability_sources[
        _plugin_capability_name(plugin_name, "skill.hot_added")
    ] = session.plugin.name

    descriptor_names_after_mutation = {
        item.name for item in supervisor.capability_router.descriptors()
    }
    assert (
        _plugin_capability_name(plugin_name, "skill.hot_added")
        not in descriptor_names_after_mutation
    )

    with pytest.raises(
        AstrBotError,
        match=_plugin_capability_name(plugin_name, "skill.hot_added"),
    ):
        await _execute_plugin_capability(
            supervisor,
            _plugin_capability_name(plugin_name, "skill.hot_added"),
            {},
            request_id="core-execute-hot-added-capability",
        )
