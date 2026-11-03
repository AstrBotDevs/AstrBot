import asyncio
import json
import traceback
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

import astrbot.core.provider.sources.openai_oauth_source as source
from astrbot.core.provider.sources.openai_oauth_source import ProviderOpenAIOAuth
from astrbot.core.provider.sources.request_retry import ProviderRequestError


@pytest_asyncio.fixture
async def provider(monkeypatch):
    writer = AsyncMock()
    monkeypatch.setattr(
        source, "db_helper", SimpleNamespace(insert_provider_stat=writer)
    )
    instance = ProviderOpenAIOAuth(
        {
            "id": "robustness-test",
            "type": "openai_oauth_chat_completion",
            "model": "gpt-6.1-sol",
            "oauth_access_token": "synthetic-token",
            "oauth_refresh_token": "synthetic-refresh",
            "oauth_account_id": "synthetic-account",
        },
        {},
    )
    instance._record_provider_stat = AsyncMock()
    try:
        yield instance
    finally:
        await instance.terminate()


def completion(text="ok", **extra):
    return {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ],
        **extra,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_public_chat_accepts_conversation_id_without_backend_state(
    provider, streaming
):
    captured = []

    async def request(payload):
        captured.append(payload)
        return completion()

    async def events(payload):
        captured.append(payload)
        yield {"type": "response.completed", "response": completion()}

    provider._request_backend = request
    provider._stream_backend_events = events
    if streaming:
        responses = [
            item
            async for item in provider.text_chat_stream(
                prompt="synthetic", conversation_id="synthetic-conversation"
            )
        ]
        assert responses[-1].completion_text == "ok"
    else:
        assert (
            await provider.text_chat(
                prompt="synthetic", conversation_id="synthetic-conversation"
            )
        ).completion_text == "ok"
    assert len(captured) == 1
    assert captured[0]["store"] is False
    assert "conversation_id" not in captured[0]


@pytest.mark.asyncio
async def test_query_stream_accepts_conversation_keyword(provider):
    async def events(payload):
        yield {"type": "response.completed", "response": completion()}

    provider._stream_backend_events = events
    responses = [
        item
        async for item in provider._query_stream(
            {"messages": []}, None, conversation_id="synthetic"
        )
    ]
    assert responses[-1].completion_text == "ok"


@pytest.mark.parametrize(
    "response_format, expected",
    [
        ({"type": "json_object"}, {"type": "json_object"}),
        ({"type": "text"}, {"type": "text"}),
        (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "strict": True,
                    "schema": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "json_schema",
                "name": "result",
                "strict": True,
                "schema": {"type": "object", "properties": {}},
            },
        ),
    ],
)
def test_response_format_preserves_text_options_and_request_wins(
    provider, response_format, expected
):
    configured = {"verbosity": "low", "format": {"type": "text"}}
    provider.provider_config["custom_extra_body"] = {"text": configured}
    params = provider._build_responses_params(
        {"messages": [], "response_format": response_format}, None
    )
    assert params["text"] == {"verbosity": "low", "format": expected}
    assert configured == {"verbosity": "low", "format": {"type": "text"}}


@pytest.mark.asyncio
async def test_public_chat_forwards_response_format(provider):
    provider._request_backend = AsyncMock(return_value=completion("{}"))
    response = await provider.text_chat(
        prompt="synthetic", response_format={"type": "json_object"}
    )
    assert response.completion_text == "{}"
    assert provider._request_backend.await_args.args[0]["text"]["format"] == {
        "type": "json_object"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [[], None])
async def test_completed_empty_response_is_valid(provider, output):
    response = await provider._parse_responses_completion(
        {"status": "completed", "output": output}, None
    )
    assert response.completion_text == ""
    assert response.role == "assistant"
    assert response.tools_call_args == []


@pytest.mark.asyncio
async def test_refusal_is_returned_as_text(provider):
    response = await provider._parse_responses_completion(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "Cannot help."}],
                }
            ],
        },
        None,
    )
    assert response.completion_text == "Cannot help."


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["wrong", {}, ["wrong"]])
async def test_completed_malformed_output_is_not_empty_success(provider, output):
    with pytest.raises(ValueError):
        await provider._parse_responses_completion(
            {"status": "completed", "output": output}, None
        )


@pytest.mark.parametrize("mode", ["json", "sse"])
@pytest.mark.parametrize("status", ["failed", "incomplete"])
def test_failed_image_or_text_backend_response_keeps_usage(provider, mode, status):
    response = completion(
        "partial", status=status, usage={"input_tokens": 6, "output_tokens": 2}
    )
    body = json.dumps(response)
    if mode == "sse":
        body = "data: " + json.dumps(
            {"type": "response.completed", "response": response}
        )
    with pytest.raises(Exception) as caught:
        provider._parse_backend_response(body)
    assert caught.value._astrbot_token_usage.total == 8


