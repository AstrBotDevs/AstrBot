from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain


class _FakeAgentRunner:
    def __init__(self, chain: MessageChain | list[MessageChain]) -> None:
        self.streaming = False
        self.req = None
        self.stats = SimpleNamespace(to_dict=lambda: {})
        self.agent_hooks = SimpleNamespace(on_agent_done=MagicMock())
        self.run_context = SimpleNamespace(
            context=SimpleNamespace(event=_FakeEvent()),
            messages=[],
        )
        self._chains = chain if isinstance(chain, list) else [chain]
        self._done = False
        self.stop_requested = False

    async def step(self):
        for chain in self._chains:
            yield SimpleNamespace(type="llm_result", data={"chain": chain})
        self._done = True

    def done(self) -> bool:
        return self._done

    def request_stop(self) -> None:
        self.stop_requested = True


class _FakeEvent:
    def __init__(self) -> None:
        self._result = None
        self.extras = {}
        self.trace = SimpleNamespace(record=MagicMock())

    def is_stopped(self) -> bool:
        return False

    def get_extra(self, key: str):
        return self.extras.get(key)

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value

    def set_result(self, result) -> None:
        self._result = result

    def clear_result(self) -> None:
        self._result = None

    def get_result(self):
        return self._result

    def get_platform_name(self) -> str:
        return "test"


@pytest.mark.asyncio
async def test_run_agent_result_chain_is_isolated_from_llm_chain_mutation():
    original_component = Plain("original")
    original_chain = MessageChain(chain=[original_component])
    runner = _FakeAgentRunner(original_chain)

    agent_output = run_agent(runner)
    yielded_chain = await anext(agent_output)

    event_result = runner.run_context.context.event.get_result()
    assert yielded_chain is original_chain
    assert event_result.chain[0] is not original_component
    assert event_result.chain[0].text == "original"

    original_component.text = "mutated"
    original_chain.chain.clear()

    assert event_result.chain[0].text == "original"
    assert len(event_result.chain) == 1

    with pytest.raises(StopAsyncIteration):
        await anext(agent_output)


@pytest.mark.asyncio
async def test_run_agent_buffered_result_chain_is_isolated_from_source_chains():
    first_component = Plain("first")
    second_component = Plain("second")
    first_chain = MessageChain(chain=[first_component])
    second_chain = MessageChain(chain=[second_component])
    runner = _FakeAgentRunner([first_chain, second_chain])

    agent_output = run_agent(runner, buffer_intermediate_messages=True)
    yielded_chain = await anext(agent_output)

    event_result = runner.run_context.context.event.get_result()
    assert yielded_chain.chain == [first_component, second_component]
    assert event_result.chain[0] is not first_component
    assert event_result.chain[1] is not second_component
    assert [comp.text for comp in event_result.chain] == ["first", "second"]

    first_component.text = "mutated-first"
    second_chain.chain.clear()

    assert [comp.text for comp in event_result.chain] == ["first", "second"]
    assert len(event_result.chain) == 2

    with pytest.raises(StopAsyncIteration):
        await anext(agent_output)
