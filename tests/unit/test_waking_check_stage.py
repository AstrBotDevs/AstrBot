from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import astrbot.core.pipeline.waking_check.stage as waking
from astrbot.core.command import (
    CommandCatalogStore,
    CommandLexer,
    build_command_catalog,
)
from astrbot.core.message.components import At, AtAll, Plain, Reply
from astrbot.core.platform.message_type import MessageType
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import ActionPermissionFilter
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


class FakeEvent:
    def __init__(
        self,
        messages,
        *,
        private=False,
        message_text="hello",
        platform="aiocqhttp",
        sender_id="user",
        group_id="group",
        extras=None,
    ):
        self.message_obj = SimpleNamespace(
            type=MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
        )
        self.message_str = message_text
        self.session_id = group_id
        self.role = "member"
        self.is_wake = False
        self.is_at_or_wake_command = False
        self.plugins_name = None
        self._messages = messages
        self._private = private
        self._platform = platform
        self._sender_id = sender_id
        self._group_id = group_id
        self._extras = extras or {}
        self.stopped = False
        self.sent = []

    def get_extra(self, key=None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_messages(self):
        return self._messages

    def is_private_chat(self):
        return self._private

    def get_platform_name(self):
        return self._platform

    def get_self_id(self):
        return "bot"

    def get_sender_id(self):
        return self._sender_id

    def get_group_id(self):
        return self._group_id

    def get_session_id(self):
        return self.session_id

    def stop_event(self):
        self.stopped = True

    def is_admin(self):
        return self.role == "admin"

    async def send(self, payload):
        self.sent.append(payload)


async def make_stage(**settings):
    config = {
        "wake_prefix": ["/"],
        "plugin_set": ["*"],
        "platform_settings": {
            "no_permission_reply": True,
            "friend_message_needs_wake_prefix": False,
            "ignore_bot_self_message": False,
            "ignore_at_all": False,
            "unique_session": False,
            "group_wake_policy": {"mention_bot": False, "reply_to_bot": False},
            **settings,
        },
    }
    stage = waking.WakingCheckStage()
    command_catalog = CommandCatalogStore()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config,
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: command_catalog,
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )
    stage.session_plugins.filter_handlers_by_session = AsyncMock(
        side_effect=lambda _, h: h
    )
    return stage


@pytest.mark.asyncio
async def test_dashboard_webchat_principal_is_kept_separate_from_username():
    stage = await make_stage()
    event = FakeEvent(
        [],
        private=True,
        platform="webchat",
        sender_id="alice",
        extras={
            "_dashboard_principal": {
                "account_id": "account-1",
                "sid": "session-1",
                "username": "alice",
                "auth_strength": "password",
            }
        },
    )

    await stage._attach_authorization(event)

    assert event.get_extra("auth_subject").kind == "dashboard-account"
    context = event.get_extra("auth_context")
    assert context.source == "webchat"
    assert context.principal_subject_id == "dashboard-account:account-1"
    assert context.caller_declared_username == "alice"
    assert context.auth_strength == "password"
    assert context.metadata["dashboard_session_id"] == "session-1"


def install_handlers(stage, monkeypatch, handlers) -> None:
    _ = monkeypatch
    stage.ctx.handlers = SimpleNamespace(
        get_handlers_by_event_type=lambda *_args, **_kwargs: handlers,
    )
    for handler in handlers:
        module_path = getattr(handler, "handler_module_path", None)
        if not module_path or stage.ctx.plugins.get_by_module(module_path):
            continue
        stage.ctx.plugins.publish(
            StarMetadata(name="Test", module_path=module_path, activated=True)
        )
    stage.command_catalog.replace(build_command_catalog(handlers))


