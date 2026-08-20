import asyncio
import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner


class _Preferences:
    def __init__(self, conversation_id=""):
        self.conversation_id = conversation_id
        self.get_calls = []
        self.put_calls = []

    async def get_async(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.conversation_id

    async def put_async(self, **kwargs):
        self.put_calls.append(kwargs)
        self.conversation_id = kwargs["value"]


class _Hooks:
    def __init__(self):
        self.began = 0
        self.done = []

    async def on_agent_begin(self, _):
        self.began += 1

    async def on_agent_done(self, _, response):
        self.done.append(response)


class _Client:
    def __init__(self, events):
        self.events = events
        self.calls = []
        self.closed = 0

    async def close(self):
        self.closed += 1

    def chat_messages(self, **kwargs):
        self.calls.append(kwargs)

        async def iterate():
            for event in self.events:
                if isinstance(event, BaseException):
                    raise event
                yield event

        return iterate()

    async def upload_file(self, _):
        return "file-uploaded"


def _runner(*, request, events, auto_save_history=True, conversation_id=""):
    runner = CozeAgentRunner.__new__(CozeAgentRunner)
    runner.req = request
    runner.streaming = True
    runner.final_llm_resp = None
    runner._state = AgentState.IDLE
    runner.agent_hooks = _Hooks()
    runner.run_context = SimpleNamespace()
    runner.preferences = _Preferences(conversation_id)
    runner.bot_id = "bot"
    runner.timeout = 10
    runner.auto_save_history = auto_save_history
    runner.api_client = _Client(events)
    runner.file_id_cache = {}
    return runner


@pytest.mark.asyncio
async def test_coze_builds_history_by_auto_save_setting_and_skips_checkpoints(
    monkeypatch,
):
    request = ProviderRequest(
        prompt="current",
        session_id="session",
        system_prompt="system",
        contexts=[
            {"role": "_checkpoint", "content": "skip"},
            {"role": "user", "content": "text history"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "multimodal history"},
                    {"type": "image_url", "image_url": {"url": "ok-image"}},
                ],
            },
        ],
        image_urls=["ok-current", "bad-current"],
    )
    runner = _runner(request=request, events=[], auto_save_history=False)

    async def upload(url, _session):
        if url == "bad-current":
            raise RuntimeError("upload failed")
        return f"id-{url}"

    monkeypatch.setattr(runner, "_download_and_upload_image", upload)
    messages = await runner._build_additional_messages("session", "")

    assert messages[0] == {
        "role": "system",
        "content": "system",
        "content_type": "text",
    }
    assert messages[1] == {
        "role": "user",
        "content": "text history",
        "content_type": "text",
    }
    assert messages[2]["content"] == [
        {"type": "text", "text": "multimodal history"},
        {"type": "file", "file_id": "id-ok-image", "file_url": "ok-image"},
    ]
    current = json.loads(messages[3]["content"])
    assert current == [
        {"type": "text", "text": "current"},
        {"type": "image", "file_id": "id-ok-current"},
    ]

    runner.auto_save_history = True
    messages = await runner._build_additional_messages(
        "session", "existing-conversation"
    )
    assert messages == [
        {
            "role": "user",
            "content": json.dumps(
                [
                    {"type": "text", "text": "current"},
                    {"type": "image", "file_id": "id-ok-current"},
                ],
                ensure_ascii=False,
            ),
            "content_type": "object_string",
        }
    ]


@pytest.mark.asyncio
async def test_coze_stream_saves_conversation_emits_deltas_and_finishes():
    request = ProviderRequest(
        prompt="hello", session_id="session", system_prompt="system"
    )
    runner = _runner(
        request=request,
        events=[
            {"event": "conversation.chat.created", "data": {"conversation_id": "conv"}},
            {"event": "conversation.message.delta", "data": {"content": "hel"}},
            {
                "event": "conversation.message.delta",
                "data": {"delta": {"content": "lo"}},
            },
            {"event": "conversation.message.completed", "data": {}},
            {"event": "conversation.chat.completed", "data": {}},
        ],
    )

    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == [
        "streaming_delta",
        "streaming_delta",
        "llm_result",
    ]
    assert runner.preferences.put_calls[0]["value"] == "conv"
    assert runner._state is AgentState.DONE
    assert runner.agent_hooks.done == [runner.final_llm_resp]
    assert runner.api_client.closed == 1
    assert runner.api_client.calls[0]["conversation_id"] == ""


@pytest.mark.asyncio
async def test_coze_reuses_conversation_and_closes_client_on_error_and_cancel():
    request = ProviderRequest(prompt="hello", session_id="session")
    runner = _runner(
        request=request,
        events=[{"event": "error", "data": {"code": "BAD", "msg": "nope"}}],
        conversation_id="conv-existing",
    )

    responses = [response async for response in runner.step()]

    assert responses[-1].type == "err"
    assert runner._state is AgentState.ERROR
    assert runner.api_client.calls[0]["conversation_id"] == "conv-existing"
    assert runner.api_client.closed == 1

    cancelling = _runner(request=request, events=[asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        _ = [response async for response in cancelling.step()]
    assert cancelling.api_client.closed == 1
