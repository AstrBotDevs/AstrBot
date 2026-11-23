"""Dify runner configuration and observable terminal states."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.dify import dify_agent_runner as dify
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
async def test_reset_maps_workflow_configuration_to_client(monkeypatch):
    transport = SimpleNamespace(close=AsyncMock())
    factory = MagicMock(return_value=transport)
    monkeypatch.setattr(dify, "DifyAPIClient", factory)
    runner = dify.DifyAgentRunner()
    request = ProviderRequest(prompt="hello")
    config = {
        "dify_api_key": "key",
        "dify_api_base": "https://example.invalid/v1",
        "dify_api_type": "workflow",
        "dify_workflow_output_key": "answer",
        "dify_query_input_key": "question",
        "timeout": "7",
        "variables": {"mode": "test"},
    }
    await runner.reset(
        request,
        ContextWrapper(context=None),
        BaseAgentRunHooks(),
        config,
        streaming=True,
    )
    factory.assert_called_once_with("key", "https://example.invalid/v1")
    assert runner.api_client is transport and runner.req is request
    assert runner.timeout == 7 and runner.streaming
    assert runner.api_type == "workflow" and runner.workflow_output_key == "answer"
    assert runner.dify_query_input_key == "question" and runner.variables == {
        "mode": "test"
    }
    assert runner.state == AgentState.IDLE and not runner.done()
    assert runner.get_final_llm_resp() is None


@pytest.mark.asyncio
async def test_failure_becomes_terminal_error_and_closes_client(monkeypatch):
    client = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(dify, "DifyAPIClient", lambda *_: client)
    runner = dify.DifyAgentRunner()
    hooks = AsyncMock(spec=BaseAgentRunHooks)
    await runner.reset(
        ProviderRequest(prompt="hello"), ContextWrapper(context=None), hooks, {}
    )

    async def failing_request():
        raise OSError("controlled failure")
        yield None

    monkeypatch.setattr(runner, "_execute_dify_request", failing_request)
    responses = [response async for response in runner.step()]
    assert len(responses) == 1 and responses[0].type == "err"
    assert runner.state == AgentState.ERROR and runner.done()
    assert runner.get_final_llm_resp().role == "err"
    assert "controlled failure" in runner.get_final_llm_resp().completion_text
    hooks.on_agent_begin.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("api_type", ["chat", "workflow"])
@pytest.mark.parametrize(
    ("upload_response", "expected_id"),
    [
        pytest.param({}, None, id="missing"),
        pytest.param({"id": None}, None, id="null"),
        pytest.param({"id": 42}, None, id="number"),
        pytest.param({"id": ["file-id"]}, None, id="list"),
        pytest.param({"id": {"value": "file-id"}}, None, id="object"),
        pytest.param({"id": "file-first"}, "file-first", id="string"),
        pytest.param({"id": ""}, "", id="empty-string"),
        pytest.param({"id": "  opaque-id  "}, "  opaque-id  ", id="opaque-string"),
    ],
)
async def test_upload_ids_filter_files_without_stopping_request(
    monkeypatch: pytest.MonkeyPatch,
    api_type: str,
    upload_response: dict[str, object],
    expected_id: str | None,
) -> None:
    """Only string upload IDs reach Dify; later images and the turn still finish."""

    async def response_stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        if api_type == "chat":
            yield {
                "event": "message",
                "answer": "done",
                "conversation_id": "conversation-id",
            }
            yield {"event": "message_end"}
        else:
            yield {
                "event": "workflow_finished",
                "workflow_run_id": "workflow-id",
                "data": {"status": "succeeded", "outputs": {"answer": "done"}},
            }

    client = SimpleNamespace(
        file_upload=AsyncMock(side_effect=[upload_response, {"id": "file-next"}]),
        chat_messages=MagicMock(side_effect=response_stream),
        workflow_run=MagicMock(side_effect=response_stream),
        close=AsyncMock(),
    )
    monkeypatch.setattr(dify, "DifyAPIClient", lambda *_: client)
    image_data = SimpleNamespace(
        mime_type="image/jpeg", to_bytes=lambda: b"jpeg-image-bytes"
    )
    resolver = SimpleNamespace(to_base64_data=AsyncMock(return_value=image_data))
    monkeypatch.setattr(dify, "MediaResolver", MagicMock(return_value=resolver))
    monkeypatch.setattr(
        dify,
        "sp",
        SimpleNamespace(
            get_async=AsyncMock(side_effect=lambda **kwargs: kwargs["default"]),
            put_async=AsyncMock(),
        ),
    )
    runner = dify.DifyAgentRunner()
    await runner.reset(
        ProviderRequest(
            prompt="describe",
            session_id="session-id",
            system_prompt="system prompt",
            image_urls=["first-image.jpg", "next-image.jpg"],
        ),
        ContextWrapper(context=None),
        BaseAgentRunHooks(),
        {
            "dify_api_type": api_type,
            "dify_workflow_output_key": "answer",
            "dify_query_input_key": "question",
            "timeout": 7,
        },
    )

    responses = [response async for response in runner.step()]

    expected_files = [
        {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": "file-next",
        }
    ]
    if expected_id is not None:
        expected_files.insert(
            0,
            {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": expected_id,
            },
        )
    selected_request = (
        client.chat_messages if api_type == "chat" else client.workflow_run
    )
    selected_request.assert_called_once()
    request_kwargs = selected_request.call_args.kwargs
    assert request_kwargs["files"] == expected_files
    assert request_kwargs["user"] == "session-id"
    assert request_kwargs["request_timeout"] == 7
    assert request_kwargs["inputs"]["system_prompt"] == "system prompt"
    if api_type == "chat":
        assert request_kwargs["query"] == "describe"
        assert request_kwargs["conversation_id"] == ""
        client.workflow_run.assert_not_called()
    else:
        assert request_kwargs["inputs"]["question"] == "describe"
        client.chat_messages.assert_not_called()
    assert client.file_upload.await_count == 2
    client.file_upload.assert_has_awaits(
        [
            call(
                file_data=b"jpeg-image-bytes",
                user="session-id",
                mime_type="image/jpeg",
                file_name="image.jpg",
            )
        ]
        * 2
    )
    assert resolver.to_base64_data.await_count == 2
    resolver.to_base64_data.assert_has_awaits([call(strict=True)] * 2)
    assert len(responses) == 1 and responses[0].type == "llm_result"
    assert runner.state == AgentState.DONE
    final_response = runner.get_final_llm_resp()
    assert final_response is not None and final_response.result_chain is not None
    assert final_response.result_chain.get_plain_text() == "done"
    client.close.assert_awaited_once()
