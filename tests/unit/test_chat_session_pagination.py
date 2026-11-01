from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from astrbot.core.db.po import ChatUIProject, PlatformSession, SessionProjectRelation
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.dashboard.api import open_api
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.open_api_service import OpenApiService


@pytest.mark.asyncio
async def test_dashboard_session_pages_reach_older_sessions_and_preserve_scope(
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "sessions.db"))
    await db.initialize()
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with db.get_db() as session:
        async with session.begin():
            session.add_all(
                [
                    PlatformSession(
                        session_id=f"session-{i:03}",
                        creator="owner",
                        platform_id="webchat",
                        display_name=f"Session {i}",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    for i in range(125)
                ]
                + [
                    PlatformSession(session_id="foreign", creator="other"),
                    PlatformSession(session_id="project-session", creator="owner"),
                    PlatformSession(
                        session_id="telegram", creator="owner", platform_id="telegram"
                    ),
                    ChatUIProject(
                        project_id="project", creator="owner", title="Project"
                    ),
                    SessionProjectRelation(
                        session_id="project-session", project_id="project"
                    ),
                ]
            )

    service = object.__new__(OpenApiService)
    service.db = db
    chat_service = object.__new__(ChatService)
    chat_service.db = db
    chat_service.platform_history_mgr = PlatformMessageHistoryManager(db)
    chat_service.running_convs = {}
    chat_service.get_active_chat_runs = lambda _username, _session_id: []
    app = FastAPI()
    app.include_router(open_api.router, prefix="/api/v1")
    app.state.services = SimpleNamespace(open_api=service, chat=chat_service)
    app.dependency_overrides[open_api.require_chat_scope] = lambda: AuthContext(
        username="owner", scopes=["chat"]
    )
    try:
        detail = await chat_service.get_session("owner", "session-000", page_size=50)
        assert detail["session"]["display_name"] == "Session 0"
        assert detail["session"]["platform_id"] == "webchat"
        assert detail["session"]["created_at"] == "2026-01-01T00:00:00+00:00"
        with pytest.raises(ChatServiceError, match="Permission denied"):
            await chat_service.get_session("owner", "foreign", page_size=50)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            ids = []
            for page in range(1, 6):
                response = await client.get(
                    "/api/v1/chat/sessions",
                    params={
                        "page": page,
                        "page_size": 30,
                        "platform_id": "webchat",
                        "username": "other",
                    },
                )
                assert response.status_code == 200
                payload = response.json()["data"]
                assert payload["total"] == 125
                assert payload["page"] == page
                assert payload["page_size"] == 30
                assert all(item["creator"] == "owner" for item in payload["sessions"])
                ids.extend(item["session_id"] for item in payload["sessions"])
            assert ids == [f"session-{i:03}" for i in reversed(range(125))]

            empty = await client.get(
                "/api/v1/chat/sessions?page=6&page_size=30&platform_id=webchat"
            )
            assert empty.json()["data"]["sessions"] == []
            legacy = await client.get("/api/v1/chat/sessions?platform_id=webchat")
            assert isinstance(legacy.json()["data"], list)
            assert len(legacy.json()["data"]) == 100
            size_only = await client.get("/api/v1/chat/sessions?page_size=2")
            assert len(size_only.json()["data"]["sessions"]) == 2
            assert size_only.json()["data"]["page"] == 1
            for query in ("page=x", "page_size=x"):
                invalid = await client.get(f"/api/v1/chat/sessions?{query}")
                assert invalid.json()["status"] == "error"
            bounded = await client.get("/api/v1/chat/sessions?page=0&page_size=1000")
            assert bounded.json()["data"]["page"] == 1
            assert bounded.json()["data"]["page_size"] == 100

            app.dependency_overrides[open_api.require_chat_scope] = lambda: AuthContext(
                username="key-owner", scopes=["chat"], via="api_key"
            )
            api_key_response = await client.get(
                "/api/v1/chat/sessions?page=1&page_size=2&username=owner"
            )
            assert api_key_response.json()["data"]["total"] == 126
            assert len(api_key_response.json()["data"]["sessions"]) == 2
    finally:
        await db.engine.dispose()
