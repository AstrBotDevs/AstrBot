# ruff: noqa: E402
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from pydantic import BaseModel, Field

import astrbot_sdk.runtime.supervisor as supervisor_module
from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from astrbot_sdk._command_model import (
    parse_command_model_remainder,
    resolve_command_model_param,
)
from astrbot_sdk.cli import EXIT_RUNTIME, _run_sync_entrypoint
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.conversation import (
    ConversationClosed,
    ConversationReplaced,
    ConversationSession,
    ConversationState,
)
from astrbot_sdk.decorators import (
    ConversationMeta,
    LimiterMeta,
    admin_only,
    cooldown,
    conversation_command,
    get_handler_meta,
    group_only,
    message_types,
    on_command,
    on_event,
    on_message,
    platforms,
    priority,
    rate_limit,
    private_only,
)
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.message_components import File, Image, MediaHelper, Record
from astrbot_sdk.message_result import MessageBuilder, MessageChain
from astrbot_sdk.protocol.descriptors import (
    CapabilityDescriptor,
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTypeFilterSpec,
    Permissions,
    PlatformFilterSpec,
    ScheduleTrigger,
    SessionRef,
)
from astrbot_sdk.runtime.capability_dispatcher import CapabilityDispatcher
from astrbot_sdk.runtime.environment_groups import EnvironmentPlanResult
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.limiter import LimiterEngine
from astrbot_sdk.runtime.loader import (
    LoadedCapability,
    LoadedHandler,
    PluginDiscoveryIssue,
    PluginDiscoveryResult,
    discover_plugins,
    load_plugin,
    load_plugin_spec,
    validate_plugin_spec,
)
from astrbot_sdk.runtime.supervisor import SupervisorRuntime
from astrbot_sdk.runtime.worker import GroupWorkerRuntime
from astrbot_sdk.star import Star
from astrbot_sdk.testing import MockClock, SDKTestEnvironment


class _Peer:
    def __init__(self) -> None:
        descriptor = SimpleNamespace(supports_stream=False)
        self.remote_peer = {"name": "dummy-core"}
        self.remote_capability_map = {
            "platform.send": descriptor,
            "platform.send_chain": descriptor,
            "platform.send_by_session": descriptor,
            "system.session_waiter.register": descriptor,
            "system.session_waiter.unregister": descriptor,
        }
        self.sent_messages: list[dict[str, object]] = []
        self.waiter_ops: list[dict[str, object]] = []

    async def invoke(
        self,
        capability: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, object]:
        if stream:
            raise AssertionError("unexpected stream invoke")
        if capability == "platform.send":
            self.sent_messages.append(
                {
                    "kind": "text",
                    "session": payload.get("session"),
                    "text": payload.get("text"),
                }
            )
            return {"message_id": f"text-{len(self.sent_messages)}"}
        if capability in {"platform.send_chain", "platform.send_by_session"}:
            self.sent_messages.append(
                {
                    "kind": "chain",
                    "session": payload.get("session"),
                    "chain": payload.get("chain"),
                }
            )
            return {"message_id": f"chain-{len(self.sent_messages)}"}
        if capability in {
            "system.session_waiter.register",
            "system.session_waiter.unregister",
        }:
            self.waiter_ops.append({"capability": capability, **payload})
            return {}
        raise AssertionError(f"unexpected capability: {capability}")


def _event_payload(text: str, *, session_id: str = "demo:private:user-1") -> dict[str, object]:
    return {
        "text": text,
        "session_id": session_id,
        "user_id": "user-1",
        "group_id": None,
        "platform": "demo",
        "platform_id": "demo",
        "message_type": "private",
        "target": SessionRef(conversation_id=session_id, platform="demo").to_payload(),
    }


class _BridgeStarContext:
    def __init__(self) -> None:
        self.registered_web_apis = []
        self.cron_manager = None

    def get_all_stars(self) -> list[object]:
        return []


class _ReplyCollector:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply(self, text: str) -> None:
        self.replies.append(text)


def _write_sdk_plugin(
    plugin_dir: Path,
    *,
    name: str,
    main_source: str,
) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                'runtime:',
                '  python: "3.11"',
                "components:",
                "  - class: main:DemoPlugin",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(main_source, encoding="utf-8")
    return plugin_dir


