"""Optional body bounds must work for streamed and already-cached requests."""

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.requests import Request as StarletteRequest

from astrbot.dashboard.asgi_runtime import DashboardRequest


@pytest.mark.asyncio
async def test_bounded_body_preserves_repeated_reads_and_json():
    app = FastAPI()

    @app.post("/")
    async def endpoint(request: Request):
        wrapped = DashboardRequest(request)
        assert await wrapped.get_data(max_size=15) == b'{"hello":"yes"}'
        assert await wrapped.get_data() == b'{"hello":"yes"}'
        assert await wrapped.get_json() == {"hello": "yes"}
        assert await request.body() == b'{"hello":"yes"}'
        with pytest.raises(ValueError, match="size limit"):
            await wrapped.get_data(max_size=3)
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/", content=b'{"hello":"yes"}')
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised_length", [None, b"1", b"999999"])
async def test_bounded_body_stops_stream_at_limit(advertised_length):
    headers = (
        [] if advertised_length is None else [(b"content-length", advertised_length)]
    )
    calls = 0

    async def receive():
        nonlocal calls
        calls += 1
        if calls > 2:
            raise AssertionError(
                "The request stream was read after exceeding the limit"
            )
        return {"type": "http.request", "body": b"1234", "more_body": True}

    raw = StarletteRequest(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers,
            "query_string": b"",
        },
        receive,
    )
    wrapped = DashboardRequest(raw)
    with pytest.raises(ValueError, match="size limit"):
        await wrapped.get_data(max_size=5)
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [-1, True, 1.5, "5"])
async def test_invalid_body_limit_does_not_read(limit):
    async def receive():
        raise AssertionError("Invalid limits must be rejected before reading")

    raw = StarletteRequest(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
        },
        receive,
    )
    with pytest.raises(ValueError, match="non-negative integer"):
        await DashboardRequest(raw).get_data(max_size=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("body,limit", [(b"", 0), (b"12345", 5), (b"123456", 5)])
async def test_cached_body_obeys_limit(body, limit):
    raw = StarletteRequest(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    raw._body = body
    wrapped = DashboardRequest(raw)
    if len(body) > limit:
        with pytest.raises(ValueError, match="size limit"):
            await wrapped.get_data(max_size=limit)
    else:
        assert await wrapped.get_data(max_size=limit) == body
    assert await wrapped.get_data() == body


@pytest.mark.asyncio
async def test_bounded_read_preserves_form_reader():
    app = FastAPI()

    @app.post("/")
    async def endpoint(request: Request):
        wrapped = DashboardRequest(request)
        assert await wrapped.get_data(max_size=17) == b"name=one&name=two"
        form = await wrapped.form
        assert form.getlist("name") == ["one", "two"]
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/",
            content=b"name=one&name=two",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
    assert response.status_code == 200
