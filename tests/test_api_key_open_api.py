import asyncio
import uuid
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from quart import Quart, g, request
from werkzeug.datastructures import FileStorage

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.routes.route import Response
from astrbot.dashboard.server import AstrBotDashboard


def _get_open_api_route(app: Quart):
    rule = next(
        (
            item
            for item in app.url_map.iter_rules()
            if item.rule == "/api/v1/chat" and "POST" in item.methods
        ),
        None,
    )
    assert rule is not None
    return app.view_functions[rule.endpoint].__self__


async def _create_api_key(
    app: Quart,
    authenticated_header: dict,
    *,
    scopes: list[str],
    name_prefix: str = "openapi-test",
) -> tuple[str, str]:
    test_client = app.test_client()
    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": f"{name_prefix}-{uuid.uuid4().hex[:8]}", "scopes": scopes},
        headers=authenticated_header,
    )
    assert create_res.status_code == 200
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    return create_data["data"]["api_key"], create_data["data"]["key_id"]


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_api_key.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()
    try:
        yield core_lifecycle
    finally:
        try:
            stop_result = core_lifecycle.stop()
            if asyncio.iscoroutine(stop_result):
                await stop_result
        except Exception:
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": core_lifecycle_td.astrbot_config["dashboard"]["password"],
        },
    )
    data = await response.get_json()
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_key_scope_and_revoke(app: Quart, authenticated_header: dict):
    test_client = app.test_client()

    raw_key, key_id = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="im-scope-key",
    )

    open_bot_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": raw_key},
    )
    assert open_bot_res.status_code == 200
    open_bot_data = await open_bot_res.get_json()
    assert open_bot_data["status"] == "ok"
    assert isinstance(open_bot_data["data"]["bot_ids"], list)

    denied_chat_sessions_res = await test_client.get(
        "/api/v1/chat/sessions?page=1&page_size=10",
        headers={"X-API-Key": raw_key},
    )
    assert denied_chat_sessions_res.status_code == 403

    denied_chat_configs_res = await test_client.get(
        "/api/v1/configs",
        headers={"X-API-Key": raw_key},
    )
    assert denied_chat_configs_res.status_code == 403

    denied_res = await test_client.post(
        "/api/v1/file",
        data={},
        headers={"X-API-Key": raw_key},
    )
    assert denied_res.status_code == 403

    revoke_res = await test_client.post(
        "/api/apikey/revoke",
        json={"key_id": key_id},
        headers=authenticated_header,
    )
    assert revoke_res.status_code == 200
    revoke_data = await revoke_res.get_json()
    assert revoke_data["status"] == "ok"

    revoked_access_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": raw_key},
    )
    assert revoked_access_res.status_code == 401


@pytest.mark.asyncio
async def test_open_send_message_with_api_key(app: Quart, authenticated_header: dict):
    test_client = app.test_client()

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="send-message-key",
    )

    send_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": "webchat:FriendMessage:open_api_test_session",
            "message": "hello",
        },
        headers={"X-API-Key": raw_key},
    )
    assert send_res.status_code == 200
    send_data = await send_res.get_json()
    assert send_data["status"] == "ok"