def make_command_handler(name: str, handler, *extra_filters):
    metadata = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"test.plugin_{handler.__name__}_{id(handler)}",
        handler_name=handler.__name__,
        handler_module_path="test.plugin",
        handler=handler,
        event_filters=[],
    )
    command_filter = CommandFilter(name)
    command_filter.init_handler_md(metadata)
    metadata.event_filters.extend((command_filter, *extra_filters))
    return metadata, command_filter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "event", "expected"),
    [
        ({}, FakeEvent([Plain("hello")], private=True), True),
        (
            {"friend_message_needs_wake_prefix": True},
            FakeEvent([Plain("hello")], private=True),
            False,
        ),
        (
            {"friend_message_needs_wake_prefix": True},
            FakeEvent([Plain("/hello")], private=True, message_text="/hello"),
            True,
        ),
        (
            {},
            FakeEvent(
                [Plain("hello")], private=True, extras={"skip_private_wake": True}
            ),
            False,
        ),
        ({}, FakeEvent([Plain("/hello")], message_text="/hello"), True),
        (
            {"group_wake_policy": {"mention_bot": True, "reply_to_bot": False}},
            FakeEvent([At(qq="bot"), Plain("hello")]),
            True,
        ),
        ({}, FakeEvent([At(qq="other"), Plain("hello")]), False),
        ({}, FakeEvent([AtAll(), Plain("hello")]), True),
        ({"ignore_at_all": True}, FakeEvent([AtAll(), Plain("hello")]), False),
    ],
)
async def test_detect_wake_behavior_matrix(settings, event, expected):
    stage = await make_stage(**settings)

    assert (await stage._detect_wake(event)).should_wake is expected
    assert event.is_wake is expected


@pytest.mark.asyncio
async def test_detect_wake_resolves_unknown_reply_sender(monkeypatch):
    event = FakeEvent([Reply(id="reply-1"), Plain("hello")])
    stage = await make_stage(
        group_wake_policy={"mention_bot": False, "reply_to_bot": True}
    )
    client = SimpleNamespace(get_msg_sender_id=AsyncMock(return_value="bot"))
    monkeypatch.setattr(waking, "OneBotClient", lambda _: client)

    assert (await stage._detect_wake(event)).should_wake is True
    assert event.get_messages()[0].sender_id == "bot"
    client.get_msg_sender_id.assert_awaited_once_with("reply-1")


@pytest.mark.asyncio
async def test_group_wake_policy_does_not_mutate_at_component(monkeypatch):
    stage = await make_stage()
    install_handlers(stage, monkeypatch, [])
    mention = At(qq="bot")
    event = FakeEvent([mention, Plain("hello")])

    await stage.process(event)

    assert event.stopped is True
    assert event.get_messages()[0] is mention


@pytest.mark.asyncio
async def test_adapter_preconfigured_wake_bypasses_group_wake_policy(monkeypatch):
    stage = await make_stage()
    install_handlers(stage, monkeypatch, [])
    event = FakeEvent([At(qq="bot")])
    event.is_wake = True

    await stage.process(event)

    assert event.stopped is False
    assert "adapter_preconfigured" in event.get_extra("wake_reasons")


@pytest.mark.asyncio
async def test_process_applies_admin_self_message_and_unique_session_rules(monkeypatch):
    stage = await make_stage(unique_session=True, ignore_bot_self_message=True)
    install_handlers(stage, monkeypatch, [])

    self_event = FakeEvent([Plain("hello")], sender_id="bot")
    await stage.process(self_event)
    assert self_event.stopped is True

    admin_event = FakeEvent([Plain("/hello")], message_text="/hello", sender_id="admin")
    await stage.process(admin_event)
    assert admin_event.role == "member"
    assert admin_event.get_extra("auth_context").subject.kind == "im"
    assert admin_event.session_id == "admin_group"

    notice_event = FakeEvent(
        [Plain("hello")], extras={"onebot_post_type": "notice"}, sender_id="admin"
    )
    await stage.process(notice_event)
    assert notice_event.session_id == "group"


@pytest.mark.asyncio
async def test_platform_sender_never_becomes_global_admin_role():
    stage = await make_stage()
    event = FakeEvent([Plain("hello")], sender_id="admin")
    await stage.process(event)
    assert event.role == "member"
    assert event.get_extra("auth_context").subject.kind == "im"


