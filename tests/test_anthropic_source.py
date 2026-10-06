from anthropic.types import MessageDeltaUsage, Usage

from astrbot.core.provider.entities import TokenUsage
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic


def _provider() -> ProviderAnthropic:
    return ProviderAnthropic.__new__(ProviderAnthropic)


def test_anthropic_extract_usage_counts_cache_creation_input():
    provider = _provider()

    usage = provider._extract_usage(
        Usage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        )
    )

    # Anthropic's input_tokens excludes cache writes, so cache_creation
    # must be folded into input_other to keep total input accurate.
    assert usage.input_other == 60
    assert usage.input_cached == 100
    assert usage.input == 160
    assert usage.output == 20


def test_anthropic_extract_usage_without_cache_breakpoints():
    provider = _provider()

    usage = provider._extract_usage(Usage(input_tokens=30, output_tokens=10))

    assert usage.input_other == 30
    assert usage.input_cached == 0
    assert usage.input == 30
    assert usage.output == 10


def test_anthropic_extract_usage_none_returns_empty():
    provider = _provider()

    assert provider._extract_usage(None) == TokenUsage()


def test_anthropic_update_usage_counts_cache_creation_input():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    provider._update_usage(
        token_usage,
        MessageDeltaUsage(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        ),
    )

    assert token_usage.input_other == 60
    assert token_usage.input_cached == 100
    assert token_usage.input == 160
    assert token_usage.output == 20


def test_anthropic_update_usage_omitted_fields_are_preserved():
    provider = _provider()
    token_usage = TokenUsage(input_other=5, input_cached=0, output=0)

    # message_delta usage only carries output tokens in practice.
    provider._update_usage(token_usage, MessageDeltaUsage(output_tokens=7))

    assert token_usage.input_other == 5
    assert token_usage.input_cached == 0
    assert token_usage.output == 7


def test_anthropic_prepare_payload_keeps_all_system_messages():
    provider = _provider()

    system_prompt, messages = provider._prepare_payload(
        [
            {"role": "system", "content": "You are Aria."},
            {"role": "system", "content": "File Extract Results: report.pdf"},
            {"role": "user", "content": "Summarize the file."},
        ]
    )

    assert system_prompt == [
        {"type": "text", "text": "You are Aria."},
        {"type": "text", "text": "File Extract Results: report.pdf"},
    ]
    assert messages == [{"role": "user", "content": "Summarize the file."}]


def test_anthropic_prepare_payload_keeps_list_system_blocks():
    provider = _provider()
    persona_blocks = [
        {"type": "text", "text": "Persona block."},
        {"type": "text", "text": "Style guide."},
    ]

    system_prompt, _ = provider._prepare_payload(
        [
            {"role": "system", "content": persona_blocks},
            {"role": "system", "content": "File Extract Results: report.pdf"},
            {"role": "user", "content": "Summarize the file."},
        ]
    )

    assert system_prompt == [
        *persona_blocks,
        {"type": "text", "text": "File Extract Results: report.pdf"},
    ]
