import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.agent.runners.dify import dify_agent_runner
from astrbot.core.message.components import At, Image, Record
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import third_party
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.star_handler import EventType

IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+"
    "X2ioAAAAASUVORK5CYII="
)
DIRECTED_PROMPT = "⚠️[DIRECTED AT YOU]\n"


@pytest.fixture
def third_party_case(monkeypatch: pytest.MonkeyPatch, mock_event):
    async def make_case(runner_type="dify", inline_config=None):
        if inline_config is None:
            inline_config = {"dify_api_key": "k"}
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

        runner_class_name = {
            "dify": "DifyAgentRunner",
            "coze": "CozeAgentRunner",
            "dashscope": "DashscopeAgentRunner",
            "deerflow": "DeerFlowAgentRunner",
        }[runner_type]
        monkeypatch.setattr(third_party, runner_class_name, RunnerFactory)
        monkeypatch.setattr(
            third_party, "AstrAgentContext", MagicMock(return_value=object())
        )
        monkeypatch.setattr(
            third_party, "AgentContextWrapper", MagicMock(return_value=object())
        )
        hook = AsyncMock(return_value=False)
        monkeypatch.setattr(third_party, "call_event_hook", hook)
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
        mock_event.message_str = "hello"
        mock_event.unified_msg_origin = "webchat:GroupMessage:test"
        mock_event.platform_meta.support_streaming_message = True

        return SimpleNamespace(
            stage=stage,
            event=mock_event,
            runner=runner,
            hook=hook,
            runner_factory_calls=runner_factory_calls,
        )

    return make_case


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_type", "config_key"),
    [
        ("dify", "dify_api_key"),
        ("coze", "coze_api_key"),
        ("dashscope", "dashscope_api_key"),
        ("deerflow", "deerflow_api_key"),
    ],
)
async def test_third_party_runner_receives_inline_profile_config(
    third_party_case,
    runner_type: str,
    config_key: str,
):
    inline_config = {config_key: "inline-secret"}
    case = await third_party_case(runner_type, inline_config)

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == [None]
    assert case.runner.reset.await_args.kwargs["provider_config"] is inline_config
    assert case.runner_factory_calls == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component", "patch_method", "request_attr"),
    [
        (Record, "convert_to_file_path", "audio_urls"),
        (Image, "convert_to_base64", "image_urls"),
    ],
)
async def test_third_party_skips_unavailable_attachment(
    monkeypatch: pytest.MonkeyPatch,
    third_party_case,
    component,
    patch_method: str,
    request_attr: str,
):
    """An unresolvable attachment must not abort the third-party request."""
    case = await third_party_case()

    async def unavailable(self):
        raise ValueError("No valid file or URL provided")

    monkeypatch.setattr(component, patch_method, unavailable)
    case.event.message_obj.message = [component(file="")]

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == [None]
    request = case.runner.reset.await_args.kwargs["request"]
    assert getattr(request, request_attr) == []
    assert request.prompt == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize("api_type", [None, "chat", "agent", "chatflow"])
async def test_dify_image_prompt_is_ready_before_request_hook(
    third_party_case,
    api_type,
):
    config = {"dify_api_key": "k"}
    if api_type is not None:
        config["dify_api_type"] = api_type
    case = await third_party_case(inline_config=config)
    case.event.message_str = ""
    case.event.message_obj.message = [
        At(qq="bot"),
        Image.fromBase64(IMAGE_BASE64),
    ]
    prompts_at_hook = []

    async def decorate_request(event, event_type, request):
        assert event is case.event
        assert event_type == EventType.OnLLMRequestEvent
        prompts_at_hook.append(request.prompt)
        request.prompt = DIRECTED_PROMPT + request.prompt
        return False

    case.hook.side_effect = decorate_request

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == [None]
    assert prompts_at_hook == ["请描述这张图片。"]
    request = case.runner.reset.await_args.kwargs["request"]
    assert request.prompt == DIRECTED_PROMPT + "请描述这张图片。"
    assert request.image_urls == [IMAGE_BASE64]
    assert request.audio_urls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner_type", "api_type"),
    [
        ("dify", "workflow"),
        ("coze", "chat"),
        ("dashscope", "chat"),
        ("deerflow", "chat"),
    ],
)
async def test_non_chat_dify_and_other_runners_keep_empty_image_prompt(
    third_party_case,
    runner_type: str,
    api_type: str,
):
    case = await third_party_case(runner_type, {"dify_api_type": api_type})
    case.event.message_str = ""
    case.event.message_obj.message = [Image.fromBase64(IMAGE_BASE64)]
    prompts_at_hook = []

    async def inspect_request(event, event_type, request):
        prompts_at_hook.append(request.prompt)
        return False

    case.hook.side_effect = inspect_request

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == [None]
    assert prompts_at_hook == [""]
    request = case.runner.reset.await_args.kwargs["request"]
    assert request.prompt == ""
    assert request.image_urls == [IMAGE_BASE64]