@pytest.mark.unit
def test_decorator_alias_and_conflict_rules() -> None:
    @on_command(["echo", "repeat", "say"])
    async def echo(event: MessageEvent, ctx: Context) -> None: ...

    meta = get_handler_meta(echo)
    assert meta is not None
    assert isinstance(meta.trigger, CommandTrigger)
    assert meta.trigger.command == "echo"
    assert meta.trigger.aliases == ["repeat", "say"]

    with pytest.raises(ValueError, match="platforms"):
        @platforms("qq")
        @on_message(platforms=["wechat"])
        async def _platform_conflict(event: MessageEvent, ctx: Context) -> None: ...

    with pytest.raises(ValueError, match="消息类型约束"):
        @group_only()
        @private_only()
        async def _scope_conflict(event: MessageEvent, ctx: Context) -> None: ...

    with pytest.raises(ValueError, match="不能叠加"):
        @rate_limit(1, 60)
        @cooldown(10)
        async def _limiter_conflict(event: MessageEvent, ctx: Context) -> None: ...

    with pytest.raises(ValueError, match="只适用于 on_command/on_message"):
        @on_event("ready")
        @rate_limit(1, 60)
        async def _event_limiter_conflict(ctx: Context) -> None: ...

    @conversation_command("quiz", timeout=12, mode="reject", busy_message="busy")
    async def quiz(
        event: MessageEvent,
        conversation: ConversationSession,
        ctx: Context,
    ) -> None: ...

    conversation_meta = get_handler_meta(quiz)
    assert conversation_meta is not None
    assert conversation_meta.conversation == ConversationMeta(
        timeout=12,
        mode="reject",
        busy_message="busy",
        grace_period=1.0,
    )

    @admin_only
    @priority(7)
    @message_types("group")
    @platforms("qq", "wechat")
    @on_message(keywords=["hello"])
    async def filtered(event: MessageEvent, ctx: Context) -> None: ...

    filtered_meta = get_handler_meta(filtered)
    assert filtered_meta is not None
    assert filtered_meta.priority == 7
    assert filtered_meta.permissions == Permissions(require_admin=True)
    assert filtered_meta.filters == [
        PlatformFilterSpec(platforms=["qq", "wechat"]),
        MessageTypeFilterSpec(message_types=["group"]),
    ]


class _EchoInput(BaseModel):
    text: str = Field(description="echo text")
    times: int = Field(default=1, ge=1, le=5)
    loud: bool | None = None


async def _echo_handler(
    event: MessageEvent,
    params: _EchoInput,
    ctx: Context,
) -> None:
    for _ in range(params.times):
        await event.reply(params.text.upper() if params.loud else params.text)


