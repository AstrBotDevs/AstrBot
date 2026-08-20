import ipaddress
import logging
import socket
from pathlib import Path

import pytest

from astrbot.core.utils.outbound_http import (
    CORE_UPDATE,
    GITHUB_MIRROR_TEST,
    JSON_FETCH,
    MCP_REMOTE,
    PLUGIN_DOWNLOAD_URL,
    PLUGIN_REGISTRY,
    PLUGIN_REPOSITORY,
    OutboundRedirectError,
    OutboundRequestError,
    OutboundSizeLimitError,
    compose_github_mirror_url,
    download_to_path,
    redact_outbound_url,
    validate_github_mirror_origin,
    validate_outbound_url,
)


def _public(*ips: str):
    return [ipaddress.ip_address(ip) for ip in ips]


def _resolver(mapping: dict[str, list[str]]):
    def resolve(hostname: str, port: int):
        del port
        if hostname not in mapping:
            raise OutboundRequestError(
                "The destination hostname could not be resolved."
            )
        return _public(*mapping[hostname])

    return resolve


def test_rejects_blocked_schemes() -> None:
    for url in (
        "file:///etc/passwd",
        "gopher://example.com/1",
        "data://text/plain,hello",
        "ftp://example.com/a.zip",
        "ws://example.com/socket",
    ):
        with pytest.raises(OutboundRequestError, match="scheme"):
            validate_outbound_url(url, PLUGIN_DOWNLOAD_URL, resolve_addresses=_public)


def test_rejects_localhost_and_loopback() -> None:
    for url in (
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://[::1]/x",
    ):
        with pytest.raises(OutboundRequestError):
            validate_outbound_url(url, PLUGIN_DOWNLOAD_URL)


def test_rejects_rfc1918_link_local_and_metadata() -> None:
    for url in (
        "https://10.0.0.1/x",
        "https://192.168.1.8/x",
        "https://172.16.0.4/x",
        "https://169.254.1.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/",
    ):
        with pytest.raises(OutboundRequestError):
            validate_outbound_url(url, PLUGIN_DOWNLOAD_URL)


def test_allows_clash_fake_ip_for_resolved_hostnames() -> None:
    fake_ip = _resolver(
        {
            "api.soulter.top": ["198.18.0.57"],
            "api.github.com": ["198.18.0.72"],
        }
    )
    validate_outbound_url(
        "https://api.soulter.top/releases",
        JSON_FETCH,
        resolve_addresses=fake_ip,
    )
    validate_outbound_url(
        "https://api.soulter.top/astrbot/plugins",
        PLUGIN_REGISTRY,
        resolve_addresses=fake_ip,
    )
    validate_outbound_url(
        "https://api.github.com/repos/AstrBotDevs/AstrBot/releases",
        JSON_FETCH,
        resolve_addresses=fake_ip,
    )


def test_still_rejects_literal_fake_ip_urls() -> None:
    with pytest.raises(OutboundRequestError, match="private or reserved"):
        validate_outbound_url("https://198.18.0.57/x", PLUGIN_DOWNLOAD_URL)


def test_rejects_mixed_public_and_private_dns() -> None:
    def resolve(hostname: str, port: int):
        del hostname, port
        return _public("93.184.216.34", "10.0.0.1")

    with pytest.raises(OutboundRequestError, match="private or reserved"):
        validate_outbound_url(
            "https://public.example/plugin.zip",
            PLUGIN_DOWNLOAD_URL,
            resolve_addresses=resolve,
        )


def test_rejects_credentials_in_url() -> None:
    with pytest.raises(OutboundRequestError, match="credentials"):
        validate_outbound_url(
            "https://user:pass@github.com/foo/bar.zip",
            PLUGIN_REPOSITORY,
            resolve_addresses=lambda host, port: _public("140.82.112.3"),
        )


def test_rejects_non_allowed_port() -> None:
    with pytest.raises(OutboundRequestError, match="port"):
        validate_outbound_url(
            "https://github.com:8443/foo/bar.zip",
            PLUGIN_REPOSITORY,
            resolve_addresses=lambda host, port: _public("140.82.112.3"),
        )