@pytest.mark.asyncio
@pytest.mark.parametrize("api_type", [None, "chat", "agent", "chatflow", "workflow"])
async def test_dify_empty_request_still_skips_hook_and_runner(
    third_party_case,
    api_type,
):
    config = {"dify_api_key": "k"}
    if api_type is not None:
        config["dify_api_type"] = api_type
    case = await third_party_case(inline_config=config)
    case.event.message_str = ""

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == []
    case.hook.assert_not_awaited()
    case.runner.reset.assert_not_awaited()
    assert case.runner_factory_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("api_type", ["chat", "agent", "chatflow"])
async def test_dify_runner_sends_directed_image_query_and_uploaded_file(
    monkeypatch: pytest.MonkeyPatch,
    third_party_case,
    api_type: str,
):
    case = await third_party_case(
        inline_config={"dify_api_key": "k", "dify_api_type": api_type}
    )
    monkeypatch.setattr(
        third_party, "DifyAgentRunner", dify_agent_runner.DifyAgentRunner
    )
    monkeypatch.setattr(
        third_party,
        "MAIN_AGENT_HOOKS",
        SimpleNamespace(on_agent_begin=AsyncMock(), on_agent_done=AsyncMock()),
    )
    client = MagicMock()
    client.file_upload = AsyncMock(return_value={"id": "uploaded-image"})
    client.close = AsyncMock()

    async def chat_messages(**kwargs):
        yield {
            "event": "message",
            "answer": "A test image.",
            "conversation_id": "conversation",
        }
        yield {"event": "message_end"}

    client.chat_messages = MagicMock(side_effect=chat_messages)
    monkeypatch.setattr(
        dify_agent_runner, "DifyAPIClient", MagicMock(return_value=client)
    )

    async def get_session_value(*, default, **kwargs):
        return default

    monkeypatch.setattr(
        dify_agent_runner.sp, "get_async", AsyncMock(side_effect=get_session_value)
    )
    monkeypatch.setattr(dify_agent_runner.sp, "put_async", AsyncMock())
    case.event.message_str = ""
    case.event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    case.event.get_self_id.return_value = "bot"
    case.event.message_obj.message = [
        At(qq="bot"),
        Image.fromBase64(IMAGE_BASE64),
    ]
    case.event.get_messages.side_effect = lambda: case.event.message_obj.message
    main = Main.__new__(Main)
    main.group_chat_context = None
    prompts_at_hook = []

    async def decorate_request(event, event_type, request):
        prompts_at_hook.append(request.prompt)
        await main.decorate_llm_req(event, request)
        return False

    case.hook.side_effect = decorate_request

    results = [item async for item in case.stage.process(case.event, "")]

    assert results == [None]
    assert prompts_at_hook == ["请描述这张图片。"]
    result = case.event.set_result.call_args.args[0]
    assert result.result_content_type == ResultContentType.LLM_RESULT
    assert result.chain[0].text == "A test image."
    query = client.chat_messages.call_args.kwargs
    assert query["query"] == DIRECTED_PROMPT + "请描述这张图片。"
    assert query["files"] == [
        {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": "uploaded-image",
        }
    ]
    client.file_upload.assert_awaited_once()
    upload = client.file_upload.await_args.kwargs
    assert upload["file_data"] == base64.b64decode(IMAGE_BASE64)
    assert upload["mime_type"] == "image/png"
    assert upload["user"] == case.event.unified_msg_origin
    client.close.assert_awaited_once()