@pytest.mark.unit
def test_command_model_parser_help_and_duplicates() -> None:
    model_param = resolve_command_model_param(_echo_handler)
    assert model_param is not None

    parsed = parse_command_model_remainder(
        remainder="hello --times 2 --loud",
        model_param=model_param,
        command_name="echo",
    )
    assert parsed.help_text is None
    assert parsed.model is not None
    assert parsed.model.model_dump() == {"text": "hello", "times": 2, "loud": True}

    equals_and_override = parse_command_model_remainder(
        remainder="hello 3 --text=override --no-loud",
        model_param=model_param,
        command_name="echo",
    )
    assert equals_and_override.model is not None
    assert equals_and_override.model.model_dump() == {
        "text": "override",
        "times": 3,
        "loud": False,
    }

    help_result = parse_command_model_remainder(
        remainder="--help --unknown nope",
        model_param=model_param,
        command_name="echo",
    )
    assert help_result.model is None
    assert help_result.help_text is not None
    assert "用法: /echo" in help_result.help_text

    with pytest.raises(AstrBotError, match="Duplicate field"):
        parse_command_model_remainder(
            remainder="--text a --text b",
            model_param=model_param,
            command_name="echo",
        )

    with pytest.raises(AstrBotError, match="Unknown field"):
        parse_command_model_remainder(
            remainder="--unknown nope",
            model_param=model_param,
            command_name="echo",
        )

    with pytest.raises(AstrBotError, match="Too many positional arguments"):
        parse_command_model_remainder(
            remainder="hello 2 extra",
            model_param=model_param,
            command_name="echo",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plugin_logger_watch_and_default_on_error_render_details() -> None:
    ctx = Context(peer=_Peer(), plugin_id="sdk-demo")
    watcher = ctx.logger.watch()
    bound_logger = ctx.logger.bind(
        request_id="req-1",
        handler_ref="sdk-demo:test.handle",
        session_id="demo:private:user-1",
        event_type="message",
    )

    async def _next_entry():
        return await watcher.__anext__()

    pending = asyncio.create_task(_next_entry())
    await asyncio.sleep(0)
    bound_logger.info("hello {}", "sdk")
    entry = await pending

    assert entry.plugin_id == "sdk-demo"
    assert entry.message == "hello sdk"
    assert entry.context == {
        "request_id": "req-1",
        "handler_ref": "sdk-demo:test.handle",
        "session_id": "demo:private:user-1",
        "event_type": "message",
    }

    await watcher.aclose()

    error = AstrBotError.invalid_input(
        "bad input",
        hint="fix it",
        docs_url="https://docs.astrbot.org/sdk/errors#invalid-input",
        details={"field": "name"},
    )
    event = _ReplyCollector()

    await Star().on_error(error, event, ctx)

    assert event.replies == [
        "fix it\n文档：https://docs.astrbot.org/sdk/errors#invalid-input\n详情：{\"field\": \"name\"}"
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_logger_binding_for_handler_and_capability_paths() -> None:
    peer = _Peer()
    watcher = Context(peer=peer, plugin_id="sdk-demo").logger.watch()

    class _LoggerPlugin(Star):
        async def handle(self, event: MessageEvent, ctx: Context) -> None:
            ctx.logger.info("handler log")

        async def capability(self, payload: dict[str, object], ctx: Context) -> dict[str, object]:
            ctx.logger.info("capability log")
            return {"ok": True}

    async def _next_entry():
        return await watcher.__anext__()

    owner = _LoggerPlugin()
    handler_dispatcher = HandlerDispatcher(
        plugin_id="sdk-demo",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id="sdk-demo:test.handle",
                    trigger=CommandTrigger(command="ping"),
                ),
                callable=owner.handle,
                owner=owner,
                plugin_id="sdk-demo",
            )
        ],
    )
    capability_dispatcher = CapabilityDispatcher(
        plugin_id="sdk-demo",
        peer=peer,
        capabilities=[
            LoadedCapability(
                descriptor=CapabilityDescriptor(
                    name="sdk-demo.echo",
                    description="echo",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                ),
                callable=owner.capability,
                owner=owner,
                plugin_id="sdk-demo",
            )
        ],
    )

    pending_handler = asyncio.create_task(_next_entry())
    await _invoke_handler(
        handler_dispatcher,
        handler_id="sdk-demo:test.handle",
        text="ping",
        request_id="h1",
    )
    handler_entry = await pending_handler
    assert handler_entry.context == {
        "plugin_id": "sdk-demo",
        "request_id": "h1",
        "handler_ref": "sdk-demo:test.handle",
        "session_id": "demo:private:user-1",
        "event_type": "private",
    }

    pending_capability = asyncio.create_task(_next_entry())
    await capability_dispatcher.invoke(
        SimpleNamespace(
            id="c1",
            capability="sdk-demo.echo",
            input={"session": "demo:private:user-1"},
            stream=False,
        ),
        CancelToken(),
    )
    capability_entry = await pending_capability
    assert capability_entry.context == {
        "plugin_id": "sdk-demo",
        "request_id": "c1",
        "capability": "sdk-demo.echo",
        "session_id": "demo:private:user-1",
        "event_type": "capability",
    }

    await watcher.aclose()


@pytest.mark.unit
def test_discovery_issue_surfaces_to_dashboard_failed_item(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    broken_dir = plugins_dir / "broken"
    broken_dir.mkdir(parents=True)
    (broken_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: broken",
                'runtime:',
                '  python: "3.11"',
                "components:",
                "  - class: main:BrokenPlugin",
            ]
        ),
        encoding="utf-8",
    )

    discovered = discover_plugins(plugins_dir)

    assert discovered.plugins == []
    assert "broken" in discovered.skipped_plugins
    assert len(discovered.issues) == 1
    issue = discovered.issues[0]
    assert issue.plugin_id == "broken"
    assert issue.phase == "discovery"
    assert "requirements.txt" in issue.details

    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._set_discovery_issues(discovered.issues)  # noqa: SLF001

    dashboard_items = bridge.list_plugins()
    assert dashboard_items == [
        {
            "name": "broken",
            "repo": "",
            "author": "",
            "desc": "插件发现失败",
            "version": "0.0.0",
            "reserved": False,
            "activated": False,
            "online_vesion": "",
            "handlers": [],
            "display_name": "broken",
            "logo": None,
            "support_platforms": [],
            "astrbot_version": "",
            "installed_at": None,
            "runtime_kind": "sdk",
            "source_kind": "local_dir",
            "managed_by": "sdk_bridge",
            "state": "failed",
            "trigger_summary": [],
            "unsupported_features": [],
            "failure_reason": issue.details,
            "issues": [issue.to_payload()],
        }
    ]

    metadata = bridge.get_plugin_metadata("broken")
    assert metadata is not None
    assert metadata["enabled"] is False
    assert metadata["runtime_kind"] == "sdk"
    assert metadata["issues"] == [issue.to_payload()]


