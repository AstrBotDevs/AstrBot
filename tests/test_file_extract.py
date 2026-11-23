"""File extraction reads real temporary bytes through a mocked HTTP transport."""

import httpx
import pytest

from astrbot.core.utils import file_extract


@pytest.mark.asyncio
async def test_file_is_uploaded_before_content_is_requested(monkeypatch, tmp_path):
    source = tmp_path / "input.md"
    source.write_bytes(b"# sample document")
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.method == "POST":
            assert request.url.path == "/v1/files"
            assert b'filename="input.md"' in request.content
            assert b"# sample document" in request.content
            assert b"file-extract" in request.content
            return httpx.Response(200, json={"id": "file-1"})
        assert request.method == "GET"
        assert request.url.path == "/v1/files/file-1/content"
        return httpx.Response(200, text="extracted content")

    real_client = httpx.AsyncClient
    clients = []

    def make_client(**kwargs):
        client = real_client(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    monkeypatch.setattr(file_extract.httpx, "AsyncClient", make_client)
    assert (
        await file_extract.extract_file_moonshotai(str(source), "test-key")
        == "extracted content"
    )
    assert [request.method for request in requests] == ["POST", "GET"]
    assert clients[0].is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("file_id", [None, "", 123, False])
async def test_invalid_file_id_never_requests_content(monkeypatch, tmp_path, file_id):
    source = tmp_path / "input.txt"
    source.write_text("sample")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"id": file_id})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        file_extract.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(ValueError, match="valid file id"):
        await file_extract.extract_file_moonshotai(str(source), "test-key")
    assert [request.method for request in requests] == ["POST"]
