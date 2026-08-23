from types import SimpleNamespace

import pytest

from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.plugin_context import I18nCapability
from astrbot.core.star.star import StarMetadata
from tests.unit.builtin_command_fakes import EN_CATALOG, ZH_CATALOG, FakeI18n
from tests.unit.test_builtin_command_extensions import DummyEvent


class _FakePreferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], object] = {}

    async def session_get(self, umo, key, default=None):
        return self.values.get((umo, key), default)


@pytest.mark.asyncio
async def test_i18n_falls_back_to_en_us_then_key():
    catalogs = RuntimeCatalogs()
    catalogs.plugins.publish(
        StarMetadata(
            name="demo",
            author="tester",
            module_path="plugin.demo",
            i18n={
                "zh-CN": {"commands": {}},
                "en-US": {"commands": {"hello.ok": "Hello {name}"}},
            },
        )
    )
    capability = I18nCapability(catalogs, _FakePreferences(), "tester/demo")
    event = DummyEvent(message_str="x")
    event.extras["locale"] = "zh-CN"
    assert await capability.t(event, "hello.ok", name="Ada") == "Hello Ada"
    assert await capability.t(event, "missing.key") == "missing.key"


@pytest.mark.asyncio
async def test_reply_helper_stops_event_without_t2i():
    from astrbot.builtin_stars.builtin_commands.commands.reply import reply_i18n

    event = DummyEvent(message_str="variable set")
    context = SimpleNamespace(i18n=FakeI18n())
    await reply_i18n(context, event, "variable.set.ok", key="foo")  # i18n interpolation
    assert event.result.is_stopped()
    assert event.result.use_t2i_ is False
    assert "foo" in event.result.chain[0].text


@pytest.mark.asyncio
async def test_send_helper_does_not_stop_event():
    from astrbot.builtin_stars.builtin_commands.commands.reply import send_i18n

    event = DummyEvent(message_str="provider list")
    context = SimpleNamespace(i18n=FakeI18n())
    await send_i18n(context, event, "provider.list.testing")
    assert event.result.use_t2i_ is False
    assert event.result.is_stopped() is False


def test_builtin_command_i18n_catalogs_share_keys():
    assert set(ZH_CATALOG["commands"]) == set(EN_CATALOG["commands"])
    assert "provider.list.ok" in EN_CATALOG["commands"]
    assert "provider.list.fail_code" in ZH_CATALOG["commands"]


@pytest.mark.asyncio
async def test_provider_reachability_marks_use_i18n():
    commands = ProviderCommands(
        SimpleNamespace(
            i18n=FakeI18n(),
            models=SimpleNamespace(on_change=lambda _hook: None),
        )
    )
    event = DummyEvent(message_str="provider list")
    assert await commands._reachability_mark(event, True, None) == " (ok)"
    assert await commands._reachability_mark(event, False, None) == " (fail)"
    assert "Timeout" in await commands._reachability_mark(event, False, "Timeout")
    event.extras["locale"] = "zh-CN"
    assert await commands._reachability_mark(event, True, None) == "（可达）"