@pytest.mark.unit
def test_loaded_plugin_issue_metadata_is_preserved_in_bridge(tmp_path: Path) -> None:
    issue = PluginDiscoveryIssue(
        severity="error",
        phase="load",
        plugin_id="sdk-demo",
        message="worker failed",
        details="boom",
    )
    bridge = SdkPluginBridge(_BridgeStarContext())
    bridge._records = {  # noqa: SLF001
        "sdk-demo": SimpleNamespace(
            plugin=SimpleNamespace(
                name="sdk-demo",
                manifest_data={},
                plugin_dir=tmp_path / "sdk-demo",
            ),
            plugin_id="sdk-demo",
            load_order=0,
            state="failed",
            unsupported_features=[],
            config={},
            handlers=[],
            llm_tools={},
            active_llm_tools=set(),
            agents={},
            dynamic_command_routes=[],
            session=None,
            restart_attempted=False,
            failure_reason="boom",
            issues=[issue.to_payload()],
        )
    }

    metadata = bridge.get_plugin_metadata("sdk-demo")
    assert metadata is not None
    assert metadata["issues"] == [issue.to_payload()]

    dashboard_items = bridge.list_plugins()
    assert dashboard_items[0]["issues"] == [issue.to_payload()]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source_name", "main_source"),
    [
        (
            "event_case",
            "\n".join(
                [
                    "from astrbot_sdk import Context, MessageEvent, Star, on_event, rate_limit",
                    "",
                    "class DemoPlugin(Star):",
                    '    @on_event("ready")',
                    "    @rate_limit(1, 60)",
                    "    async def broken(self, event: MessageEvent, ctx: Context) -> None:",
                    "        return None",
                ]
            ),
        ),
        (
            "schedule_case",
            "\n".join(
                [
                    "from astrbot_sdk import Context, Star, on_schedule, rate_limit",
                    "",
                    "class DemoPlugin(Star):",
                    '    @on_schedule(interval_seconds=60)',
                    "    @rate_limit(1, 60)",
                    "    async def broken(self, ctx: Context) -> None:",
                    "        return None",
                ]
            ),
        ),
    ],
)
def test_invalid_limiter_trigger_combinations_fail_during_plugin_load(
    tmp_path: Path,
    source_name: str,
    main_source: str,
) -> None:
    env = SDKTestEnvironment(tmp_path)
    plugin_dir = _write_sdk_plugin(
        env.plugin_dir(source_name),
        name=source_name,
        main_source=main_source,
    )

    plugin = load_plugin_spec(plugin_dir)
    validate_plugin_spec(plugin)
    with pytest.raises(ValueError, match="只适用于 on_command/on_message"):
        load_plugin(plugin)


@pytest.mark.unit
def test_cli_error_render_includes_docs_details_and_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    CliRunner()  # keep click testing dependency exercised in the SDK test env

    def _boom() -> None:
        raise AstrBotError.invalid_input(
            "bad input",
            hint="fix it",
            docs_url="https://docs.astrbot.org/sdk/errors#invalid-input",
            details={"field": "name"},
        )

    with pytest.raises(SystemExit) as exc_info:
        _run_sync_entrypoint(
            _boom,
            log_message="run test entrypoint",
            context={"plugin_dir": Path("demo-plugin")},
        )

    assert exc_info.value.code == EXIT_RUNTIME
    captured = capsys.readouterr()
    assert "Error[invalid_input]: bad input" in captured.err
    assert "Suggestion: fix it" in captured.err
    assert "Docs: https://docs.astrbot.org/sdk/errors#invalid-input" in captured.err
    assert "Details: {'field': 'name'}" in captured.err
    assert "plugin_dir: demo-plugin" in captured.err


