from types import SimpleNamespace

import pytest

from astrbot.core.agent.response import AgentResponse, AgentResponseData
from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.message_event_result import MessageChain


class _StreamingRunner:
    """Provide the minimal streaming runner interface required by run_agent."""

    def __init__(self, *responses: AgentResponse) -> None:
        extras = {}
        event = SimpleNamespace(
            is_stopped=lambda: False,
            get_extra=lambda key, default=None: extras.get(key, default),
            get_platform_name=lambda: "test",
        )
        self.run_context = SimpleNamespace(
            context=SimpleNamespace(event=event),
            messages=[],
        )
        self.streaming = True
        self.req = None
        self._responses = responses
        self._done = False

    async def step(self):
        """Yield configured responses and then mark the runner as done."""
        for response in self._responses:
            yield response
        self._done = True

    def done(self) -> bool:
        """Return whether all configured responses have been yielded."""
        return self._done

    def request_stop(self) -> None:
        """Mark the runner as done when run_agent requests a stop."""
        self._done = True


@pytest.mark.asyncio
async def test_run_agent_yields_streaming_error_chain():
    error_chain = MessageChain().message("LLM response failed")
    runner = _StreamingRunner(
        AgentResponse(
            type="err",
            data=AgentResponseData(chain=error_chain),
        )
    )

    yielded = [chain async for chain in run_agent(runner)]

    assert yielded == [error_chain]


@pytest.mark.asyncio
async def test_run_agent_preserves_streaming_delta():
    delta_chain = MessageChain().message("streamed answer")
    runner = _StreamingRunner(
        AgentResponse(
            type="streaming_delta",
            data=AgentResponseData(chain=delta_chain),
        )
    )

    yielded = [chain async for chain in run_agent(runner)]

    assert yielded == [delta_chain]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("show_reasoning", "expected_count"),
    [(False, 0), (True, 1)],
)
async def test_run_agent_preserves_reasoning_visibility_filter(
    show_reasoning: bool,
    expected_count: int,
):
    reasoning_chain = MessageChain(type="reasoning").message("internal reasoning")
    runner = _StreamingRunner(
        AgentResponse(
            type="streaming_delta",
            data=AgentResponseData(chain=reasoning_chain),
        )
    )

    yielded = [
        chain async for chain in run_agent(runner, show_reasoning=show_reasoning)
    ]

    assert yielded == [reasoning_chain] * expected_count
