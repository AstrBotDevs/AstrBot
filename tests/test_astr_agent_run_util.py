import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.response import AgentResponse
from astrbot.core.astr_agent_runtime.runner import (
    _should_buffer_llm_result,
    _simulated_stream_tts,
    run_agent,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.speech_output import stream_speech


class _FakeEvent:
    """Minimal event surface used by the agent stream bridge."""

    def __init__(self) -> None:
        self.extras: dict[str, object] = {}

    def is_stopped(self) -> bool:
        return False

    def get_extra(self, key: str):
        return self.extras.get(key)

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    def get_platform_name(self) -> str:
        return "test"


class _StreamingErrorRunner:
    """Agent runner that finishes with one provider error response."""

    streaming = True
    req = None

    def __init__(self, error_text: str) -> None:
        self.error_text = error_text
        self.finished = False
        self.run_context = SimpleNamespace(context=SimpleNamespace(event=_FakeEvent()))

    async def step(self):
        self.finished = True
        yield AgentResponse(
            type="err",
            data={"chain": MessageChain().message(self.error_text)},
        )

    def done(self) -> bool:
        return self.finished


class _MalformedStreamingErrorRunner(_StreamingErrorRunner):
    """Agent runner that returns an invalid provider error payload."""

    async def step(self):
        self.finished = True
        yield AgentResponse(type="err", data={})


@pytest.mark.asyncio
async def test_run_agent_forwards_streaming_provider_error():
    error_text = (
        "LLM 响应错误: Not found the model k2.7-code-highspeed or Permission denied"
    )
    runner = _StreamingErrorRunner(error_text)

    chains = [chain async for chain in run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == error_text


@pytest.mark.asyncio
async def test_run_agent_replaces_malformed_streaming_provider_error():
    runner = _MalformedStreamingErrorRunner("unused")

    chains = [chain async for chain in run_agent(runner)]

    assert len(chains) == 1
    assert chains[0].get_plain_text() == "Error occurred during AI execution."


@pytest.mark.asyncio
async def test_simulated_stream_tts_leaves_audio_for_deferred_cleanup(tmp_path):
    audio_path = tmp_path / "speech.wav"
    audio_path.write_bytes(b"audio")

    class _TTSProvider:
        async def get_audio(self, text: str) -> str:
            assert text == "hello"
            return str(audio_path)

    text_queue: asyncio.Queue[str | None] = asyncio.Queue()
    audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None] = asyncio.Queue()
    await text_queue.put("hello")
    await text_queue.put(None)

    await _simulated_stream_tts(_TTSProvider(), text_queue, audio_queue)

    assert await audio_queue.get() == ("hello", b"audio")
    assert await audio_queue.get() is None
    assert audio_path.exists()


@pytest.mark.asyncio
async def test_speech_output_preserves_sentences_and_native_model_metadata():
    from unittest.mock import AsyncMock

    spoken = []

    async def audio_stream(text_queue, audio_queue):
        while (text := await text_queue.get()) is not None:
            spoken.append(text)
            await audio_queue.put(b"audio")

    provider = SimpleNamespace(
        support_stream=lambda: True,
        get_audio_stream=audio_stream,
        meta=lambda: SimpleNamespace(type="test-tts"),
    )
    event = SimpleNamespace(
        get_platform_name=lambda: "webchat",
        get_extra=lambda key, default=None: "test-chat-model",
        send=AsyncMock(),
    )

    async def chains():
        yield MessageChain().message("Hello, ")
        yield MessageChain().message("world! Remaining")

    chunks = [chain async for chain in stream_speech(chains(), provider, event=event)]
    assert spoken == ["Hello, world!", " Remaining"]
    assert len(chunks) == 2
    assert all(chain.type == "audio_chunk" for chain in chunks)
    stats = event.send.await_args.args[0].chain[0].data
    assert stats["chat_model"] == "test-chat-model"


@pytest.mark.asyncio
async def test_closing_speech_output_joins_both_input_and_audio_workers():
    input_closed, audio_closed = asyncio.Event(), asyncio.Event()

    async def chains():
        try:
            yield MessageChain().message("A complete sentence.")
            await asyncio.Event().wait()
        finally:
            input_closed.set()

    async def audio_stream(text_queue, audio_queue):
        try:
            await text_queue.get()
            await audio_queue.put(b"audio")
            await asyncio.Event().wait()
        finally:
            audio_closed.set()

    provider = SimpleNamespace(
        support_stream=lambda: True,
        get_audio_stream=audio_stream,
    )
    output = stream_speech(chains(), provider, event=_FakeEvent())
    assert (await asyncio.wait_for(anext(output), 1)).type == "audio_chunk"
    await output.aclose()
    assert input_closed.is_set()
    assert audio_closed.is_set()


class _StopMidStreamRunner:
    """Agent runner that requests a stop right after its first streamed delta."""

    streaming = True
    req = None

    def __init__(self) -> None:
        self.event = _FakeEvent()
        self.run_context = SimpleNamespace(context=SimpleNamespace(event=self.event))
        self.finished = False

    async def step(self):
        yield AgentResponse(
            type="streaming_delta",
            data={"chain": MessageChain().message("A")},
        )
        self.event.set_extra("agent_stop_requested", True)
        yield AgentResponse(
            type="streaming_delta",
            data={"chain": MessageChain().message("B")},
        )
        self.finished = True
        yield AgentResponse(type="aborted", data={"chain": MessageChain()})

    def request_stop(self) -> None:
        pass

    def done(self) -> bool:
        return self.finished


@pytest.mark.asyncio
async def test_run_agent_forwards_streaming_delta_emitted_before_stop():
    """Text streamed before the stop request stays visible; later text is dropped."""
    runner = _StopMidStreamRunner()

    chains = [chain async for chain in run_agent(runner)]

    assert [chain.get_plain_text() for chain in chains] == ["A"]
    assert runner.event.extras["agent_user_aborted"] is True
    assert runner.event.extras["agent_stop_requested"] is False


def test_buffering_stays_configuration_driven():
    """Buffering depends on configuration only, never on registered hooks."""
    streaming_runner = SimpleNamespace(streaming=True)
    plain_runner = SimpleNamespace(streaming=False)

    assert _should_buffer_llm_result(True, False, plain_runner) is True
    assert _should_buffer_llm_result(True, True, plain_runner) is False
    assert _should_buffer_llm_result(False, False, plain_runner) is False
    assert _should_buffer_llm_result(True, False, streaming_runner) is False
