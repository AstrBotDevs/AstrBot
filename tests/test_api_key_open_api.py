import asyncio
import copy
import io
import uuid
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from werkzeug.datastructures import FileStorage

from astrbot.core.auth.models import AuthContext as CoreAuthContext
from astrbot.core.auth.models import Resource, Subject
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogBroker
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_md5_dashboard_password,
)
from astrbot.dashboard.api import open_api as open_api_routes
from astrbot.dashboard.responses import ok
from astrbot.dashboard.server import AstrBotDashboard
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import DASHBOARD_JWT_COOKIE_NAME
from tests.fixtures.helpers import create_isolated_runtime_services
from tests.helpers.dashboard_test_adapter import DashboardTestClient

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"


async def _create_api_key(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    *,
    scopes: list[str],
    name_prefix: str = "openapi-test",
) -> tuple[str, str]:
    step_up_res = await test_client.post(
        "/api/v1/authorization/step-up",
        json={
            "action": "identity.manage",
            "resource_type": "api-key",
            "resource_id": "collection",
            "password": dashboard_password,
        },
        headers=authenticated_header,
    )
    assert step_up_res.status_code == 200
    step_up_data = await step_up_res.get_json()
    step_up_token = step_up_data["data"]["token"]
    create_res = await test_client.post(
        "/api/v1/api-keys",
        json={"name": f"{name_prefix}-{uuid.uuid4().hex[:8]}", "scopes": scopes},
        headers={**authenticated_header, "X-AstrBot-Step-Up": step_up_token},
    )
    assert create_res.status_code == 200
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    return create_data["data"]["api_key"], create_data["data"]["key_id"]


async def _create_step_up(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    config_id: str | None = None,
) -> str:
    payload = {
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "password": dashboard_password,
    }
    if config_id is not None:
        payload["config_id"] = config_id
    response = await test_client.post(
        "/api/v1/authorization/step-up",
        json=payload,
        headers=authenticated_header,
    )
    assert response.status_code == 200
    return (await response.get_json())["data"]["token"]


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    runtime_root = tmp_path_factory.mktemp("astrbot-runtime")
    tmp_db_path = runtime_root / "data" / "test_data_api_key.db"
    log_broker = LogBroker()
    services = create_isolated_runtime_services(runtime_root, tmp_db_path)
    core_lifecycle = AstrBotCoreLifecycle(log_broker, services)
    await core_lifecycle.initialize()
    generated_password = getattr(
        core_lifecycle.astrbot_config,
        "_generated_dashboard_password",
        None,
    )
    dashboard_password = generated_password or _TEST_DASHBOARD_PASSWORD
    if not generated_password:
        core_lifecycle.astrbot_config["dashboard"]["pbkdf2_password"] = (
            hash_dashboard_password(dashboard_password)
        )
        core_lifecycle.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(dashboard_password)
        )
    object.__setattr__(
        core_lifecycle,
        "_dashboard_plain_password",
        dashboard_password,
    )
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
    server = asyncio.run(
        AstrBotDashboard.create(
            core_lifecycle_td.runtime,
            core_lifecycle_td,
            core_lifecycle_td.db,
            shutdown_event,
        )
    )
    return server.asgi_app


@pytest_asyncio.fixture(scope="module")
async def test_client(app: FastAPI):
    client = DashboardTestClient(app)
    try:
        yield client
    finally:
        await client.aclose()


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: FastAPI, core_lifecycle_td: AstrBotCoreLifecycle):
    client = DashboardTestClient(app)
    try:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        data = await response.get_json()
        cookies = SimpleCookie()
        for value in response.headers.getlist("set-cookie"):
            cookies.load(value)
        dashboard_cookie = cookies.get(DASHBOARD_JWT_COOKIE_NAME)
        if dashboard_cookie is None or not dashboard_cookie.value:
            dashboard_cookie_value = data["data"]["token"]
        else:
            dashboard_cookie_value = dashboard_cookie.value
        return {
            "Authorization": f"Bearer {data['data']['token']}",
            "Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={dashboard_cookie_value}",
            "Origin": "http://testserver",
        }
    finally:
        await client.aclose()