def test_redirect_to_private_address_is_rejected() -> None:
    from astrbot.core.utils import outbound_http as module

    public_resolver = _resolver({"cdn.example": ["93.184.216.34"]})
    validate_outbound_url(
        "https://cdn.example/a.zip",
        PLUGIN_DOWNLOAD_URL,
        resolve_addresses=public_resolver,
    )
    with pytest.raises(OutboundRequestError):
        module.validate_outbound_url(
            "https://127.0.0.1/secret",
            PLUGIN_DOWNLOAD_URL,
            resolve_addresses=public_resolver,
        )


@pytest.mark.asyncio
async def test_too_many_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    hops: list[str] = []

    class FakeResponse:
        def __init__(self, location: str) -> None:
            self.status = 302
            self.headers = {"Location": location}

        async def release(self) -> None:
            return None

    class FakeSession:
        async def request(self, method: str, url: str, **kwargs):
            del method, kwargs
            hops.append(url)
            return FakeResponse("https://cdn.example/next.zip")

    def fake_validate(url: str, policy, resolve_addresses=None):
        del policy, resolve_addresses
        from astrbot.core.utils.outbound_http import ValidatedOutboundURL

        return ValidatedOutboundURL(
            url=url,
            scheme="https",
            hostname="cdn.example",
            port=443,
            addresses=(ipaddress.ip_address("93.184.216.34"),),
        )

    monkeypatch.setattr(
        "astrbot.core.utils.outbound_http.validate_outbound_url",
        fake_validate,
    )

    from astrbot.core.utils.outbound_http import (
        OutboundRequestPolicy,
        _request_with_manual_redirects,
    )

    policy = OutboundRequestPolicy(
        allowed_schemes=frozenset({"https"}),
        allowed_hosts=None,
        allowed_ports=frozenset({443}),
        allow_private_network=False,
        max_redirects=1,
        max_url_length=2048,
        max_response_bytes=1024,
        timeout_seconds=5,
    )
    with pytest.raises(OutboundRedirectError, match="Too many"):
        await _request_with_manual_redirects(
            FakeSession(),
            "GET",
            "https://cdn.example/start.zip",
            policy,
            resolve_addresses=None,
            allow_redirects=True,
        )
    assert len(hops) == 2


def test_dns_pinning_uses_validated_addresses_only() -> None:
    seen: list[str] = []

    def resolve(hostname: str, port: int):
        del port
        seen.append(hostname)
        return _public("93.184.216.34")

    validated = validate_outbound_url(
        "https://cdn.example/a.zip",
        PLUGIN_DOWNLOAD_URL,
        resolve_addresses=resolve,
    )
    assert validated.addresses == (ipaddress.ip_address("93.184.216.34"),)
    assert seen == ["cdn.example"]


@pytest.mark.asyncio
async def test_download_over_size_limit_deletes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.utils import outbound_http as outbound

    target = tmp_path / "plugin.zip"

    class FakeStream:
        async def iter_chunked(self, size: int):
            del size
            yield b"a" * 16
            yield b"b" * 16

    class FakeResponse:
        status = 200
        headers = {"Content-Type": "application/zip", "Content-Length": "32"}
        content = FakeStream()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def release(self) -> None:
            return None

    async def fake_request(*args, **kwargs):
        del args, kwargs
        return FakeResponse()

    monkeypatch.setattr(outbound, "_request_with_manual_redirects", fake_request)
    monkeypatch.setattr(
        outbound,
        "validate_outbound_url",
        lambda url, policy, resolve_addresses=None: outbound.ValidatedOutboundURL(
            url=url,
            scheme="https",
            hostname="cdn.example",
            port=443,
            addresses=(ipaddress.ip_address("93.184.216.34"),),
        ),
    )

    class FakeConnector:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def close(self) -> None:
            return None

    class FakeSession:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(outbound.aiohttp, "TCPConnector", FakeConnector)
    monkeypatch.setattr(outbound.aiohttp, "ClientSession", FakeSession)

    policy = outbound.OutboundRequestPolicy(
        allowed_schemes=frozenset({"https"}),
        allowed_hosts=None,
        allowed_ports=frozenset({443}),
        allow_private_network=False,
        max_redirects=0,
        max_url_length=2048,
        max_response_bytes=8,
        timeout_seconds=5,
        allowed_content_types=outbound._ARCHIVE_CONTENT_TYPES,
    )
    with pytest.raises(OutboundSizeLimitError):
        await download_to_path("https://cdn.example/a.zip", target, policy)
    assert not target.exists()


