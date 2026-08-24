from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event.filter import option
from astrbot.builtin_stars.builtin_commands.commands.admin import AdminCommands
from astrbot.builtin_stars.builtin_commands.commands.bot import (
    BotCommands,
    _flag_enabled,
)
from astrbot.builtin_stars.builtin_commands.commands.chat import ChatCommands
from astrbot.builtin_stars.builtin_commands.commands.help import HelpCommand
from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands
from astrbot.builtin_stars.builtin_commands.commands.plugin import PluginCommands
from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.builtin_stars.builtin_commands.main import Main
from astrbot.core.command import (
    CommandEngine,
    CommandError,
    CommandErrorCode,
    build_command_catalog,
)
from astrbot.core.command.schema import compile_command_schema
from astrbot.core.provider.entities import ProviderType
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import ActionPermissionFilter
from astrbot.core.star.register.star_handler import collect_plugin_module_declarations
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    materialize_handler_declarations,
)
from tests.unit.builtin_command_fakes import FakeI18n


class DummyEvent:
    def __init__(
        self,
        *,
        message_str: str,
        unified_msg_origin: str = "napcat:FriendMessage:42",
        platform_name: str = "napcat",
        platform_id: str = "napcat",
        role: str = "admin",
        group_id: str | None = None,
        sender_id: str = "42",
        supported_actions: tuple[str, ...] = (),
    ) -> None:
        self.message_str = message_str
        self.unified_msg_origin = unified_msg_origin
        self._platform_name = platform_name
        self._platform_id = platform_id
        self.role = role
        self._group_id = group_id
        self._sender_id = sender_id
        self.result = None
        self.extras: dict[str, object] = {}
        self.temporary_files: list[str] = []
        self.call_llm = False
        self.stopped = False
        self.sent: list[object] = []
        self._supported_actions = supported_actions

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self.extras
        return self.extras.get(key, default)

    def set_result(self, result) -> None:
        self.result = result

    async def send(self, result) -> None:
        self.sent.append(result)
        self.result = result

    def get_platform_name(self) -> str:
        return self._platform_name

    def get_platform_id(self) -> str:
        return self._platform_id

    def get_group_id(self) -> str | None:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    def track_temporary_local_file(self, path: str) -> None:
        self.temporary_files.append(path)

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm

    def supports_platform_action(self, action_name: str) -> bool:
        return action_name in self._supported_actions

    def clear_result(self) -> None:
        self.result = None

    def stop_event(self) -> None:
        self.stopped = True
        if self.result is not None and hasattr(self.result, "stop_event"):
            self.result.stop_event()

    def is_stopped(self) -> bool:
        if self.stopped:
            return True
        checker = getattr(self.result, "is_stopped", None)
        return bool(callable(checker) and checker())


def _plain_text(result) -> str:
    return result.chain[0].text


def test_all_builtin_extension_commands_use_native_command_schemas():
    expected_handlers = {
        "admin_list",
        "admin_grant",
        "admin_revoke",
        "conversation_create",
        "conversation_create_for",
        "conversation_delete",
        "conversation_history",
        "conversation_list",
        "conversation_rename",
        "conversation_reset",
        "conversation_stats",
        "conversation_switch",
        "help",
        "bot_status",
        "bot_enable",
        "bot_disable",
        "bot_leave",
        "chat_disable",
        "chat_enable",
        "chat_status",
        "model_list",
        "model_set",
        "session_name",
        "session_info",
        "persona_list",
        "persona_set",
        "persona_status",
        "persona_unset",
        "persona_show",
        "plugin_install",
        "plugin_show",
        "plugin_list",
        "plugin_disable",
        "plugin_enable",
        "provider_list",
        "provider_set_llm",
        "provider_set_stt",
        "provider_set_tts",
        "task_stop",
        "variable_set",
        "variable_unset",
        "flow_enable",
        "flow_disable",
        "flow_unset",
        "flow_status",
    }
    assert expected_handlers <= vars(Main).keys()

    required_params = {
        "admin_revoke": ("user_id",),
        "conversation_create_for": ("session_id",),
        "model_set": ("model_or_index",),
        "admin_grant": ("user_id",),
        "persona_set": ("persona_id",),
        "persona_show": ("persona_id",),
        "plugin_install": ("repository_url",),
        "plugin_show": ("plugin_name",),
        "plugin_disable": ("plugin_name",),
        "plugin_enable": ("plugin_name",),
        "provider_set_llm": ("index",),
        "provider_set_stt": ("index",),
        "provider_set_tts": ("index",),
        "conversation_rename": ("title",),
        "variable_set": ("key", "value"),
        "conversation_switch": ("index",),
        "variable_unset": ("key",),
    }
    for handler_name, names in required_params.items():
        params = compile_command_schema(getattr(Main, handler_name)).params
        assert tuple(param.name for param in params) == names
    assert all(param.is_required for param in params)


