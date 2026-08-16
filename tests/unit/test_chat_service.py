import asyncio
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from starlette.datastructures import UploadFile

import astrbot.dashboard.services.chat_service as chat_service_module
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.result_reducer import BotMessageAccumulator
from astrbot.core.webchat.run_coordinator import WebChatRun, WebChatRunCoordinator
from astrbot.dashboard.api import open_api as open_api_routes
from astrbot.dashboard.api.auth import AuthContext as DashboardAuthContext
from astrbot.dashboard.services.chat_service import (
    WEBCHAT_IMAGE_MIME_TYPES,
    ChatRunState,
    ChatService,
    ChatServiceError,
    extract_web_search_refs,
    find_turn_final_assistant_index,
    replace_assistant_conversation_content,
    replace_user_conversation_content,
)


def _service() -> ChatService:
    service = ChatService.__new__(ChatService)
    service.db = MagicMock()
    service.db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(creator="alice", platform_id="webchat")
    )
    service.db.create_platform_session = AsyncMock()
    service.conv_mgr = MagicMock()
    service.platform_history_mgr = MagicMock()
    service.chat_run_states = {}
    service.delete_threads_by_ids = AsyncMock()
    service.preferences = SimpleNamespace(temporary_cache={})
    service.webchat_run_coordinator = WebChatRunCoordinator(WebChatQueueManager())
    return service


def _create_webchat_run(
    service: ChatService,
    *,
    session_id: str,
    username: str,
    request_id: str,
) -> WebChatRun:
    return service.webchat_run_coordinator.create_run(
        session_id=session_id,
        username=username,
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_session_running_is_derived_from_non_subscription_runs() -> None:
    service = _service()
    subscription = service.webchat_run_coordinator.create_run(
        session_id="session-1",
        username="alice",
        request_id="subscription-1",
        kind="subscription",
    )

    assert service._is_session_running("session-1") is False

    request = _create_webchat_run(
        service,
        session_id="session-1",
        username="alice",
        request_id="request-1",
    )
    assert service._is_session_running("session-1") is True

    await service.webchat_run_coordinator.close_run(request)
    assert service._is_session_running("session-1") is False
    await service.webchat_run_coordinator.close_run(subscription)


@pytest.mark.asyncio
async def test_open_api_chat_forwards_dashboard_principal(monkeypatch):
    auth = DashboardAuthContext(
        username="alice",
        scopes=["*"],
        subject="dashboard-account:account-1",
        account_id="account-1",
        sid="sid-1",
        auth_strength="password",
    )
    expected = object()
    captured: dict = {}

    async def fake_streaming_response(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_streaming_response,
    )

    result = await open_api_routes._open_api_chat_response(
        {"message": "hello", "session_id": "session-1"},
        auth,
        MagicMock(),
        MagicMock(),
    )

    assert result is expected
    assert captured["kwargs"]["dashboard_principal"] == {
        "account_id": "account-1",
        "sid": "sid-1",
        "username": "alice",
        "auth_strength": "password",
    }


def _session(
    session_id: str = "session-1", creator: str = "alice", platform_id: str = "webchat"
):
    return SimpleNamespace(
        session_id=session_id,
        creator=creator,
        platform_id=platform_id,
        is_group=0,
    )


def _history_record(
    record_id: int,
    content: dict,
    *,
    checkpoint_id: str | None = None,
    created_at: datetime | None = None,
    platform_id: str = "webchat",
    user_id: str = "session-1",
):
    return SimpleNamespace(
        id=record_id,
        content=content,
        llm_checkpoint_id=checkpoint_id,
        created_at=created_at or datetime.now(UTC),
        platform_id=platform_id,
        user_id=user_id,
        model_dump=lambda: {"id": record_id, "content": content},
    )


async def _collect(async_iterable):
    items = []
    async for item in async_iterable:
        items.append(item)
    return items


def test_replace_user_conversation_content_preserves_system_reminder_and_inserts_text():
    original = [
        {"type": "text", "text": "<system_reminder>keep</system_reminder>"},
        {"type": "image_url", "image_url": {"url": "img"}},
        {"type": "text", "text": "old text"},
        {"type": "text", "text": "second text"},
    ]

    replaced = replace_user_conversation_content(original, "new text")

    assert replaced == [
        {"type": "text", "text": "<system_reminder>keep</system_reminder>"},
        {"type": "image_url", "image_url": {"url": "img"}},
        {"type": "text", "text": "new text"},
    ]


def test_replace_assistant_conversation_content_rewrites_text_and_reasoning():
    original = [
        {"type": "think", "think": "old reasoning"},
        {"type": "text", "text": "old text"},
        {"type": "tool_call", "tool_calls": [{"id": "1"}]},
    ]

    replaced = replace_assistant_conversation_content(
        original,
        "new text",
        "new reasoning",
    )

    assert replaced == [
        {"type": "think", "think": "new reasoning"},
        {"type": "text", "text": "new text"},
        {"type": "tool_call", "tool_calls": [{"id": "1"}]},
    ]


def test_find_turn_final_assistant_index_skips_tool_only_messages():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "tool_calls": [{"id": "call-1"}], "content": None},
        {"role": "assistant", "content": "final answer"},
    ]

    assert find_turn_final_assistant_index(history, 0, len(history)) == 2


