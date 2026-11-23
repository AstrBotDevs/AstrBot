import json
import warnings

from astrbot.core.provider.entities import LLMResponse


def _response() -> LLMResponse:
    return LLMResponse(
        role="tool",
        tools_call_args=[{"query": "明天北京的天气怎么样", "lang": "日本語"}],
        tools_call_name=["web_search"],
        tools_call_ids=["call_1"],
    )


def test_tool_call_arguments_keep_non_ascii_text():
    """Replayed tool-call arguments should not be ASCII-escaped."""
    arguments = _response().to_openai_tool_calls_model()[0].function.arguments

    assert arguments == '{"query": "明天北京的天气怎么样", "lang": "日本語"}'
    assert json.loads(arguments) == _response().tools_call_args[0]


def test_deprecated_tool_call_dict_keeps_non_ascii_text():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        arguments = _response().to_openai_tool_calls()[0]["function"]["arguments"]

    assert "\\u" not in arguments
    assert json.loads(arguments) == _response().tools_call_args[0]