@pytest.mark.asyncio
async def test_open_chat_send_auto_session_id_and_username(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["chat"],
        name_prefix="chat-send-key",
    )
    open_api_route = _get_open_api_route(app)

    original_chat = open_api_route.chat_route.chat

    async def fake_chat(post_data: dict | None = None):
        payload = post_data or await request.get_json()
        return (
            Response()
            .ok(
                data={
                    "session_id": payload.get("session_id"),
                    "creator": g.get("username"),
                }
            )
            .__dict__
        )

    open_api_route.chat_route.chat = fake_chat
    try:
        send_res = await test_client.post(
            "/api/v1/chat",
            json={
                "message": "hello",
                "username": "alice_auto_session",
                "enable_streaming": False,
            },
            headers={"X-API-Key": raw_key},
        )
    finally:
        open_api_route.chat_route.chat = original_chat

    assert send_res.status_code == 200
    send_data = await send_res.get_json()
    assert send_data["status"] == "ok"
    created_session_id = send_data["data"]["session_id"]
    assert isinstance(created_session_id, str)
    uuid.UUID(created_session_id)
    assert send_data["data"]["creator"] == "alice_auto_session"
    created_session = await core_lifecycle_td.db.get_platform_session_by_id(
        created_session_id
    )
    assert created_session is not None
    assert created_session.creator == "alice_auto_session"
    assert created_session.platform_id == "webchat"

    await core_lifecycle_td.db.create_platform_session(
        creator="bob_auto_session",
        platform_id="webchat",
        session_id="open_api_existing_bob_session",
        is_group=0,
    )
    another_user_session_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": "open_api_existing_bob_session",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    another_user_session_data = await another_user_session_res.get_json()
    assert another_user_session_data["status"] == "error"
    assert (
        another_user_session_data["message"] == "session_id belongs to another username"
    )

    missing_username_res = await test_client.post(
        "/api/v1/chat",
        json={"message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    missing_username_data = await missing_username_res.get_json()
    assert missing_username_data["status"] == "error"
    assert missing_username_data["message"] == "Missing key: username"


@pytest.mark.asyncio
async def test_open_chat_sessions_pagination(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["chat"],
        name_prefix="chat-scope-key",
    )

    creator = f"alice_{uuid.uuid4().hex[:8]}"
    other_creator = f"bob_{uuid.uuid4().hex[:8]}"
    for idx in range(3):
        await core_lifecycle_td.db.create_platform_session(
            creator=creator,
            platform_id="webchat",
            session_id=f"open_api_paginated_{idx}",
            display_name=f"Open API Session {idx}",
            is_group=0,
        )
    await core_lifecycle_td.db.create_platform_session(
        creator=other_creator,
        platform_id="webchat",
        session_id=f"open_api_paginated_bob_{uuid.uuid4().hex[:8]}",
        display_name="Open API Session Bob",
        is_group=0,
    )

    page_1_res = await test_client.get(
        f"/api/v1/chat/sessions?page=1&page_size=2&username={creator}",
        headers={"X-API-Key": raw_key},
    )
    assert page_1_res.status_code == 200
    page_1_data = await page_1_res.get_json()
    assert page_1_data["status"] == "ok"
    assert page_1_data["data"]["page"] == 1
    assert page_1_data["data"]["page_size"] == 2
    assert page_1_data["data"]["total"] == 3
    assert len(page_1_data["data"]["sessions"]) == 2
    assert all(item["creator"] == creator for item in page_1_data["data"]["sessions"])

    page_2_res = await test_client.get(
        f"/api/v1/chat/sessions?page=2&page_size=2&username={creator}",
        headers={"X-API-Key": raw_key},
    )
    assert page_2_res.status_code == 200
    page_2_data = await page_2_res.get_json()
    assert page_2_data["status"] == "ok"
    assert page_2_data["data"]["page"] == 2
    assert len(page_2_data["data"]["sessions"]) == 1

    missing_username_res = await test_client.get(
        "/api/v1/chat/sessions?page=1&page_size=2",
        headers={"X-API-Key": raw_key},
    )
    missing_username_data = await missing_username_res.get_json()
    assert missing_username_data["status"] == "error"
    assert missing_username_data["message"] == "Missing key: username"


@pytest.mark.asyncio
async def test_open_chat_configs_list(
    app: Quart,
    authenticated_header: dict,
):
    test_client = app.test_client()

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["config"],
        name_prefix="chat-config-key",
    )

    configs_res = await test_client.get(
        "/api/v1/configs",
        headers={"X-API-Key": raw_key},
    )
    assert configs_res.status_code == 200
    configs_data = await configs_res.get_json()
    assert configs_data["status"] == "ok"
    assert isinstance(configs_data["data"]["configs"], list)
    assert any(item["id"] == "default" for item in configs_data["data"]["configs"])
    for item in configs_data["data"]["configs"]:
        assert isinstance(item["id"], str)
        assert isinstance(item["name"], str)
        assert isinstance(item["path"], str)
        assert isinstance(item["is_default"], bool)


@pytest.mark.asyncio
async def test_open_api_auth_validation_and_key_carriers(
    app: Quart,
    authenticated_header: dict,
):
    test_client = app.test_client()

    missing_key_res = await test_client.get("/api/v1/im/bots")
    assert missing_key_res.status_code == 401
    missing_key_data = await missing_key_res.get_json()
    assert missing_key_data["status"] == "error"
    assert missing_key_data["message"] == "Missing API key"

    invalid_key_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": "abk_invalid"},
    )
    assert invalid_key_res.status_code == 401
    invalid_key_data = await invalid_key_res.get_json()
    assert invalid_key_data["status"] == "error"
    assert invalid_key_data["message"] == "Invalid API key"

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="auth-carrier-key",
    )

    headers_and_urls = [
        ({"X-API-Key": raw_key}, "/api/v1/im/bots"),
        ({}, f"/api/v1/im/bots?api_key={raw_key}"),
        ({}, f"/api/v1/im/bots?key={raw_key}"),
        ({"Authorization": f"Bearer {raw_key}"}, "/api/v1/im/bots"),
        ({"Authorization": f"ApiKey {raw_key}"}, "/api/v1/im/bots"),
    ]
    for headers, url in headers_and_urls:
        res = await test_client.get(url, headers=headers)
        assert res.status_code == 200
        data = await res.get_json()
        assert data["status"] == "ok"
        assert isinstance(data["data"]["bot_ids"], list)