def test_bot_message_accumulator_merges_streaming_reasoning_and_tool_results():
    accumulator = BotMessageAccumulator()

    accumulator.add_plain("Hel", chain_type=None, streaming=True)
    accumulator.add_plain("lo", chain_type=None, streaming=True)
    accumulator.add_plain("thinking", chain_type="reasoning", streaming=True)
    accumulator.add_plain(
        '{"id":"call-1","name":"web_search_baidu"}',
        chain_type="tool_call",
        streaming=True,
    )
    accumulator.add_plain(
        '{"id":"call-1","result":"done","ts":123}',
        chain_type="tool_call_result",
        streaming=True,
    )

    assert accumulator.has_content() is True
    assert accumulator.plain_text() == "Hello"
    assert accumulator.reasoning_text() == "thinking"
    assert accumulator.build_message_parts() == [
        {"type": "plain", "text": "Hello"},
        {"type": "think", "think": "thinking"},
        {
            "type": "tool_call",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "web_search_baidu",
                    "result": "done",
                    "finished_ts": 123,
                }
            ],
        },
    ]


def test_bot_message_accumulator_flushes_unfinished_tool_calls_when_requested():
    accumulator = BotMessageAccumulator()

    accumulator.add_plain(
        '{"id":"call-2","name":"web_search_tavily"}',
        chain_type="tool_call",
        streaming=True,
    )

    assert accumulator.build_message_parts(include_pending_tool_calls=True) == [
        {
            "type": "tool_call",
            "tool_calls": [{"id": "call-2", "name": "web_search_tavily"}],
        }
    ]
    assert accumulator.pending_tool_calls == {}


def test_extract_web_search_refs_filters_supported_results_and_adds_favicon():
    preferences = SimpleNamespace(
        temporary_cache={"_ws_favicon": {"https://example.com": "favicon.ico"}}
    )
    refs = extract_web_search_refs(
        "Use <ref>1</ref> but ignore <ref>3</ref>",
        [
            {
                "type": "tool_call",
                "tool_calls": [
                    {
                        "name": "web_search_baidu",
                        "result": (
                            '{"results":[{"index":"1","url":"https://example.com",'
                            '"title":"Example","snippet":"snippet"}]}'
                        ),
                    },
                    {
                        "name": "other_tool",
                        "result": '{"results":[{"index":"3","url":"https://skip"}]}',
                    },
                ],
            }
        ],
        preferences,
    )

    assert refs == {
        "used": [
            {
                "index": "1",
                "url": "https://example.com",
                "title": "Example",
                "snippet": "snippet",
                "favicon": "favicon.ico",
            }
        ]
    }


@pytest.mark.asyncio
async def test_load_current_conversation_history_returns_empty_for_invalid_json():
    service = _service()
    session = _session()
    service.conv_mgr.get_curr_conversation_id = AsyncMock(return_value="conv-1")
    service.conv_mgr.get_conversation = AsyncMock(
        return_value=SimpleNamespace(history="{bad json"),
    )

    assert await service.load_current_conversation_history(session) == ("", [])


@pytest.mark.asyncio
async def test_resolve_webchat_file_prefers_webchat_image_dir_and_reports_mime(
    tmp_path,
):
    service = _service()
    service.attachments_dir = str(tmp_path / "attachments")
    service.webchat_img_dir = str(tmp_path / "imgs")
    attachments_dir = tmp_path / "attachments"
    webchat_img_dir = tmp_path / "imgs"
    attachments_dir.mkdir()
    webchat_img_dir.mkdir()
    image_path = webchat_img_dir / "photo.png"
    image_path.write_bytes(b"img")

    resolved_path, mime_type = await service.resolve_webchat_file("photo.png")

    assert resolved_path == str(image_path.resolve())
    assert mime_type == "image/png"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "expected_mime_type"),
    WEBCHAT_IMAGE_MIME_TYPES.items(),
)
@pytest.mark.parametrize("use_webchat_image_dir", [False, True])
async def test_resolve_webchat_file_uses_the_image_suffix_mime_type(
    tmp_path,
    suffix: str,
    expected_mime_type: str,
    use_webchat_image_dir: bool,
) -> None:
    service = _service()
    attachments_dir = tmp_path / "attachments"
    webchat_img_dir = tmp_path / "imgs"
    attachments_dir.mkdir()
    webchat_img_dir.mkdir()
    service.attachments_dir = str(attachments_dir)
    service.webchat_img_dir = str(webchat_img_dir)
    file_dir = webchat_img_dir if use_webchat_image_dir else attachments_dir
    image_path = file_dir / f"photo{suffix}"
    image_path.write_bytes(b"image")

    resolved_path, mime_type = await service.resolve_webchat_file(image_path.name)

    assert resolved_path == str(image_path.resolve())
    assert mime_type == expected_mime_type


@pytest.mark.asyncio
async def test_resolve_attachment_file_rejects_missing_attachment(tmp_path):
    service = _service()
    service.db.get_attachment_by_id = AsyncMock(return_value=None)

    with pytest.raises(ChatServiceError, match="Attachment not found"):
        await service.resolve_attachment_file("att-1")


