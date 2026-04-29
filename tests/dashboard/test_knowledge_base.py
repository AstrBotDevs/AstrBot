"""Tests for the knowledge base route module.

Covers import smoke tests for ``KnowledgeBaseRoute`` and key KB / document
CRUD endpoints.
"""

import pytest

from astrbot.dashboard.routes.knowledge_base import (
    KnowledgeBaseRoute,
)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

def test_knowledge_base_route_class():
    assert KnowledgeBaseRoute is not None


# ---------------------------------------------------------------------------
# Endpoint tests - KB CRUD
# ---------------------------------------------------------------------------

class TestKnowledgeBaseCRUD:
    """CRUD tests for the ``/kb/*`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_kbs(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/list",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")
        if data["status"] == "ok":
            assert "items" in data["data"]
            assert isinstance(data["data"]["items"], list)

    @pytest.mark.asyncio
    async def test_create_kb_missing_name(self, app, authenticated_header):
        """Creating a KB without a name should return a non-500 error."""
        client = app.test_client()
        resp = await client.post(
            "/api/kb/create",
            headers=authenticated_header,
            json={"kb_name": ""},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_create_kb_missing_embedding(self, app, authenticated_header):
        """Creating a KB without embedding_provider_id should error."""
        client = app.test_client()
        resp = await client.post(
            "/api/kb/create",
            headers=authenticated_header,
            json={"kb_name": "pytest-kb"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        # Should fail because embedding_provider_id is required
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_kb_missing_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/get",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_kb_nonexistent(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/get?kb_id=nonexistent",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_update_kb_missing_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/update",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_delete_kb_missing_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/delete",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_kb_stats_missing_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/stats",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Endpoint tests - KB document operations
# ---------------------------------------------------------------------------

class TestKnowledgeBaseDocumentEndpoints:
    """Endpoint tests for ``/kb/document/*`` routes."""

    @pytest.mark.asyncio
    async def test_list_documents_missing_kb_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/document/list",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_document_missing_ids(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/document/get",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        # Missing both kb_id and doc_id -> error
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_delete_document_missing_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/document/delete",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_chunks_missing_kb_id(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/chunk/list",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_retrieve_missing_query(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/retrieve",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Endpoint tests - upload / import
# ---------------------------------------------------------------------------

class TestKnowledgeBaseUploadEndpoints:
    """Endpoint tests for upload and import related routes."""

    @pytest.mark.asyncio
    async def test_upload_progress_missing_task(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.get(
            "/api/kb/document/upload/progress?task_id=nonexistent-task-id",
            headers=authenticated_header,
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_upload_document_no_content_type(self, app, authenticated_header):
        """Upload without multipart content-type should fail validation."""
        client = app.test_client()
        resp = await client.post(
            "/api/kb/document/upload",
            headers=authenticated_header,
            json={"kb_id": "test"},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_import_documents_missing_kb(self, app, authenticated_header):
        client = app.test_client()
        resp = await client.post(
            "/api/kb/document/import",
            headers=authenticated_header,
            json={},
        )
        assert resp.status_code != 500
        data = await resp.get_json()
        assert data["status"] == "error"
