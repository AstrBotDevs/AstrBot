import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)


class _DummyError(Exception):
    def __init__(self, message: str, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _provider() -> ProviderOpenAIResponses:
    return ProviderOpenAIResponses.__new__(ProviderOpenAIResponses)


def test_is_retryable_upstream_error_with_5xx_status():
    err = _DummyError("server error", status_code=502)

    assert _provider()._is_retryable_upstream_error(err)


def test_is_retryable_upstream_error_with_upstream_error_type():
    err = _DummyError(
        "bad gateway",
        status_code=400,
        body={"error": {"type": "upstream_error"}},
    )

    assert _provider()._is_retryable_upstream_error(err)


def test_is_retryable_upstream_error_returns_false_for_non_retryable_error():
    err = _DummyError(
        "invalid request",
        status_code=400,
        body={"error": {"type": "invalid_request_error"}},
    )

    assert not _provider()._is_retryable_upstream_error(err)


def test_build_responses_input_and_instructions_moves_system_messages():
    provider = _provider()
    provider.custom_headers = {}

    response_input, instructions = provider._build_responses_input_and_instructions(
        [
            {"role": "system", "content": "sys text"},
            {"role": "developer", "content": [{"type": "text", "text": "dev text"}]},
            {"role": "user", "content": "hello"},
        ]
    )

    assert instructions == "sys text\n\ndev text"
    assert all(
        item.get("role") not in {"system", "developer"} for item in response_input
    )
    assert any(item.get("role") == "user" for item in response_input)


def test_build_extra_headers_keeps_custom_headers_and_ignores_authorization():
    provider = _provider()
    provider.custom_headers = {
        "X-Test": "value",
        "Authorization": "Bearer should-not-pass",
    }

    headers = provider._build_extra_headers()

    assert "User-Agent" not in headers
    assert headers["X-Test"] == "value"
    assert "Authorization" not in headers
