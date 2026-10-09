"""Network-free tests of the plugin OAuth public-client implementation."""

import asyncio
import base64
import hashlib
import time
from dataclasses import asdict
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from astrbot.core.provider.oauth import OAuth2Error, OAuth2Session, OAuth2Token

pytestmark = pytest.mark.asyncio


class MemoryStore:
    def __init__(self, token=None):
        self.token = token
        self.loads = 0

    async def load(self):
        self.loads += 1
        return self.token

    async def save(self, token):
        self.token = token


def make_session(handler=None, token=None, **kwargs):
    store = MemoryStore(token)
    calls = []

    async def handle(request):
        calls.append(request)
        if handler:
            result = handler(request)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        return httpx.Response(200, json={
            "access_token": "new-access", "token_type": "Bearer",
            "refresh_token": "new-refresh", "expires_in": 3600,
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True)
    config = dict(
        client_id="registered-public-client",
        authorization_endpoint="https://login.example.com/authorize?audience=ai",
        token_endpoint="https://login.example.com/token",
        redirect_uri="http://127.0.0.1:9876/callback",
        api_base="https://api.example.com/v1",
        http_client=client,
        load_token=store.load,
        save_token=store.save,
        scopes=("models:read", "inference"),
    )
    config.update(kwargs)
    return OAuth2Session(**config), store, calls, client


async def callback(session, owner="admin", **overrides):
    url = await session.begin_authorization(owner=owner)
    state = parse_qs(urlsplit(url).query)["state"][0]
    params = {"code": "one-time-code", "state": state}
    params.update(overrides)
    return "http://127.0.0.1:9876/callback?" + urlencode(params)


async def test_pkce_exchange_persistence_and_public_url():
    session, store, calls, client = make_session()
    async with client:
        url = await session.begin_authorization(owner="admin")
        query = parse_qs(urlsplit(url).query)
        assert query["audience"] == ["ai"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["models:read inference"]
        assert "code_verifier" not in query
        cb = "http://127.0.0.1:9876/callback?" + urlencode({
            "code": "one-time-code", "state": query["state"][0],
        })
        await session.complete_authorization(cb, owner="admin")
        assert len(calls) == 1
        form = parse_qs(calls[0].content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["client_id"] == ["registered-public-client"]
        assert form["redirect_uri"] == ["http://127.0.0.1:9876/callback"]
        verifier = form["code_verifier"][0]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        assert 43 <= len(verifier) <= 128
        assert challenge == query["code_challenge"][0]
        assert verifier not in url
        assert store.token.access_token == "new-access"
        assert await session.get_access_token() == "new-access"
        assert len(calls) == 1
        with pytest.raises(OAuth2Error, match="expired"):
            await session.complete_authorization(cb, owner="admin")


async def test_wrong_owner_or_state_does_not_consume_login():
    session, _, calls, client = make_session()
    async with client:
        cb = await callback(session)
        with pytest.raises(OAuth2Error, match="another user"):
            await session.complete_authorization(cb, owner="other")
        with pytest.raises(OAuth2Error, match="state"):
            await session.complete_authorization(cb + "&state=wrong", owner="admin")
        assert not calls
        await session.complete_authorization(cb, owner="admin")
        assert len(calls) == 1


@pytest.mark.parametrize("suffix", [
    "&code=duplicate", "#fragment", "&state=duplicate", "&state=",
])
async def test_ambiguous_callback_rejected(suffix):
    session, _, calls, client = make_session()
    async with client:
        cb = await callback(session)
        with pytest.raises(OAuth2Error):
            await session.complete_authorization(cb + suffix, owner="admin")
        assert not calls


async def test_expiry_new_attempt_and_cancel(monkeypatch):
    session, _, calls, client = make_session()
    async with client:
        old = await callback(session)
        new = await callback(session)
        assert old != new
        with pytest.raises(OAuth2Error):
            await session.complete_authorization(old, owner="admin")
        with pytest.raises(OAuth2Error):
            await session.cancel_authorization(owner="other")
        await session.cancel_authorization(owner="admin")
        with pytest.raises(OAuth2Error):
            await session.complete_authorization(new, owner="admin")
        cb = await callback(session)
        now = time.monotonic()
        monkeypatch.setattr("astrbot.core.provider.oauth.time.monotonic", lambda: now + 601)
        with pytest.raises(OAuth2Error, match="expired"):
            await session.complete_authorization(cb, owner="admin")
        assert not calls


async def test_denial_consumes_attempt_without_echoing_provider_text():
    session, _, calls, client = make_session()
    async with client:
        cb = await callback(session, error="access_denied", error_description="PRIVATE_SECRET")
        with pytest.raises(OAuth2Error, match="denied") as error:
            await session.complete_authorization(cb, owner="admin")
        assert "PRIVATE_SECRET" not in str(error.value)
        with pytest.raises(OAuth2Error, match="expired"):
            await session.complete_authorization(cb, owner="admin")
        assert not calls


@pytest.mark.parametrize("field,value", [
    ("authorization_endpoint", "http://evil.example/authorize"),
    ("authorization_endpoint", " https://login.example.com/auth"),
    ("authorization_endpoint", "https://login.example.com/au\nth"),
    ("authorization_endpoint", "https://login.example.com/a b"),
    ("token_endpoint", "https://user:secret@example.com/token"),
    ("token_endpoint", "https://@example.com/token"),
    ("token_endpoint", "https://example.com:bad/token"),
    ("redirect_uri", "https://example.com/callback#fragment"),
    ("redirect_uri", "https://example.com/callback?state="),
    ("authorization_endpoint", "https://example.com/authorize?client_id="),
    ("api_base", "http://127.0.0.1.evil.example/v1"),
    ("api_base", "https://example.com/v1?api_key=secret"),
    ("client_id", ""), ("scopes", ("two scopes",)),
])
async def test_invalid_configuration_rejected(field, value):
    with pytest.raises(ValueError):
        make_session(**{field: value})


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
async def test_loopback_http_is_allowed(host):
    session, _, _, client = make_session(api_base=f"http://{host}:8000/v1")
    await session.close()
    await client.aclose()


async def test_callback_origin_and_fixed_query_are_bound():
    session, _, calls, client = make_session(redirect_uri="https://ui.example/cb?workspace=one")
    async with client:
        url = await session.begin_authorization(owner="admin")
        state = parse_qs(urlsplit(url).query)["state"][0]
        query = urlencode({"state": state, "code": "code"})
        for url in [
            f"https://other.example/cb?workspace=one&{query}",
            f"https://ui.example/cb?workspace=two&{query}",
            f"https://ui.example/other?workspace=one&{query}",
        ]:
            with pytest.raises(OAuth2Error):
                await session.complete_authorization(url, owner="admin")
        assert not calls
        await session.complete_authorization(f"https://ui.example/cb?workspace=one&{query}", owner="admin")


async def test_concurrent_refresh_is_single_flight_and_rotates():
    old = OAuth2Token("old-access", "old-refresh", time.time() - 1, "inference")
    session, store, calls, client = make_session(token=old)
    async with client:
        tokens = await asyncio.gather(*(session.get_access_token() for _ in range(20)))
        assert tokens == ["new-access"] * 20
        assert len(calls) == store.loads == 1
        assert parse_qs(calls[0].content.decode())["refresh_token"] == ["old-refresh"]
        assert store.token.refresh_token == "new-refresh"
        assert store.token.scope == "inference"


async def test_refresh_omission_retains_refresh_but_new_login_does_not():
    def handler(_):
        return httpx.Response(200, json={"access_token": "new-access", "token_type": "bearer", "expires_in": 3600})
    session, store, _, client = make_session(handler, token=OAuth2Token("old", "old-refresh", 0))
    async with client:
        await session.get_access_token()
        assert store.token.refresh_token == "old-refresh"
        await session.complete_authorization(await callback(session), owner="admin")
        assert store.token.refresh_token is None


async def test_invalid_grant_clears_credentials_and_does_not_leak_errors():
    def handler(_):
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "SECRET_REFRESH"})
    session, store, calls, client = make_session(handler, token=OAuth2Token("old", "SECRET_REFRESH", 0))
    async with client:
        with pytest.raises(OAuth2Error, match="sign in again") as error:
            await session.get_access_token()
        assert "SECRET_REFRESH" not in str(error.value)
        assert store.token is None
        with pytest.raises(OAuth2Error, match="sign-in"):
            await session.get_access_token()
        assert len(calls) == 1


async def test_transient_refresh_failure_retains_credentials():
    def handler(_):
        return httpx.Response(503, json={"error": "temporary", "secret": "PRIVATE"})
    old = OAuth2Token("old", "refresh", 0)
    session, store, calls, client = make_session(handler, token=old)
    async with client:
        for _ in range(2):
            with pytest.raises(OAuth2Error, match="request failed"):
                await session.get_access_token()
        assert store.token is old
        assert len(calls) == 2


@pytest.mark.parametrize("payload", [
    [], {"access_token": "ok", "token_type": "MAC"},
    {"access_token": "bad\r\nHeader: value", "token_type": "Bearer"},
    {"access_token": "", "token_type": "Bearer"},
    {"access_token": "ok", "token_type": "Bearer", "expires_in": True},
    {"access_token": "ok", "token_type": "Bearer", "expires_in": -1},
    {"access_token": "ok", "token_type": "Bearer", "expires_in": "NaN"},
    {"access_token": "ok", "token_type": "Bearer", "expires_in": "Infinity"},
    {"access_token": "ok", "token_type": "Bearer", "refresh_token": []},
    {"access_token": "ok", "token_type": "Bearer", "scope": {}},
])
async def test_invalid_token_payloads_are_rejected(payload):
    session, store, calls, client = make_session(lambda _: httpx.Response(200, json=payload))
    async with client:
        cb = await callback(session)
        with pytest.raises(OAuth2Error):
            await session.complete_authorization(cb, owner="admin")
        assert store.token is None
        with pytest.raises(OAuth2Error, match="expired"):
            await session.complete_authorization(cb, owner="admin")
        assert len(calls) == 1


@pytest.mark.parametrize("response", [
    httpx.Response(302, headers={"location": "https://evil.example/token"}),
    httpx.Response(200, content=b"x" * 65537),
    httpx.Response(500, text="PRIVATE_ACCESS_TOKEN"),
])
async def test_redirects_large_bodies_and_raw_errors_are_not_exposed(response):
    session, _, calls, client = make_session(lambda _: response)
    async with client:
        with pytest.raises(OAuth2Error) as error:
            await session.complete_authorization(await callback(session), owner="admin")
        assert "PRIVATE_ACCESS_TOKEN" not in str(error.value)
        assert len(calls) == 1


async def test_transport_error_is_sanitized():
    def handler(_):
        raise httpx.ConnectError("PRIVATE_ACCESS_TOKEN")
    session, _, _, client = make_session(handler)
    async with client:
        with pytest.raises(OAuth2Error) as error:
            await session.complete_authorization(await callback(session), owner="admin")
        assert str(error.value) == "OAuth token request failed."


async def test_unload_disconnect_and_owner_validation():
    session, store, _, client = make_session(token=OAuth2Token("existing"))
    async with client:
        with pytest.raises(OAuth2Error):
            await session.begin_authorization(owner="")
        cb = await callback(session)
        await session.disconnect()
        assert store.token is None
        with pytest.raises(OAuth2Error):
            await session.complete_authorization(cb, owner="admin")
        with pytest.raises(OAuth2Error):
            await session.get_access_token()
        await session.close()
        with pytest.raises(OAuth2Error, match="closed"):
            await session.begin_authorization(owner="admin")
        with pytest.raises(OAuth2Error, match="closed"):
            await session.get_access_token()


async def test_close_retains_store_but_blocks_old_transport():
    session, store, _, client = make_session(token=OAuth2Token("existing"))
    async with client:
        await session.close()
        assert store.token.access_token == "existing"
        with pytest.raises(OAuth2Error, match="closed"):
            await session.authorize_request(httpx.Request("GET", "https://api.example.com/v1/models"))


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize("operation", ["refresh", "login", "disconnect", "invalid_grant"])
async def test_failed_storage_never_reuses_old_credentials(failure, operation):
    async def fail(token):
        raise failure("PRIVATE_REFRESH_TOKEN")

    def invalid_grant(_):
        return httpx.Response(400, json={"error": "invalid_grant"})

    expired = operation in {"refresh", "invalid_grant"}
    old = OAuth2Token("old", "refresh", 0 if expired else None)
    session, store, calls, client = make_session(
        invalid_grant if operation == "invalid_grant" else None,
        token=old, save_token=fail,
    )
    async with client:
        if not expired:
            assert await session.get_access_token() == "old"
        expected = asyncio.CancelledError if failure is asyncio.CancelledError else OAuth2Error
        with pytest.raises(expected) as error:
            if operation == "login":
                await session.complete_authorization(await callback(session), owner="admin")
            elif operation == "disconnect":
                await session.disconnect()
            else:
                await session.get_access_token()
        if expected is OAuth2Error:
            assert "PRIVATE_REFRESH_TOKEN" not in str(error.value)
        # A failed/cancelled write must not reload or reuse an old rotated token.
        with pytest.raises(OAuth2Error, match="sign-in"):
            await session.get_access_token()
        assert len(calls) == (0 if operation == "disconnect" else 1)
        assert store.loads == 1


async def test_load_error_is_sanitized():
    async def fail():
        raise RuntimeError("PRIVATE_REFRESH_TOKEN")

    session, _, _, client = make_session(load_token=fail)
    async with client:
        with pytest.raises(OAuth2Error, match="load") as error:
            await session.get_access_token()
        assert "PRIVATE_REFRESH_TOKEN" not in str(error.value)


@pytest.mark.parametrize("url", [
    "https://evil.example/v1/models", "http://api.example.com/v1/models",
    "https://api.example.com:444/v1/models", "https://api.example.com/v10/models",
    "https://api.example.com/other",
    "https://api.example.com/v1/%2e%2e/admin",
    "https://api.example.com/v1/%5c..%5cadmin",
])
async def test_auth_hook_refuses_other_resources_before_loading_credentials(url):
    session, store, _, client = make_session(token=OAuth2Token("private"))
    async with client:
        request = httpx.Request("GET", url, headers={"Authorization": "Bearer old"})
        with pytest.raises(OAuth2Error, match="outside"):
            await session.authorize_request(request)
        assert "Authorization" not in request.headers
        assert store.loads == 0


async def test_auth_hook_covers_redirects_and_never_replays_401():
    session, _, _, client = make_session(token=OAuth2Token("private"))
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer private"
        return httpx.Response(302, headers={"location": "https://evil.example/collect"})
    async with client, httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True,
        event_hooks={"request": [session.authorize_request]},
    ) as resource_client:
        with pytest.raises(OAuth2Error, match="outside"):
            await resource_client.get("https://api.example.com/v1/models")
        assert len(requests) == 1
    session, _, _, client = make_session(token=OAuth2Token("private"))
    requests.clear()
    def unauthorized(request):
        requests.append(request)
        return httpx.Response(401)
    async with client, httpx.AsyncClient(
        transport=httpx.MockTransport(unauthorized),
        event_hooks={"request": [session.authorize_request]},
    ) as resource_client:
        assert (await resource_client.post("https://api.example.com/v1/chat/completions")).status_code == 401
        assert len(requests) == 1