@pytest.mark.asyncio
async def test_admin_list_reports_authorization_bindings():
    bindings = [
        SimpleNamespace(
            subject_id="im:napcat:bot:42",
            role="session_admin",
            scope_type="session",
        )
    ]
    authz = SimpleNamespace(list_bindings=AsyncMock(return_value=bindings))
    context = SimpleNamespace(authz=authz, i18n=FakeI18n())
    command = AdminCommands(context)

    event = DummyEvent(message_str="admin list")
    await command.list_admins(event)
    assert _plain_text(event.result) == (
        "Authorization bindings:\n- im:napcat:bot:42: session_admin (session)"
    )
    assert event.result.is_stopped()
    authz.list_bindings.assert_awaited_once_with(event)

    authz.list_bindings.reset_mock(return_value=True)
    authz.list_bindings.return_value = []
    empty_event = DummyEvent(message_str="admin list")
    await command.list_admins(empty_event)
    assert _plain_text(empty_event.result) == "Authorization bindings:\n- none"


@pytest.mark.asyncio
async def test_admin_grant_and_revoke_delegate_to_authorization_capability():
    authz = SimpleNamespace(
        grant_session_admin=AsyncMock(),
        revoke_session_admin=AsyncMock(return_value=True),
    )
    context = SimpleNamespace(authz=authz, i18n=FakeI18n())
    command = AdminCommands(context)

    grant_event = DummyEvent(message_str="admin grant 42")
    revoke_event = DummyEvent(message_str="admin revoke 42")
    await command.grant(grant_event, "42")
    await command.revoke(revoke_event, "42")

    authz.grant_session_admin.assert_awaited_once_with(grant_event, "42")
    authz.revoke_session_admin.assert_awaited_once_with(revoke_event, "42")
    assert _plain_text(grant_event.result) == "Session administrator granted."
    assert _plain_text(revoke_event.result) == "Session administrator revoked."


@pytest.mark.asyncio
async def test_admin_commands_report_authorization_denial():
    authz = SimpleNamespace(
        grant_session_admin=AsyncMock(side_effect=PermissionError),
        revoke_session_admin=AsyncMock(side_effect=PermissionError),
    )
    context = SimpleNamespace(authz=authz, i18n=FakeI18n())
    command = AdminCommands(context)

    grant_event = DummyEvent(message_str="admin grant 42")
    await command.grant(grant_event, "42")

    assert _plain_text(grant_event.result) == "Authorization denied."

    revoke_event = DummyEvent(message_str="admin revoke 42")
    await command.revoke(revoke_event, "42")

    assert _plain_text(revoke_event.result) == "Authorization denied."