@pytest.mark.unit
def test_group_worker_metadata_serializes_issues() -> None:
    runtime = object.__new__(GroupWorkerRuntime)
    runtime.group_id = "group-1"
    runtime.plugins = [SimpleNamespace(name="sdk-demo")]
    runtime.skipped_plugins = {"sdk-broken": "boom"}
    runtime.issues = [
        PluginDiscoveryIssue(
            severity="error",
            phase="lifecycle",
            plugin_id="sdk-demo",
            message="on_start failed",
            details="boom",
        )
    ]
    runtime._active_plugin_states = [
        SimpleNamespace(
            plugin=SimpleNamespace(name="sdk-demo"),
            loaded_plugin=SimpleNamespace(
                capabilities=[],
                llm_tools=[],
                agents=[],
            ),
        )
    ]

    metadata = runtime._initialize_metadata()  # noqa: SLF001

    assert metadata["issues"] == [runtime.issues[0].to_payload()]
    assert metadata["skipped_plugins"] == {"sdk-broken": "boom"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supervisor_metadata_includes_discovery_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = PluginDiscoveryIssue(
        severity="error",
        phase="discovery",
        plugin_id="broken",
        message="插件发现失败",
        details="missing requirements.txt",
    )

    class _FakePeer:
        def __init__(self, *args, **kwargs) -> None:
            self.initialized_metadata: dict[str, object] | None = None

        def set_invoke_handler(self, handler) -> None:
            self.invoke_handler = handler

        def set_cancel_handler(self, handler) -> None:
            self.cancel_handler = handler

        async def start(self) -> None:
            return None

        async def initialize(self, handlers, *, provided_capabilities, metadata) -> None:
            self.initialized_metadata = metadata

        async def stop(self) -> None:
            return None

    class _FakeEnvManager:
        def plan(self, plugins):
            return EnvironmentPlanResult(groups=[], plugins=[], plugin_to_group={})

    monkeypatch.setattr(supervisor_module, "Peer", _FakePeer)
    monkeypatch.setattr(
        supervisor_module,
        "discover_plugins",
        lambda _plugins_dir: PluginDiscoveryResult(
            plugins=[],
            skipped_plugins={"broken": "missing requirements.txt"},
            issues=[issue],
        ),
    )

    runtime = SupervisorRuntime(
        transport=object(),
        plugins_dir=tmp_path,
        env_manager=_FakeEnvManager(),
    )
    await runtime.start()

    assert runtime.peer.initialized_metadata is not None  # type: ignore[union-attr]
    assert runtime.peer.initialized_metadata["issues"] == [issue.to_payload()]  # type: ignore[index,union-attr]

    await runtime.stop()


@pytest.mark.unit
def test_testing_helpers_mock_clock_and_environment(tmp_path: Path) -> None:
    env = SDKTestEnvironment(tmp_path)

    assert env.plugins_dir == tmp_path / "plugins"
    assert env.plugins_dir.exists()
    assert env.plugin_dir("demo") == tmp_path / "plugins" / "demo"

    clock = MockClock(now=10.0)
    assert clock.time() == 10.0
    assert clock.advance(2.5) == 12.5
    assert clock.time() == 12.5


class _LimiterPlugin(Star):
    async def handle(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("ok")


async def _invoke_handler(
    dispatcher: HandlerDispatcher,
    *,
    handler_id: str,
    text: str,
    request_id: str,
    session_id: str = "demo:private:user-1",
) -> dict[str, object]:
    message = SimpleNamespace(
        id=request_id,
        input={
            "handler_id": handler_id,
            "event": _event_payload(text, session_id=session_id),
            "args": {},
        },
    )
    return await dispatcher.invoke(message, CancelToken())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_and_cooldown_behaviors() -> None:
    peer = _Peer()
    owner = _LimiterPlugin()
    handler_id = "sdk-demo:test.handle"

    limited = LoadedHandler(
        descriptor=HandlerDescriptor(
            id=handler_id,
            trigger=CommandTrigger(command="ping"),
        ),
        callable=owner.handle,
        owner=owner,
        plugin_id="sdk-demo",
        limiter=LimiterMeta(kind="rate_limit", limit=1, window=60),
    )
    dispatcher = HandlerDispatcher(
        plugin_id="sdk-demo",
        peer=peer,
        handlers=[limited],
    )

    await _invoke_handler(dispatcher, handler_id=handler_id, text="ping", request_id="r1")
    await _invoke_handler(dispatcher, handler_id=handler_id, text="ping", request_id="r2")

    assert peer.sent_messages[0]["text"] == "ok"
    assert peer.sent_messages[1]["text"] == "操作过于频繁，请稍后再试。"

    cooldown_loaded = LoadedHandler(
        descriptor=HandlerDescriptor(
            id="sdk-demo:test.cooldown",
            trigger=CommandTrigger(command="cool"),
        ),
        callable=owner.handle,
        owner=owner,
        plugin_id="sdk-demo",
        limiter=LimiterMeta(
            kind="cooldown",
            limit=1,
            window=30,
            behavior="error",
        ),
    )
    cooldown_dispatcher = HandlerDispatcher(
        plugin_id="sdk-demo",
        peer=_Peer(),
        handlers=[cooldown_loaded],
    )

    await _invoke_handler(
        cooldown_dispatcher,
        handler_id="sdk-demo:test.cooldown",
        text="cool",
        request_id="c1",
    )
    with pytest.raises(AstrBotError) as exc_info:
        await _invoke_handler(
            cooldown_dispatcher,
            handler_id="sdk-demo:test.cooldown",
            text="cool",
            request_id="c2",
        )
    assert exc_info.value.code == ErrorCodes.COOLDOWN_ACTIVE


@pytest.mark.unit
def test_limiter_scope_keys_and_behavior_with_mock_clock() -> None:
    clock = MockClock()
    engine = LimiterEngine(clock=clock.time)
    base_event = SimpleNamespace(
        session_id="demo:private:user-1",
        platform_id="demo",
        user_id="user-1",
        group_id="room-1",
    )

    assert (
        engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=LimiterMeta(kind="rate_limit", limit=1, window=60, scope="session"),
            event=base_event,
        ).allowed
        is True
    )
    session_block = engine.evaluate(
        plugin_id="sdk-demo",
        handler_id="h",
        limiter=LimiterMeta(kind="rate_limit", limit=1, window=60, scope="session"),
        event=base_event,
    )
    assert session_block.allowed is False
    assert session_block.hint == "操作过于频繁，请稍后再试。"
    assert "sdk-demo:h:demo:private:user-1" in engine._windows  # noqa: SLF001

    assert (
        engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=LimiterMeta(kind="rate_limit", limit=1, window=60, scope="session"),
            event=SimpleNamespace(
                session_id="demo:private:user-2",
                platform_id="demo",
                user_id="user-2",
                group_id="room-1",
            ),
        ).allowed
        is True
    )

    user_engine = LimiterEngine(clock=clock.time)
    user_limiter = LimiterMeta(kind="rate_limit", limit=1, window=60, scope="user")
    assert (
        user_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=user_limiter,
            event=base_event,
        ).allowed
        is True
    )
    assert (
        user_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=user_limiter,
            event=SimpleNamespace(
                session_id="demo:private:user-9",
                platform_id="demo",
                user_id="user-1",
                group_id="room-9",
            ),
        ).allowed
        is False
    )
    assert "sdk-demo:h:demo:user-1" in user_engine._windows  # noqa: SLF001

    group_engine = LimiterEngine(clock=clock.time)
    group_limiter = LimiterMeta(kind="rate_limit", limit=1, window=60, scope="group")
    assert (
        group_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=group_limiter,
            event=base_event,
        ).allowed
        is True
    )
    assert (
        group_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=group_limiter,
            event=SimpleNamespace(
                session_id="demo:group:room-2",
                platform_id="demo",
                user_id="user-2",
                group_id="room-1",
            ),
        ).allowed
        is False
    )
    assert "sdk-demo:h:demo:room-1" in group_engine._windows  # noqa: SLF001

    global_engine = LimiterEngine(clock=clock.time)
    global_limiter = LimiterMeta(
        kind="cooldown",
        limit=1,
        window=30,
        scope="global",
        behavior="error",
    )
    assert (
        global_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=global_limiter,
            event=base_event,
        ).allowed
        is True
    )
    global_block = global_engine.evaluate(
        plugin_id="sdk-demo",
        handler_id="h",
        limiter=global_limiter,
        event=SimpleNamespace(
            session_id="demo:private:user-2",
            platform_id="demo",
            user_id="user-2",
            group_id="room-2",
        ),
    )
    assert global_block.allowed is False
    assert global_block.error is not None
    assert global_block.error.code == ErrorCodes.COOLDOWN_ACTIVE
    assert "sdk-demo:h" in global_engine._windows  # noqa: SLF001

    silent_engine = LimiterEngine(clock=clock.time)
    silent_limiter = LimiterMeta(
        kind="rate_limit",
        limit=1,
        window=60,
        scope="global",
        behavior="silent",
    )
    assert (
        silent_engine.evaluate(
            plugin_id="sdk-demo",
            handler_id="h",
            limiter=silent_limiter,
            event=base_event,
        ).allowed
        is True
    )
    silent_block = silent_engine.evaluate(
        plugin_id="sdk-demo",
        handler_id="h",
        limiter=silent_limiter,
        event=base_event,
    )
    assert silent_block.allowed is False
    assert silent_block.error is None
    assert silent_block.hint is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_builder_event_helpers_and_media_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _record_build(url: str, *, kind: str = "auto"):
        calls.append((url, kind))
        return Image.fromURL(url)

    monkeypatch.setattr(
        "astrbot_sdk.message_result.build_media_component_from_url",
        _record_build,
    )
    chain = (
        MessageBuilder()
        .text("hello")
        .at("123")
        .image("https://example.com/a.png")
        .build()
    )
    assert isinstance(chain, MessageChain)
    assert chain.plain_text(with_other_comps_mark=True) == "hello [At] [Image]"
    assert calls == [("https://example.com/a.png", "image")]

    event = MessageEvent.from_payload(
        {
            **_event_payload("hello"),
            "message_type": "group",
            "group_id": "room-1",
            "messages": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "at", "data": {"qq": "123"}},
                {"type": "image", "data": {"file": "https://example.com/a.png"}},
                {"type": "file", "data": {"name": "a.txt", "file": "https://example.com/a.txt"}},
            ],
        }
    )
    assert event.is_group_chat() is True
    assert event.has_component(Image) is True
    assert len(event.get_images()) == 1
    assert len(event.get_files()) == 1
    assert event.extract_plain_text() == "hello"
    assert event.get_at_users() == ["123"]

    assert isinstance(await MediaHelper.from_url("https://example.com/a.png"), Image)
    assert isinstance(await MediaHelper.from_url("https://example.com/a.mp3"), Record)
    assert isinstance(await MediaHelper.from_url("https://example.com/a.bin"), File)
    assert isinstance(
        await MediaHelper.from_url("https://example.com/a.png", kind="record"),
        Record,
    )
    assert isinstance(
        await MediaHelper.from_url("https://example.com/a.png", kind="file"),
        File,
    )
    assert isinstance(await MediaHelper.from_url("https://example.com/download"), File)

    with pytest.raises(AstrBotError, match="Unsupported media kind"):
        await MediaHelper.from_url("https://example.com/a.png", kind="unknown")

    with pytest.raises(AstrBotError) as invalid_exc:
        await MediaHelper.download("ftp://example.com/a.bin", tmp_path)
    assert invalid_exc.value.code == ErrorCodes.INVALID_INPUT

    file_save_dir = tmp_path / "existing-file"
    file_save_dir.write_text("x", encoding="utf-8")
    with pytest.raises(AstrBotError) as internal_exc:
        await MediaHelper.download("https://example.com/a.bin", file_save_dir)
    assert internal_exc.value.code == ErrorCodes.INTERNAL_ERROR

    def _boom(url: str, filename: str | Path):
        raise OSError("network")

    monkeypatch.setattr("astrbot_sdk.message_components.urlretrieve", _boom)
    with pytest.raises(AstrBotError) as network_exc:
        await MediaHelper.download("https://example.com/a.bin", tmp_path / "downloads")
    assert network_exc.value.code == ErrorCodes.NETWORK_ERROR