@pytest.fixture(scope="module")
def dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    return _resolve_dashboard_password(core_lifecycle_td)


@pytest.mark.asyncio
async def test_conversation_export_requires_dashboard_step_up(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    user_id = f"webchat:FriendMessage:export-{uuid.uuid4().hex[:8]}"
    cid = await core_lifecycle_td.conversation_manager.new_conversation(
        user_id,
        content=[{"role": "user", "content": "export regression"}],
    )
    payload = {"conversations": [{"user_id": user_id, "cid": cid}]}

    without_step_up = await test_client.post(
        "/api/v1/conversations/export",
        json=payload,
        headers=authenticated_header,
    )
    assert without_step_up.status_code == 403
    assert (await without_step_up.get_json())["data"]["requires_step_up"] is True

    step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="data.export_all",
        resource_type="conversation",
        resource_id="export",
    )
    exported = await test_client.post(
        "/api/v1/conversations/export",
        json=payload,
        headers={**authenticated_header, "X-AstrBot-Step-Up": step_up},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    assert "export regression" in (await exported.get_data()).decode()


@pytest.mark.asyncio
async def test_provider_source_step_up_preserves_config_scope(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    source_id = f"openai-step-up-{uuid.uuid4().hex[:8]}"
    config = {
        "id": source_id,
        "type": "openai_chat_completions",
        "provider_type": "chat_completion",
        "provider": "openai",
        "enable": True,
        "api_base": "https://api.example.test/v1",
        "key": ["test-key"],
    }

    without_step_up = await test_client.put(
        f"/api/v1/provider-sources/{source_id}",
        json={"config": config},
        headers=authenticated_header,
    )
    assert without_step_up.status_code == 403
    assert (await without_step_up.get_json())["data"]["requires_step_up"] is True

    step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="provider.credentials.write",
        resource_type="provider-source",
        resource_id=source_id,
        config_id="default",
    )
    saved = await test_client.put(
        f"/api/v1/provider-sources/{source_id}",
        json={"config": config},
        headers={**authenticated_header, "X-AstrBot-Step-Up": step_up},
    )
    assert saved.status_code == 200

    deleted = await test_client.delete(
        f"/api/v1/provider-sources/{source_id}",
        headers=authenticated_header,
    )
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_session_role_binding_step_up_preserves_config_scope(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    subject_id = f"im:napcat:bot:{uuid.uuid4().hex[:8]}"
    umo = f"napcat:GroupMessage:step-up-{uuid.uuid4().hex[:8]}"
    payload = {
        "subject_id": subject_id,
        "role": "session_admin",
        "scope_type": "session",
        "scope_id": umo,
        "config_id": "default",
    }
    step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="session",
        resource_id=umo,
        config_id="default",
    )

    granted = await test_client.post(
        "/api/v1/authorization/role-bindings",
        json=payload,
        headers={**authenticated_header, "X-AstrBot-Step-Up": step_up},
    )

    assert granted.status_code == 200
    binding = (await granted.get_json())["data"]
    assert binding["subject_id"] == subject_id
    assert binding["config_id"] == "default"

    revoke_step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="session",
        resource_id=umo,
        config_id="default",
    )
    revoked = await test_client.post(
        f"/api/v1/authorization/role-bindings/{binding['binding_id']}/revoke",
        headers={**authenticated_header, "X-AstrBot-Step-Up": revoke_step_up},
    )

    assert revoked.status_code == 200

    second_payload = {
        **payload,
        "subject_id": f"im:napcat:bot:{uuid.uuid4().hex[:8]}",
    }
    second_step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="session",
        resource_id=umo,
        config_id="default",
    )
    second_granted = await test_client.post(
        "/api/v1/authorization/role-bindings",
        json=second_payload,
        headers={**authenticated_header, "X-AstrBot-Step-Up": second_step_up},
    )
    assert second_granted.status_code == 200
    second_binding_id = (await second_granted.get_json())["data"]["binding_id"]

    batch_step_up = await test_client.post(
        "/api/v1/authorization/role-bindings/batch-revoke/step-up",
        json={"binding_ids": [second_binding_id], "password": dashboard_password},
        headers=authenticated_header,
    )
    assert batch_step_up.status_code == 200
    batch_token = (await batch_step_up.get_json())["data"]["token"]
    batch_revoked = await test_client.post(
        "/api/v1/authorization/role-bindings/batch-revoke",
        json={"binding_ids": [second_binding_id]},
        headers={**authenticated_header, "X-AstrBot-Step-Up": batch_token},
    )

    assert batch_revoked.status_code == 200
    assert (await batch_revoked.get_json())["data"]["revoked_count"] == 1