@pytest.mark.asyncio
async def test_save_uploaded_file_renames_image_to_detected_suffix(
    tmp_path, monkeypatch
):
    service = _service()
    service.attachments_dir = str(tmp_path)
    service.db.insert_attachment = AsyncMock(
        return_value=SimpleNamespace(
            attachment_id="att-1",
            path=str((tmp_path / "photo.png").resolve()),
        )
    )
    upload = UploadFile(
        filename="photo.bin",
        file=BytesIO(b"binary"),
        headers={"content-type": "image/jpeg"},
    )

    async def fake_save_upload_to_path(file, path):
        path.write_bytes(b"binary")

    monkeypatch.setattr(
        chat_service_module,
        "save_upload_to_path",
        fake_save_upload_to_path,
    )
    monkeypatch.setattr(
        chat_service_module,
        "detect_image_mime_type_async",
        AsyncMock(return_value="image/png"),
    )

    result = await service.save_uploaded_file(upload)

    insert_kwargs = service.db.insert_attachment.await_args.kwargs
    assert insert_kwargs["type"] == "image"
    assert insert_kwargs["mime_type"] == "image/png"
    assert insert_kwargs["path"].endswith("photo.png")
    assert result == {
        "attachment_id": "att-1",
        "filename": "photo.png",
        "type": "image",
    }


@pytest.mark.asyncio
async def test_build_chat_stream_saves_plain_response_and_emits_saved_events(
    monkeypatch,
):
    service = _service()
    queue = AsyncMock()
    queue.put = AsyncMock()
    back_queue = asyncio.Queue()
    user_record = _history_record(
        1,
        {"type": "user", "message": [{"type": "plain", "text": "hi"}]},
        checkpoint_id="ck-1",
    )
    bot_record = _history_record(
        2,
        {"type": "bot", "message": [{"type": "plain", "text": "hello"}]},
        checkpoint_id="ck-1",
    )
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hi"}]
    )
    service.platform_history_mgr.insert = AsyncMock(return_value=user_record)
    service.save_bot_message = AsyncMock(return_value=bot_record)

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda *_args: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda *_args: queue,
    )
    remove_back_queue = MagicMock()
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        remove_back_queue,
    )

    results = iter(
        [
            (
                {
                    "message_id": "mid-1",
                    "type": "plain",
                    "data": "hello",
                    "streaming": False,
                },
                False,
            ),
            (
                {"message_id": "mid-1", "type": "end", "data": "", "streaming": False},
                False,
            ),
        ]
    )

    async def fake_poll(_back_queue, _username):
        return next(results)

    await back_queue.put(
        {
            "message_id": "mid-1",
            "type": "plain",
            "data": "hello",
            "streaming": False,
        }
    )
    await back_queue.put(
        {"message_id": "mid-1", "type": "end", "data": "", "streaming": False}
    )
    monkeypatch.setattr(chat_service_module.uuid, "uuid4", lambda: "mid-1")

    stream = await service.build_chat_stream(
        "alice",
        {"session_id": "session-1", "message": [{"type": "plain", "text": "hi"}]},
        dashboard_principal={
            "account_id": "account-1",
            "sid": "session-1",
            "username": "alice",
            "auth_strength": "password",
        },
    )
    webchat_run = service.webchat_run_coordinator.get_run("mid-1")
    assert webchat_run is not None
    events = await _collect(stream)
    assert webchat_run.task is not None
    await webchat_run.task

    queue.put.assert_awaited_once()
    queued_payload = queue.put.await_args.args[0]
    assert queued_payload == (
        "alice",
        "session-1",
        {
            "message": [{"type": "plain", "text": "hi"}],
            "selected_provider": None,
            "selected_model": None,
            "enable_streaming": True,
            "message_id": "mid-1",
            "llm_checkpoint_id": "mid-1",
            "thread_selected_text": None,
            "_dashboard_principal": {
                "account_id": "account-1",
                "sid": "session-1",
                "username": "alice",
                "auth_strength": "password",
            },
        },
    )
    service.platform_history_mgr.insert.assert_awaited_once()
    service.save_bot_message.assert_awaited_once_with(
        "session-1",
        [{"type": "plain", "text": "hello"}],
        {},
        {},
        "mid-1",
        "webchat",
    )
    remove_back_queue.assert_called_once_with("mid-1")

    payloads = [
        json.loads(event.removeprefix("data: ").strip())
        for event in events
        if event.startswith("data: {")
    ]
    assert [payload["type"] for payload in payloads] == [
        "session_id",
        "user_message_saved",
        "plain",
        "message_saved",
        "end",
    ]
    assert payloads[3]["data"]["id"] == 2


