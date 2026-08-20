from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import At, Plain, Record, Reply
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage


def _make_stage(
    *, use_file_service: bool, callback_api_base: str
) -> ResultDecorateStage:
    stage = ResultDecorateStage()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.enable_segmented_reply = False
    stage.only_llm_result = False
    stage.words_count_threshold = 100
    stage.split_mode = "words"
    stage.split_words = ["。"]
    stage.split_words_pattern = None
    stage.content_cleanup_rule = ""
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0
    stage.reply_with_mention = False
    stage.reply_with_quote = False
    stage.forward_threshold = 1000
    stage.t2i_word_threshold = 10
    stage.t2i_active_template = "base"
    stage.t2i_use_file_service = use_file_service
    stage.ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            get_using_tts_provider=lambda _umo: None,
        ),
        handlers=SimpleNamespace(
            get_handlers_by_event_type=lambda *_args, **_kwargs: [],
        ),
        plugins=SimpleNamespace(get_by_module=lambda _module_path: None),
        astrbot_config={
            "provider_tts_settings": {
                "enable": False,
                "use_file_service": False,
                "dual_output": False,
            },
            "callback_api_base": callback_api_base,
            "t2i": True,
        },
        html_renderer=SimpleNamespace(render_t2i=AsyncMock()),
        file_token_service=SimpleNamespace(register_file=AsyncMock()),
    )
    stage.session_services = SimpleNamespace(
        should_process_tts_request=AsyncMock(return_value=True),
    )
    return stage


async def _consume(stage: ResultDecorateStage, event: object) -> None:
    async for _ in stage.process(cast(Any, event)):
        pass


def _make_event(result: MessageEventResult, **overrides: Any) -> SimpleNamespace:
    values = {
        "plugins_name": None,
        "unified_msg_origin": "napcat:FriendMessage:42",
        "get_result": lambda: result,
        "get_platform_name": lambda: "napcat",
        "get_message_type": lambda: "group",
        "get_sender_id": lambda: "42",
        "get_sender_name": lambda: "tester",
        "get_self_id": lambda: "bot",
        "message_obj": SimpleNamespace(message_id="message-id"),
        "is_stopped": lambda: False,
        "get_extra": lambda *_args, **_kwargs: None,
        "track_temporary_local_file": lambda *_args, **_kwargs: None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_result_decorate_uses_local_t2i_and_file_token_url(monkeypatch):
    stage = _make_stage(
        use_file_service=False,
        callback_api_base="http://127.0.0.1:6185/",
    )
    result = MessageEventResult(chain=[Plain("0123456789abcde")])
    tracked_files: list[str] = []

    async def fake_render_t2i(text: str, template_name: str | None = None) -> str:
        assert text == "\n\n0123456789abcde"
        assert template_name == "base"
        return "D:/temp/rendered.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/temp/rendered.png"
        return "token-123"

    monkeypatch.setattr(stage.ctx.html_renderer, "render_t2i", fake_render_t2i)
    monkeypatch.setattr(
        stage.ctx.file_token_service, "register_file", fake_register_file
    )

    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="napcat:FriendMessage:42",
        get_result=lambda: result,
        get_platform_name=lambda: "napcat",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
        track_temporary_local_file=tracked_files.append,
    )

    await _consume(stage, event)

    image = result.chain[0]
    assert image.file == "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    assert tracked_files == ["D:/temp/rendered.png"]


@pytest.mark.asyncio
async def test_result_decorate_keeps_local_file_when_no_callback_url(
    monkeypatch, tmp_path
):
    stage = _make_stage(use_file_service=False, callback_api_base="")
    result = MessageEventResult(chain=[Plain("0123456789abcde")])
    image_path = tmp_path / "rendered.png"

    monkeypatch.setattr(
        stage.ctx.html_renderer,
        "render_t2i",
        AsyncMock(return_value=str(image_path)),
    )

    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="qq_official:GroupMessage:group-1",
        get_result=lambda: result,
        get_platform_name=lambda: "qq_official",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
        track_temporary_local_file=lambda *_args, **_kwargs: None,
    )

    await _consume(stage, event)

    image = result.chain[0]
    assert image.file == image_path.resolve().as_uri()
    assert image.path == str(image_path.resolve())


