import asyncio
import uuid

import pytest
import pytest_asyncio
from quart import Quart, g, request

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.routes.route import Response
from astrbot.dashboard.server import AstrBotDashboard


@pytest_asyncio.fixture(scope="module", loop_scope="module")
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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
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

    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "im-scope-key", "scopes": ["im"]},
        headers=authenticated_header,
    )
    assert create_res.status_code == 200
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    raw_key = create_data["data"]["api_key"]
    key_id = create_data["data"]["key_id"]

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

    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "send-message-key", "scopes": ["im"]},
        headers=authenticated_header,
    )
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    raw_key = create_data["data"]["api_key"]

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

    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "chat-send-key", "scopes": ["chat"]},
        headers=authenticated_header,
    )
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    raw_key = create_data["data"]["api_key"]

    rule = next(
        (
            item
            for item in app.url_map.iter_rules()
            if item.rule == "/api/v1/chat" and "POST" in item.methods
        ),
        None,
    )
    assert rule is not None
    open_api_route = app.view_functions[rule.endpoint].__self__

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
                "username": "alice",
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
    assert send_data["data"]["creator"] == "alice"
    created_session = await core_lifecycle_td.db.get_platform_session_by_id(
        created_session_id
    )
    assert created_session is not None
    assert created_session.creator == "alice"
    assert created_session.platform_id == "webchat"

    await core_lifecycle_td.db.create_platform_session(
        creator="bob",
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
        another_user_session_data["message"]
        == "session_id belongs to another username"
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

    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "chat-scope-key", "scopes": ["chat"]},
        headers=authenticated_header,
    )
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    raw_key = create_data["data"]["api_key"]

    creator = f"alice_{uuid.uuid4().hex[:8]}"
    for idx in range(3):
        await core_lifecycle_td.db.create_platform_session(
            creator=creator,
            platform_id="webchat",
            session_id=f"open_api_paginated_{idx}",
            display_name=f"Open API Session {idx}",
            is_group=0,
        )
    await core_lifecycle_td.db.create_platform_session(
        creator="bob",
        platform_id="webchat",
        session_id="open_api_paginated_bob",
        display_name="Open API Session Bob",
        is_group=0,
    )

    page_1_res = await test_client.get(
        "/api/v1/chat/sessions?page=1&page_size=2&username="
        f"{creator}",
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
        "/api/v1/chat/sessions?page=2&page_size=2&username="
        f"{creator}",
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

    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "chat-config-key", "scopes": ["config"]},
        headers=authenticated_header,
    )
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    raw_key = create_data["data"]["api_key"]

    configs_res = await test_client.get(
        "/api/v1/configs",
        headers={"X-API-Key": raw_key},
    )
    assert configs_res.status_code == 200
    configs_data = await configs_res.get_json()
    assert configs_data["status"] == "ok"
    assert isinstance(configs_data["data"]["configs"], list)
    assert any(item["id"] == "default" for item in configs_data["data"]["configs"])