@pytest.mark.asyncio
async def test_napcat_instance_operator_role_binding_crud(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    """Exercise Dashboard CRUD and runtime authorization for a NapCat identity."""

    subject_id = "im:napcat:3013138453:3656185279"
    payload = {
        "subject_id": subject_id,
        "role": "instance_operator",
        "scope_type": "instance",
        "scope_id": "default",
        "config_id": "default",
    }

    create_step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="instance",
        resource_id="default",
        config_id="default",
    )
    created = await test_client.post(
        "/api/v1/authorization/role-bindings",
        json=payload,
        headers={**authenticated_header, "X-AstrBot-Step-Up": create_step_up},
    )
    assert created.status_code == 200
    binding = (await created.get_json())["data"]
    assert binding["role"] == "instance_operator"
    assert binding["scope_type"] == "instance"

    listed = await test_client.get(
        "/api/v1/authorization/role-bindings", headers=authenticated_header
    )
    assert listed.status_code == 200
    assert any(
        item["binding_id"] == binding["binding_id"]
        for item in (await listed.get_json())["data"]
    )

    napcat_subject = Subject.im(
        platform_instance="napcat",
        bot_account_id="3013138453",
        sender_id="3656185279",
    )
    authorization = core_lifecycle_td.runtime.services.authorization
    decision = await authorization.authorize(
        napcat_subject,
        "provider.manage",
        Resource.instance("default"),
        CoreAuthContext(
            subject=napcat_subject,
            source="im",
            config_id="default",
            authenticated=True,
        ),
    )
    assert decision.allowed

    update_step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="instance",
        resource_id="default",
        config_id="default",
    )
    updated = await test_client.post(
        "/api/v1/authorization/role-bindings",
        json={**payload, "expires_at": "2030-01-01T00:00:00Z"},
        headers={**authenticated_header, "X-AstrBot-Step-Up": update_step_up},
    )
    assert updated.status_code == 200
    updated_binding = (await updated.get_json())["data"]
    assert updated_binding["binding_id"] == binding["binding_id"]
    assert updated_binding["expires_at"].startswith("2030-01-01T00:00:00")

    revoke_step_up = await _create_step_up(
        test_client,
        authenticated_header,
        dashboard_password,
        action="identity.manage",
        resource_type="instance",
        resource_id="default",
        config_id="default",
    )
    revoked = await test_client.post(
        f"/api/v1/authorization/role-bindings/{binding['binding_id']}/revoke",
        headers={**authenticated_header, "X-AstrBot-Step-Up": revoke_step_up},
    )
    assert revoked.status_code == 200

    listed_after_revoke = await test_client.get(
        "/api/v1/authorization/role-bindings", headers=authenticated_header
    )
    assert listed_after_revoke.status_code == 200
    assert all(
        item["binding_id"] != binding["binding_id"]
        for item in (await listed_after_revoke.get_json())["data"]
    )