class _ConversationPlugin(Star):
    def __init__(self, states: list[ConversationState]) -> None:
        super().__init__()
        self.states = states

    async def run(
        self,
        event: MessageEvent,
        conversation: ConversationSession,
        ctx: Context,
    ) -> None:
        try:
            answer = await conversation.ask("question?")
            await conversation.reply(f"answer:{answer.text}")
        finally:
            self.states.append(conversation.state)


class _ReplaceAwareConversationPlugin(Star):
    def __init__(
        self,
        states: list[ConversationState],
        replaced_errors: list[type[Exception]],
        stale_errors: list[type[Exception]],
    ) -> None:
        super().__init__()
        self.states = states
        self.replaced_errors = replaced_errors
        self.stale_errors = stale_errors

    async def run(
        self,
        event: MessageEvent,
        conversation: ConversationSession,
        ctx: Context,
    ) -> None:
        was_replaced = False
        try:
            await conversation.ask("question?")
        except ConversationReplaced as exc:
            was_replaced = True
            self.replaced_errors.append(type(exc))
        finally:
            self.states.append(conversation.state)
            if was_replaced:
                try:
                    await conversation.reply("stale")
                except ConversationClosed as exc:
                    self.stale_errors.append(type(exc))


class _StickyConversationPlugin(Star):
    async def run(
        self,
        event: MessageEvent,
        conversation: ConversationSession,
        ctx: Context,
    ) -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await asyncio.sleep(0.1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_reject_and_replace_modes() -> None:
    async def _exercise(mode: str) -> tuple[HandlerDispatcher, _Peer, list[ConversationState]]:
        peer = _Peer()
        states: list[ConversationState] = []
        owner = _ConversationPlugin(states)
        handler = LoadedHandler(
            descriptor=HandlerDescriptor(
                id=f"sdk-demo:test.{mode}",
                trigger=CommandTrigger(command="quiz"),
            ),
            callable=owner.run,
            owner=owner,
            plugin_id="sdk-demo",
            conversation=ConversationMeta(
                timeout=30,
                mode=mode,  # type: ignore[arg-type]
                busy_message="busy now",
                grace_period=0.05,
            ),
        )
        dispatcher = HandlerDispatcher(
            plugin_id="sdk-demo",
            peer=peer,
            handlers=[handler],
        )

        await _invoke_handler(
            dispatcher,
            handler_id=handler.descriptor.id,
            text="quiz",
            request_id=f"{mode}-1",
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        await _invoke_handler(
            dispatcher,
            handler_id=handler.descriptor.id,
            text="quiz",
            request_id=f"{mode}-2",
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        waiter_message = SimpleNamespace(
            id=f"{mode}-wait",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": _event_payload("42"),
            },
        )
        await dispatcher.invoke(waiter_message, CancelToken())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return dispatcher, peer, states

    reject_dispatcher, reject_peer, reject_states = await _exercise("reject")
    assert [item["text"] for item in reject_peer.sent_messages if item["kind"] == "text"] == [
        "question?",
        "busy now",
        "answer:42",
    ]
    assert not reject_dispatcher._conversations  # noqa: SLF001
    assert ConversationState.REPLACED not in reject_states

    replace_dispatcher, replace_peer, replace_states = await _exercise("replace")
    assert [item["text"] for item in replace_peer.sent_messages if item["kind"] == "text"] == [
        "question?",
        "question?",
        "answer:42",
    ]
    assert not replace_dispatcher._conversations  # noqa: SLF001
    assert ConversationState.REPLACED in replace_states


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_replace_injects_exception_and_rejects_stale_messages() -> None:
    peer = _Peer()
    states: list[ConversationState] = []
    replaced_errors: list[type[Exception]] = []
    stale_errors: list[type[Exception]] = []
    owner = _ReplaceAwareConversationPlugin(states, replaced_errors, stale_errors)
    handler = LoadedHandler(
        descriptor=HandlerDescriptor(
            id="sdk-demo:test.replace-aware",
            trigger=CommandTrigger(command="quiz"),
        ),
        callable=owner.run,
        owner=owner,
        plugin_id="sdk-demo",
        conversation=ConversationMeta(
            timeout=30,
            mode="replace",
            busy_message="busy now",
            grace_period=0.05,
        ),
    )
    dispatcher = HandlerDispatcher(
        plugin_id="sdk-demo",
        peer=peer,
        handlers=[handler],
    )

    await _invoke_handler(
        dispatcher,
        handler_id=handler.descriptor.id,
        text="quiz",
        request_id="replace-aware-1",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await _invoke_handler(
        dispatcher,
        handler_id=handler.descriptor.id,
        text="quiz",
        request_id="replace-aware-2",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    waiter_message = SimpleNamespace(
        id="replace-aware-wait",
        input={
            "handler_id": "__sdk_session_waiter__",
            "event": _event_payload("42"),
        },
    )
    await dispatcher.invoke(waiter_message, CancelToken())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert replaced_errors == [ConversationReplaced]
    assert stale_errors
    assert all(error is ConversationClosed for error in stale_errors)
    assert [item["text"] for item in peer.sent_messages if item["kind"] == "text"] == [
        "question?",
        "question?",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_replace_grace_timeout_only_logs_warning() -> None:
    peer = _Peer()
    watcher = Context(peer=peer, plugin_id="sdk-demo").logger.watch()
    owner = _StickyConversationPlugin()
    handler = LoadedHandler(
        descriptor=HandlerDescriptor(
            id="sdk-demo:test.sticky",
            trigger=CommandTrigger(command="quiz"),
        ),
        callable=owner.run,
        owner=owner,
        plugin_id="sdk-demo",
        conversation=ConversationMeta(
            timeout=30,
            mode="replace",
            grace_period=0.01,
        ),
    )
    dispatcher = HandlerDispatcher(
        plugin_id="sdk-demo",
        peer=peer,
        handlers=[handler],
    )

    async def _next_entry():
        return await watcher.__anext__()

    await _invoke_handler(
        dispatcher,
        handler_id=handler.descriptor.id,
        text="quiz",
        request_id="sticky-1",
    )
    await asyncio.sleep(0)

    pending_warning = asyncio.create_task(_next_entry())
    await _invoke_handler(
        dispatcher,
        handler_id=handler.descriptor.id,
        text="quiz",
        request_id="sticky-2",
    )
    warning_entry = await pending_warning

    assert warning_entry.level == "WARNING"
    assert "grace period exceeded" in warning_entry.message

    for active in list(dispatcher._conversations.values()):  # noqa: SLF001
        active.task.cancel()
        await asyncio.gather(active.task, return_exceptions=True)
    await watcher.aclose()