@pytest.mark.asyncio
async def test_process_filters_handlers_by_session(monkeypatch):
    stage = await make_stage()
    handler = SimpleNamespace(
        handler_module_path="test.plugin",
        handler_full_name="test.handler",
        event_filters=[SimpleNamespace(filter=lambda *_: True)],
    )
    install_handlers(stage, monkeypatch, [handler])
    stage.session_plugins.filter_handlers_by_session = AsyncMock(return_value=[])
    event = FakeEvent([Plain("hello")])

    await stage.process(event)

    assert event.is_wake is True
    assert event.get_extra("activated_handlers") == []
    stage.session_plugins.filter_handlers_by_session.assert_awaited_once_with(
        event, [handler]
    )


@pytest.mark.asyncio
async def test_command_is_lexed_once_and_params_stay_handler_scoped(monkeypatch):
    stage = await make_stage()

    async def first(self, event, value: int) -> None: ...

    async def second(self, event, value: str) -> None: ...

    first_md, _ = make_command_handler("demo", first)
    second_md, _ = make_command_handler("demo", second)
    install_handlers(stage, monkeypatch, [first_md, second_md])
    calls = 0
    original_lex = CommandLexer.lex

    def counted_lex(self, source, *, offset=0):
        nonlocal calls
        calls += 1
        return original_lex(self, source, offset=offset)

    monkeypatch.setattr(CommandLexer, "lex", counted_lex)
    event = FakeEvent([Plain("/demo 3")], message_text="/demo 3")

    await stage.process(event)

    assert calls == 1
    assert event.get_extra("activated_handlers") == [first_md, second_md]
    assert event.get_extra("handlers_parsed_params") == {
        first_md.handler_full_name: {"value": 3},
        second_md.handler_full_name: {"value": "3"},
    }


@pytest.mark.asyncio
async def test_command_permission_denial_keeps_existing_behavior(monkeypatch):
    stage = await make_stage()

    async def admin_only(self, event) -> None: ...

    handler, _ = make_command_handler(
        "admin", admin_only, ActionPermissionFilter("session.manage")
    )
    install_handlers(stage, monkeypatch, [handler])
    event = FakeEvent([Plain("/admin")], message_text="/admin")

    await stage.process(event)

    assert event.stopped is True
    assert event.get_extra("activated_handlers", []) == []
    assert "权限不足" in event.sent[0].get_plain_text()


