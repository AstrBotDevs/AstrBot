import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial import qqofficial_platform_adapter as qq
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest.fixture(params=[qq.QQOfficialPlatformAdapter, QQOfficialWebhookPlatformAdapter])
def adapter_factory(request):
    def create(**overrides):
        config = {
            "id": "qq-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
            "use_markdown": False,
            **overrides,
        }
        adapter = request.param(config, {}, asyncio.Queue())
        adapter.client.api = SimpleNamespace(
            post_group_message=AsyncMock(return_value={"id": "sent-group"}),
            post_message=AsyncMock(return_value={"id": "sent-channel"}),
        )
        return adapter

    return create


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,scene",
    [
        ("on_group_at_message_create", "group"),
        ("on_group_message_create", "group"),
        ("on_at_message_create", "channel"),
    ],
)
async def test_incoming_event_waits_for_route_persistence(
    adapter_factory, handler, scene, monkeypatch
):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def write(*args):
        entered.set()
        await release.wait()

    store = SimpleNamespace(put_async=AsyncMock(side_effect=write))
    monkeypatch.setattr(qq, "sp", store)
    monkeypatch.setattr(
        qq.QQOfficialPlatformAdapter,
        "_parse_from_qqofficial",
        AsyncMock(return_value=SimpleNamespace()),
    )
    adapter = adapter_factory()
    commit = Mock()
    monkeypatch.setattr(adapter.client, "_commit", commit)
    task = asyncio.create_task(
        getattr(adapter.client, handler)(
            SimpleNamespace(group_openid="target", channel_id="target")
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        commit.assert_not_called()
        release.set()
        await asyncio.wait_for(task, timeout=5)
        commit.assert_called_once()
        store.put_async.assert_awaited_once_with(
            "qqofficial", "qq-test:123", "group_scene:target", scene
        )
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["group", "channel"])
async def test_route_survives_new_adapter_and_store(
    adapter_factory, scene, tmp_path, monkeypatch
):
    database = SQLiteDatabase(str(tmp_path / "routes.db"))
    await database.initialize()
    store = SharedPreferences(database, tmp_path / "unused.json")
    try:
        monkeypatch.setattr(qq, "sp", store)
        original = adapter_factory()
        await original.remember_session_scene("target", scene)
        await store.close()
        await database.engine.dispose()

        database = SQLiteDatabase(str(tmp_path / "routes.db"))
        await database.initialize()
        store = SharedPreferences(database, tmp_path / "unused.json")
        monkeypatch.setattr(qq, "sp", store)
        restarted = adapter_factory()
        assert restarted._session_scene == {}
        assert restarted._session_last_message_id == {}

        # Unique sessions must still resolve to the raw destination ID.
        await restarted.send_by_session(
            MessageSession("qq-test", MessageType.GROUP_MESSAGE, "member_target"),
            MessageChain(chain=[Plain("scheduled notification")]),
        )
        api = restarted.client.api
        selected = api.post_group_message if scene == "group" else api.post_message
        other = api.post_message if scene == "group" else api.post_group_message
        selected.assert_awaited_once()
        other.assert_not_awaited()
        payload = selected.await_args.kwargs
        assert payload["group_openid" if scene == "group" else "channel_id"] == "target"
        assert "msg_id" not in payload
        assert restarted._session_scene == {"target": scene}

        # Neither another instance nor another bot may reuse this route.
        for overrides in ({"id": "other-instance"}, {"appid": "other-app"}):
            unrelated = adapter_factory(**overrides)
            with pytest.raises(ValueError, match="Unknown delivery scene"):
                await unrelated.send_by_session(
                    MessageSession(
                        unrelated.meta().id, MessageType.GROUP_MESSAGE, "target"
                    ),
                    MessageChain(chain=[Plain("hello")]),
                )
            unrelated.client.api.post_group_message.assert_not_awaited()
            unrelated.client.api.post_message.assert_not_awaited()
    finally:
        await store.close()
        await database.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["group", "channel"])
@pytest.mark.parametrize("cached_id", [None, "expired-reply-id"])
async def test_proactive_send_never_uses_cached_reply_id(
    adapter_factory, scene, cached_id, monkeypatch
):
    store = SimpleNamespace(get_async=AsyncMock())
    monkeypatch.setattr(qq, "sp", store)
    adapter = adapter_factory()
    adapter._session_scene["target"] = scene
    if cached_id:
        adapter._session_last_message_id["target"] = cached_id
    session = MessageSession("qq-test", MessageType.GROUP_MESSAGE, "target")
    # A second send must not use the bot's own ID cached by the first send.
    for _ in range(2):
        await adapter.send_by_session(session, MessageChain(chain=[Plain("hello")]))
    api = adapter.client.api
    selected = api.post_group_message if scene == "group" else api.post_message
    assert selected.await_count == 2
    for call in selected.await_args_list:
        assert "msg_id" not in call.kwargs
        if scene == "channel":
            assert "msg_type" not in call.kwargs
    store.get_async.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_scene", [None, "friend", "invalid", {"scene": "group"}]
)
async def test_unknown_route_never_calls_a_send_api(
    adapter_factory, stored_scene, monkeypatch
):
    monkeypatch.setattr(
        qq, "sp", SimpleNamespace(get_async=AsyncMock(return_value=stored_scene))
    )
    adapter = adapter_factory()
    adapter._session_last_message_id["target"] = "cached-id"
    with pytest.raises(ValueError, match="Unknown delivery scene"):
        await adapter.send_by_session(
            MessageSession("qq-test", MessageType.GROUP_MESSAGE, "target"),
            MessageChain(chain=[Plain("hello")]),
        )
    adapter.client.api.post_group_message.assert_not_awaited()
    adapter.client.api.post_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_write_failure_is_retried_and_unchanged_routes_are_not_rewritten(
    adapter_factory, monkeypatch
):
    store = SimpleNamespace(
        put_async=AsyncMock(side_effect=[OSError("disk error"), None, None])
    )
    monkeypatch.setattr(qq, "sp", store)
    adapter = adapter_factory()
    await adapter.remember_session_scene("target", "group")
    assert "target" not in adapter._session_scene
    await adapter.remember_session_scene("target", "group")
    assert adapter._session_scene["target"] == "group"
    await adapter.remember_session_scene("target", "group")
    assert store.put_async.await_count == 2
    await adapter.remember_session_scene("target", "channel")
    assert adapter._session_scene["target"] == "channel"
    store.put_async.assert_awaited_with(
        "qqofficial", "qq-test:123", "group_scene:target", "channel"
    )
    await adapter.remember_session_scene("private-user", "friend")
    assert store.put_async.await_count == 3
