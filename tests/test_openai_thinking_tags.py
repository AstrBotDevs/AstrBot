import pytest
from openai.types.chat.chat_completion import ChatCompletion

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


thinking_close = "</" + "thinking>"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "reasoning_field", "answer", "reasoning"),
    [
        ("<think>First\nsecond</think>Answer", None, "Answer", "First\nsecond"),
        ("<thinking>First\nsecond</thinking>Answer", None, "Answer", "First\nsecond"),
        ("<thinking></thinking>Answer", None, "Answer", ""),
        ("<thinking>Only reasoning</thinking>", None, "", "Only reasoning"),
        (
            "<think>One</think><thinking>Two</thinking>Answer",
            None,
            "Answer",
            "One\nTwo",
        ),
        ("Answer</think>", None, "Answer", None),
        ("Answer</thinking>  ", None, "Answer", None),
        (
            "Ordinary thinking and reasoning",
            None,
            "Ordinary thinking and reasoning",
            None,
        ),
        ("<thinker>Example</thinker>", None, "<thinker>Example</thinker>", None),
        ("<thinking>Inline</thinking>Answer", "Structured", "Answer", "Structured"),
        ("<thinking>Inline</thinking>Answer", "", "Answer", ""),
        (
            "<thinking>Unfinished",
            None,
            "",
            "<thinking>Unfinished",
        ),
        (
            "<think>Example</thinking>Answer",
            None,
            "Answer",
            "Example",
        ),
        (
            (
                f"Draft one{thinking_close}\n"
                f"Intermediate draft{thinking_close}\n"
                "Final answer"
            ),
            None,
            "Final answer",
            f"Draft one{thinking_close}\nIntermediate draft{thinking_close}",
        ),
        (
            f"Draft{thinking_close}\nFinal answer",
            None,
            "Final answer",
            f"Draft{thinking_close}",
        ),
        (
            f"Literal closing tag {thinking_close} remains visible",
            None,
            f"Literal closing tag {thinking_close} remains visible",
            None,
        ),
        (
            f"Examples: {thinking_close} and {thinking_close}",
            None,
            f"Examples: {thinking_close} and",
            None,
        ),
        (
            f"Draft{thinking_close}\nPrefix <thinking>Unfinished",
            None,
            "",
            f"Draft{thinking_close}\n<thinking>Unfinished",
        ),
    ],
)
async def test_openai_reasoning_tag_compatibility(
    content, reasoning_field, answer, reasoning
):
    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    provider.reasoning_key = "reasoning_content"
    message = {"role": "assistant", "content": content}
    if reasoning_field is not None:
        message["reasoning_content"] = reasoning_field
    completion = ChatCompletion.model_validate(
        {
            "id": "reasoning-tags",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": message,
                }
            ],
        }
    )
    response = await provider._parse_openai_completion(completion, None)
    assert response.completion_text == answer
    if reasoning is not None:
        assert response.reasoning_content == reasoning
    else:
        assert not response.reasoning_content