@pytest.mark.asyncio
async def test_download_exception_deletes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.utils import outbound_http as outbound

    target = tmp_path / "plugin.zip"
    target.write_bytes(b"partial")

    async def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr(outbound, "_request_with_manual_redirects", boom)
    monkeypatch.setattr(
        outbound,
        "validate_outbound_url",
        lambda url, policy, resolve_addresses=None: outbound.ValidatedOutboundURL(
            url=url,
            scheme="https",
            hostname="cdn.example",
            port=443,
            addresses=(ipaddress.ip_address("93.184.216.34"),),
        ),
    )

    class FakeConnector:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def close(self) -> None:
            return None

    class FakeSession:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(outbound.aiohttp, "TCPConnector", FakeConnector)
    monkeypatch.setattr(outbound.aiohttp, "ClientSession", FakeSession)

    with pytest.raises(OutboundRequestError):
        await download_to_path("https://cdn.example/a.zip", target, PLUGIN_DOWNLOAD_URL)
    assert not target.exists()


def test_proxy_credentials_are_redacted() -> None:
    redacted = redact_outbound_url("https://user:secret@mirror.example/path?token=abc")
    assert "secret" not in redacted
    assert "token=abc" not in redacted


def test_core_update_rejects_arbitrary_host() -> None:
    with pytest.raises(OutboundRequestError, match="host"):
        validate_outbound_url(
            "https://evil.example/source.zip",
            CORE_UPDATE,
            resolve_addresses=lambda host, port: _public("93.184.216.34"),
        )


def test_core_update_allows_soulter_and_github() -> None:
    validate_outbound_url(
        "https://astrbot-registry.soulter.top/download/astrbot-core/v1/source.zip",
        CORE_UPDATE,
        resolve_addresses=lambda host, port: _public("93.184.216.34"),
    )
    validate_outbound_url(
        "https://codeload.github.com/AstrBotDevs/AstrBot/legacy.zip/master",
        CORE_UPDATE,
        resolve_addresses=lambda host, port: _public("140.82.112.3"),
    )


def test_mirror_origin_rejects_private_and_credentials() -> None:
    with pytest.raises(OutboundRequestError):
        validate_github_mirror_origin("http://mirror.example")
    with pytest.raises(OutboundRequestError):
        validate_github_mirror_origin("https://user:pass@mirror.example")
    with pytest.raises(OutboundRequestError):
        validate_github_mirror_origin(
            "https://127.0.0.1",
        )


def test_compose_github_mirror_url_validates_both_sides() -> None:
    url = compose_github_mirror_url(
        "https://mirror.example",
        "https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/master.zip",
        resolve_addresses=lambda host, port: _public("93.184.216.34"),
    )
    assert url.startswith("https://mirror.example/https://github.com/")


def test_mcp_remote_allows_private_only_with_opt_in() -> None:
    with pytest.raises(OutboundRequestError):
        validate_outbound_url("http://127.0.0.1:8000/mcp", MCP_REMOTE)
    validate_outbound_url(
        "http://127.0.0.1:8000/mcp",
        outbound_policy_with_private(),
    )


def outbound_policy_with_private():
    from dataclasses import replace

    return replace(MCP_REMOTE, allow_private_network=True)


def test_github_mirror_test_uses_same_origin_rules() -> None:
    validate_outbound_url(
        "https://mirror.example",
        GITHUB_MIRROR_TEST,
        resolve_addresses=lambda host, port: _public("93.184.216.34"),
    )
    with pytest.raises(OutboundRequestError):
        validate_outbound_url("https://169.254.169.254", GITHUB_MIRROR_TEST)


def test_getaddrinfo_is_not_globally_patched() -> None:
    original = socket.getaddrinfo
    validate_outbound_url(
        "https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/master.zip",
        PLUGIN_REPOSITORY,
        resolve_addresses=lambda host, port: _public("140.82.112.3"),
    )
    assert socket.getaddrinfo is original


