import asyncio
import base64
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate import stage as result_stage
from astrbot.core.utils import io
from astrbot.core.utils.t2i.network_strategy import NetworkRenderStrategy
from astrbot.core.utils.t2i.renderer import HtmlRenderer

HttpResponseBuilder = Callable[[bytes], tuple[int, dict[str, str], bytes]]


def _png_bytes() -> bytes:
    """Return a valid one-pixel PNG payload for local HTTP test responses."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )


async def _serve_http_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    response_builder: HttpResponseBuilder,
) -> None:
    try:
        request = await reader.readuntil(b"\r\n\r\n")
        headers = request.decode("latin-1").split("\r\n")
        content_length = next(
            (
                int(header.split(":", 1)[1].strip())
                for header in headers
                if header.lower().startswith("content-length:")
            ),
            0,
        )
        request_body = await reader.readexactly(content_length)
        status, response_headers, response_body = response_builder(request_body)
        header_lines = [
            f"HTTP/1.1 {status} {'OK' if status == 200 else 'Found'}",
            f"Content-Length: {len(response_body)}",
            "Connection: close",
            *[f"{key}: {value}" for key, value in response_headers.items()],
            "",
            "",
        ]
        writer.write("\r\n".join(header_lines).encode("latin-1") + response_body)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _start_http_server(response_builder: HttpResponseBuilder) -> asyncio.Server:
    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await _serve_http_request(reader, writer, response_builder)

    return await asyncio.start_server(handler, "127.0.0.1", 0)


def _server_url(server: asyncio.Server) -> str:
    """Return the HTTP origin for a test server."""
    socket = server.sockets[0]
    host, port = socket.getsockname()[:2]
    return f"http://{host}:{port}"


@pytest.mark.parametrize(
    ("use_file_service", "callback_api_base"),
    [
        (False, ""),
        (True, "http://127.0.0.1:1"),
    ],
    ids=["without-file-service", "with-private-file-service"],
)
@pytest.mark.asyncio
async def test_self_hosted_t2i_downloads_a_local_image_for_result_decoration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_file_service: bool,
    callback_api_base: str,
) -> None:
    image_bytes = _png_bytes()
    request_payloads: list[dict[str, Any]] = []

    def response_builder(request_body: bytes) -> tuple[int, dict[str, str], bytes]:
        request_payloads.append(json.loads(request_body))
        return 200, {"Content-Type": "image/png"}, image_bytes

    server = await _start_http_server(response_builder)
    endpoint = f"{_server_url(server)}/text2img"
    monkeypatch.setattr(io, "get_astrbot_temp_path", lambda: str(tmp_path))
    register_file = AsyncMock(return_value="test-token")
    monkeypatch.setattr(result_stage.file_token_service, "register_file", register_file)
    monkeypatch.setattr(
        result_stage,
        "html_renderer",
        HtmlRenderer(endpoint),
    )

    config = {
        "platform_settings": {
            "reply_prefix": "",
            "reply_with_mention": False,
            "reply_with_quote": False,
            "forward_threshold": 1000,
            "segmented_reply": {
                "words_count_threshold": 1000,
                "enable": False,
                "only_llm_result": False,
                "split_mode": "regex",
                "regex": r".*?[。？！~…]+|.+$",
                "split_words": [],
                "content_cleanup_rule": "",
            },
        },
        "t2i_word_threshold": 50,
        "t2i_strategy": "remote",
        "t2i_endpoint": endpoint,
        "t2i_active_template": "base",
        "t2i": False,
        "t2i_use_file_service": use_file_service,
        "callback_api_base": callback_api_base,
        "provider_tts_settings": {"enable": False, "trigger_probability": 1},
        "content_safety": {"also_use_in_response": False},
        "provider_settings": {"display_reasoning_text": False},
    }
    stage = result_stage.ResultDecorateStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config,
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(
                    get_using_tts_provider_async=AsyncMock(return_value=None),
                ),
            ),
        ),
    )
    result = MessageEventResult(
        chain=[Plain("self-hosted renderer output " * 4)],
        result_content_type=ResultContentType.LLM_RESULT,
    ).use_t2i(True)
    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="test:t2i",
        get_result=lambda: result,
        get_platform_name=lambda: "test",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
    )

    try:
        async for _ in stage.process(event):
            pass

        assert len(request_payloads) == 1
        assert request_payloads[0]["json"] is False
        assert isinstance(result.chain[0], Image)
        if use_file_service:
            assert result.chain[0].url == f"{callback_api_base}/api/file/test-token"
            register_file.assert_awaited_once()
        image_path = await result.chain[0].convert_to_file_path()
        try:
            assert Path(image_path).exists()
            assert (
                await result.chain[0].convert_to_base64()
                == base64.b64encode(image_bytes).decode()
            )
        finally:
            Path(image_path).unlink(missing_ok=True)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_self_hosted_t2i_download_rejects_cross_origin_redirect() -> None:
    destination_requests: list[bytes] = []

    def destination_response(request_body: bytes) -> tuple[int, dict[str, str], bytes]:
        destination_requests.append(request_body)
        return 200, {"Content-Type": "image/png"}, _png_bytes()

    destination_server = await _start_http_server(destination_response)
    destination_url = f"{_server_url(destination_server)}/image.png"

    def redirect_response(_request_body: bytes) -> tuple[int, dict[str, str], bytes]:
        return 302, {"Location": destination_url}, b""

    renderer_server = await _start_http_server(redirect_response)
    endpoint = f"{_server_url(renderer_server)}/text2img"

    try:
        with pytest.raises(RuntimeError, match="trusted origin"):
            await NetworkRenderStrategy(endpoint).render("hello", return_url=False)
        assert not destination_requests
    finally:
        renderer_server.close()
        destination_server.close()
        await renderer_server.wait_closed()
        await destination_server.wait_closed()


@pytest.mark.asyncio
async def test_self_hosted_t2i_return_url_contract_is_unchanged() -> None:
    def response_builder(_request_body: bytes) -> tuple[int, dict[str, str], bytes]:
        return (
            200,
            {"Content-Type": "application/json"},
            b'{"data": {"id": "rendered.png"}}',
        )

    server = await _start_http_server(response_builder)
    endpoint = f"{_server_url(server)}/text2img"
    try:
        result = await NetworkRenderStrategy(endpoint).render(
            "hello",
            return_url=True,
        )
        assert result == f"{endpoint}/rendered.png"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_regular_private_image_url_remains_blocked() -> None:
    with pytest.raises(io.SSRFProtectionError, match="non-public address"):
        await Image.fromURL("http://127.0.0.1:1/image.png").convert_to_file_path()