@pytest.mark.asyncio
async def test_data_api_key_cannot_export_conversations(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["data"],
        name_prefix="data-export-denied",
    )

    response = await test_client.post(
        "/api/v1/conversations/export",
        json={"conversations": [{"user_id": "any-user", "cid": "any-cid"}]},
        headers={"X-API-Key": raw_key},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_backup_download_uses_root_binding_and_fails_closed(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
    tmp_path,
):
    """Backup archives require the live Dashboard root, never a data API key."""

    service = app.state.services.backups
    original_backup_dir = service.backup_dir
    service.backup_dir = str(tmp_path)
    (tmp_path / "authorized-backup.zip").write_bytes(b"backup")
    try:
        dashboard = await test_client.get(
            "/api/v1/backups/authorized-backup.zip",
            headers=authenticated_header,
        )
        assert dashboard.status_code == 200
        assert (await dashboard.get_data()) == b"backup"

        data_key, _ = await _create_api_key(
            test_client,
            authenticated_header,
            dashboard_password,
            scopes=["data"],
            name_prefix="backup-data-denied",
        )
        api_key = await test_client.get(
            "/api/v1/backups/authorized-backup.zip",
            headers={"X-API-Key": data_key},
        )
        assert api_key.status_code == 403

        authorization = core_lifecycle_td.runtime.services.authorization
        core_lifecycle_td.runtime.services.authorization = None
        try:
            unavailable = await test_client.get(
                "/api/v1/backups/authorized-backup.zip",
                headers=authenticated_header,
            )
            assert unavailable.status_code == 503
            assert (await unavailable.get_json())[
                "message"
            ] == "Authorization unavailable"
        finally:
            core_lifecycle_td.runtime.services.authorization = authorization
    finally:
        service.backup_dir = original_backup_dir


@pytest.mark.asyncio
async def test_control_plane_management_routes_fail_closed_without_authorization(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    authorization = core_lifecycle_td.runtime.services.authorization
    core_lifecycle_td.runtime.services.authorization = None
    try:
        api_keys = await test_client.get(
            "/api/v1/api-keys", headers=authenticated_header
        )
        role_bindings = await test_client.get(
            "/api/v1/authorization/role-bindings",
            headers=authenticated_header,
        )
    finally:
        core_lifecycle_td.runtime.services.authorization = authorization

    assert api_keys.status_code == 503
    assert (await api_keys.get_json())["message"] == "Authorization unavailable"
    assert role_bindings.status_code == 503
    assert (await role_bindings.get_json())["message"] == "Authorization unavailable"


@pytest.mark.asyncio
async def test_api_key_scope_and_revoke(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):

    raw_key, key_id = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
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
        files={
            "file": FileStorage(
                stream=io.BytesIO(b"scope denied"),
                filename="denied.txt",
                content_type="text/plain",
            ),
        },
        headers={"X-API-Key": raw_key},
    )
    assert denied_res.status_code == 403

    revoke_res = await test_client.post(
        f"/api/v1/api-keys/{key_id}/revoke",
        headers={
            **authenticated_header,
            "X-AstrBot-Step-Up": (
                await (
                    await test_client.post(
                        "/api/v1/authorization/step-up",
                        json={
                            "action": "identity.manage",
                            "resource_type": "api-key",
                            "resource_id": "collection",
                            "password": dashboard_password,
                        },
                        headers=authenticated_header,
                    )
                ).get_json()
            )["data"]["token"],
        },
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
async def test_open_send_message_with_api_key(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):

    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["im"],
        name_prefix="send-message-key",
    )

    send_res = await test_client.post(
        "/api/v1/im/messages",
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
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
):

    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["chat"],
        name_prefix="chat-send-key",
    )

    async def fake_chat_response(
        _chat_service,
        username: str,
        post_data: dict,
        **_kwargs,
    ):
        return ok(
            {
                "session_id": post_data.get("session_id"),
                "creator": username,
            }
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_chat_response,
    )
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
        monkeypatch.undo()

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
async def test_open_chat_username_is_not_an_admin_identity(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    monkeypatch: pytest.MonkeyPatch,
):
    basic_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["chat"],
        name_prefix="chat-basic-admin-boundary",
    )
    calls: list[tuple[str, tuple[str, ...] | None]] = []

    async def fake_chat_response(
        _chat_service,
        username: str,
        post_data: dict,
        *,
        api_key_principal: dict | None = None,
        **_kwargs,
    ):
        scopes = api_key_principal.get("scopes", ()) if api_key_principal else None
        calls.append((username, None if scopes is None else tuple(scopes)))
        return ok({"session_id": post_data["session_id"], "creator": username})

    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_chat_response,
    )

    accepted = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "fixture-api-admin",
            "session_id": f"openapi_admin_denied_{uuid.uuid4().hex[:8]}",
        },
        headers={"X-API-Key": basic_key},
    )
    assert accepted.status_code == 200
    assert calls[-1] == ("fixture-api-admin", ("chat",))

    ordinary = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "ordinary-api-user",
            "session_id": f"openapi_internal_flag_{uuid.uuid4().hex[:8]}",
        },
        headers={"X-API-Key": basic_key},
    )
    assert ordinary.status_code == 200
    assert calls[-1] == ("ordinary-api-user", ("chat",))

    allowed = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "fixture-api-admin",
            "session_id": f"openapi_admin_allowed_{uuid.uuid4().hex[:8]}",
        },
        headers={"X-API-Key": basic_key},
    )
    assert allowed.status_code == 200
    allowed_data = await allowed.get_json()
    assert allowed_data["status"] == "ok"
    assert calls[-1] == ("fixture-api-admin", ("chat",))

    dashboard = await test_client.post(
        "/api/v1/chat",
        json={"message": "hello", "session_id": f"dashboard_{uuid.uuid4().hex[:8]}"},
        headers=authenticated_header,
    )
    assert dashboard.status_code == 200
    assert calls[-1][1] is None