@pytest.mark.asyncio
async def test_help_command_defaults_to_plain_text(monkeypatch):
    async def fake_list_commands():
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            },
            {
                "reserved": True,
                "enabled": True,
                "type": "command_group",
                "parent_signature": None,
                "effective_command": "plugin",
                "description": "Plugin management",
            },
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "model",
                "description": "View or switch the current model",
            },
            {
                "reserved": True,
                "enabled": True,
                "type": "group",
                "parent_signature": None,
                "effective_command": "variable",
                "description": "Manage session variables",
                "sub_commands": [
                    {
                        "reserved": True,
                        "enabled": True,
                        "effective_command": "variable set",
                        "description": "Set a session variable",
                    }
                ],
            },
        ]

    async def fake_dashboard_version():
        return "test-ui"

    command = HelpCommand(
        SimpleNamespace(
            runtime_info=SimpleNamespace(
                commands=fake_list_commands,
                version="9.9.9",
                dashboard_version=fake_dashboard_version,
            ),
            i18n=FakeI18n(),
        )
    )
    event = DummyEvent(message_str="help")
    await command.help(event)

    text = _plain_text(event.result)
    assert "AstrBot v" in text
    assert "/persona - View or switch persona" in text
    assert "/plugin - Plugin management" in text
    assert "/model - View or switch the current model" in text
    assert "/variable - Manage session variables" in text
    assert "  /variable set - Set a session variable" in text
    assert "/help --image" in text
    assert event.result.use_t2i_ is False
    assert event.result.is_stopped()
    assert event.call_llm is False


