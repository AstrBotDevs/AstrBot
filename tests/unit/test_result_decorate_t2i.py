from types import SimpleNamespace

import pytest

import astrbot.core.pipeline.result_decorate.stage as stage_module
from astrbot.core.message.components import Image, Plain, Record
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage

LONG_TEXT = "这是一段用于验证文本转图像阈值的长文本。" * 20
SHORT_TEXT = "短文本"


def _build_config(*, tts_enable: bool, dual_output: bool, t2i: bool) -> dict:
    return {
        "platform_settings": {
            "reply_prefix": "",
            "reply_with_mention": False,
            "reply_with_quote": False,
            "forward_threshold": 999999,
            "segmented_reply": {
                "enable": False,
                "only_llm_result": True,
                "words_count_threshold": 150,
                "regex": r".*?[。？！~…]+|.+$",
                "content_cleanup_rule": "",
            },
        },
        "t2i": t2i,
        "t2i_word_threshold": 50,
        "t2i_strategy": "local",
        "t2i_active_template": "base",
        "t2i_use_file_service": False,
        "callback_api_base": "",
        "provider_tts_settings": {
            "enable": tts_enable,
            "dual_output": dual_output,
            "use_file_service": False,
            "trigger_probability": 1,
        },
        "content_safety": {"also_use_in_response": False},
        "provider_settings": {"display_reasoning_text": False},
    }


class FakeTTSProvider:
    async def get_audio(self, text: str) -> str:
        del text
        return "/tmp/fake_tts_audio.wav"


class FakeEvent:
    def __init__(self, result: MessageEventResult):
        self._result = result
        self.plugins_name = None
        self.unified_msg_origin = "test:GroupMessage:1"
        self.tracked_files: list[str] = []

    def get_result(self) -> MessageEventResult:
        return self._result

    def get_extra(self, key: str):
        del key
        return None

    def get_platform_name(self) -> str:
        return "test"

    def is_stopped(self) -> bool:
        return False

    def track_temporary_local_file(self, path: str) -> None:
        self.tracked_files.append(path)


async def _run_stage(
    config: dict, result: MessageEventResult, monkeypatch
) -> FakeEvent:
    tts_provider = (
        FakeTTSProvider() if config["provider_tts_settings"]["enable"] else None
    )
    ctx = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(
                get_using_tts_provider=lambda umo: tts_provider,
            ),
        ),
    )

    async def _always_tts(event):
        del event
        return True

    async def _fake_render(text, return_url=True, use_network=False, template_name=""):
        del text, return_url, use_network, template_name
        return "http://fake.local/t2i.png"

    monkeypatch.setattr(
        stage_module.SessionServiceManager,
        "should_process_tts_request",
        staticmethod(_always_tts),
    )
    monkeypatch.setattr(stage_module.html_renderer, "render_t2i", _fake_render)

    stage = ResultDecorateStage()
    await stage.initialize(ctx)
    event = FakeEvent(result)
    generator = stage.process(event)
    if generator is not None:
        async for _ in generator:
            pass
    return event


@pytest.mark.asyncio
async def test_t2i_still_applies_when_tts_dual_output(monkeypatch):
    result = MessageEventResult(chain=[Plain(LONG_TEXT)]).set_result_content_type(
        ResultContentType.LLM_RESULT
    )
    await _run_stage(
        _build_config(tts_enable=True, dual_output=True, t2i=True),
        result,
        monkeypatch,
    )

    assert any(isinstance(comp, Record) for comp in result.chain)
    assert isinstance(result.chain[-1], Image)
    assert not any(isinstance(comp, Plain) for comp in result.chain)


@pytest.mark.asyncio
async def test_t2i_without_tts_keeps_original_behavior(monkeypatch):
    result = MessageEventResult(chain=[Plain(LONG_TEXT)]).set_result_content_type(
        ResultContentType.LLM_RESULT
    )
    await _run_stage(
        _build_config(tts_enable=False, dual_output=False, t2i=True),
        result,
        monkeypatch,
    )

    assert len(result.chain) == 1
    assert isinstance(result.chain[0], Image)


@pytest.mark.asyncio
async def test_dual_output_below_threshold_keeps_voice_and_text(monkeypatch):
    result = MessageEventResult(chain=[Plain(SHORT_TEXT)]).set_result_content_type(
        ResultContentType.LLM_RESULT
    )
    await _run_stage(
        _build_config(tts_enable=True, dual_output=True, t2i=True),
        result,
        monkeypatch,
    )

    assert isinstance(result.chain[0], Record)
    assert isinstance(result.chain[1], Plain)


@pytest.mark.asyncio
async def test_tts_without_dual_output_sends_voice_only(monkeypatch):
    result = MessageEventResult(chain=[Plain(LONG_TEXT)]).set_result_content_type(
        ResultContentType.LLM_RESULT
    )
    await _run_stage(
        _build_config(tts_enable=True, dual_output=False, t2i=True),
        result,
        monkeypatch,
    )

    assert len(result.chain) == 1
    assert isinstance(result.chain[0], Record)
