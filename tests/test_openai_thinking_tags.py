import pytest
from openai.types.chat.chat_completion import ChatCompletion

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


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
        ("<thinking>Unfinished", None, "<thinking>Unfinished", None),
        (
            "<think>Example</thinking>Answer",
            None,
            "<think>Example</thinking>Answer",
            None,
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


@pytest.mark.asyncio
async def test_openai_discards_reasoning_before_unmatched_closing_tags():
    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    provider.reasoning_key = "reasoning_content"
    closing_tag = "</" + "thinking>"
    completion = ChatCompletion.model_validate(
        {
            "id": "unmatched-reasoning-tags",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"Draft one{closing_tag}"
                            f"Draft two\n{closing_tag}"
                            "Final answer"
                        ),
                    },
                }
            ],
        }
    )

    response = await provider._parse_openai_completion(completion, None)

    assert response.completion_text == "Final answer"
    assert response.reasoning_content == (
        f"Draft one{closing_tag}Draft two\n{closing_tag}"
    )


def test_openai_discards_reasoning_tags_split_across_stream_chunks():
    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    state = [False, ""]
    chunks = [
        "Visible <thi",
        "nking>hidden</thi",
        "nking> answer",
    ]

    visible = "".join(provider._strip_stream_reasoning(chunk, state) for chunk in chunks)

    assert visible == "Visible  answer"
    assert state == [False, ""]
