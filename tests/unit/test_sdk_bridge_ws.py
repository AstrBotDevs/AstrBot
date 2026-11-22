"""External plugin Runners over WebSocket: token routing and redial restart."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest
import websockets
from astrbot_sdk.capabilities import CapabilitySet
from astrbot_sdk.runtime.env import runner_env
from astrbot_sdk.runtime.ws_runner import RUNNER_TOKEN_ENV

from astrbot.core.star.sdk_bridge.supervisor import (
    ExternalRunnerSupervisor,
    SupervisorTiming,
)
from astrbot.core.star.sdk_bridge.ws_listener import ExternalRunnerListener
from tests.unit.test_sdk_bridge_supervisor import (
    make_event,
    no_capabilities,
    wait_for_client,
    write_legacy_plugin,
)


async def spawn_ws_runner(plugin_root: Path, url: str, token: str):
    """Spawn one legacy Runner process dialed into the test listener."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "astrbot_sdk.runtime",
        "--ws",
        url,
        "--legacy",
        "--plugin-root",
        str(plugin_root),
        env=runner_env({RUNNER_TOKEN_ENV: token}),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


@pytest.mark.asyncio
async def test_listener_routes_connections_by_token() -> None:
    listener = ExternalRunnerListener("127.0.0.1", 0)
    await listener.start()
    url = f"ws://127.0.0.1:{listener.port}"
    try:
        claims_a = listener.register("token-a")
        listener.register("token-b")
        with pytest.raises(ValueError, match="duplicate"):
            listener.register("token-a")

        # Unknown tokens are rejected during the HTTP upgrade.
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(
                url,
                additional_headers={"Authorization": "Bearer nope"},
                proxy=None,
            ):
                pass
        assert exc_info.value.response.status_code == 401

        # A registered token connects and lands in its own claim queue.
        async with websockets.connect(
            url,
            additional_headers={"Authorization": "Bearer token-a"},
            proxy=None,
        ):
            transport = await asyncio.wait_for(claims_a.get(), timeout=5)
            assert not transport.closed
        # The owner observes the peer's close without running a read loop.
        await asyncio.wait_for(transport.wait_closed(), timeout=5)
        assert transport.closed

        # After unregister the same token is rejected again.
        listener.unregister("token-a")
        with pytest.raises(websockets.exceptions.InvalidStatus):
            async with websockets.connect(
                url,
                additional_headers={"Authorization": "Bearer token-a"},
                proxy=None,
            ):
                pass
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_external_supervisor_waits_for_redial(tmp_path: Path) -> None:
    plugin_root = tmp_path / "ext_legacy"
    write_legacy_plugin(
        plugin_root,
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class ExtPlugin(Star):
    @filter.command("ok")
    async def ok(self, event: AstrMessageEvent):
        yield event.plain_result("fine")
""",
    )
    listener = ExternalRunnerListener("127.0.0.1", 0)
    await listener.start()
    url = f"ws://127.0.0.1:{listener.port}"
    claims = listener.register("token-1")
    supervisor = ExternalRunnerSupervisor(
        "ext_legacy",
        claims=claims,
        legacy=True,
        grants=CapabilitySet.from_ids("storage.kv", "assets.transfer", "message.send"),
        config=None,
        capability_handler=no_capabilities,
        logger=logging.getLogger("test.external_supervisor"),
        timing=SupervisorTiming(base_backoff=0.05, max_backoff=0.1),
    )
    process = await spawn_ws_runner(plugin_root, url, "token-1")
    try:
        handshake = await supervisor.start()
        assert handshake.name == "ext_legacy"
        first_client = supervisor.require_client()
        results = [r async for r in first_client.invoke("ok", make_event())]
        assert [r.message.text for r in results if r is not None] == ["fine"]

        # The runner dies; instead of respawning, the supervisor backs off
        # and waits for the operator's runner to dial back in.
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)
        process = await spawn_ws_runner(plugin_root, url, "token-1")
        await wait_for_client(supervisor, old_client=first_client)
        restarted = supervisor.require_client()
        assert restarted is not first_client
        results = [r async for r in restarted.invoke("ok", make_event())]
        assert [r.message.text for r in results if r is not None] == ["fine"]
    finally:
        await supervisor.stop()
        await listener.stop()
        if process.returncode is None:
            process.terminate()
            await process.wait()


@pytest.mark.asyncio
async def test_external_ws_parity_dependencies_config_views_and_platform_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify external WS specs support dependencies, inline config_schema, views, and get_client()."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from astrbot_sdk.errors import CapabilityDenied

    from astrbot.core.chatui import ViewSpec
    from astrbot.core.star.sdk_bridge import SDKPluginBridge
    from astrbot.core.star.sdk_bridge.services.platform import PlatformRawService
    from astrbot.core.star.sdk_bridge.services.plugin_service_router import (
        PluginServiceRouter,
    )
    from astrbot.core.star.star import star_map
    from tests.unit.test_sdk_bridge import FakeKVStore

    monkeypatch.setattr(
        "astrbot.core.utils.astrbot_path.get_astrbot_config_path",
        lambda: str(tmp_path / "cfg"),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)

    # 1. PlatformRawService falls back to adapter.get_client() when adapter.bot is None.
    class _ClientOnlyAdapter:
        bot = None

        def meta(self):
            return SimpleNamespace(id="qq_main", name="aiocqhttp")

        def get_client(self):
            class _Api:
                async def call_action(self, action: str, **params):
                    return {"action": action, "params": params}

            return _Api()

    ctx_stub = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[_ClientOnlyAdapter()]),
        _star_map={},
        get_all_stars=lambda: [],
    )
    raw_svc = PlatformRawService(ctx_stub)  # type: ignore[arg-type]
    raw_res = await raw_svc.handle(
        "call_action",
        {"platform_id": "qq_main", "action": "get_group_list", "params": {"no_cache": True}},
    )
    assert raw_res == {
        "result": {"action": "get_group_list", "params": {"no_cache": True}}
    }

    # 2. PluginServiceRouter authorizes external specs declaring dependencies.
    async def _target_invoke(service: str, payload):
        return {"svc": service, "in": dict(payload)}

    target_bridge = SimpleNamespace(
        plugin_id="peer_svc",
        plugin_name="peer_svc",
        root_dir_name="peer_svc",
        invoke_service=_target_invoke,
    )
    caller_bridge = SimpleNamespace(
        plugin_id="ext_caller",
        manifest_metadata=None,
        _external={"plugin_id": "ext_caller", "dependencies": {"peer_svc": ">=0.1.0"}},
    )
    router = PluginServiceRouter()
    router.register(target_bridge)
    routed = await router.route(caller_bridge, "peer_svc", "ping", {"x": 1})
    assert routed == {"svc": "ping", "in": {"x": 1}}
    with pytest.raises(CapabilityDenied):
        await router.route(caller_bridge, "undeclared_svc", "ping", {})

    # 3. External WS SdkPluginBridge preserves inline config_schema, views, and support_platforms.
    plugin_root = tmp_path / "ext_sdk_ws"
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "metadata.yaml").write_text(
        """
schema_version: 2
name: ext_sdk_ws
desc: External WS SDK plugin
version: 0.1.0
author: test
views:
  - name: panel
    title: Panel
runtime:
  api: sdk
  entrypoint: main:ExtSdkPlugin
  sdk_version: ">=0.1.0"
capabilities:
  required: []
  optional: []
""".strip(),
        encoding="utf-8",
    )
    (plugin_root / "views" / "panel").mkdir(parents=True, exist_ok=True)
    (plugin_root / "views" / "panel" / "index.html").write_text(
        "<h1>Panel</h1>", encoding="utf-8"
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, PluginConfig, on


class Cfg(PluginConfig):
    greeting: str = "hi"


class ExtSdkPlugin(Plugin[Cfg]):
    config_model = Cfg

    @on.command("greet")
    async def greet(self, event: MessageEvent) -> str:
        _ = event
        return self.ctx.config.greeting
""".strip(),
        encoding="utf-8",
    )

    listener = ExternalRunnerListener("127.0.0.1", 0)
    await listener.start()
    url = f"ws://127.0.0.1:{listener.port}"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "astrbot_sdk.runtime",
        "--ws",
        url,
        "--plugin-root",
        str(plugin_root),
        env=runner_env({RUNNER_TOKEN_ENV: "tok-ext-sdk"}),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    bridge_ctx = MagicMock()
    bridge_ctx.registered_web_apis = []
    bridge = SDKPluginBridge(
        tmp_path / "ext_sdk_ws_pseudo",
        bridge_ctx,
        legacy=False,
        external={
            "plugin_id": "test/ext_sdk_ws",
            "token": "tok-ext-sdk",
            "capabilities": [],
            "views": [{"name": "panel", "title": "Panel"}],
            "support_platforms": ["aiocqhttp"],
            "config_schema": {
                "type": "object",
                "properties": {"greeting": {"type": "string", "default": "hi"}},
            },
            "config": {"greeting": "hello-ws"},
        },
        listener=listener,
    )
    try:
        await bridge.start()
        md = star_map[bridge.module_path]
        assert md.support_platforms == ["aiocqhttp"]
        assert bridge._json_schema is not None
        assert bridge._plugin_config is not None
        assert bridge._plugin_config["greeting"] == "hello-ws"
        assert md.views == [ViewSpec(name="panel", title="Panel")]
    finally:
        await bridge.stop()
        await listener.stop()
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