@pytest.mark.asyncio
async def test_build_chat_stream_collects_tool_call_refs_and_agent_stats_on_end(
    monkeypatch,
):
    service = _service()
    queue = AsyncMock()
    queue.put = AsyncMock()
    back_queue = asyncio.Queue()
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "ask"}]
    )
    service.platform_history_mgr.insert = AsyncMock()
    service.save_bot_message = AsyncMock(
        return_value=_history_record(
            3,
            {
                "type": "bot",
                "message": [{"type": "plain", "text": "Answer <ref>1</ref>"}],
            },
            checkpoint_id="ck-2",
        )
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda *_args: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda *_args: queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        MagicMock(),
    )
    service.preferences.temporary_cache = {
        "_ws_favicon": {"https://example.com": "fav.ico"}
    }

    results = iter(
        [
            (
                {
                    "message_id": "mid-2",
                    "type": "plain",
                    "data": '{"id":"call-1","name":"web_search_baidu"}',
                    "streaming": True,
                    "chain_type": "tool_call",
                },
                False,
            ),
            (
                {
                    "message_id": "mid-2",
                    "type": "plain",
                    "data": (
                        '{"id":"call-1","result":"{\\"results\\":[{\\"index\\":\\"1\\",'
                        '\\"url\\":\\"https://example.com\\",\\"title\\":\\"Example\\",'
                        '\\"snippet\\":\\"Snippet\\"}]}","ts":123}'
                    ),
                    "streaming": True,
                    "chain_type": "tool_call_result",
                },
                False,
            ),
            (
                {
                    "message_id": "mid-2",
                    "type": "agent_stats",
                    "data": '{"latency": 12}',
                },
                False,
            ),
            (
                {
                    "message_id": "mid-2",
                    "type": "plain",
                    "data": "Answer <ref>1</ref>",
                    "streaming": True,
                },
                False,
            ),
            (
                {"message_id": "mid-2", "type": "end", "data": "", "streaming": True},
                False,
            ),
        ]
    )

    async def fake_poll(_back_queue, _username):
        return next(results)

    await back_queue.put(
        {
            "message_id": "mid-2",
            "type": "plain",
            "data": '{"id":"call-1","name":"web_search_baidu"}',
            "streaming": True,
            "chain_type": "tool_call",
        }
    )
    await back_queue.put(
        {
            "message_id": "mid-2",
            "type": "plain",
            "data": (
                '{"id":"call-1","result":"{\\"results\\":[{\\"index\\":\\"1\\",'
                '\\"url\\":\\"https://example.com\\",\\"title\\":\\"Example\\",'
                '\\"snippet\\":\\"Snippet\\"}]}","ts":123}'
            ),
            "streaming": True,
            "chain_type": "tool_call_result",
        }
    )
    await back_queue.put(
        {"message_id": "mid-2", "type": "agent_stats", "data": '{"latency": 12}'}
    )
    await back_queue.put(
        {
            "message_id": "mid-2",
            "type": "plain",
            "data": "Answer <ref>1</ref>",
            "streaming": True,
        }
    )
    await back_queue.put(
        {"message_id": "mid-2", "type": "end", "data": "", "streaming": True}
    )
    monkeypatch.setattr(chat_service_module.uuid, "uuid4", lambda: "mid-2")

    try:
        stream = await service.build_chat_stream(
            "alice",
            {
                "session_id": "session-2",
                "message": [{"type": "plain", "text": "ask"}],
                "_skip_user_history": True,
            },
        )
        events = await _collect(stream)
    finally:
        pass

    service.platform_history_mgr.insert.assert_not_called()
    assert service.save_bot_message.await_args_list == [
        call(
            "session-2",
            [
                {
                    "type": "tool_call",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "web_search_baidu",
                            "result": '{"results":[{"index":"1","url":"https://example.com","title":"Example","snippet":"Snippet"}]}',
                            "finished_ts": 123,
                        }
                    ],
                }
            ],
            {},
            {},
            "mid-2",
            "webchat",
        ),
        call(
            "session-2",
            [{"type": "plain", "text": "Answer <ref>1</ref>"}],
            {},
            {},
            "mid-2",
            "webchat",
        ),
    ]

    payloads = [
        json.loads(event.removeprefix("data: ").strip())
        for event in events
        if event.startswith("data: {")
    ]
    assert [payload["type"] for payload in payloads] == [
        "session_id",
        "plain",
        "plain",
        "agent_stats",
        "message_saved",
        "plain",
        "end",
        "message_saved",
    ]


@pytest.mark.asyncio
async def test_chat_run_persists_native_refs_and_publishes_them():
    service = _service()
    webchat_run = _create_webchat_run(
        service,
        session_id="session-native-refs",
        username="alice",
        request_id="native-refs",
    )
    run = ChatRunState(
        run=webchat_run,
        llm_checkpoint_id="checkpoint-1",
        platform_history_id="webchat",
    )
    service.chat_run_states[webchat_run.request_id] = run
    published = []
    service._publish_chat_run = MagicMock(
        side_effect=lambda _run, payload: published.append(payload)
    )
    service.save_bot_message = AsyncMock(
        return_value=_history_record(10, {"type": "bot", "message": []})
    )
    native_refs = {
        "used": [
            {"url": "https://example.com/one", "title": "One"},
            {"url": "https://example.com/one", "snippet": "duplicate"},
        ]
    }
    await webchat_run.back_queue.put(
        {"message_id": webchat_run.request_id, "type": "refs", "data": native_refs}
    )
    await webchat_run.back_queue.put(
        {"message_id": webchat_run.request_id, "type": "end", "data": ""}
    )

    task = service.webchat_run_coordinator.start_task(
        webchat_run,
        service._consume_chat_run(run),
        name="test_native_refs",
    )
    await task

    assert run.refs == {"used": [native_refs["used"][0]]}
    service.save_bot_message.assert_awaited_once_with(
        webchat_run.session_id,
        [],
        {},
        {"used": [native_refs["used"][0]]},
        run.llm_checkpoint_id,
        run.platform_history_id,
    )
    assert any(payload["type"] == "refs" for payload in published)