@pytest.mark.asyncio
async def test_api_key_configuration_rejects_deprecated_permission_fields(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    config_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["config"],
        name_prefix="config-admin-boundary",
    )
    rejected_create = await test_client.post(
        "/api/v1/config-profiles",
        json={
            "name": "deprecated-config-profile",
            "config": {"admins_id": ["stale-admin"]},
        },
        headers={"X-API-Key": config_key},
    )
    assert rejected_create.status_code == 422

    created = await test_client.post(
        "/api/v1/config-profiles",
        json={"name": "ordinary-config-profile"},
        headers={"X-API-Key": config_key},
    )
    assert created.status_code == 200
    profile_id = (await created.get_json())["data"]["conf_id"]
    profile = await test_client.get(
        f"/api/v1/config-profiles/{profile_id}",
        headers={"X-API-Key": config_key},
    )
    profile_config = copy.deepcopy((await profile.get_json())["data"]["config"])
    profile_config["admins_id"] = ["changed-profile-admin"]
    profile_config["tool_permissions"] = {"shell": "admin"}
    profile_config["disable_builtin_commands"] = True
    profile_update = await test_client.put(
        f"/api/v1/config-profiles/{profile_id}",
        json=profile_config,
        headers={"X-API-Key": config_key},
    )
    assert profile_update.status_code == 422
    stored_profile = await test_client.get(
        f"/api/v1/config-profiles/{profile_id}",
        headers={"X-API-Key": config_key},
    )
    stored_profile_config = (await stored_profile.get_json())["data"]["config"]
    assert not {
        "admins_id",
        "tool_permissions",
        "disable_builtin_commands",
    }.intersection(stored_profile_config)

    system = await test_client.get(
        "/api/v1/system-config",
        headers={"X-API-Key": config_key},
    )
    system_config = copy.deepcopy((await system.get_json())["data"]["config"])
    system_config["admins_id"] = ["changed-system-admin"]
    system_config["tool_permissions"] = {"python": "admin"}
    system_config["disable_builtin_commands"] = True
    system_update = await test_client.put(
        "/api/v1/system-config",
        json=system_config,
        headers={"X-API-Key": config_key},
    )
    assert system_update.status_code == 422
    stored_system = await test_client.get(
        "/api/v1/system-config",
        headers={"X-API-Key": config_key},
    )
    stored_system_config = (await stored_system.get_json())["data"]["config"]
    assert not {
        "admins_id",
        "tool_permissions",
        "disable_builtin_commands",
    }.intersection(stored_system_config)


