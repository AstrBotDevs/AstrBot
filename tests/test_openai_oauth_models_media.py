import asyncio
import base64
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from PIL import Image

import astrbot.core.provider.sources.openai_oauth_source as oauth_source
from tests.test_openai_oauth_source import _make_provider


@pytest.mark.asyncio
@pytest.mark.parametrize("positional", [False, True])
async def test_context_already_contains_user_message_does_not_append_metadata_turn(
    positional,
):
    from astrbot.core.agent.message import TextPart

    provider = _make_provider()
    context = [{"role": "user", "content": "actual user message"}]
    extra = [TextPart(text="sender metadata")]
    try:
        if positional:
            payload, _ = await provider._prepare_chat_payload(
                None, None, None, context, extra_user_content_parts=extra
            )
        else:
            payload, _ = await provider._prepare_chat_payload(
                None, contexts=context, extra_user_content_parts=extra
            )
        assert payload["messages"] == context
        assert context == [{"role": "user", "content": "actual user message"}]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_extra_only_turn_and_audio_with_context_remain_present():
    from astrbot.core.agent.message import AudioURLPart, TextPart

    provider = _make_provider({"oauth_audio_transcription": True})
    provider.transcribe_audio = AsyncMock(return_value="spoken text")
    try:
        payload, _ = await provider._prepare_chat_payload(
            None, extra_user_content_parts=[TextPart(text="new text")]
        )
        assert "new text" in str(payload["messages"])
        payload, _ = await provider._prepare_chat_payload(
            None, None, ["voice.wav"], [{"role": "user", "content": "earlier"}]
        )
        assert len(payload["messages"]) == 2
        assert "spoken text" in str(payload["messages"][-1])
        payload, _ = await provider._prepare_chat_payload(
            None,
            contexts=[{"role": "user", "content": "earlier"}],
            extra_user_content_parts=[AudioURLPart(audio_url={"url": "voice.wav"})],
        )
        assert len(payload["messages"]) == 2
        assert "spoken text" in str(payload["messages"][-1])
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("positional_context", [False, True])
@pytest.mark.parametrize("with_metadata", [False, True])
async def test_extra_image_with_history_reaches_real_responses_payload(
    positional_context, with_metadata
):
    from astrbot.core.agent.message import ImageURLPart, TextPart

    image = io.BytesIO()
    with Image.new("RGB", (2, 2), "red") as reference:
        reference.save(image, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
    provider = _make_provider()
    history = [{"role": "user", "content": "earlier conversation"}]
    parts = [ImageURLPart(image_url={"url": data_url})]
    if with_metadata:
        parts.insert(0, TextPart(text="sender metadata"))
    try:
        if positional_context:
            payload, _ = await provider._prepare_chat_payload(
                None, None, None, history, extra_user_content_parts=parts
            )
        else:
            payload, _ = await provider._prepare_chat_payload(
                None, contexts=history, extra_user_content_parts=parts
            )
        assert len(payload["messages"]) == 2
        assert history == [{"role": "user", "content": "earlier conversation"}]
        params = provider._build_responses_params(payload, None)
        assert any(
            part.get("type") == "input_image" and part.get("image_url") == data_url
            for message in params["input"]
            for part in message.get("content", [])
            if isinstance(part, dict)
        )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", ["none", "low", "medium", "high", "xhigh", "max"])
async def test_terra_reasoning_and_sampling_parameters(effort):
    provider = _make_provider(
        {
            "model": "gpt-6.1-terra",
            "custom_extra_body": {
                "top_p": 0.5,
                "top_logprobs": 5,
            },
        }
    )
    try:
        params = provider._build_responses_params(
            {"model": "gpt-6.1-terra", "messages": [], "reasoning_effort": effort}, None
        )
        assert params["reasoning"]["effort"] == effort
        assert "top_p" not in params
        assert "top_logprobs" not in params
        assert "gpt-6.1-terra" in provider.model_capabilities
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_models_discovery_filters_catalog_and_caches_requests(monkeypatch):
    provider = _make_provider()
    requests = []

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "slug": "gpt-6.1-terra",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                        {
                            "slug": "future-model",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                        {
                            "slug": "hidden",
                            "visibility": "hide",
                            "supported_in_api": True,
                        },
                        {
                            "slug": "not-api",
                            "visibility": "list",
                            "supported_in_api": False,
                        },
                        {
                            "slug": "gpt-6.1-terra",
                            "visibility": "list",
                            "supported_in_api": True,
                        },
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        assert await provider.get_models() == ["gpt-6.1-terra", "future-model"]
        assert await provider.get_models() == ["gpt-6.1-terra", "future-model"]
        assert len(requests) == 1
        assert requests[0].url.path.endswith("/models")
        assert (
            requests[0].url.params["client_version"]
            == oauth_source.CODEX_CLIENT_VERSION
        )
        assert requests[0].headers["authorization"] == "Bearer test-token"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["normal", "timeout", "cancel"])
async def test_python310_catalog_without_asyncio_timeout(monkeypatch, outcome):
    provider = _make_provider()
    requests = []
    closed = []
    started = asyncio.Event()
    task = None

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            requests.append(request)
            started.set()
            if outcome != "normal":
                await asyncio.Event().wait()
            return httpx.Response(
                200, json={"models": [{"slug": "dynamic-python310-model"}]}
            )

        try:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handle)
            ) as client:
                yield client
        finally:
            closed.append(True)

    monkeypatch.delattr(asyncio, "timeout", raising=False)
    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        if outcome == "normal":
            assert await provider.get_models() == ["dynamic-python310-model"]
        elif outcome == "timeout":
            monkeypatch.setattr(oauth_source, "MODEL_CATALOG_TIMEOUT_SECONDS", 0.01)
            assert await provider.get_models() == list(provider.model_capabilities)
        else:
            task = asyncio.create_task(provider.get_models())
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not provider._oauth_shared_state.models_cache
        assert len(requests) == 1
        assert closed == [True]
        assert not provider._oauth_shared_state.models_lock.locked()
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["invalid_json", "invalid_shape", "empty", "http_failure", "network"]
)
async def test_models_discovery_failure_falls_back_without_leaking_response(
    monkeypatch, mode
):
    provider = _make_provider()
    warnings = []
    monkeypatch.setattr(
        oauth_source.logger, "warning", lambda *args: warnings.append(args)
    )

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            if mode == "network":
                raise httpx.ConnectError("SECRET-TOKEN request detail", request=request)
            if mode == "invalid_json":
                return httpx.Response(200, text="SECRET-TOKEN")
            if mode == "http_failure":
                return httpx.Response(503, text="SECRET-TOKEN")
            return httpx.Response(
                200, json=[] if mode == "invalid_shape" else {"models": []}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        models = await provider.get_models()
        assert models == list(provider.model_capabilities)
        assert "gpt-6.1-terra" in models
        assert warnings
        assert "SECRET" not in str(warnings)
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["account", "base_url"])
async def test_stale_model_catalog_survives_failure_but_not_account_or_backend_change(
    monkeypatch, changed
):
    provider = _make_provider()
    state = provider._oauth_shared_state
    state.models_cache_key = (provider.base_url, provider.account_id)
    state.models_cache = ["previous-dynamic-model"]
    state.models_expires_at = 0

    @asynccontextmanager
    async def open_client(**kwargs):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        ) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        assert await provider.get_models() == ["previous-dynamic-model"]
        if changed == "account":
            state.apply({"oauth_account_id": "different-account"})
        else:
            provider.base_url = "https://different.example/codex"
        models = await provider.get_models()
        assert "previous-dynamic-model" not in models
        assert "gpt-6.1-terra" in models
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_catalog_auth_retry_uses_rotated_credentials_and_shared_cache(
    monkeypatch,
):
    persist = AsyncMock()
    provider = _make_provider(persist_callback=persist)
    other = _make_provider(shared_state=provider._oauth_shared_state)
    seen_tokens = []

    refresh = AsyncMock(
        return_value={
            "access_token": "rotated-token",
            "refresh_token": "rotated-refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "account_id": "test-account",
        }
    )

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            seen_tokens.append(request.headers["authorization"])
            if len(seen_tokens) == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"models": [{"slug": "discovered-model"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    monkeypatch.setattr(oauth_source, "refresh_access_token", refresh)
    try:
        assert await provider.get_models() == ["discovered-model"]
        assert await other.get_models() == ["discovered-model"]
        assert seen_tokens == ["Bearer test-token", "Bearer rotated-token"]
        refresh.assert_awaited_once_with("test-refresh", "")
        persist.assert_awaited_once()
        assert persist.await_args.args[0]["oauth_refresh_token"] == "rotated-refresh"
    finally:
        await provider.terminate()
        await other.terminate()


@pytest.mark.asyncio
async def test_concurrent_model_requests_share_one_catalog_request(monkeypatch):
    provider = _make_provider()
    other = _make_provider(shared_state=provider._oauth_shared_state)
    requests = []

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            requests.append(request)
            await asyncio.sleep(0)
            return httpx.Response(200, json={"models": [{"slug": "shared-model"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    monkeypatch.setattr(other, "_open_oauth_http_client", open_client)
    try:
        assert await asyncio.gather(provider.get_models(), other.get_models()) == [
            ["shared-model"],
            ["shared-model"],
        ]
        assert len(requests) == 1
    finally:
        await provider.terminate()
        await other.terminate()


@pytest.mark.asyncio
async def test_cancelled_catalog_query_does_not_install_fallback(monkeypatch):
    provider = _make_provider()

    @asynccontextmanager
    async def open_client(**kwargs):
        raise asyncio.CancelledError
        yield

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        with pytest.raises(asyncio.CancelledError):
            await provider.get_models()
        assert not provider._oauth_shared_state.models_cache
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["oversized", "timeout", "account_change"])
async def test_catalog_limits_and_inflight_account_change_discard_results(
    monkeypatch, mode
):
    provider = _make_provider()
    monkeypatch.setattr(oauth_source, "MODEL_CATALOG_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(oauth_source, "MODEL_CATALOG_MAX_BYTES", 100)

    @asynccontextmanager
    async def open_client(**kwargs):
        async def handle(request):
            if mode == "timeout":
                await asyncio.sleep(60)
            if mode == "oversized":
                return httpx.Response(200, content=b" " * 101)
            provider._oauth_shared_state.apply({"oauth_account_id": "new-account"})
            return httpx.Response(200, json={"models": [{"slug": "old-account-model"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(provider, "_open_oauth_http_client", open_client)
    try:
        models = await provider.get_models()
        assert models == list(provider.model_capabilities)
        assert "old-account-model" not in provider._oauth_shared_state.models_cache
        if mode == "account_change":
            assert provider._oauth_shared_state.models_cache_key == (
                provider.base_url,
                "new-account",
            )
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_dashboard_source_catalog_shares_auth_and_does_not_remove_configured_models(
    monkeypatch,
):
    from tests.test_openai_oauth_config_service import _build_service

    service, manager, _ = _build_service()
    captured = []
    original_models = list(service.config["provider"])

    async def models(provider):
        captured.append(provider)
        return ["new-visible-model"]

    monkeypatch.setattr(oauth_source.ProviderOpenAIOAuth, "get_models", models)
    result = await service.list_provider_source_models("openai_oauth")
    assert result["models"] == ["new-visible-model"]
    assert service.config["provider"] == original_models
    assert captured[0]._oauth_shared_state is manager.get_openai_oauth_shared_state(
        "openai_oauth"
    )
    assert callable(captured[0]._oauth_persist_callback)


def test_backend_error_logged_before_raising_without_content(monkeypatch):
    provider = _make_provider()
    warning = Mock()
    monkeypatch.setattr(oauth_source.logger, "warning", warning)
    with pytest.raises(Exception):
        provider._parse_backend_response(
            "data: "
            + json.dumps(
                {
                    "type": "error",
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "SECRET-PROMPT",
                    },
                }
            )
        )
    warning.assert_called_once()
    assert "rate limit exceeded" in str(warning.call_args)
    assert "SECRET-PROMPT" not in str(warning.call_args)


def animated_gif():
    frames = [Image.new("RGB", (2, 2), color) for color in ("red", "blue")]
    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    return output.getvalue()


@pytest.mark.asyncio
async def test_gif_input_and_output_preserve_frames_bytes_and_mime(tmp_path):
    provider = _make_provider({"generated_image_dir": str(tmp_path)})
    original = animated_gif()
    source = tmp_path / "input.wrong-suffix"
    source.write_bytes(original)
    try:
        reference = provider._reference_image_to_image_url(str(source))
        assert reference.startswith("data:image/gif;base64,")
        assert base64.b64decode(reference.split(",", 1)[1]) == original
        results = await provider._extract_generated_images(
            {
                "output": [
                    {
                        "type": "image_generation_call",
                        "result": base64.b64encode(original).decode(),
                        "output_format": "gif",
                    }
                ]
            }
        )
        assert results[0].mime_type == "image/gif"
        assert Path(results[0].path).suffix == ".gif"
        assert Path(results[0].path).read_bytes() == original
        with Image.open(results[0].path) as image:
            assert image.n_frames == 2
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_chat_provider_gif_reference_keeps_animation_bytes(tmp_path):
    provider = _make_provider()
    source = tmp_path / "animation.gif"
    original = animated_gif()
    source.write_bytes(original)
    try:
        payload, _ = await provider._prepare_chat_payload(
            "describe", image_urls=[str(source)]
        )
        params = provider._build_responses_params(payload, None)
        part = next(
            part
            for part in params["input"][0]["content"]
            if part["type"] == "input_image"
        )
        assert part["image_url"].startswith("data:image/gif;base64,")
        assert base64.b64decode(part["image_url"].split(",", 1)[1]) == original
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_model",
    [
        None,
        "gpt-image-2.6-sunburst",
        "gpt-image-2.6-flare",
        "gpt-image-2.5-sunburst",
        "gpt-image-2.5-flare",
        "gpt-image-2",
    ],
)
async def test_image_model_selection_and_gif_parameters_reach_tool(
    tmp_path, image_model
):
    provider = _make_provider({"generated_image_dir": str(tmp_path)})
    provider._request_image_backend = AsyncMock(
        return_value={
            "output": [
                {
                    "type": "image_generation_call",
                    "result": base64.b64encode(animated_gif()).decode(),
                    "output_format": "gif",
                }
            ]
        }
    )
    try:
        results = await provider.generate_image(
            "animate a bouncing dot",
            image_model=image_model,
            output_format="gif",
            frame_count=2,
            frame_duration_ms=100,
        )
        tool = provider._request_image_backend.await_args.args[0]["tools"][0]
        assert tool["model"] == (image_model or "gpt-image-2.6-sunburst")
        assert tool["output_format"] == "gif"
        assert tool["frame_count"] == 2
        assert tool["frame_duration_ms"] == 100
        assert results[0].mime_type == "image/gif"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"output_format": "bad"},
        {"frame_count": 1},
        {"frame_count": True},
        {"output_format": "gif", "frame_count": 17},
        {"output_format": "gif", "frame_duration_ms": 19},
        {"output_format": "gif", "frame_duration_ms": 2001},
        {"output_format": "gif", "frame_duration_ms": True},
    ],
)
async def test_invalid_image_output_controls_fail_before_request(kwargs):
    provider = _make_provider()
    provider._request_image_backend = AsyncMock()
    try:
        with pytest.raises(ValueError):
            await provider.generate_image("draw", **kwargs)
        provider._request_image_backend.assert_not_awaited()
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_requested_gif_does_not_silently_succeed_as_png(tmp_path):
    provider = _make_provider({"generated_image_dir": str(tmp_path)})
    provider._request_image_backend = AsyncMock(
        return_value={
            "output": [
                {
                    "type": "image_generation_call",
                    "result": base64.b64encode(
                        b"\x89PNG\r\n\x1a\nPNG-legacy-test"
                    ).decode(),
                }
            ]
        }
    )
    try:
        with pytest.raises(RuntimeError, match="did not return.*GIF"):
            await provider.generate_image("animate", output_format="gif")
        assert not list(tmp_path.iterdir())
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_unknown_image_data_is_rejected_before_writing_any_results(tmp_path):
    provider = _make_provider({"generated_image_dir": str(tmp_path)})
    try:
        with pytest.raises(ValueError, match="unsupported image format"):
            await provider._extract_generated_images(
                {
                    "output": [
                        {
                            "type": "image_generation_call",
                            "result": base64.b64encode(animated_gif()).decode(),
                        },
                        {
                            "type": "image_generation_call",
                            "result": base64.b64encode(b"SECRET-NOT-AN-IMAGE").decode(),
                        },
                    ]
                }
            )
        assert not list(tmp_path.iterdir())
    finally:
        await provider.terminate()