@pytest.mark.asyncio
async def test_completed_response_with_error_is_not_success(provider):
    with pytest.raises(Exception):
        await provider._parse_responses_completion(
            completion(error={"message": "synthetic failure"}), None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled", "in_progress"])
async def test_unsuccessful_response_does_not_return_partial_text(provider, status):
    with pytest.raises(Exception) as caught:
        await provider._parse_responses_completion(
            completion("partial", status=status, instructions="SECRET_PROMPT"), None
        )
    assert "SECRET_PROMPT" not in str(caught.value)


@pytest.mark.asyncio
async def test_legacy_response_without_status_still_parses(provider):
    response = completion()
    response.pop("status")
    assert (
        await provider._parse_responses_completion(response, None)
    ).completion_text == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ['{"broken":', "[]", "null", "1", ["wrong"]])
async def test_invalid_tool_arguments_never_become_executable_empty_args(
    provider, arguments
):
    response = {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": "synthetic_tool",
                "call_id": "synthetic-call",
                "arguments": arguments,
            }
        ],
    }
    with pytest.raises(ValueError, match="tool arguments"):
        await provider._parse_responses_completion(response, None)


@pytest.mark.asyncio
async def test_valid_tools_keep_existing_public_representation(provider):
    response = await provider._parse_responses_completion(
        {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "synthetic_tool",
                    "call_id": "synthetic-call",
                    "arguments": '{"value": 4}',
                }
            ],
        },
        None,
    )
    assert response.role == "tool"
    assert response.tools_call_name == ["synthetic_tool"]
    assert response.tools_call_ids == ["synthetic-call"]
    assert response.tools_call_args == [{"value": 4}]


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["{}", {}])
async def test_valid_no_argument_tool_is_preserved(provider, arguments):
    response = await provider._parse_responses_completion(
        {
            "status": "completed",
            "output": [
                {"type": "function_call", "name": "noop", "arguments": arguments}
            ],
        },
        None,
    )
    assert response.tools_call_args == [{}]


@pytest.mark.parametrize(
    "code,expected",
    [
        ("invalid_attachment", "invalid_attachment"),
        ("tool_not_supported", "tools not supported"),
    ],
)
def test_known_errors_keep_safe_fallback_classification(provider, code, expected):
    message = provider._format_backend_error(
        400, json.dumps({"error": {"code": code, "message": "SECRET"}})
    )
    assert expected in message
    assert "SECRET" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_tool_parse_failure_preserves_usage_and_is_recorded(provider, streaming):
    response = {
        "status": "completed",
        "usage": {"input_tokens": 8, "output_tokens": 3},
        "output": [
            {
                "type": "function_call",
                "name": "synthetic_tool",
                "call_id": "synthetic-call",
                "arguments": '{"SECRET_ARGUMENT":',
            }
        ],
    }
    provider._request_backend = AsyncMock(return_value=response)

    async def events(payload):
        yield {"type": "response.completed", "response": response}

    provider._stream_backend_events = events
    with pytest.raises(ValueError) as caught:
        if streaming:
            _ = [item async for item in provider.text_chat_stream(prompt="synthetic")]
        else:
            await provider.text_chat(prompt="synthetic")
    assert "SECRET_ARGUMENT" not in str(caught.value)
    assert caught.value._astrbot_token_usage.total == 11
    assert provider._record_provider_stat.await_args.kwargs["usage"].total == 11
    assert provider._record_provider_stat.await_args.kwargs["status"] == "error"


@pytest.mark.parametrize("route", ["http", "sse", "stream", "completion", "image"])
def test_backend_error_paths_do_not_echo_arbitrary_fields(provider, route):
    marker = "SECRET_PROMPT_OR_TOKEN"
    response = {
        "id": marker,
        "status": "failed",
        "instructions": marker,
        "error": {"message": marker, "code": marker, "type": marker},
        "output": [],
    }
    event = {"type": "response.failed", "response": response}
    if route == "http":
        assert marker not in provider._format_backend_error(400, json.dumps(response))
    elif route == "sse":
        with pytest.raises(Exception) as caught:
            provider._parse_backend_response("data: " + json.dumps(event))
        assert marker not in str(caught.value)
    elif route == "stream":
        with pytest.raises(Exception) as caught:
            provider._apply_stream_event(event, [], [], {})
        assert marker not in str(caught.value)
    elif route == "completion":
        with pytest.raises(Exception) as caught:
            asyncio.run(provider._parse_responses_completion(response, None))
        assert marker not in str(caught.value)
    else:
        with pytest.raises(Exception) as caught:
            asyncio.run(provider._extract_generated_images(response))
        assert marker not in str(caught.value)


def test_context_limit_error_keeps_safe_recovery_classification(provider):
    message = provider._format_backend_error(
        400,
        json.dumps(
            {"error": {"code": "context_length_exceeded", "message": "SECRET_PROMPT"}}
        ),
    )
    assert "context length" in message.lower()
    assert "SECRET_PROMPT" not in message