@pytest.mark.asyncio
async def test_chat_run_redacts_web_search_reference_exceptions(monkeypatch, caplog):
    """Internal ref extraction failures must not leak into Dashboard logs."""
    service = _service()
    webchat_run = _create_webchat_run(
        service,
        session_id="session-redacted-refs",
        username="alice",
        request_id="redacted-refs",
    )
    run = ChatRunState(
        run=webchat_run,
        llm_checkpoint_id="checkpoint-1",
        platform_history_id="webchat",
    )
    service.chat_run_states[webchat_run.request_id] = run
    service._publish_chat_run = MagicMock()
    service.save_bot_message = AsyncMock(
        return_value=_history_record(10, {"type": "bot", "message": []})
    )
    sensitive_error = (
        "api_key=api-key-top-secret Bearer bearer-secret-token "
        "password=dashboard-password https://internal.example/private/config "
        "C:\\private\\config\\secret.txt /srv/astrbot/private/config.json"
    )
    monkeypatch.setattr(
        chat_service_module,
        "extract_web_search_refs",
        MagicMock(side_effect=RuntimeError(sensitive_error)),
    )
    await webchat_run.back_queue.put(
        {"message_id": webchat_run.request_id, "type": "plain", "data": "Answer"}
    )
    await webchat_run.back_queue.put(
        {"message_id": webchat_run.request_id, "type": "end", "data": ""}
    )

    with caplog.at_level("ERROR", logger="astrbot"):
        task = service.webchat_run_coordinator.start_task(
            webchat_run,
            service._consume_chat_run(run),
            name="test_redacted_refs",
        )
        await task

    for secret in (
        "api-key-top-secret",
        "bearer-secret-token",
        "dashboard-password",
        "https://internal.example/private/config",
        "C:\\private\\config\\secret.txt",
        "/srv/astrbot/private/config.json",
    ):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_build_chat_stream_emits_attachment_saved_event_for_image(monkeypatch):
    service = _service()
    queue = AsyncMock()
    queue.put = AsyncMock()
    back_queue = asyncio.Queue()
    user_record = _history_record(
        4,
        {"type": "user", "message": [{"type": "plain", "text": "upload"}]},
        checkpoint_id="ck-3",
    )
    bot_record = _history_record(
        5,
        {"type": "bot", "message": [{"type": "image", "attachment_id": "att-1"}]},
        checkpoint_id="ck-3",
    )
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "upload"}]
    )
    service.create_attachment_from_file = AsyncMock(
        return_value={"type": "image", "attachment_id": "att-1"}
    )
    service.platform_history_mgr.insert = AsyncMock(return_value=user_record)
    service.save_bot_message = AsyncMock(return_value=bot_record)

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda *_args: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda *_args: queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        MagicMock(),
    )

    results = iter(
        [
            (
                {
                    "message_id": "mid-3",
                    "type": "image",
                    "data": "[IMAGE]photo.png",
                    "streaming": False,
                },
                False,
            ),
            (
                {"message_id": "mid-3", "type": "end", "data": "", "streaming": False},
                False,
            ),
        ]
    )

    async def fake_poll(_back_queue, _username):
        return next(results)

    await back_queue.put(
        {
            "message_id": "mid-3",
            "type": "image",
            "data": "[IMAGE]photo.png",
            "streaming": False,
        }
    )
    await back_queue.put(
        {"message_id": "mid-3", "type": "end", "data": "", "streaming": False}
    )
    monkeypatch.setattr(chat_service_module.uuid, "uuid4", lambda: "mid-3")

    stream = await service.build_chat_stream(
        "alice",
        {"session_id": "session-3", "message": [{"type": "plain", "text": "upload"}]},
    )
    events = await _collect(stream)

    service.create_attachment_from_file.assert_awaited_once_with(
        "photo.png", "image", display_name=None
    )
    service.save_bot_message.assert_awaited_once_with(
        "session-3",
        [{"type": "image", "attachment_id": "att-1"}],
        {},
        {},
        "mid-3",
        "webchat",
    )
    assert any('"type": "attachment_saved"' in event for event in events)


@pytest.mark.asyncio
async def test_delete_platform_history_after_deletes_only_following_messages():
    service = _service()
    session = _session()
    history = [
        _history_record(1, {"type": "user", "message": []}),
        _history_record(2, {"type": "bot", "message": []}),
        _history_record(3, {"type": "user", "message": []}),
        _history_record(4, {"type": "bot", "message": []}),
    ]
    service.get_sorted_platform_history = AsyncMock(return_value=history)
    service.platform_history_mgr.delete_by_id = AsyncMock()

    deleted_ids = await service.delete_platform_history_after(session, 2)

    assert deleted_ids == [3, 4]
    assert service.platform_history_mgr.delete_by_id.await_args_list == [
        ((3,), {}),
        ((4,), {}),
    ]