@pytest.mark.asyncio
async def test_help_command_supports_image_mode(monkeypatch):
    async def fake_list_commands():
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    render_calls: list[dict[str, object]] = []

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        render_calls.append(
            {
                "text": text,
                "template_name": template_name,
            }
        )
        return "D:/Documents/Github/AstrBot/data/temp/help-card.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/Documents/Github/AstrBot/data/temp/help-card.png"
        return "token-123"

    command = HelpCommand(
        SimpleNamespace(
            runtime_info=SimpleNamespace(
                commands=fake_list_commands,
                version="9.9.9",
                dashboard_version=fake_dashboard_version,
            ),
            i18n=FakeI18n(),
            config=SimpleNamespace(
                get=lambda umo=None: {"callback_api_base": "http://127.0.0.1:6185"},
            ),
            rendering=SimpleNamespace(text_to_image=fake_render_t2i),
            files=SimpleNamespace(publish=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert len(render_calls) == 1
    assert render_calls[0]["template_name"] == "astrbot_help"
    markup = str(render_calls[0]["text"])
    assert "help-grid" in markup
    assert "AstrBot v9.9.9" in markup
    assert "WebUI test-ui" in markup

    assert event.result.chain[0].file == (
        "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    )
    assert event.result.chain[0].path == ""
    assert event.result.use_t2i_ is False
    assert event.temporary_files == [
        "D:/Documents/Github/AstrBot/data/temp/help-card.png"
    ]
    assert event.call_llm is False
    assert event.result.is_stopped()


@pytest.mark.asyncio
async def test_help_command_sends_local_image_when_callback_url_is_unavailable(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "help-card.png"

    async def fake_list_commands():
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return str(image_path)

    command = HelpCommand(
        SimpleNamespace(
            runtime_info=SimpleNamespace(
                commands=fake_list_commands,
                version="9.9.9",
                dashboard_version=fake_dashboard_version,
            ),
            i18n=FakeI18n(),
            config=SimpleNamespace(get=lambda umo=None: {}),
            rendering=SimpleNamespace(text_to_image=fake_render_t2i),
            files=SimpleNamespace(publish=AsyncMock()),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == image_path.resolve().as_uri()
    assert event.result.chain[0].path == str(image_path.resolve())
    assert event.result.use_t2i_ is False
    assert event.temporary_files == [str(image_path)]


@pytest.mark.asyncio
async def test_help_command_sends_local_image_when_file_token_registration_fails(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "help-card.png"

    async def fake_list_commands():
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return str(image_path)

    async def fake_register_file(path: str) -> str:
        assert path == str(image_path)
        raise RuntimeError("file service unavailable")

    command = HelpCommand(
        SimpleNamespace(
            runtime_info=SimpleNamespace(
                commands=fake_list_commands,
                version="9.9.9",
                dashboard_version=fake_dashboard_version,
            ),
            i18n=FakeI18n(),
            config=SimpleNamespace(
                get=lambda umo=None: {"callback_api_base": "http://127.0.0.1:6185"},
            ),
            rendering=SimpleNamespace(text_to_image=fake_render_t2i),
            files=SimpleNamespace(publish=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == image_path.resolve().as_uri()
    assert event.result.chain[0].path == str(image_path.resolve())
    assert event.temporary_files == [str(image_path)]


@pytest.mark.asyncio
async def test_help_command_uses_file_token_for_local_image_when_callback_is_available(
    monkeypatch,
):
    async def fake_list_commands():
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return "D:/Documents/Github/AstrBot/data/temp/help-card.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/Documents/Github/AstrBot/data/temp/help-card.png"
        return "token-123"

    command = HelpCommand(
        SimpleNamespace(
            runtime_info=SimpleNamespace(
                commands=fake_list_commands,
                version="9.9.9",
                dashboard_version=fake_dashboard_version,
            ),
            i18n=FakeI18n(),
            config=SimpleNamespace(
                get=lambda umo=None: {"callback_api_base": "http://127.0.0.1:6185"},
            ),
            rendering=SimpleNamespace(text_to_image=fake_render_t2i),
            files=SimpleNamespace(publish=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == (
        "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    )
    assert event.temporary_files == [
        "D:/Documents/Github/AstrBot/data/temp/help-card.png"
    ]


@pytest.mark.asyncio
async def test_plugin_show_lists_command_signatures_and_aliases():
    catalogs = RuntimeCatalogs()
    plugin = StarMetadata(
        name="demo",
        author="Tester",
        version="1.2.3",
        module_path="plugin.demo",
        activated=True,
    )
    catalogs.plugins.publish(plugin)

    async def greet(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    greet.__module__ = "plugin.demo"
    greet_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.demo_greet",
        handler_name="greet",
        handler_module_path="plugin.demo",
        handler=greet,
        event_filters=[],
        desc="Greet someone",
    )
    greet_filter = CommandFilter("greet", alias={"hello"})
    greet_filter.init_handler_md(greet_handler)
    greet_handler.event_filters.append(greet_filter)
    catalogs.handlers.append(greet_handler)

    async def tools(self, event) -> None: ...

    tools.__module__ = "plugin.demo"
    tools_handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name="plugin.demo_tools",
        handler_name="tools",
        handler_module_path="plugin.demo",
        handler=tools,
        event_filters=[],
        desc="Tool commands",
    )
    tools_handler.event_filters.append(CommandGroupFilter("tools", alias={"t"}))
    catalogs.handlers.append(tools_handler)

    from astrbot.core.star.plugin_context import RuntimeInfoCapability

    context = SimpleNamespace(
        runtime_info=RuntimeInfoCapability(
            catalogs,
            MagicMock(),
            demo_mode=False,
        ),
        i18n=FakeI18n(),
    )
    command = PluginCommands(context)
    event = DummyEvent(message_str="plugin show demo")

    await command.show(event, "demo")

    text = _plain_text(event.result)
    assert "/greet (name(str),force[--force/-f](bool)=False) [aliases: hello]" in text
    assert "/tools [aliases: t]" in text
    assert "Greet someone" in text
    assert "Tool commands" in text


@pytest.mark.asyncio
async def test_chat_commands_report_and_set_session_service_status():
    calls: list[tuple[str, dict[str, bool]]] = []
    settings = {"llm_enabled": True}

    async def session_get(
        umo: str, key: str, default: dict[str, bool]
    ) -> dict[str, bool]:
        assert umo == "napcat:FriendMessage:42"
        assert key == "session_service_config"
        assert default == {}
        return dict(settings)

    async def session_put(umo: str, key: str, value: dict[str, bool]) -> None:
        assert umo == "napcat:FriendMessage:42"
        assert key == "session_service_config"
        calls.append((umo, dict(value)))
        settings.update(value)

    command = ChatCommands(
        SimpleNamespace(
            preferences=SimpleNamespace(
                session_get=session_get,
                session_put=session_put,
            ),
            i18n=FakeI18n(),
        )
    )
    status_event = DummyEvent(message_str="chat status")
    await command.status(status_event)
    assert "enabled" in _plain_text(status_event.result)

    disable_event = DummyEvent(message_str="chat disable")
    await command.set_enabled(disable_event, False)
    enable_event = DummyEvent(message_str="chat enable")
    await command.set_enabled(enable_event, True)

    assert calls == [
        ("napcat:FriendMessage:42", {"llm_enabled": False}),
        ("napcat:FriendMessage:42", {"llm_enabled": True}),
    ]
    assert "disabled" in _plain_text(disable_event.result)
    assert "enabled" in _plain_text(enable_event.result)


def test_bot_flag_enabled_defaults_missing_and_invalid_values():
    assert _flag_enabled({}, "session_enabled") is True
    assert _flag_enabled({"session_enabled": False}, "session_enabled") is False
    assert _flag_enabled({"session_enabled": "no"}, "session_enabled") is True


@pytest.mark.asyncio
async def test_bot_commands_report_and_set_session_enabled():
    settings = {"llm_enabled": False, "tts_enabled": True}

    async def session_get(umo: str, key: str, default: dict) -> dict:
        assert umo == "napcat:FriendMessage:42"
        assert key == "session_service_config"
        return dict(settings)

    async def session_put(umo: str, key: str, value: dict) -> None:
        assert umo == "napcat:FriendMessage:42"
        assert key == "session_service_config"
        settings.clear()
        settings.update(value)

    command = BotCommands(
        SimpleNamespace(
            preferences=SimpleNamespace(
                session_get=session_get,
                session_put=session_put,
            ),
            i18n=FakeI18n(),
            runtime_info=SimpleNamespace(version="9.9.9"),
        )
    )
    status_event = DummyEvent(message_str="bot status")
    await command.status(status_event)
    status_text = _plain_text(status_event.result)
    assert "v9.9.9" in status_text
    assert "Session: enabled" in status_text
    assert "LLM: disabled" in status_text
    assert "TTS: enabled" in status_text

    disable_event = DummyEvent(message_str="bot disable")
    await command.set_enabled(disable_event, False)
    enable_event = DummyEvent(message_str="bot enable")
    await command.set_enabled(enable_event, True)

    assert settings["session_enabled"] is True
    assert "disabled" in _plain_text(disable_event.result)
    assert "enabled" in _plain_text(enable_event.result)


@pytest.mark.asyncio
async def test_bot_leave_requires_group_support_and_confirmation():
    invokes: list[tuple[object, str, dict]] = []

    async def invoke_for_event(event, action_name: str, **kwargs):
        invokes.append((event, action_name, kwargs))

    command = BotCommands(
        SimpleNamespace(
            i18n=FakeI18n(),
            platform_actions=SimpleNamespace(invoke_for_event=invoke_for_event),
        )
    )

    private_event = DummyEvent(message_str="bot leave --confirm")
    await command.leave(private_event, confirm=True)
    assert "group chats" in _plain_text(private_event.result)
    assert invokes == []

    unsupported = DummyEvent(message_str="bot leave --confirm", group_id="99")
    await command.leave(unsupported, confirm=True)
    assert "does not support" in _plain_text(unsupported.result)
    assert invokes == []

    unconfirmed = DummyEvent(
        message_str="bot leave",
        group_id="99",
        supported_actions=("leave_group",),
    )
    await command.leave(unconfirmed, confirm=False)
    assert "--confirm" in _plain_text(unconfirmed.result)
    assert invokes == []

    confirmed = DummyEvent(
        message_str="bot leave --confirm",
        group_id="99",
        supported_actions=("leave_group",),
    )
    await command.leave(confirmed, confirm=True)
    assert invokes == [(confirmed, "leave_group", {"group_id": "99"})]
    assert confirmed.stopped is True
    assert confirmed.result is None
    assert "Leaving" in confirmed.sent[0].chain[0].text


@pytest.mark.asyncio
async def test_bot_leave_reports_failure_without_leaving_result():
    async def invoke_for_event(event, action_name: str, **kwargs):
        raise RuntimeError("adapter down")

    command = BotCommands(
        SimpleNamespace(
            i18n=FakeI18n(),
            platform_actions=SimpleNamespace(invoke_for_event=invoke_for_event),
        )
    )
    event = DummyEvent(
        message_str="bot leave --confirm",
        group_id="99",
        supported_actions=("leave_group",),
    )
    await command.leave(event, confirm=True)
    assert "Leaving" in event.sent[0].chain[0].text
    assert "Failed to leave" in event.sent[1].chain[0].text
    assert event.stopped is True
    assert event.result is None


@pytest.mark.asyncio
async def test_persona_command_switches_current_conversation_persona():
    updates: list[tuple[str, str]] = []

    async def current_id(_umo: str) -> str:
        return "abcd-1234"

    async def get(_umo: str, _conversation_id: str, *, create_if_missing: bool):
        assert create_if_missing is True
        return SimpleNamespace(title="Current", persona_id=None)

    async def update(umo: str, *, persona_id: str, **kwargs) -> None:
        _ = kwargs
        updates.append((umo, persona_id))

    async def resolve(**kwargs):
        _ = kwargs
        return ("default", {"name": "default"}, None, False)

    context = SimpleNamespace(
        conversations=SimpleNamespace(
            current_id=current_id,
            get=get,
            update=update,
        ),
        personas=SimpleNamespace(
            resolve=resolve,
            get=lambda persona_id: (
                {"name": persona_id, "prompt": "prompt"}
                if persona_id == "assistant"
                else None
            ),
        ),
        config=SimpleNamespace(get=lambda umo=None: {"provider_settings": {}}),
        i18n=FakeI18n(),
    )

    command = PersonaCommands(context)
    event = DummyEvent(message_str="persona set assistant")
    await command.set_persona(event, "assistant")

    assert updates == [("napcat:FriendMessage:42", "assistant")]
    assert "Persona updated" in _plain_text(event.result)


def test_persona_operations_are_registered_as_native_subcommands():
    persona_group = Main.persona.parent_group
    subcommands = {
        filter_ref.command_name: filter_ref
        for filter_ref in persona_group.sub_command_filters
        if isinstance(filter_ref, CommandFilter)
    }

    assert persona_group.group_name == "persona"
    assert set(subcommands) == {"list", "set", "show", "status", "unset"}
    assert subcommands["status"].alias == set()
    assert subcommands["set"].handler_params[0].is_greedy is True
    assert subcommands["set"].handler_params[0].is_required is True
    assert subcommands["show"].handler_params[0].is_required is True


def test_provider_operations_are_registered_as_native_subcommands():
    provider_group = Main.provider.parent_group
    root_subcommands = {
        filter_ref.command_name: filter_ref
        for filter_ref in provider_group.sub_command_filters
        if isinstance(filter_ref, CommandFilter)
    }
    set_group = next(
        filter_ref
        for filter_ref in provider_group.sub_command_filters
        if isinstance(filter_ref, CommandGroupFilter) and filter_ref.group_name == "set"
    )
    set_subcommands = {
        filter_ref.command_name: filter_ref
        for filter_ref in set_group.sub_command_filters
        if isinstance(filter_ref, CommandFilter)
    }

    assert provider_group.group_name == "provider"
    assert set(root_subcommands) == {"list"}
    assert set(set_subcommands) == {"llm", "stt", "tts"}
    for name in ("llm", "stt", "tts"):
        assert set_subcommands[name].handler_params[0].value_type is int
        assert set_subcommands[name].handler_params[0].is_required is True


def test_model_operations_are_registered_as_native_subcommands():
    model_group = Main.model.parent_group
    subcommands = {
        filter_ref.command_name: filter_ref
        for filter_ref in model_group.sub_command_filters
        if isinstance(filter_ref, CommandFilter)
    }

    assert model_group.group_name == "model"
    assert set(subcommands) == {"list", "set"}
    assert subcommands["set"].handler_params[0].is_greedy is True
    assert subcommands["set"].handler_params[0].is_required is True


def test_builtin_command_names_follow_grouped_cli_conventions():
    def command_names(group: CommandGroupFilter) -> set[str]:
        return {
            filter_ref.command_name
            for filter_ref in group.sub_command_filters
            if isinstance(filter_ref, CommandFilter)
        }

    expected_groups = {
        "bot": {"disable", "enable", "leave", "status"},
        "session": {"info", "name"},
        "conversation": {
            "create",
            "create-for",
            "delete",
            "history",
            "list",
            "rename",
            "reset",
            "stats",
            "switch",
        },
        "task": {"stop"},
        "model": {"list", "set"},
        "variable": {"set", "unset"},
        "chat": {"disable", "enable", "status"},
        "flow": {"disable", "enable", "status", "unset"},
        "admin": {"grant", "list", "revoke"},
        "persona": {"list", "set", "show", "status", "unset"},
        "plugin": {"disable", "enable", "install", "list", "show"},
    }
    for attribute, expected in expected_groups.items():
        group = getattr(Main, attribute).parent_group
        assert group.group_name == attribute
        assert command_names(group) == expected

    history_param = compile_command_schema(Main.conversation_history).params[0]
    list_param = compile_command_schema(Main.conversation_list).params[0]
    leave_param = compile_command_schema(Main.bot_leave).params[0]
    assert history_param.option.names == ("--page", "-p")
    assert list_param.option.names == ("--page", "-p")
    assert history_param.default == 1
    assert list_param.default == 1
    assert leave_param.option.names == ("--confirm", "-c")
    assert leave_param.default is False


def test_non_public_builtin_commands_declare_the_planned_actions():
    from astrbot.builtin_stars.builtin_commands import main as builtin_commands_main

    declarations = collect_plugin_module_declarations(builtin_commands_main)
    handlers = materialize_handler_declarations(list(declarations.handlers))
    actions = {
        handler.handler_name: next(
            (
                filter_ref.action
                for filter_ref in handler.event_filters
                if isinstance(filter_ref, ActionPermissionFilter)
            ),
            None,
        )
        for handler in handlers
    }

    assert {
        "session_info": "session.read",
        "bot_status": "session.read",
        "bot_enable": "session.manage",
        "bot_disable": "session.manage",
        "bot_leave": "session.manage",
        "task_stop": "session.manage",
        "conversation_create": "session.manage",
        "conversation_stats": "session.read",
        "conversation_history": "session.read",
        "conversation_list": "session.read",
        "conversation_switch": "session.manage",
        "conversation_rename": "session.manage",
        "variable_set": "session.manage",
        "variable_unset": "session.manage",
        "plugin_list": "extension.read",
        "plugin_show": "extension.read",
        "conversation_create_for": "session.assign",
    }.items() <= actions.items()


def test_normalized_builtin_paths_resolve_and_legacy_subcommands_do_not():
    # Static declarations intentionally have no live handler metadata. Build the
    # catalog through the same materialization boundary as the plugin runtime.
    from astrbot.builtin_stars.builtin_commands import main as builtin_commands_main

    declarations = collect_plugin_module_declarations(builtin_commands_main)
    handlers = materialize_handler_declarations(list(declarations.handlers))
    engine = CommandEngine(build_command_catalog(handlers))

    plugin = engine.resolve("plugin list")
    provider = engine.resolve("provider set llm 2")
    conversations = engine.resolve("conversation list --page 3")

    assert plugin.resolution.command_path == ("plugin", "list")
    assert provider.resolution.command_path == ("provider", "set", "llm")
    assert conversations.resolution.command_path == ("conversation", "list")
    entry = conversations.resolution.entries[0]
    assert dict(engine.bind(entry, conversations).values) == {"page": 3}

    flow = engine.resolve("flow enable")
    assert flow.resolution.command_path == ("flow", "enable")

    bot_leave = engine.resolve("bot leave --confirm")
    assert bot_leave.resolution.command_path == ("bot", "leave")
    bot_entry = bot_leave.resolution.entries[0]
    assert dict(engine.bind(bot_entry, bot_leave).values) == {"confirm": True}

    with pytest.raises(CommandError) as legacy:
        engine.resolve("plugin ls")
    assert legacy.value.diagnostic.code is CommandErrorCode.UNKNOWN_SUBCOMMAND

    with pytest.raises(CommandError) as flow_legacy:
        engine.resolve("flow on")
    assert flow_legacy.value.diagnostic.code is CommandErrorCode.UNKNOWN_SUBCOMMAND


class DummyProvider:
    def __init__(self) -> None:
        self.model = "model-a"

    def meta(self):
        return SimpleNamespace(
            id="demo",
            model=self.model,
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    async def get_models(self) -> list[str]:
        return ["model-a", "model-b"]

    def get_model(self) -> str:
        return self.model

    def set_model(self, model: str) -> None:
        self.model = model


@pytest.mark.asyncio
async def test_provider_native_switch_methods_use_explicit_provider_types():
    provider = DummyProvider()
    calls = []

    async def set_provider(**kwargs):
        calls.append(kwargs)

    context = SimpleNamespace(
        models=SimpleNamespace(
            on_change=lambda hook: None,
            select=set_provider,
            chat=lambda: (provider,),
            text_to_speech=lambda: (provider,),
            speech_to_text=lambda: (provider,),
        ),
        i18n=FakeI18n(),
    )
    command = ProviderCommands(context)

    await command.set_llm_provider(DummyEvent(message_str="provider set llm 1"), 1)
    await command.set_tts_provider(DummyEvent(message_str="provider set tts 1"), 1)
    await command.set_stt_provider(DummyEvent(message_str="provider set stt 1"), 1)

    assert [call["provider_type"] for call in calls] == [
        ProviderType.CHAT_COMPLETION,
        ProviderType.TEXT_TO_SPEECH,
        ProviderType.SPEECH_TO_TEXT,
    ]
    assert all(call["provider_id"] == "demo" for call in calls)


@pytest.mark.asyncio
async def test_provider_model_commands_list_and_switch_by_index():
    provider = DummyProvider()

    async def set_provider(**kwargs):
        _ = kwargs
        return None

    context = SimpleNamespace(
        models=SimpleNamespace(
            on_change=lambda hook: None,
            select=set_provider,
            chat=lambda: (provider,),
            text_to_speech=lambda: (),
            speech_to_text=lambda: (),
            using_chat=lambda umo=None: provider,
            using_text_to_speech=lambda umo=None: None,
            using_speech_to_text=lambda umo=None: None,
        ),
        config=SimpleNamespace(get=lambda umo=None: {"provider_settings": {}}),
        i18n=FakeI18n(),
    )

    command = ProviderCommands(context)

    list_event = DummyEvent(message_str="model")
    await command.list_models(list_event)
    assert "Available models" in _plain_text(list_event.result)
    assert "model-b" in _plain_text(list_event.result)

    switch_event = DummyEvent(message_str="model 2")
    await command.set_model(switch_event, "2")
    assert provider.model == "model-b"
    assert "Switched model." in _plain_text(switch_event.result)