@pytest.mark.asyncio
async def test_command_group_permission_applies_to_subcommands(monkeypatch):
    stage = await make_stage()
    group = CommandGroupFilter("admin")

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_admin_group",
        "admin",
        "test.plugin",
        group_handler,
        [group, ActionPermissionFilter("session.manage")],
    )

    async def run(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_admin_run",
        "run",
        "test.plugin",
        run,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("run", parent_command_names=["admin"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)
    install_handlers(stage, monkeypatch, [group_md, child_md])
    event = FakeEvent([Plain("/admin run")], message_text="/admin run")

    await stage.process(event)

    assert event.stopped is True
    assert event.get_extra("activated_handlers", []) == []
    assert "权限不足" in event.sent[0].get_plain_text()


@pytest.mark.asyncio
async def test_command_group_custom_filter_blocks_subcommands(monkeypatch):
    stage = await make_stage()
    group = CommandGroupFilter("restricted")
    group.add_custom_filter(SimpleNamespace(filter=lambda *_args: False))

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_restricted_group",
        "restricted",
        "test.plugin",
        group_handler,
        [group],
    )

    async def run(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_restricted_run",
        "run",
        "test.plugin",
        run,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("run", parent_command_names=["restricted"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)
    install_handlers(stage, monkeypatch, [group_md, child_md])
    event = FakeEvent(
        [Plain("/restricted run")],
        message_text="/restricted run",
    )

    await stage.process(event)

    assert event.stopped is False
    assert event.get_extra("activated_handlers", []) == []


@pytest.mark.asyncio
async def test_command_group_permission_precedes_group_diagnostics(monkeypatch):
    stage = await make_stage()
    group = CommandGroupFilter("admin")

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_admin_group_diagnostic",
        "admin",
        "test.plugin",
        group_handler,
        [ActionPermissionFilter("session.manage"), group],
    )

    async def run(self, event) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_admin_run_diagnostic",
        "run",
        "test.plugin",
        run,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("run", parent_command_names=["admin"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)
    install_handlers(stage, monkeypatch, [group_md, child_md])
    event = FakeEvent([Plain("/admin")], message_text="/admin")

    await stage.process(event)

    text = event.sent[0].get_plain_text()
    assert event.stopped is True
    assert "权限不足" in text
    assert "可用子指令" not in text


@pytest.mark.asyncio
async def test_command_syntax_error_is_not_attributed_to_plugin(monkeypatch):
    stage = await make_stage()

    async def name(self, event, value: str) -> None: ...

    handler, _ = make_command_handler("name", name)
    install_handlers(stage, monkeypatch, [handler])
    event = FakeEvent([Plain("/name $HOME")], message_text="/name $HOME")

    await stage.process(event)

    text = event.sent[0].get_plain_text()
    assert event.stopped is True
    assert "参数展开" in text
    assert "插件" not in text


@pytest.mark.asyncio
async def test_command_filter_internal_error_is_redacted_from_response_and_logs(
    monkeypatch,
):
    stage = await make_stage()
    secret = "api_key=super-secret Bearer provider-token https://internal.example/path"

    class ExplodingFilter:
        def filter(self, event, cfg):
            raise RuntimeError(secret)

    async def demo(self, event) -> None: ...

    handler, _ = make_command_handler("demo", demo, ExplodingFilter())
    install_handlers(stage, monkeypatch, [handler])
    fake_logger = Mock()
    monkeypatch.setattr(waking, "logger", fake_logger)
    event = FakeEvent([Plain("/demo")], message_text="/demo")

    await stage.process(event)

    assert event.stopped is True
    assert event.sent[0].get_plain_text() == "指令处理失败，请稍后重试。"
    assert event.sent[0].use_markdown_ is False
    assert secret not in event.sent[0].get_plain_text()
    assert fake_logger.error.call_count == 1
    logged = " ".join(
        str(argument)
        for call in fake_logger.error.call_args_list
        for argument in call.args
    )
    assert "super-secret" not in logged
    assert "provider-token" not in logged
    assert "internal.example" not in logged
    assert "[REDACTED]" in logged
    assert "[REDACTED_URL]" in logged


@pytest.mark.asyncio
async def test_command_group_filter_error_is_redacted_and_plain_text(monkeypatch):
    stage = await make_stage()
    secret = "api_key=group-secret https://internal.example/group"
    handler = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_group",
        "group",
        "test.plugin",
        lambda *_args: None,
        [],
    )
    install_handlers(stage, monkeypatch, [handler])
    fake_logger = Mock()
    monkeypatch.setattr(waking, "logger", fake_logger)
    event = FakeEvent([Plain("/group")], message_text="/group")

    await stage._send_filter_error(event, handler, RuntimeError(secret))

    assert event.stopped is True
    assert event.sent[0].get_plain_text() == "指令处理失败，请稍后重试。"
    assert event.sent[0].use_markdown_ is False
    assert secret not in event.sent[0].get_plain_text()
    logged = " ".join(
        str(argument)
        for call in fake_logger.error.call_args_list
        for argument in call.args
    )
    assert "group-secret" not in logged
    assert "internal.example" not in logged
    assert "[REDACTED]" in logged
    assert "[REDACTED_URL]" in logged


@pytest.mark.asyncio
async def test_command_preserves_non_ascii_space_and_rejects_trailing_newline(
    monkeypatch,
):
    stage = await make_stage()

    async def name(self, event, value: str) -> None: ...

    handler, _ = make_command_handler("name", name)
    install_handlers(stage, monkeypatch, [handler])

    unicode_space = FakeEvent([Plain("/name a\u00a0b")], message_text="/name a\u00a0b")
    await stage.process(unicode_space)
    assert unicode_space.get_extra("handlers_parsed_params") == {
        handler.handler_full_name: {"value": "a\u00a0b"}
    }

    newline = FakeEvent([Plain("/name value\n")], message_text="/name value\n")
    await stage.process(newline)
    assert newline.stopped is True
    assert "未引用的换行" in newline.sent[0].get_plain_text()


@pytest.mark.asyncio
async def test_failed_and_filter_does_not_leave_bound_params(monkeypatch):
    stage = await make_stage()

    async def demo(self, event, value: str) -> None: ...

    rejecting_filter = SimpleNamespace(filter=lambda *_args: False)
    handler, command_filter = make_command_handler("demo", demo)
    command_filter.add_custom_filter(rejecting_filter)
    install_handlers(stage, monkeypatch, [handler])
    event = FakeEvent([Plain("/demo value")], message_text="/demo value")

    await stage.process(event)

    assert event.get_extra("activated_handlers") == []
    assert event.get_extra("handlers_parsed_params") == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "/请解释 $HOME",
        "/请读取 https://example.com?a=1&b=2#readme",
        "/请解释 '未闭合的引号",
    ],
)
async def test_unknown_root_prompts_bypass_orbit(monkeypatch, message):
    stage = await make_stage()

    async def known(self, event, value: str) -> None: ...

    handler, _ = make_command_handler("name", known)
    install_handlers(stage, monkeypatch, [handler])
    event = FakeEvent([Plain(message)], message_text=message)

    await stage.process(event)

    assert event.stopped is False
    assert event.sent == []
    assert event.get_extra("activated_handlers") == []


