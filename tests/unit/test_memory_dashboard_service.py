from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from astrbot.core.memory import MemoryManager
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.api.memory import list_memory_facts, refresh_memory_profile
from astrbot.dashboard.api.memory import router as memory_router
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.schemas import MemoryProfileRefreshRequest
from astrbot.dashboard.services.auth_service import DashboardTokenValidator
from astrbot.dashboard.services.memory_service import MemoryService
from tests.fixtures.auth import TestAuthorizationService

JWT_SECRET = "memory-dashboard-service-test-secret"


def _memory_headers() -> dict[str, str]:
    token = DashboardTokenValidator(JWT_SECRET).issue("memory-dashboard-user")
    return {"Authorization": f"Bearer {token}"}


def _memory_app(service: MemoryService, db) -> FastAPI:
    app = FastAPI()
    app.state.jwt_secret = JWT_SECRET
    app.state.dashboard_token_validator = DashboardTokenValidator(JWT_SECRET)
    app.state.db = db
    app.state.services = SimpleNamespace(memory=service)
    app.state.runtime = SimpleNamespace(
        services=SimpleNamespace(
            authorization=TestAuthorizationService("data.manage"),
        )
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request, exc: ApiError):
        return JSONResponse(error(exc.message, exc.data), status_code=exc.status_code)

    app.include_router(memory_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_memory_service_fact_lifecycle_stats_and_logs(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    service = MemoryService(temp_db, memory_manager)

    created, _ = await service.create_fact(
        {
            "person_id": "user-api",
            "chat_id": "telegram:GroupMessage:g1",
            "fact_text": "用户喜欢猫娘。",
            "fact_type": "preference",
            "confidence": 0.8,
        },
        operator="dashboard-user",
    )
    fact_id = created["id"]

    listed = await service.list_facts(
        page=1,
        page_size=10,
        person_id="user-api",
        chat_id="telegram:GroupMessage:g1",
        query="猫娘",
    )
    detail = await service.get_fact(fact_id)
    updated, _ = await service.update_fact(
        fact_id,
        {"confidence": 0.7, "reason": "manual correction"},
        operator="dashboard-user",
    )
    await service.set_fact_status(
        fact_id,
        status="deleted",
        operator="dashboard-user",
        reason="user requested deletion",
    )
    deleted_detail = await service.get_fact(fact_id)
    deleted_stats = await service.stats()
    await service.set_fact_status(
        fact_id,
        status="active",
        operator="dashboard-user",
        reason="restore same fact",
    )
    operations = await service.list_operations(
        page=1,
        page_size=20,
        target_type="memory_fact",
        target_id=str(fact_id),
    )

    assert listed["total"] == 1
    assert detail["fact"]["id"] == fact_id
    assert updated["confidence"] == 0.7
    assert deleted_detail["fact"]["id"] == fact_id
    assert deleted_detail["fact"]["status"] == "deleted"
    assert deleted_detail["operation_logs"][0]["action"] == "delete"
    assert deleted_stats["deleted_facts"] == 1
    assert [item["action"] for item in operations["items"][:4]] == [
        "restore",
        "delete",
        "update",
        "create",
    ]


@pytest.mark.asyncio
async def test_memory_service_profiles_refresh_and_api_route_listing(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    service = MemoryService(temp_db, memory_manager)
    fact, _ = await temp_db.upsert_memory_fact(
        person_id="user-profile",
        chat_id="webchat:FriendMessage:s1",
        scope_id="isolated:webchat:FriendMessage:s1",
        fact_text="User likes service tests.",
        fact_type="preference",
        source_message_id="s1:1",
    )

    refresh = await service.refresh_profile(
        "user-profile",
        {"chat_scope": "isolated:webchat:FriendMessage:s1"},
        operator="dashboard-user",
    )
    await next(iter(service._background_tasks))  # noqa: SLF001

    profiles = await service.list_profiles(
        page=1,
        page_size=10,
        person_id="user-profile",
    )
    route_response = await list_memory_facts(
        SimpleNamespace(
            query_params={
                "page": "1",
                "page_size": "10",
                "person_id": "user-profile",
            }
        ),
        AuthContext(
            username="dashboard-user",
            scopes=["*"],
            subject="dashboard-session:test",
        ),
        service,
    )

    assert refresh["status"] == "pending"
    assert profiles["items"][0]["profile_text"].startswith("Known user profile")
    assert route_response["status"] == "ok"
    assert route_response["data"]["items"][0]["id"] == fact.id


@pytest.mark.asyncio
async def test_memory_profile_refresh_route_accepts_optional_body(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    service = MemoryService(temp_db, memory_manager)
    auth = AuthContext(
        username="dashboard-user",
        scopes=["*"],
        subject="dashboard-session:test",
    )

    missing_scope = await refresh_memory_profile(
        "user-profile",
        None,
        auth,
        service,
    )
    queued = await refresh_memory_profile(
        "user-profile",
        MemoryProfileRefreshRequest(chat_scope="isolated:webchat:FriendMessage:s1"),
        auth,
        service,
    )

    await next(iter(service._background_tasks))  # noqa: SLF001

    assert missing_scope["status"] == "error"
    assert "chat_scope or chat_id is required" in missing_scope["message"]
    assert queued["status"] == "ok"
    assert queued["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_memory_api_routes_use_real_http_and_sqlite(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    service = MemoryService(temp_db, memory_manager)
    app = _memory_app(service, temp_db)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        unauthorized = await client.get("/api/v1/memory/facts")
        created = await client.post(
            "/api/v1/memory/facts",
            json={
                "person_id": "http-user",
                "chat_id": "telegram:GroupMessage:g1",
                "fact_text": "用户喜欢猫娘。",
                "fact_type": "preference",
                "confidence": 0.8,
            },
            headers=_memory_headers(),
        )
        fact_id = created.json()["data"]["id"]
        listed = await client.get(
            "/api/v1/memory/facts",
            params={"person_id": "http-user", "query": "猫娘"},
            headers=_memory_headers(),
        )
        deleted = await client.post(
            f"/api/v1/memory/facts/{fact_id}/delete",
            json={"reason": "http delete"},
            headers=_memory_headers(),
        )
        detail_after_delete = await client.get(
            f"/api/v1/memory/facts/{fact_id}",
            headers=_memory_headers(),
        )
        restored = await client.post(
            f"/api/v1/memory/facts/{fact_id}/restore",
            headers=_memory_headers(),
        )
        stats = await client.get("/api/v1/memory/stats", headers=_memory_headers())
        refresh_without_body = await client.post(
            "/api/v1/memory/profiles/http-user/refresh",
            headers=_memory_headers(),
        )

    assert unauthorized.status_code == 401
    assert created.status_code == 200
    assert created.json()["status"] == "ok"
    assert listed.json()["data"]["items"][0]["id"] == fact_id
    assert deleted.json()["status"] == "ok"
    assert detail_after_delete.json()["data"]["fact"]["id"] == fact_id
    assert detail_after_delete.json()["data"]["fact"]["status"] == "deleted"
    assert detail_after_delete.json()["data"]["operation_logs"][0]["action"] == "delete"
    assert restored.json()["status"] == "ok"
    assert stats.json()["data"]["facts"] == 1
    assert refresh_without_body.status_code == 200
    assert refresh_without_body.json()["status"] == "error"


@pytest.mark.asyncio
async def test_memory_api_returns_503_when_authorization_service_is_unavailable(
    temp_db,
):
    await temp_db.initialize()
    service = MemoryService(temp_db, MemoryManager(temp_db))
    app = _memory_app(service, temp_db)
    del app.state.runtime

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        unauthenticated = await client.get("/api/v1/memory/facts")
        unavailable = await client.get(
            "/api/v1/memory/facts",
            headers=_memory_headers(),
        )

    assert unauthenticated.status_code == 401
    assert unavailable.status_code == 503