@pytest.mark.asyncio
async def test_open_chat_send_conversation_alias_and_blank_username(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["chat"],
        name_prefix="chat-conversation-key",
    )
    open_api_route = _get_open_api_route(app)

    async def fake_chat(post_data: dict | None = None):
        payload = post_data or await request.get_json()
        resolved_session_id = payload.get("session_id") or payload.get(
            "conversation_id"
        )
        return Response().ok(data={"session_id": resolved_session_id}).__dict__

    monkeypatch.setattr(open_api_route.chat_route, "chat", fake_chat)

    conversation_id = f"open_api_conversation_{uuid.uuid4().hex[:10]}"
    send_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alias-user",
            "conversation_id": conversation_id,
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    assert send_res.status_code == 200
    send_data = await send_res.get_json()
    assert send_data["status"] == "ok"
    assert send_data["data"]["session_id"] == conversation_id

    created_session = await core_lifecycle_td.db.get_platform_session_by_id(
        conversation_id
    )
    assert created_session is not None
    assert created_session.creator == "alias-user"

    blank_username_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "   ",
            "session_id": f"open_api_blank_{uuid.uuid4().hex[:8]}",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    blank_username_data = await blank_username_res.get_json()
    assert blank_username_data["status"] == "error"
    assert blank_username_data["message"] == "username is empty"


