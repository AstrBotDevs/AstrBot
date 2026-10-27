import re
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import DEFAULT_SEGMENTED_REPLY_REGEX
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage


async def _segment(text: str, threshold: int, regex: str | None = None) -> list[str]:
    stage = ResultDecorateStage()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.enable_segmented_reply = True
    stage.only_llm_result = False
    stage.words_count_threshold = threshold
    stage.split_mode = "regex" if regex is not None else "words"
    stage.regex = regex
    stage.split_words = ["."]
    stage.split_words_pattern = re.compile(r"(.*?(\.)|.+$)", re.DOTALL)
    stage.content_cleanup_rule = ""
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0
    stage.reply_with_mention = False
    stage.reply_with_quote = False
    stage.forward_threshold = 10000
    stage.ctx = cast(
        Any,
        SimpleNamespace(
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(
                    get_using_tts_provider_async=AsyncMock(return_value=None)
                )
            ),
            astrbot_config={
                "provider_tts_settings": {"enable": False},
                "callback_api_base": "",
                "t2i": False,
            },
        ),
    )
    result = MessageEventResult(
        chain=[Plain(text)],
        result_content_type=ResultContentType.LLM_RESULT,
    )
    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="test:FriendMessage:user",
        get_result=lambda: result,
        get_platform_name=lambda: "test",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
    )
    async for _ in stage.process(cast(Any, event)):
        pass
    return [comp.text for comp in result.chain if isinstance(comp, Plain)]


@pytest.mark.asyncio
async def test_english_reply_threshold_counts_words_not_characters():
    text = "This is the first sentence. This is the second one. And a third."
    assert len(text) > 20

    segments = await _segment(text, threshold=20)

    assert len(segments) == 3


@pytest.mark.asyncio
async def test_english_reply_over_word_threshold_is_not_segmented():
    text = "One two three. Four five six."

    segments = await _segment(text, threshold=5)

    assert segments == [text]


@pytest.mark.asyncio
async def test_cjk_reply_threshold_still_counts_characters():
    text = "第一段内容.第二段内容."

    assert await _segment(text, threshold=len(text) - 1) == [text]
    assert len(await _segment(text, threshold=len(text))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "A café is open. Let's go!",
        "It’s ready now. Enjoy 😊!",
        "Cafe\u0301 is open. Enjoy!",
    ],
)
async def test_non_ascii_english_counts_words(text):
    assert len(await _segment(text, threshold=10)) == 2


@pytest.mark.asyncio
async def test_word_threshold_is_inclusive():
    assert len(await _segment("One two. Three four.", threshold=4)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "regex", [DEFAULT_SEGMENTED_REPLY_REGEX, r".*?[。？！~…]+|.+$", "["]
)
async def test_default_and_invalid_regex_split_english(regex):
    assert await _segment("Hello there. How are you? Fine!", 20, regex) == [
        "Hello there.",
        "How are you?",
        "Fine!",
    ]


@pytest.mark.asyncio
async def test_default_regex_preserves_decimals_abbreviations_and_cjk():
    regex = r".*?[。？！~…]+|.+$"
    assert await _segment("Dr. Smith paid 3.14 dollars. Next!", 20, regex) == [
        "Dr. Smith paid 3.14 dollars.",
        "Next!",
    ]
    assert await _segment("你好。再见！", 20, regex) == ["你好。", "再见！"]


@pytest.mark.asyncio
async def test_custom_regex_remains_authoritative():
    assert await _segment("Hello. Still together|Next", 20, r"[^|]+") == [
        "Hello. Still together",
        "Next",
    ]