@pytest.mark.asyncio
async def test_unknown_sensitive_scopes_are_rejected_and_null_is_baseline(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    monkeypatch: pytest.MonkeyPatch,
):
    step_up_res = await test_client.post(
        "/api/v1/authorization/step-up",
        json={
            "action": "identity.manage",
            "resource_type": "api-key",
            "resource_id": "collection",
            "password": dashboard_password,
        },
        headers=authenticated_header,
    )
    assert step_up_res.status_code == 200
    management_headers = {
        **authenticated_header,
        "X-AstrBot-Step-Up": (await step_up_res.get_json())["data"]["token"],
    }
    child_only = await test_client.post(
        "/api/v1/api-keys",
        json={"name": "invalid-child", "scopes": ["chat:admin"]},
        headers=management_headers,
    )
    assert child_only.status_code == 400

    async def fake_chat_response(
        _chat_service,
        username: str,
        post_data: dict,
        *,
        api_key_principal: dict | None = None,
    ):
        return ok({"session_id": post_data["session_id"], "creator": username})

    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_chat_response,
    )

    raw_key = f"abk_null_scope_{uuid.uuid4().hex}"
    await app.state.db.create_api_key(
        name="legacy-null-scope",
        key_hash=ApiKeyService.hash_key(raw_key),
        key_prefix=raw_key[:12],
        scopes=None,
        created_by="test",
    )
    accepted = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "fixture-api-admin",
            "session_id": f"null_scope_{uuid.uuid4().hex[:8]}",
        },
        headers={"X-API-Key": raw_key},
    )
    assert accepted.status_code == 200

    list_step_up = await test_client.post(
        "/api/v1/authorization/step-up",
        json={
            "action": "identity.manage",
            "resource_type": "api-key",
            "resource_id": "collection",
            "password": dashboard_password,
        },
        headers=authenticated_header,
    )
    list_headers = {
        **authenticated_header,
        "X-AstrBot-Step-Up": (await list_step_up.get_json())["data"]["token"],
    }
    listed = await test_client.get("/api/v1/api-keys", headers=list_headers)
    null_scope_key = next(
        item
        for item in (await listed.get_json())["data"]
        if item["name"] == "legacy-null-scope"
    )
    assert "chat" in null_scope_key["scopes"]
    assert "chat:admin" not in null_scope_key["scopes"]