@pytest.mark.asyncio
async def test_result_decorate_warns_when_tts_is_enabled_without_provider(caplog):
    stage = _make_stage(use_file_service=False, callback_api_base="")
    stage.ctx.astrbot_config["provider_tts_settings"]["enable"] = True
    stage.tts_trigger_probability = 1
    result = MessageEventResult(
        chain=[Plain("hello")], result_content_type=ResultContentType.LLM_RESULT
    )

    await _consume(stage, _make_event(result))

    assert "未配置文本转语音模型" in caplog.text
    assert isinstance(result.chain[0], Plain)


@pytest.mark.asyncio
async def test_result_decorate_tts_dual_output_and_t2i_are_mutually_exclusive():
    stage = _make_stage(use_file_service=False, callback_api_base="")
    stage.ctx.astrbot_config["provider_tts_settings"].update(
        {"enable": True, "dual_output": True}
    )
    stage.tts_trigger_probability = 1
    stage.ctx.astrbot_config["t2i"] = True
    provider = SimpleNamespace(get_audio=AsyncMock(return_value="D:/temp/a.mp3"))
    stage.ctx.execution_context.get_using_tts_provider = lambda _umo: provider
    result = MessageEventResult(
        chain=[Plain("hello")], result_content_type=ResultContentType.LLM_RESULT
    )

    await _consume(stage, _make_event(result))

    assert [type(component) for component in result.chain] == [Record, Plain]
    stage.ctx.html_renderer.render_t2i.assert_not_awaited()


@pytest.mark.asyncio
async def test_result_decorate_invalid_segment_regex_falls_back():
    stage = _make_stage(use_file_service=False, callback_api_base="")
    stage.enable_segmented_reply = True
    stage.split_mode = "regex"
    stage.regex = "["
    stage.words_count_threshold = 100
    stage.ctx.astrbot_config["t2i"] = False
    result = MessageEventResult(chain=[Plain("one。two。")])

    await _consume(stage, _make_event(result))

    assert [component.text for component in result.chain] == ["one。", "two。"]


@pytest.mark.asyncio
async def test_result_decorate_file_service_failure_falls_back_to_local_image(tmp_path):
    stage = _make_stage(use_file_service=True, callback_api_base="https://example.com")
    image_path = tmp_path / "rendered.png"
    stage.ctx.html_renderer.render_t2i = AsyncMock(return_value=str(image_path))
    stage.ctx.file_token_service.register_file = AsyncMock(side_effect=RuntimeError())
    result = MessageEventResult(chain=[Plain("0123456789abcde")])

    await _consume(stage, _make_event(result))

    assert result.chain[0].path == str(image_path.resolve())


@pytest.mark.asyncio
async def test_result_decorate_streaming_result_short_circuits():
    stage = _make_stage(use_file_service=False, callback_api_base="")
    result = MessageEventResult(
        chain=[Plain("hello")], result_content_type=ResultContentType.STREAMING_RESULT
    )

    await _consume(stage, _make_event(result))

    assert result.chain[0].text == "hello"


@pytest.mark.asyncio
async def test_result_decorate_adds_mention_then_quote():
    stage = _make_stage(use_file_service=False, callback_api_base="")
    stage.ctx.astrbot_config["t2i"] = False
    stage.reply_with_mention = True
    stage.reply_with_quote = True
    result = MessageEventResult(chain=[Plain("hello")])

    await _consume(stage, _make_event(result))

    assert isinstance(result.chain[0], Reply)
    assert isinstance(result.chain[1], At)
    assert result.chain[2].text == "\nhello"