@pytest.mark.asyncio
async def test_known_group_rejects_unknown_subcommand(monkeypatch):
    stage = await make_stage()
    group = CommandGroupFilter("plugin")

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_group",
        "group",
        "test.plugin",
        group_handler,
        [group],
    )

    async def get(self, event, url: str) -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_get",
        "get",
        "test.plugin",
        get,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("get", parent_command_names=["plugin"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)
    install_handlers(stage, monkeypatch, [group_md, child_md])
    event = FakeEvent([Plain("/plugin remove")], message_text="/plugin remove")

    await stage.process(event)

    assert event.stopped is True
    assert "不存在子指令" in event.sent[0].get_plain_text()
    assert "get" in event.sent[0].get_plain_text()


@pytest.mark.asyncio
async def test_catalog_snapshot_replacement_handles_rename_alias_and_disable():
    stage = await make_stage()
    group = CommandGroupFilter("plugin", alias={"p"})

    def group_handler(self) -> None: ...

    group_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_group_rebuild",
        "group",
        "test.plugin",
        group_handler,
        [group],
    )

    async def get(self, event, value: str = "") -> None: ...

    child_md = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "test.plugin_get_rebuild",
        "get",
        "test.plugin",
        get,
        [],
        extras_configs={"sub_command": True},
    )
    child = CommandFilter("get", alias={"install"}, parent_command_names=["plugin"])
    child.init_handler_md(child_md)
    child_md.event_filters.append(child)
    group.add_sub_command_filter(child)

    stage.command_catalog.replace(build_command_catalog([group_md, child_md]))
    initial = stage._command_engine()
    assert initial.resolve("p install value").invocation.argv == ("value",)

    group.group_name = "extension"
    group.alias = {"ext"}
    child.command_name = "add"
    child.alias = {"install"}
    stage.command_catalog.replace(build_command_catalog([group_md, child_md]))
    rebuilt = stage._command_engine()
    assert rebuilt.resolve("ext add value").invocation.argv == ("value",)
    assert (
        rebuilt.resolve("plugin get value").resolution.kind
        is waking.CommandResolutionKind.UNKNOWN_ROOT
    )

    stage.command_catalog.replace(build_command_catalog([group_md]))
    disabled = stage._command_engine()
    with pytest.raises(waking.CommandError) as caught:
        disabled.resolve("extension add value")
    assert caught.value.diagnostic.code.value == "resolution.unknown_subcommand"