@pytest.mark.asyncio
async def test_open_chat_send_config_resolution(
    app: Quart,
    authenticated_header: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["chat"],
        name_prefix="chat-config-resolution-key",
    )
    open_api_route = _get_open_api_route(app)

    conf_list = [
        {
            "id": "default",
            "name": "Default",
            "path": "default.json",
            "is_default": True,
        },
        {"id": "cfg-alpha", "name": "Alpha", "path": "alpha.json", "is_default": False},
        {"id": "cfg-1", "name": "Duplicated", "path": "a.json", "is_default": False},
        {"id": "cfg-2", "name": "Duplicated", "path": "b.json", "is_default": False},
    ]
    monkeypatch.setattr(open_api_route, "_get_chat_config_list", lambda: conf_list)

    update_route = AsyncMock()
    delete_route = AsyncMock()
    monkeypatch.setattr(
        open_api_route.core_lifecycle.umop_config_router,
        "update_route",
        update_route,
    )
    monkeypatch.setattr(
        open_api_route.core_lifecycle.umop_config_router,
        "delete_route",
        delete_route,
    )

    async def fake_chat(post_data: dict | None = None):
        payload = post_data or await request.get_json()
        return (
            Response()
            .ok(
                data={
                    "session_id": payload.get("session_id"),
                    "creator": g.get("username"),
                }
            )
            .__dict__
        )

    monkeypatch.setattr(open_api_route.chat_route, "chat", fake_chat)

    invalid_config_id_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": f"openapi_cfg_invalid_{uuid.uuid4().hex[:8]}",
            "config_id": "missing",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    invalid_config_id_data = await invalid_config_id_res.get_json()
    assert invalid_config_id_data["status"] == "error"
    assert invalid_config_id_data["message"] == "config_id not found: missing"

    missing_config_name_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": f"openapi_cfg_name_missing_{uuid.uuid4().hex[:8]}",
            "config_name": "NotExists",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    missing_config_name_data = await missing_config_name_res.get_json()
    assert missing_config_name_data["status"] == "error"
    assert missing_config_name_data["message"] == "config_name not found: NotExists"

    ambiguous_config_name_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": f"openapi_cfg_name_ambiguous_{uuid.uuid4().hex[:8]}",
            "config_name": "Duplicated",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    ambiguous_config_name_data = await ambiguous_config_name_res.get_json()
    assert ambiguous_config_name_data["status"] == "error"
    assert ambiguous_config_name_data["message"] == (
        "config_name is ambiguous, please use config_id: Duplicated"
    )

    session_id = f"openapi_cfg_default_{uuid.uuid4().hex[:8]}"
    use_default_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": session_id,
            "config_name": "Default",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    use_default_data = await use_default_res.get_json()
    assert use_default_data["status"] == "ok"
    assert use_default_data["data"]["creator"] == "alice"
    expected_umo = f"webchat:FriendMessage:webchat!alice!{session_id}"
    delete_route.assert_awaited_with(expected_umo)

    use_named_config_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alice",
            "session_id": f"openapi_cfg_alpha_{uuid.uuid4().hex[:8]}",
            "config_name": "Alpha",
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    use_named_config_data = await use_named_config_res.get_json()
    assert use_named_config_data["status"] == "ok"
    assert use_named_config_data["data"]["creator"] == "alice"
    update_route.assert_awaited()


@pytest.mark.asyncio
async def test_open_chat_sessions_input_validation_and_filtering(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["chat"],
        name_prefix="chat-sessions-bounds-key",
    )

    creator = f"chat_bounds_{uuid.uuid4().hex[:8]}"
    webchat_sid = f"open_api_bounds_webchat_{uuid.uuid4().hex[:8]}"
    telegram_sid = f"open_api_bounds_telegram_{uuid.uuid4().hex[:8]}"
    await core_lifecycle_td.db.create_platform_session(
        creator=creator,
        platform_id="webchat",
        session_id=webchat_sid,
        display_name="Bounds Webchat",
        is_group=0,
    )
    await core_lifecycle_td.db.create_platform_session(
        creator=creator,
        platform_id="telegram",
        session_id=telegram_sid,
        display_name="Bounds Telegram",
        is_group=0,
    )

    invalid_page_res = await test_client.get(
        f"/api/v1/chat/sessions?page=x&page_size=y&username={creator}",
        headers={"X-API-Key": raw_key},
    )
    invalid_page_data = await invalid_page_res.get_json()
    assert invalid_page_data["status"] == "error"
    assert invalid_page_data["message"] == "page and page_size must be integers"

    normalized_res = await test_client.get(
        f"/api/v1/chat/sessions?page=0&page_size=0&username={creator}",
        headers={"X-API-Key": raw_key},
    )
    normalized_data = await normalized_res.get_json()
    assert normalized_data["status"] == "ok"
    assert normalized_data["data"]["page"] == 1
    assert normalized_data["data"]["page_size"] == 1
    assert len(normalized_data["data"]["sessions"]) == 1

    capped_page_size_res = await test_client.get(
        f"/api/v1/chat/sessions?page=1&page_size=1000&username={creator}",
        headers={"X-API-Key": raw_key},
    )
    capped_page_size_data = await capped_page_size_res.get_json()
    assert capped_page_size_data["status"] == "ok"
    assert capped_page_size_data["data"]["page_size"] == 100

    filtered_res = await test_client.get(
        f"/api/v1/chat/sessions?page=1&page_size=10&username={creator}&platform_id=telegram",
        headers={"X-API-Key": raw_key},
    )
    filtered_data = await filtered_res.get_json()
    assert filtered_data["status"] == "ok"
    assert filtered_data["data"]["total"] == 1
    assert len(filtered_data["data"]["sessions"]) == 1
    assert filtered_data["data"]["sessions"][0]["platform_id"] == "telegram"

    empty_username_res = await test_client.get(
        "/api/v1/chat/sessions?page=1&page_size=2&username=%20%20",
        headers={"X-API-Key": raw_key},
    )
    empty_username_data = await empty_username_res.get_json()
    assert empty_username_data["status"] == "error"
    assert empty_username_data["message"] == "username is empty"