async def test_cancelled_exchange_cannot_be_replayed():
    started = asyncio.Event()
    release = asyncio.Event()
    async def handler(_):
        started.set()
        await release.wait()
        return httpx.Response(200, json={})
    session, _, calls, client = make_session(handler)
    async with client:
        cb = await callback(session)
        task = asyncio.create_task(session.complete_authorization(cb, owner="admin"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(OAuth2Error, match="expired"):
            await session.complete_authorization(cb, owner="admin")
        assert len(calls) == 1


async def test_logout_serializes_with_refresh():
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(_):
        started.set()
        await release.wait()
        return httpx.Response(200, json={"access_token": "new", "token_type": "Bearer", "expires_in": 3600})
    session, store, _, client = make_session(handler, token=OAuth2Token("old", "refresh", 0))
    async with client:
        refreshing = asyncio.create_task(session.get_access_token())
        await started.wait()
        logout = asyncio.create_task(session.disconnect())
        release.set()
        await asyncio.gather(refreshing, logout)
        assert store.token is None
        with pytest.raises(OAuth2Error, match="sign-in"):
            await session.get_access_token()


async def test_tokens_are_redacted_in_repr_and_isolated_by_session():
    token = OAuth2Token("PRIVATE_ACCESS", "PRIVATE_REFRESH", time.time() + 3600)
    assert "PRIVATE" not in repr(token)
    assert OAuth2Token(**asdict(token)) == token
    a, _, _, ac = make_session(token=token)
    b, _, _, bc = make_session(token=OAuth2Token("other"))
    async with ac, bc:
        assert await a.get_access_token() == "PRIVATE_ACCESS"
        assert await b.get_access_token() == "other"
        await a.disconnect()
        assert await b.get_access_token() == "other"


async def test_expired_token_without_refresh_is_not_used():
    session, _, calls, client = make_session(token=OAuth2Token("expired", expires_at=0))
    async with client:
        with pytest.raises(OAuth2Error, match="expired"):
            await session.get_access_token()
        assert not calls


async def test_real_openai_sdk_discovery_chat_and_stream_use_current_bearer():
    """Exercise the actual SDK transport, not a mocked SDK method."""
    import json
    from openai import AsyncOpenAI

    session, _, token_requests, token_client = make_session(
        token=OAuth2Token("expired", "refresh", 0)
    )
    requests = []

    def resource(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer new-access"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={
                "object": "list", "data": [{"id": "example-model", "object": "model", "created": 0, "owned_by": "example"}],
            })
        payload = json.loads(request.content)
        if payload.get("stream"):
            chunk = {"id": "s1", "object": "chat.completion.chunk", "created": 0, "model": "example-model", "choices": [{"index": 0, "delta": {"content": "hello"}, "finish_reason": None}]}
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
        return httpx.Response(200, json={
            "id": "c1", "object": "chat.completion", "created": 0, "model": "example-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
        })

    async with token_client, AsyncOpenAI(
        api_key="oauth-managed",
        base_url="https://api.example.com/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(resource),
            event_hooks={"request": [session.authorize_request]},
            follow_redirects=False,
        ),
    ) as sdk:
        assert (await sdk.models.list()).data[0].id == "example-model"
        result = await sdk.chat.completions.create(model="example-model", messages=[{"role": "user", "content": "hi"}])
        assert result.choices[0].message.content == "hello"
        stream = await sdk.chat.completions.create(model="example-model", messages=[{"role": "user", "content": "hi"}], stream=True)
        assert [chunk.choices[0].delta.content async for chunk in stream] == ["hello"]
        assert sdk.api_key == "oauth-managed"
        assert len(token_requests) == 1
        assert len(requests) == 3