@pytest.mark.asyncio
async def test_open_chat_sessions_pagination(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
):

    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
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
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):

    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
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
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):

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
        test_client,
        authenticated_header,
        dashboard_password,
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
async def test_open_chat_rejects_blank_username_and_uses_session_id(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["chat"],
        name_prefix="chat-conversation-key",
    )

    async def fake_chat_response(
        _chat_service,
        _username: str,
        post_data: dict,
        **_kwargs,
    ):
        return ok({"session_id": post_data.get("session_id")})

    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_chat_response,
    )

    session_id = f"open_api_session_{uuid.uuid4().hex[:10]}"
    send_res = await test_client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "username": "alias-user",
            "session_id": session_id,
            "enable_streaming": False,
        },
        headers={"X-API-Key": raw_key},
    )
    assert send_res.status_code == 200
    send_data = await send_res.get_json()
    assert send_data["status"] == "ok"
    assert send_data["data"]["session_id"] == session_id

    created_session = await core_lifecycle_td.db.get_platform_session_by_id(session_id)
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
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    monkeypatch: pytest.MonkeyPatch,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["chat"],
        name_prefix="chat-config-resolution-key",
    )
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
    monkeypatch.setattr(
        open_api_routes,
        "_get_chat_config_list",
        lambda _service: conf_list,
    )

    update_route = AsyncMock()
    delete_route = AsyncMock()
    monkeypatch.setattr(
        app.state.dashboard_server.runtime.umop_config_router,
        "update_route",
        update_route,
    )
    monkeypatch.setattr(
        app.state.dashboard_server.runtime.umop_config_router,
        "delete_route",
        delete_route,
    )

    async def fake_chat_response(
        _chat_service,
        username: str,
        post_data: dict,
        **_kwargs,
    ):
        return ok(
            {
                "session_id": post_data.get("session_id"),
                "creator": username,
            }
        )

    monkeypatch.setattr(
        open_api_routes,
        "_build_streaming_chat_response",
        fake_chat_response,
    )

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
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
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
async def test_open_send_message_error_paths(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["im"],
        name_prefix="im-errors-key",
    )

    missing_message_res = await test_client.post(
        "/api/v1/im/messages",
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
        "/api/v1/im/messages",
        json={"message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    missing_umo_data = await missing_umo_res.get_json()
    assert missing_umo_data["status"] == "error"
    assert missing_umo_data["message"] == "Missing key: umo"

    invalid_umo_res = await test_client.post(
        "/api/v1/im/messages",
        json={"umo": "broken-umo", "message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    invalid_umo_data = await invalid_umo_res.get_json()
    assert invalid_umo_data["status"] == "error"
    assert invalid_umo_data["message"] == "Invalid umo"

    missing_platform_res = await test_client.post(
        "/api/v1/im/messages",
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
async def test_open_api_key_scope_normalization(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    _, config_key_id = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["config"],
        name_prefix="config-contained-scopes",
    )
    _, extra_key_id = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["mcp", "skill"],
        name_prefix="mcp-skill-scope",
    )
    keys = await app.state.db.list_api_keys()
    scopes_by_id = {key.key_id: key.scopes for key in keys}
    assert set(scopes_by_id[config_key_id]) == {"config", "bot", "provider"}
    assert set(scopes_by_id[extra_key_id]) == {"mcp", "skill"}


@pytest.mark.asyncio
async def test_api_key_extension_scopes_do_not_grant_high_risk_writes(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    mcp_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["mcp"],
        name_prefix="mcp-read-only",
    )
    plugin_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["plugin"],
        name_prefix="plugin-read-only",
    )

    mcp_response = await test_client.post(
        "/api/v1/mcp/servers",
        json={"name": "external", "url": "https://example.com/mcp"},
        headers={"X-API-Key": mcp_key},
    )
    plugin_response = await test_client.post(
        "/api/v1/plugins/install/url",
        json={"url": "https://example.com/plugin.zip"},
        headers={"X-API-Key": plugin_key},
    )

    assert mcp_response.status_code == 403
    assert plugin_response.status_code == 403


@pytest.mark.asyncio
async def test_file_scope_is_available_for_developer_api_key(
    app: FastAPI,
    test_client: DashboardTestClient,
    authenticated_header: dict,
    dashboard_password: str,
):
    raw_key, _ = await _create_api_key(
        test_client,
        authenticated_header,
        dashboard_password,
        scopes=["file"],
        name_prefix="file-scope",
    )

    upload_res = await test_client.post(
        "/api/v1/file",
        files={
            "file": FileStorage(
                stream=io.BytesIO(b"hello from api key"),
                filename="api-key-upload.txt",
                content_type="text/plain",
            ),
        },
        headers={"X-API-Key": raw_key},
    )
    upload_data = await upload_res.get_json()

    assert upload_res.status_code == 200
    assert upload_data["status"] == "ok"
    assert upload_data["data"]["filename"] == "api-key-upload.txt"
    assert upload_data["data"]["type"] == "file"
    assert upload_data["data"]["attachment_id"]