@pytest.mark.asyncio
async def test_update_message_truncates_latest_turn_and_returns_regenerate_flag():
    service = _service()
    session = _session()
    edited_content = {"type": "user", "message": [{"type": "plain", "text": "edited"}]}
    record = _history_record(
        10,
        {"type": "user", "message": [{"type": "plain", "text": "old"}]},
        checkpoint_id="ck-1",
    )
    platform_history = [
        _history_record(9, {"type": "bot", "message": []}, checkpoint_id="older"),
        record,
    ]
    updated_record = _history_record(10, edited_content, checkpoint_id="new-ck")

    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        side_effect=[record, updated_record]
    )
    service.get_sorted_platform_history = AsyncMock(return_value=platform_history)
    service.load_current_conversation_history = AsyncMock(
        return_value=(
            "conv-1",
            [
                {"role": "user", "content": "older"},
                {"role": "_checkpoint", "content": {"id": "older"}},
                {"role": "user", "content": "editable"},
                {"role": "assistant", "content": "reply"},
                {"role": "_checkpoint", "content": {"id": "ck-1"}},
            ],
        )
    )
    service.delete_platform_history_after = AsyncMock(return_value=[11, 12])
    service.db.delete_webchat_threads_by_parent_message_ids = AsyncMock(
        return_value=["thread-1"]
    )
    service.conv_mgr.update_conversation = AsyncMock()
    service.db.update_platform_session = AsyncMock()
    service.platform_history_mgr.update = AsyncMock()

    result = await service.update_message(
        "alice",
        {"session_id": "session-1", "message_id": 10, "content": edited_content},
    )

    service.platform_history_mgr.update.assert_awaited_once()
    update_kwargs = service.platform_history_mgr.update.await_args.kwargs
    assert update_kwargs["message_id"] == 10
    assert update_kwargs["content"] == edited_content
    assert isinstance(update_kwargs["llm_checkpoint_id"], str)
    service.conv_mgr.update_conversation.assert_awaited_once_with(
        unified_msg_origin="webchat:FriendMessage:webchat!alice!session-1",
        conversation_id="conv-1",
        history=[
            {"role": "user", "content": "older"},
            {"role": "_checkpoint", "content": {"id": "older"}},
        ],
    )
    service.delete_threads_by_ids.assert_awaited_once_with(["thread-1"], "alice")
    assert result["message"] == {
        "id": 10,
        "content": edited_content,
        "created_at": result["message"]["created_at"],
        "updated_at": None,
    }
    assert result["needs_regenerate"] is True
    assert result["truncated_after_message"] is True


@pytest.mark.asyncio
async def test_update_message_rejects_non_latest_user_message():
    service = _service()
    session = _session()
    edited_content = {"type": "user", "message": [{"type": "plain", "text": "edited"}]}
    target_record = _history_record(
        10,
        {"type": "user", "message": [{"type": "plain", "text": "older"}]},
        checkpoint_id="ck-1",
    )
    latest_user = _history_record(
        11,
        {"type": "user", "message": [{"type": "plain", "text": "latest"}]},
        checkpoint_id="ck-2",
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )

    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=target_record
    )
    service.get_sorted_platform_history = AsyncMock(
        return_value=[target_record, latest_user]
    )

    with pytest.raises(
        ChatServiceError, match="Only the latest user message can be edited"
    ):
        await service.update_message(
            "alice",
            {"session_id": "session-1", "message_id": 10, "content": edited_content},
        )


@pytest.mark.asyncio
async def test_prepare_regenerate_message_payload_rewrites_latest_turn():
    service = _service()
    session = _session()
    target_record = _history_record(
        20,
        {"type": "bot", "message": [{"type": "plain", "text": "answer"}]},
        checkpoint_id="ck-1",
    )
    source_user_record = _history_record(
        19,
        {"type": "user", "message": [{"type": "plain", "text": "question"}]},
        checkpoint_id="ck-1",
    )
    platform_history = [
        source_user_record,
        target_record,
        _history_record(
            21,
            {"type": "bot", "message": [{"type": "plain", "text": "extra bot"}]},
            checkpoint_id="ck-1",
        ),
    ]

    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=target_record
    )
    service.load_current_conversation_history = AsyncMock(
        return_value=(
            "conv-1",
            [
                {"role": "user", "content": "older"},
                {"role": "_checkpoint", "content": {"id": "older"}},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
                {"role": "_checkpoint", "content": {"id": "ck-1"}},
            ],
        )
    )
    service.get_sorted_platform_history = AsyncMock(return_value=platform_history)
    service.conv_mgr.update_conversation = AsyncMock()
    service.db.delete_webchat_threads_by_parent_message_ids = AsyncMock(
        return_value=["thread-1", "thread-2"]
    )
    service.platform_history_mgr.delete_by_id = AsyncMock()
    service.platform_history_mgr.update = AsyncMock()

    result = await service.prepare_regenerate_message_payload(
        "alice",
        {
            "session_id": "session-1",
            "message_id": 20,
            "enable_streaming": False,
            "selected_provider": "provider-1",
            "selected_model": "model-1",
        },
    )

    service.conv_mgr.update_conversation.assert_awaited_once_with(
        unified_msg_origin="webchat:FriendMessage:webchat!alice!session-1",
        conversation_id="conv-1",
        history=[
            {"role": "user", "content": "older"},
            {"role": "_checkpoint", "content": {"id": "older"}},
        ],
    )
    service.delete_threads_by_ids.assert_awaited_once_with(
        ["thread-1", "thread-2"],
        "alice",
    )
    assert service.platform_history_mgr.delete_by_id.await_args_list == [
        ((20,), {}),
        ((21,), {}),
    ]
    update_kwargs = service.platform_history_mgr.update.await_args.kwargs
    assert update_kwargs["message_id"] == 19
    assert isinstance(update_kwargs["llm_checkpoint_id"], str)
    assert result == {
        "session_id": "session-1",
        "message": [{"type": "plain", "text": "question"}],
        "enable_streaming": False,
        "selected_provider": "provider-1",
        "selected_model": "model-1",
        "_skip_user_history": True,
        "_llm_checkpoint_id": update_kwargs["llm_checkpoint_id"],
    }


