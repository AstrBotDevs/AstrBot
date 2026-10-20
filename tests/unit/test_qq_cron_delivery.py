"""Verify QQ scheduled delivery without live credentials or network calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Plain
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.star.context import Context
from astrbot.core.tools.message_tools import SendMessageToUserTool

GROUP_OPENID = "A" * 32
CURRENT_SESSION = f"qq-test:GroupMessage:{GROUP_OPENID}"
DELIVERY_KEY = "_send_message_to_user_current_session_delivery_confirmed"


@pytest_asyncio.fixture
async def adapter(monkeypatch):
    """Use the real adapter with a fake QQ API and no cached messages."""
    monkeypatch.setattr("astrbot.core.platform.platform.Metric.upload", AsyncMock())
    platform = QQOfficialPlatformAdapter(
        {
            "id": "qq-test",
            "appid": "test-app-id",
            "secret": "test-only-not-a-real-secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    platform.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "accepted-message"}),
        post_message=AsyncMock(return_value={"id": "accepted-channel-message"}),
    )
    return platform


@pytest.mark.asyncio
async def test_empty_cache_restores_proactive_group_route(adapter):
    """Restart must not require another incoming group message before sending."""
    await adapter.send_by_session(
        MessageSession.from_str(CURRENT_SESSION),
        MessageChain(chain=[Plain("Reminder")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    adapter.client.api.post_message.assert_not_awaited()
    payload = adapter.client.api.post_group_message.await_args.kwargs
    assert payload["group_openid"] == GROUP_OPENID
    assert "msg_id" not in payload
    assert adapter._session_scene[GROUP_OPENID] == "group"
    assert adapter._session_last_message_id[GROUP_OPENID] == "accepted-message"


@pytest.mark.asyncio
async def test_unknown_route_fails_instead_of_silently_skipping(adapter):
    """Ambiguous sessions must never claim success or hit the wrong endpoint."""
    with pytest.raises(RuntimeError, match="delivery context is unavailable"):
        await adapter.send_by_session(
            MessageSession("qq-test", MessageType.GROUP_MESSAGE, "unknown-session"),
            MessageChain(chain=[Plain("Reminder")]),
        )

    adapter.client.api.post_group_message.assert_not_awaited()
    adapter.client.api.post_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_guild_channel_is_not_misrouted_to_group_api(adapter):
    """Known guild channels retain their existing reply routing."""
    adapter._session_scene["1234567890123456789"] = "channel"
    adapter._session_last_message_id["1234567890123456789"] = "incoming-channel-id"

    await adapter.send_by_session(
        MessageSession("qq-test", MessageType.GROUP_MESSAGE, "1234567890123456789"),
        MessageChain(chain=[Plain("Channel reply")]),
    )

    adapter.client.api.post_group_message.assert_not_awaited()
    adapter.client.api.post_message.assert_awaited_once()
    assert adapter.client.api.post_message.await_args.kwargs["msg_id"] == (
        "incoming-channel-id"
    )


@pytest.mark.parametrize("receipt", [None, {}, {"message": "request rejected"}])
@pytest.mark.asyncio
async def test_missing_api_receipt_is_a_send_failure(adapter, receipt):
    """A returned coroutine without a message ID is not a delivery receipt."""
    adapter.client.api.post_group_message.return_value = receipt

    with pytest.raises(RuntimeError, match="message receipt has no id"):
        await adapter.send_by_session(
            MessageSession.from_str(CURRENT_SESSION),
            MessageChain(chain=[Plain("Reminder")]),
        )

    assert GROUP_OPENID not in adapter._session_last_message_id


@pytest_asyncio.fixture
async def delivery_env(tmp_path, adapter):
    """Exercise the real tool, Context, adapter and cron persistence together."""
    db = SQLiteDatabase(str(tmp_path / "delivery.db"))
    await db.initialize()
    context = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[adapter]),
        conversation_manager=SimpleNamespace(),
        get_config=lambda umo: {
            "admins_id": [],
            "provider_ltm_settings": {"group_message_history_enable": False},
        },
        get_llm_tool_manager=lambda: SimpleNamespace(
            get_builtin_tool=lambda tool_class: tool_class()
        ),
    )

    async def send_message(session, message, *, require_delivery_confirmation=False):
        return await Context.send_message(
            context,
            session,
            message,
            require_delivery_confirmation=require_delivery_confirmation,
        )

    context.send_message = send_message
    manager = CronJobManager(db)
    manager.ctx = context
    job = await db.create_cron_job(
        name="Test QQ reminder",
        job_type="active_agent",
        cron_expression="49 11 * * *",
        timezone="Asia/Shanghai",
        payload={"session": CURRENT_SESSION, "note": "Send a reminder"},
        persistent=True,
    )
    env = SimpleNamespace(
        db=db,
        manager=manager,
        adapter=adapter,
        context=context,
        job=job,
        calls=[],
        results=[],
        event=None,
    )

    async def build_main_agent(*, event, plugin_context, config, req):
        env.event = event
        tool_context = SimpleNamespace(
            context=SimpleNamespace(event=event, context=context)
        )

        class FakeRunner:
            state = AgentState.DONE

            async def step_until_done(self, max_step):
                for messages in env.calls:
                    env.results.append(
                        await SendMessageToUserTool().call(
                            tool_context, messages=messages
                        )
                    )
                if False:
                    yield None

            def get_final_llm_resp(self):
                return SimpleNamespace(role="assistant", completion_text="Done")

        return SimpleNamespace(agent_runner=FakeRunner())

    with (
        patch("astrbot.core.astr_main_agent.build_main_agent", build_main_agent),
        patch(
            "astrbot.core.astr_main_agent._get_session_conv",
            AsyncMock(return_value=SimpleNamespace(history="[]")),
        ),
        patch(
            "astrbot.core.cron.manager.persist_agent_history", AsyncMock()
        ) as persist,
    ):
        env.persist = persist
        try:
            yield env
        finally:
            await manager.shutdown()
            await db.engine.dispose()


@pytest.mark.asyncio
async def test_two_mentions_with_space_send_in_one_request(delivery_env):
    """The exact reminder structure must pass validation and receive an ack."""
    delivery_env.calls = [
        [
            {"type": "mention_user", "mention_user_id": "member-a"},
            {"type": "plain", "text": " "},
            {"type": "mention_user", "mention_user_id": "member-b"},
            {"type": "plain", "text": " 该QQ互发消息啦"},
        ]
    ]

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "completed"
    assert saved.last_error is None
    assert delivery_env.event.get_extra(DELIVERY_KEY) is True
    delivery_env.adapter.client.api.post_group_message.assert_awaited_once()
    payload = delivery_env.adapter.client.api.post_group_message.await_args.kwargs
    content = payload["markdown"]["content"]
    assert content == (
        '<qqbot-at-user id="member-a" /> <qqbot-at-user id="member-b" /> 该QQ互发消息啦'
    )
    assert "msg_id" not in payload


@pytest.mark.asyncio
async def test_api_error_marks_done_runner_as_failed(delivery_env):
    """A DONE agent cannot turn a rejected QQ send into a completed task."""
    delivery_env.calls = [[{"type": "plain", "text": "Reminder"}]]
    delivery_env.adapter.client.api.post_group_message.side_effect = RuntimeError(
        "QQ API rejected proactive sending"
    )

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "failed"
    assert "delivery failed" in saved.last_error
    assert delivery_env.event.get_extra(DELIVERY_KEY) is False
    assert "QQ API rejected" in delivery_env.results[0]
    delivery_env.persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_receipt_marks_task_failed(delivery_env):
    """Missing QQ acknowledgements are reflected in durable job status."""
    delivery_env.calls = [[{"type": "plain", "text": "Reminder"}]]
    delivery_env.adapter.client.api.post_group_message.return_value = None

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "failed"
    assert "message receipt has no id" in delivery_env.results[0]


@pytest.mark.parametrize(
    "invalid_message",
    [
        {"type": "plain", "plain": "separator"},
        {"type": "plain", "text": ""},
        {"type": "plain", "text": None},
        {"type": "plain", "text": 123},
        {"type": "plain", "text": "   "},
    ],
)
@pytest.mark.asyncio
async def test_invalid_components_do_not_mark_task_completed(
    delivery_env, invalid_message
):
    """Invalid or whitespace-only messages cannot silently complete a job."""
    delivery_env.calls = [[invalid_message]]

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "failed"
    assert delivery_env.results[0].startswith("error:")
    delivery_env.adapter.client.api.post_group_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_can_correct_bad_arguments_and_complete(delivery_env):
    """A failed argument attempt followed by a confirmed send is recovered."""
    delivery_env.calls = [
        [{"type": "plain", "plain": "wrong field"}],
        [{"type": "plain", "text": "Corrected reminder"}],
    ]

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "completed"
    assert delivery_env.results[0].startswith("error:")
    assert delivery_env.results[1].startswith("Message sent")
    delivery_env.adapter.client.api.post_group_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_success_then_failed_send_is_not_completed(delivery_env):
    """A partial reminder must not hide the final failed message attempt."""
    delivery_env.calls = [
        [{"type": "mention_user", "mention_user_id": "member-a"}],
        [{"type": "plain", "plain": "undelivered reminder"}],
    ]

    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "failed"
    assert delivery_env.event._has_send_oper is True
    assert delivery_env.event.get_extra(DELIVERY_KEY) is False


@pytest.mark.asyncio
async def test_configured_delivery_requires_adapter_acceptance(delivery_env):
    """A configured delivery session must be explicitly accepted by its adapter."""
    await delivery_env.manager._run_job(delivery_env.job.job_id)

    saved = await delivery_env.db.get_cron_job(delivery_env.job.job_id)
    assert saved.status == "failed"
    assert "did not receive explicit acceptance" in saved.last_error
    delivery_env.adapter.client.api.post_group_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_mentions_are_preserved_in_plain_text_mode(adapter):
    """Disabling Markdown must not cause individual mentions to disappear."""
    chain = MessageChain(chain=[At(qq="member-a"), Plain(" Reminder")])
    chain.use_markdown(False)

    await adapter.send_by_session(MessageSession.from_str(CURRENT_SESSION), chain)

    payload = adapter.client.api.post_group_message.await_args.kwargs
    assert payload["content"] == '<qqbot-at-user id="member-a" /> Reminder'
    assert "markdown" not in payload


@pytest.mark.asyncio
async def test_mention_identifiers_cannot_inject_extra_markup():
    """Escape the attribute value instead of treating it as a raw XML fragment."""
    result = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain(chain=[At(qq='member" /><qqbot-cmd-enter text="bad')])
    )

    assert result[0] == (
        '<qqbot-at-user id="member&quot; /&gt;&lt;qqbot-cmd-enter text=&quot;bad" />'
    )


@pytest.mark.asyncio
async def test_plain_text_all_mention_keeps_upstream_behavior():
    """Do not turn the upstream all-member marker into an individual mention."""
    result = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain(chain=[At(qq="all"), Plain("Reminder")])
    )

    assert result[0] == "Reminder"