def test_redact_does_not_log_signed_query(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    message = redact_outbound_url(
        "https://cdn.example/file.zip?X-Amz-Signature=supersecret"
    )
    assert "supersecret" not in message


def test_proxy_for_url_uses_configured_http_proxy() -> None:
    from astrbot.core.utils.outbound_http import _proxy_for_url
    from astrbot.core.utils.proxy_route import set_global_network_config

    set_global_network_config(http_proxy="http://127.0.0.1:7890")
    try:
        assert (
            _proxy_for_url("https://raw.githubusercontent.com/AstrBotDevs/x")
            == "http://127.0.0.1:7890"
        )
    finally:
        set_global_network_config(http_proxy="", no_proxy=[])


@pytest.mark.asyncio
async def test_fetch_json_rejects_html_body(monkeypatch: pytest.MonkeyPatch) -> None:
    from astrbot.core.utils import outbound_http as outbound

    async def fake_fetch_text(url, policy, **kwargs):
        del url, policy, kwargs
        return 200, "<!DOCTYPE html><html></html>", {}

    monkeypatch.setattr(outbound, "fetch_text", fake_fetch_text)
    with pytest.raises(OutboundRequestError, match="HTML"):
        await outbound.fetch_json("https://cdn.example/plugins", PLUGIN_REGISTRY)


def test_decode_text_payload_accepts_gzip_and_utf8_bom() -> None:
    import gzip

    from astrbot.core.utils.outbound_http import _decode_text_payload

    assert _decode_text_payload(b'\xef\xbb\xbf{"ok": true}') == '{"ok": true}'
    compressed = gzip.compress(b'{"ok": true}')
    assert _decode_text_payload(compressed) == '{"ok": true}'


def test_decode_text_payload_rejects_gzip_bomb() -> None:
    import gzip

    from astrbot.core.utils.outbound_http import _decode_text_payload

    compressed = gzip.compress(b"a" * 64 * 1024)
    with pytest.raises(OutboundSizeLimitError):
        _decode_text_payload(compressed, max_bytes=1024)


@pytest.mark.asyncio
async def test_fetch_json_does_not_leak_body_in_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.utils import outbound_http as outbound

    async def fake_fetch_text(url, policy, **kwargs):
        del url, policy, kwargs
        return 200, "not-json secret-token-value", {}

    monkeypatch.setattr(outbound, "fetch_text", fake_fetch_text)
    with pytest.raises(OutboundRequestError, match="not valid JSON") as excinfo:
        await outbound.fetch_json("https://cdn.example/plugins", PLUGIN_REGISTRY)
    assert "secret-token-value" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_fetch_text_reads_only_max_plus_one_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.utils import outbound_http as outbound

    class FakeStream:
        def __init__(self) -> None:
            self.n: int | None = None

        async def read(self, n: int = -1) -> bytes:
            self.n = n
            return b"x" * n

    stream = FakeStream()

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}
        content = stream

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def read(self) -> bytes:
            raise AssertionError("unbounded response.read()")

    class FakeConnector:
        async def close(self) -> None:
            return None

    class FakeSession:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_request(*args, **kwargs):
        del args, kwargs
        return FakeResponse()

    monkeypatch.setattr(outbound, "_request_with_manual_redirects", fake_request)
    monkeypatch.setattr(
        outbound,
        "validate_outbound_url",
        lambda url, policy, resolve_addresses=None: outbound.ValidatedOutboundURL(
            url=url,
            scheme="https",
            hostname="cdn.example",
            port=443,
            addresses=(ipaddress.ip_address("93.184.216.34"),),
        ),
    )
    monkeypatch.setattr(outbound, "_proxy_for_url", lambda url: None)
    monkeypatch.setattr(
        outbound,
        "_open_connector",
        lambda *args, **kwargs: (FakeConnector(), None),
    )
    monkeypatch.setattr(outbound.aiohttp, "ClientSession", FakeSession)

    policy = outbound.OutboundRequestPolicy(
        allowed_schemes=frozenset({"https"}),
        allowed_hosts=None,
        allowed_ports=frozenset({443}),
        allow_private_network=False,
        max_redirects=0,
        max_url_length=2048,
        max_response_bytes=8,
        timeout_seconds=5,
    )
    with pytest.raises(OutboundSizeLimitError):
        await outbound.fetch_text("https://cdn.example/plugins", policy)
    assert stream.n == 9