@pytest.mark.asyncio
async def test_prepare_regenerate_message_payload_rejects_non_latest_turn():
    service = _service()
    session = _session()
    target_record = _history_record(
        20,
        {"type": "bot", "message": [{"type": "plain", "text": "answer"}]},
        checkpoint_id="ck-1",
    )

    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=target_record
    )
    service.load_current_conversation_history = AsyncMock(
        return_value=(
            "conv-1",
            [
                {"role": "user", "content": "older"},
                {"role": "_checkpoint", "content": {"id": "ck-1"}},
                {"role": "user", "content": "newer"},
                {"role": "_checkpoint", "content": {"id": "ck-2"}},
            ],
        )
    )

    with pytest.raises(
        ChatServiceError,
        match="Regenerating older turns requires branching",
    ):
        await service.prepare_regenerate_message_payload(
            "alice",
            {"session_id": "session-1", "message_id": 20},
        )


@pytest.mark.asyncio
async def test_batch_delete_sessions_tracks_not_found_permission_and_internal_failure():
    service = _service()
    own_session = _session("session-own", creator="alice")
    other_session = _session("session-other", creator="bob")
    service.db.get_platform_sessions_by_ids = AsyncMock(
        return_value=[own_session, other_session]
    )

    async def fake_delete(session, username):
        assert username == "alice"
        if session.session_id == "session-own":
            raise RuntimeError("boom")

    result = await service.batch_delete_sessions(
        "alice",
        ["session-own", "session-other", "missing"],
        delete_session=fake_delete,
    )

    assert result == {
        "deleted_count": 0,
        "failed_count": 3,
        "failed_items": [
            {"session_id": "session-own", "reason": "internal_error"},
            {"session_id": "session-other", "reason": "permission denied"},
            {"session_id": "missing", "reason": "not found"},
        ],
    }


@pytest.mark.asyncio
async def test_delete_attachments_still_deletes_rows_when_file_removal_fails(
    monkeypatch,
):
    service = _service()
    first = SimpleNamespace(attachment_id="att-1", path="C:/tmp/one.png")
    second = SimpleNamespace(attachment_id="att-2", path="C:/tmp/two.png")
    service.db.get_attachments = AsyncMock(return_value=[first, second])
    service.db.delete_attachments = AsyncMock()

    monkeypatch.setattr(chat_service_module.os.path, "exists", lambda _path: True)

    def fake_remove(path):
        if path == first.path:
            raise OSError("locked")

    monkeypatch.setattr(chat_service_module.os, "remove", fake_remove)

    await service.delete_attachments(["att-1", "att-2"])

    service.db.delete_attachments.assert_awaited_once_with(["att-1", "att-2"])


