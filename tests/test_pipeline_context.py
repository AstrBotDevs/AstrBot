"""Pipeline contexts expose only their own active message snapshot."""

import asyncio

import pytest

from astrbot.core.config.runtime import MessageConfig, current_message_config
from astrbot.core.pipeline.context import PipelineContext


def test_pipeline_context_owns_its_runtime_registry() -> None:
    first = PipelineContext({"profile": "first"}, object(), "first")
    second = PipelineContext({"profile": "second"}, object(), "second")
    first.agent_runtimes["native"] = object()
    assert second.agent_runtimes == {}
    explicit = {}
    assert (
        PipelineContext({}, object(), "third", agent_runtimes=explicit).agent_runtimes
        is explicit
    )


@pytest.mark.parametrize(
    ("active", "same_context"), [(True, True), (False, True), (True, False)]
)
def test_message_configuration_is_scoped_and_restored(
    active: bool, same_context: bool
) -> None:
    base, snapshot = {"value": "base"}, {"value": "message"}
    context = PipelineContext(base, object(), "default")
    owner = context if same_context else PipelineContext({}, object(), "other")
    scope = MessageConfig(
        "test:FriendMessage:alice", snapshot, owner, frozenset(), active
    )
    token = current_message_config.set(scope)
    try:
        assert context.astrbot_config is (snapshot if active and same_context else base)
    finally:
        current_message_config.reset(token)
    assert context.astrbot_config is base


@pytest.mark.asyncio
async def test_parallel_messages_keep_independent_configuration() -> None:
    base = {"value": "base"}
    context = PipelineContext(base, object(), "default")
    ready = asyncio.Event()
    entered = 0

    async def read_message(value: str) -> str:
        nonlocal entered
        token = current_message_config.set(
            MessageConfig(value, {"value": value}, context, frozenset())
        )
        try:
            entered += 1
            if entered == 2:
                ready.set()
            await ready.wait()
            return context.astrbot_config["value"]
        finally:
            current_message_config.reset(token)

    assert await asyncio.gather(read_message("alice"), read_message("bob")) == [
        "alice",
        "bob",
    ]
    assert context.astrbot_config is base
