"""Third-party stages use lazy runner imports, scoped configuration, and real events."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.message.components import Image, Plain, Record, Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import third_party
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.active_event_registry import ActiveEventRegistry

RUNNERS = [
    ("dify", "dify.dify_agent_runner", "DifyAgentRunner", "dify_api_key"),
    ("coze", "coze.coze_agent_runner", "CozeAgentRunner", "coze_api_key"),
    (
        "dashscope",
        "dashscope.dashscope_agent_runner",
        "DashscopeAgentRunner",
        "dashscope_api_key",
    ),
    (
        "deerflow",
        "deerflow.deerflow_agent_runner",
        "DeerFlowAgentRunner",
        "deerflow_api_key",
    ),
]


def make_event(components):
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "test"
    message.message_id = "message"
    message.sender = MessageMember(user_id="user", nickname="Test")
    message.message = components
    message.message_str = "hello"
    message.raw_message = {}
    return AstrMessageEvent(
        "hello",
        message,
        PlatformMetadata(name="webchat", id="webchat", description="Test"),
        "test",
    )


@pytest.fixture
def prepare_stage(monkeypatch):
    """Mock external runner execution while keeping context and event validation real."""
    hooks = AsyncMock(return_value=False)
    registry = ActiveEventRegistry()
    monkeypatch.setattr(third_party, "call_event_hook", hooks)
    monkeypatch.setattr(third_party, "active_event_registry", registry)
    monkeypatch.setattr(third_party.Metric, "upload", AsyncMock())

    async def prepare(runner_type, runner_module, runner_class, inline_config):
        runner = SimpleNamespace(
            reset=AsyncMock(),
            close=AsyncMock(),
            done=Mock(return_value=True),
            get_final_llm_resp=Mock(
                return_value=LLMResponse(
                    role="assistant", result_chain=MessageChain().message("done")
                )
            ),
        )

        async def step_until_done(max_step):
            assert max_step == 128
            for item in ():
                yield item

        runner.step_until_done = step_until_done
        create_runner = Mock(return_value=runner)

        class RunnerFactory:
            @classmethod
            def __class_getitem__(cls, item):
                return cls

            def __new__(cls):
                return create_runner()

        module = importlib.import_module(f"astrbot.core.agent.runners.{runner_module}")
        monkeypatch.setattr(module, runner_class, RunnerFactory)
        config = {
            "agent": {"runtime": runner_type, "config": inline_config},
            "provider_settings": {
                "streaming_response": False,
                "unsupported_streaming_strategy": "turn_off",
                "third_party_stream_consumption_close_timeout_sec": 30,
            },
        }
        context = Context(
            event_queue=asyncio.Queue(),
            config=config,
            db=object(),
            provider_manager=object(),
            platform_manager=object(),
            conversation_manager=object(),
            message_history_manager=object(),
            persona_manager=object(),
            astrbot_config_mgr=object(),
            knowledge_base_manager=object(),
            cron_manager=object(),
            agent_runtimes={},
        )
        bridge = SimpleNamespace(dispatch_message_event=AsyncMock())
        context.sdk_plugin_bridge = bridge
        stage = third_party.ThirdPartyAgentSubStage()
        await stage.initialize(
            SimpleNamespace(
                astrbot_config=config,
                plugin_manager=SimpleNamespace(context=context),
            )
        )
        monkeypatch.setattr(
            stage, "_resolve_persona_custom_error_message", AsyncMock(return_value=None)
        )
        return SimpleNamespace(
            stage=stage,
            runner=runner,
            create_runner=create_runner,
            context=context,
            config=config,
            hooks=hooks,
            bridge=bridge,
            registry=registry,
        )

    return prepare


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_type", "runner_module", "runner_class", "config_key"), RUNNERS
)
async def test_third_party_runner_receives_inline_profile_config(
    prepare_stage, runner_type, runner_module, runner_class, config_key
):
    initial_config = {config_key: "inline-secret"}
    harness = await prepare_stage(
        runner_type, runner_module, runner_class, initial_config
    )
    scoped_config = {**initial_config, "persona_id": "session-persona"}
    harness.stage.ctx.astrbot_config = {
        **harness.config,
        "agent": {"runtime": runner_type, "config": scoped_config},
    }
    event = make_event(
        [Reply(id="quoted", sender_nickname="Alice", chain=[Plain("Tomorrow at ten.")])]
    )

    assert [item async for item in harness.stage.process(event, "")] == [None]
    harness.create_runner.assert_called_once_with()
    harness.runner.reset.assert_awaited_once()
    arguments = harness.runner.reset.await_args.kwargs
    request = arguments["request"]
    assert arguments["provider_config"] is scoped_config
    assert request.prompt == (
        "hello\n\n<Quoted Message>\n(Alice): Tomorrow at ten.\n</Quoted Message>"
    )
    assert arguments["run_context"].context.context is harness.context
    assert arguments["run_context"].context.event is event
    assert "persona_id" not in initial_config
    harness.hooks.assert_awaited_once_with(
        event, EventType.OnLLMRequestEvent, request, context_observer=None
    )
    harness.bridge.dispatch_message_event.assert_awaited_once_with(
        "llm_request",
        event,
        {"prompt": request.prompt, "provider_id": "", "runner_type": runner_type},
        provider_request=request,
    )
    assert event.get_result().get_plain_text() == "done"
    harness.runner.close.assert_awaited_once_with()
    assert not harness.registry._agent_stop_callbacks
    await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_type", "runner_module", "runner_class", "config_key"), RUNNERS[2:]
)
async def test_third_party_initializes_real_remote_runner_without_local_provider(
    prepare_stage, monkeypatch, runner_type, runner_module, runner_class, config_key
):
    """Exercise the real reset signature at the stage-to-service boundary."""
    module = importlib.import_module(f"astrbot.core.agent.runners.{runner_module}")
    real_runner = getattr(module, runner_class)()
    inline_config = {
        config_key: "test-key",
        "dashscope_app_id": "test-app",
        "dashscope_app_type": "agent",
    }
    harness = await prepare_stage(
        runner_type, runner_module, runner_class, inline_config
    )
    reset = AsyncMock(wraps=real_runner.reset)
    monkeypatch.setattr(harness.runner, "reset", reset)
    event = make_event([Plain("hello")])

    try:
        assert [item async for item in harness.stage.process(event, "")] == [None]
        reset.assert_awaited_once()
        assert real_runner.req.prompt == "hello"
        assert real_runner.run_context.context.event is event
        assert real_runner.streaming is False
        assert event.get_result().get_plain_text() == "done"
    finally:
        await third_party._close_runner_if_supported(real_runner)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component", "patch_method", "request_attr"),
    [
        (Record, "convert_to_file_path", "audio_urls"),
        (Image, "convert_to_base64", "image_urls"),
    ],
)
async def test_third_party_skips_unavailable_attachment(
    prepare_stage, monkeypatch, component, patch_method, request_attr
):
    """An unavailable attachment must not abort text execution or leak the runner."""
    harness = await prepare_stage(*RUNNERS[0][:3], {"dify_api_key": "inline-secret"})
    converter = AsyncMock(side_effect=ValueError("No valid file or URL provided"))
    monkeypatch.setattr(component, patch_method, converter)
    event = make_event([component(file="")])

    assert [item async for item in harness.stage.process(event, "")] == [None]
    converter.assert_awaited_once_with()
    harness.runner.reset.assert_awaited_once()
    request = harness.runner.reset.await_args.kwargs["request"]
    assert getattr(request, request_attr) == []
    assert request.prompt == "hello"
    assert event.get_result().get_plain_text() == "done"
    harness.runner.close.assert_awaited_once_with()
    assert not harness.registry._agent_stop_callbacks
    await asyncio.sleep(0)