@pytest.mark.asyncio
async def test_get_session_includes_project_threads_and_running_state():
    service = _service()
    session = _session()
    _create_webchat_run(
        service,
        session_id="session-1",
        username="alice",
        request_id="active-session-run",
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_project_by_session = AsyncMock(
        return_value=SimpleNamespace(project_id="proj-1", title="Alpha", emoji="A")
    )
    service.platform_history_mgr.get = AsyncMock(
        return_value=[_history_record(1, {"type": "user", "message": []})]
    )
    thread = SimpleNamespace(
        thread_id="thread-1",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="quoted",
        creator="alice",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.db.get_webchat_threads_by_parent_session = AsyncMock(return_value=[thread])

    result = await service.get_session("alice", "session-1")

    assert result["is_running"] is True
    assert result["history"][0]["id"] == 1
    assert result["history"][0]["content"] == {"type": "user", "message": []}
    assert result["project"] == {"project_id": "proj-1", "title": "Alpha", "emoji": "A"}
    assert result["threads"][0]["thread_id"] == "thread-1"
    service.platform_history_mgr.get.assert_awaited_once_with(
        platform_id="webchat",
        user_id="session-1",
        page=1,
        page_size=1000,
    )


@pytest.mark.asyncio
async def test_create_thread_returns_existing_thread_without_creating_conversation():
    service = _service()
    session = _session()
    parent_record = _history_record(
        10,
        {"type": "bot", "message": [{"type": "plain", "text": "answer"}]},
        checkpoint_id="ck-1",
    )
    existing = SimpleNamespace(
        thread_id="thread-1",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="quoted",
        creator="alice",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=parent_record
    )
    service.db.get_webchat_thread_by_parent_message_and_text = AsyncMock(
        return_value=existing
    )
    service.load_current_conversation_history = AsyncMock()
    service.db.create_webchat_thread = AsyncMock()
    service.conv_mgr.new_conversation = AsyncMock()

    result = await service.create_thread(
        "alice",
        {
            "session_id": "session-1",
            "parent_message_id": 10,
            "selected_text": " quoted ",
        },
    )

    assert result["thread_id"] == "thread-1"
    service.load_current_conversation_history.assert_not_called()
    service.db.create_webchat_thread.assert_not_awaited()
    service.conv_mgr.new_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_session_display_name_rejects_permission_denied():
    service = _service()
    service.db.get_platform_session_by_id = AsyncMock(
        return_value=_session("session-1", creator="bob")
    )
    service.db.update_platform_session = AsyncMock()

    with pytest.raises(ChatServiceError, match="Permission denied"):
        await service.update_session_display_name("alice", "session-1", "Renamed")

    service.db.update_platform_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_thread_returns_history_and_running_state():
    service = _service()
    thread = SimpleNamespace(
        thread_id="thread-1",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="quoted",
        creator="alice",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _create_webchat_run(
        service,
        session_id="thread-1",
        username="alice",
        request_id="active-thread-run",
    )
    service.db.get_webchat_thread_by_id = AsyncMock(return_value=thread)
    service.platform_history_mgr.get = AsyncMock(
        return_value=[_history_record(2, {"type": "bot", "message": []})]
    )

    result = await service.get_thread("alice", "thread-1")

    assert result["is_running"] is True
    assert result["thread"]["thread_id"] == "thread-1"
    assert result["history"][0]["id"] == 2
    assert result["history"][0]["content"] == {"type": "bot", "message": []}
    service.platform_history_mgr.get.assert_awaited_once_with(
        platform_id="webchat_thread",
        user_id="thread-1",
        page=1,
        page_size=1000,
    )


@pytest.mark.asyncio
async def test_prepare_thread_chat_payload_returns_selected_text_and_overrides():
    service = _service()
    thread = SimpleNamespace(
        thread_id="thread-1",
        selected_text="quoted context",
        creator="alice",
    )
    service.db.get_webchat_thread_by_id = AsyncMock(return_value=thread)

    result = await service.prepare_thread_chat_payload(
        "alice",
        {
            "thread_id": "thread-1",
            "message": [{"type": "plain", "text": "follow up"}],
            "enable_streaming": False,
            "selected_provider": "provider-1",
            "selected_model": "model-1",
        },
    )

    assert result == {
        "session_id": "thread-1",
        "message": [{"type": "plain", "text": "follow up"}],
        "enable_streaming": False,
        "selected_provider": "provider-1",
        "selected_model": "model-1",
        "_platform_history_id": "webchat_thread",
        "_thread_selected_text": "quoted context",
    }


@pytest.mark.asyncio
async def test_delete_thread_removes_thread_and_session_resources():
    service = _service()
    thread = SimpleNamespace(thread_id="thread-1", creator="alice")
    service.db.get_webchat_thread_by_id = AsyncMock(return_value=thread)
    service.db.delete_webchat_thread = AsyncMock()

    result = await service.delete_thread("alice", "thread-1")

    service.db.delete_webchat_thread.assert_awaited_once_with("thread-1")
    service.delete_threads_by_ids.assert_awaited_once_with(["thread-1"], "alice")
    assert result == {"thread_id": "thread-1"}


@pytest.mark.asyncio
async def test_update_message_rejects_type_change_before_history_mutation():
    service = _service()
    session = _session()
    record = _history_record(
        10,
        {"type": "user", "message": [{"type": "plain", "text": "old"}]},
        checkpoint_id="ck-1",
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(return_value=record)
    service.platform_history_mgr.update = AsyncMock()

    with pytest.raises(ChatServiceError, match="Message type cannot be changed"):
        await service.update_message(
            "alice",
            {
                "session_id": "session-1",
                "message_id": 10,
                "content": {"type": "bot", "message": [{"type": "plain", "text": "x"}]},
            },
        )

    service.platform_history_mgr.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_message_rejects_message_without_checkpoint():
    service = _service()
    session = _session()
    record = _history_record(
        10,
        {"type": "user", "message": [{"type": "plain", "text": "old"}]},
        checkpoint_id=None,
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(return_value=record)
    service.get_sorted_platform_history = AsyncMock(return_value=[record])

    with pytest.raises(
        ChatServiceError,
        match="This message is not linked to LLM history and cannot be edited",
    ):
        await service.update_message(
            "alice",
            {
                "session_id": "session-1",
                "message_id": 10,
                "content": {
                    "type": "user",
                    "message": [{"type": "plain", "text": "x"}],
                },
            },
        )


@pytest.mark.asyncio
async def test_prepare_regenerate_message_payload_rejects_missing_linked_user_display_message():
    service = _service()
    session = _session()
    target_record = _history_record(
        20,
        {"type": "bot", "message": [{"type": "plain", "text": "answer"}]},
        checkpoint_id="ck-1",
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=target_record
    )
    service.load_current_conversation_history = AsyncMock(
        return_value=(
            "conv-1",
            [
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
                {"role": "_checkpoint", "content": {"id": "ck-1"}},
            ],
        )
    )
    service.get_sorted_platform_history = AsyncMock(return_value=[target_record])

    with pytest.raises(
        ChatServiceError,
        match="Linked user display message not found",
    ):
        await service.prepare_regenerate_message_payload(
            "alice",
            {"session_id": "session-1", "message_id": 20},
        )


@pytest.mark.asyncio
async def test_prepare_regenerate_message_payload_rejects_missing_linked_bot_display_message():
    service = _service()
    session = _session()
    target_record = _history_record(
        20,
        {"type": "bot", "message": [{"type": "plain", "text": "answer"}]},
        checkpoint_id="ck-1",
    )
    source_user_record = _history_record(
        19,
        {"type": "user", "message": [{"type": "plain", "text": "question"}]},
        checkpoint_id="ck-1",
    )
    service.db.get_platform_session_by_id = AsyncMock(return_value=session)
    service.db.get_platform_message_history_by_id = AsyncMock(
        return_value=target_record
    )
    service.load_current_conversation_history = AsyncMock(
        return_value=(
            "conv-1",
            [
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
                {"role": "_checkpoint", "content": {"id": "ck-1"}},
            ],
        )
    )
    service.get_sorted_platform_history = AsyncMock(return_value=[source_user_record])

    with pytest.raises(
        ChatServiceError,
        match="Linked bot display message not found",
    ):
        await service.prepare_regenerate_message_payload(
            "alice",
            {"session_id": "session-1", "message_id": 20},
        )