@pytest.mark.parametrize(
    "text, expected",
    [
        ("maximum context length exceeded SECRET", "context length"),
        ("invalid_attachment SECRET", "invalid_attachment"),
        ("Function calling is not enabled SECRET", "tools not supported"),
        ("The model is not a VLM SECRET", "The model is not a VLM"),
    ],
)
def test_plain_text_errors_preserve_known_recovery_without_echo(
    provider, text, expected
):
    message = provider._format_backend_error(400, text)
    assert expected in message
    assert "SECRET" not in message


def test_configured_moderation_recovery_uses_safe_marker(provider):
    provider.provider_config["image_moderation_error_patterns"] = [
        "private moderation code"
    ]
    message = provider._format_backend_error(
        400, json.dumps({"error": {"message": "private moderation code SECRET"}})
    )
    assert "SECRET" not in message and "private moderation code" not in message
    assert provider._is_content_moderated_upload_error(RuntimeError(message))
    unrelated = provider._format_backend_error(
        400, json.dumps({"error": {"message": "other error"}})
    )
    assert not provider._is_content_moderated_upload_error(RuntimeError(unrelated))


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": "SECRET_USAGE", "output_tokens": 2},
        {"input_tokens": 4, "output_tokens": 2, "input_tokens_details": "SECRET_USAGE"},
    ],
)
def test_error_usage_malformed_values_do_not_echo_or_mask_status(provider, usage):
    event = {
        "type": "response.failed",
        "response": {"error": {"code": "rate_limit_exceeded"}, "usage": usage},
    }
    with pytest.raises(ProviderRequestError) as caught:
        provider._parse_backend_response("data: " + json.dumps(event))
    assert caught.value.status_code == 429
    assert "SECRET_USAGE" not in str(caught.value)
    assert getattr(caught.value, "_astrbot_token_usage", None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_parse_failure_with_malformed_usage_remains_safe(provider, streaming):
    response = completion(
        status="failed",
        error={"code": "rate_limit_exceeded"},
        usage={"input_tokens": "SECRET_USAGE", "output_tokens": 2},
    )
    provider._request_backend = AsyncMock(return_value=response)

    async def events(payload):
        yield {"type": "response.completed", "response": response}

    provider._stream_backend_events = events
    with pytest.raises(ProviderRequestError) as caught:
        if streaming:
            _ = [item async for item in provider._query_stream({"messages": []}, None)]
        else:
            await provider._query({"messages": []}, None, retry_rate_limits=False)
    assert caught.value.status_code == 429
    assert "SECRET_USAGE" not in str(caught.value)
    assert getattr(caught.value, "_astrbot_token_usage", None) is None


def test_rate_limit_error_keeps_status_without_raw_error(provider):
    with pytest.raises(ProviderRequestError) as caught:
        provider._parse_backend_response(
            "data: "
            + json.dumps(
                {
                    "type": "response.failed",
                    "response": {
                        "error": {"code": "rate_limit_exceeded", "message": "SECRET"},
                        "usage": {"input_tokens": 7, "output_tokens": 1},
                    },
                }
            )
        )
    assert caught.value.status_code == 429
    assert "SECRET" not in str(caught.value)
    assert caught.value._astrbot_token_usage.total == 8


def test_non_stream_malformed_lines_are_reported_once_without_raw_data(
    provider, monkeypatch
):
    warning = Mock()
    monkeypatch.setattr(source.logger, "warning", warning)
    text = "\n".join(
        [
            'data: {"SECRET":',
            "data: not-json-SECRET",
            "data: "
            + json.dumps({"type": "response.completed", "response": completion()}),
        ]
    )
    assert provider._parse_backend_response(text)["status"] == "completed"
    warning.assert_called_once()
    assert "2" in str(warning.call_args)
    assert "SECRET" not in str(warning.call_args)


@pytest.mark.asyncio
async def test_real_stream_parser_stays_fail_closed_and_reports_safe_warning(
    provider, monkeypatch
):
    warning = Mock()
    monkeypatch.setattr(source.logger, "warning", warning)
    provider._ensure_fresh_oauth_token = AsyncMock()

    class Response:
        status_code = 200

        async def aiter_lines(self):
            for line in ['data: {"SECRET":', "", "data: [DONE]", ""]:
                yield line

    @asynccontextmanager
    async def stream(*args, **kwargs):
        yield Response()

    @asynccontextmanager
    async def client():
        yield SimpleNamespace(stream=stream)

    provider._open_oauth_stream_client = client
    with pytest.raises(ValueError) as caught:
        _ = [event async for event in provider._stream_backend_events({})]
    assert "SECRET" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert "SECRET" not in "".join(traceback.format_exception(caught.value))
    warning.assert_called_once()
    assert "SECRET" not in str(warning.call_args)
