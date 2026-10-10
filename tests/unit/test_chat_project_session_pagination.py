from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from astrbot.core.db.po import ChatUIProject, PlatformSession, SessionProjectRelation
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.api import chat_projects
from astrbot.dashboard.api.auth import AuthContext
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService


@pytest.mark.asyncio
async def test_project_session_pages_reach_older_sessions_and_preserve_scope(tmp_path):
    """Project pagination must reach old sessions without crossing project ownership."""
    db = SQLiteDatabase(str(tmp_path / "projects.db"))
    await db.initialize()
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        async with db.get_db() as session:
            async with session.begin():
                session.add_all(
                    [
                        ChatUIProject(project_id="project", creator="owner", title="P"),
                        ChatUIProject(project_id="other", creator="owner", title="O"),
                        ChatUIProject(project_id="foreign", creator="other", title="F"),
                    ]
                )
                for i in range(126):
                    session.add(
                        PlatformSession(
                            session_id=f"session-{i:03}",
                            creator="owner",
                            platform_id="webchat",
                            updated_at=timestamp,
                        )
                    )
                    session.add(
                        SessionProjectRelation(
                            session_id=f"session-{i:03}",
                            project_id="project" if i < 125 else "other",
                        )
                    )
        app = FastAPI()
        app.include_router(chat_projects.router, prefix="/api/v1")
        app.state.services = SimpleNamespace(chat_projects=ChatUIProjectService(db))
        app.dependency_overrides[chat_projects.require_chat_scope] = lambda: (
            AuthContext(username="owner", scopes=["chat"])
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            url = "/api/v1/chat/projects/project/sessions"
            ids = []
            for page in range(1, 6):
                response = await client.get(url, params={"page": page, "page_size": 30})
                assert response.status_code == 200
                data = response.json()["data"]
                assert data["page"] == page
                assert data["page_size"] == 30
                assert data["total"] == 125
                ids.extend(item["session_id"] for item in data["sessions"])
            assert ids == [f"session-{i:03}" for i in reversed(range(125))]
            legacy = (await client.get(url)).json()["data"]
            assert isinstance(legacy, list)
            assert len(legacy) == 100
            empty = (await client.get(url, params={"page": 6, "page_size": 30})).json()[
                "data"
            ]
            assert empty["sessions"] == []
            assert empty["total"] == 125
            full_page = (
                await client.get(url, params={"page": 5, "page_size": 25})
            ).json()["data"]
            assert len(full_page["sessions"]) == 25
            assert full_page["page"] * full_page["page_size"] == full_page["total"]
            size_only = (await client.get(url, params={"page_size": 30})).json()["data"]
            assert size_only["page"] == 1
            assert len(size_only["sessions"]) == 30
            for query in ("page=0", "page=x", "page_size=0", "page_size=101"):
                assert (await client.get(f"{url}?{query}")).status_code == 422
            denied = await client.get("/api/v1/chat/projects/foreign/sessions?page=1")
            assert denied.json()["status"] == "error"
    finally:
        await db.engine.dispose()