@pytest.mark.asyncio
async def test_open_send_message_error_paths(app: Quart, authenticated_header: dict):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="im-errors-key",
    )

    missing_message_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": f"webchat:FriendMessage:open_api_im_{uuid.uuid4().hex[:8]}",
            "message": None,
        },
        headers={"X-API-Key": raw_key},
    )
    missing_message_data = await missing_message_res.get_json()
    assert missing_message_data["status"] == "error"
    assert missing_message_data["message"] == "Missing key: message"

    missing_umo_res = await test_client.post(
        "/api/v1/im/message",
        json={"message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    missing_umo_data = await missing_umo_res.get_json()
    assert missing_umo_data["status"] == "error"
    assert missing_umo_data["message"] == "Missing key: umo"

    invalid_umo_res = await test_client.post(
        "/api/v1/im/message",
        json={"umo": "broken-umo", "message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    invalid_umo_data = await invalid_umo_res.get_json()
    assert invalid_umo_data["status"] == "error"
    assert invalid_umo_data["message"].startswith("Invalid umo:")

    missing_platform_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": f"platform-not-running:FriendMessage:{uuid.uuid4().hex[:8]}",
            "message": "hello",
        },
        headers={"X-API-Key": raw_key},
    )
    missing_platform_data = await missing_platform_res.get_json()
    assert missing_platform_data["status"] == "error"
    assert missing_platform_data["message"] == (
        "Bot not found or not running for platform: platform-not-running"
    )


@pytest.mark.asyncio
async def test_open_file_upload_requires_file_and_can_upload(
    app: Quart,
    authenticated_header: dict,
):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["file"],
        name_prefix="file-scope-key",
    )

    missing_file_res = await test_client.post(
        "/api/v1/file",
        data={},
        headers={"X-API-Key": raw_key},
    )
    missing_file_data = await missing_file_res.get_json()
    assert missing_file_data["status"] == "error"
    assert missing_file_data["message"] == "Missing key: file"

    upload_res = await test_client.post(
        "/api/v1/file",
        files={
            "file": FileStorage(
                stream=BytesIO(b"openapi-file-content"),
                filename="openapi_test.txt",
                content_type="text/plain",
            )
        },
        headers={"X-API-Key": raw_key},
    )
    assert upload_res.status_code == 200
    upload_data = await upload_res.get_json()
    assert upload_data["status"] == "ok"
    assert isinstance(upload_data["data"]["attachment_id"], str)
    assert upload_data["data"]["filename"] == "openapi_test.txt"
    assert upload_data["data"]["type"] == "file"
