from types import SimpleNamespace

from astrbot.core.agent.llm_types import TokenUsage
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic


def _provider() -> ProviderAnthropic:
    return ProviderAnthropic.__new__(ProviderAnthropic)


def test_anthropic_extract_usage_counts_cache_creation_input():
    provider = _provider()

    usage = provider._extract_usage(
        SimpleNamespace(
            input_tokens=10,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=50,
            output_tokens=20,
        )
    )

    assert usage.input_other == 60
    assert usage.input_cached == 100
    assert usage.input == 160
    assert usage.output == 20


def test_anthropic_extract_usage_without_cache_breakpoints():
    provider = _provider()

    usage = provider._extract_usage(
        SimpleNamespace(
            input_tokens=30,
            cache_read_input_tokens=None,
            cache_creation_input_tokens=None,
            output_tokens=10,
        )
    )

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
        SimpleNamespace(
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

    provider._update_usage(
        token_usage,
        SimpleNamespace(
            input_tokens=None,
            cache_read_input_tokens=None,
            cache_creation_input_tokens=None,
            output_tokens=7,
        ),
    )

    assert token_usage.input_other == 5
    assert token_usage.input_cached == 0
    assert token_usage.output == 7


def test_anthropic_update_usage_zero_cache_creation_keeps_input_tokens():
    provider = _provider()
    token_usage = TokenUsage()

    provider._update_usage(
        token_usage,
        SimpleNamespace(
            input_tokens=12,
            cache_read_input_tokens=3,
            cache_creation_input_tokens=0,
            output_tokens=4,
        ),
    )

    assert token_usage.input_other == 12
    assert token_usage.input_cached == 3
    assert token_usage.output == 4
