from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import third_party


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_type", "runner_class_name", "config_key"),
    [
        ("dify", "DifyAgentRunner", "dify_api_key"),
        ("coze", "CozeAgentRunner", "coze_api_key"),
        ("dashscope", "DashscopeAgentRunner", "dashscope_api_key"),
        ("deerflow", "DeerFlowAgentRunner", "deerflow_api_key"),
    ],
)
async def test_third_party_runner_receives_inline_profile_config(
    monkeypatch: pytest.MonkeyPatch,
    runner_type: str,
    runner_class_name: str,
    config_key: str,
):
    inline_config = {config_key: "inline-secret"}
    runner = MagicMock()
    runner.reset = AsyncMock()
    runner.get_final_llm_resp.return_value = LLMResponse(
        role="assistant",
        result_chain=MessageChain().message("done"),
    )
    runner.close = AsyncMock()

    async def step_until_done(max_step: int = 30):
        _ = max_step
        if False:
            yield None

    runner.step_until_done = step_until_done
    runner_factory_calls = []

    class RunnerFactory:
        @classmethod
        def __class_getitem__(cls, item):
            _ = item
            return cls

        def __new__(cls):
            runner_factory_calls.append(True)
            return runner

    monkeypatch.setattr(third_party, runner_class_name, RunnerFactory)
    monkeypatch.setattr(
        third_party, "AstrAgentContext", MagicMock(return_value=object())
    )
    monkeypatch.setattr(
        third_party, "AgentContextWrapper", MagicMock(return_value=object())
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party.Metric, "upload", AsyncMock(return_value=None))

    config = {
        "agent_runner": {"runner_type": runner_type, "config": inline_config},
        "provider_settings": {
            "streaming_response": False,
            "unsupported_streaming_strategy": "turn_off",
            "third_party_stream_consumption_close_timeout_sec": 30,
        },
    }
    stage = third_party.ThirdPartyAgentSubStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config,
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(
                    conversation_manager=MagicMock(),
                    persona_manager=MagicMock(),
                )
            ),
        )
    )
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    event = MagicMock()
    event.message_str = "hello"
    event.unified_msg_origin = "webchat:FriendMessage:test"
    event.message_obj.message = []
    event.platform_meta.support_streaming_message = True
    event.get_extra.return_value = None

    results = [item async for item in stage.process(event, "")]

    assert results == [None]
    assert runner.reset.await_args.kwargs["provider_config"] is inline_config
    assert runner_factory_calls == [True]
