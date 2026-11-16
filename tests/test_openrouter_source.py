from collections.abc import Mapping

import pytest
from openai.types.chat import ChatCompletion

from astrbot.core.provider.sources.openrouter_source import ProviderOpenRouter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_fields", "expected"),
    [
        (
            {
                "reasoning_details": [
                    {"type": "reasoning.summary", "summary": "Check the inputs."},
                    {"type": "reasoning.text", "text": " Then compare results."},
                    {"type": "reasoning.encrypted", "data": "opaque"},
                    {"type": "reasoning.text", "text": None},
                    None,
                ],
            },
            "Check the inputs. Then compare results.",
        ),
        (
            {
                "reasoning": "Existing flat text",
                "reasoning_details": [
                    {"type": "reasoning.summary", "summary": "Duplicate detail"}
                ],
            },
            "Existing flat text",
        ),
        (
            {"reasoning_details": [{"type": "reasoning.encrypted", "data": "opaque"}]},
            None,
        ),
    ],
)
async def test_openrouter_parses_textual_reasoning_in_non_streaming_completion(
    message_fields: Mapping[str, object], expected: str | None
):
    provider = ProviderOpenRouter(
        provider_config={
            "id": "test-openrouter",
            "type": "openrouter_chat_completion",
            "model": "test-model",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Result",
                        **message_fields,
                    },
                    "finish_reason": "stop",
                }
            ],
        }
    )
    try:
        response = await provider._parse_openai_completion(completion, tools=None)
        assert response.completion_text == "Result"
        assert response.reasoning_content == expected
    finally:
        await provider.terminate()
