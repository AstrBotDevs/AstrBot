"""Stable codes for failed model requests, used by ChatUI error cards."""

import pytest

from astrbot.core.llm_error_messages import classify_provider_failure


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            "All chat models failed: AuthenticationError: Error code: 401 - "
            "{'error': {'message': 'Incorrect API key provided'}}",
            "providerAuth",
        ),
        (
            "All chat models failed: PermissionDeniedError: Error code: 403",
            "providerAuth",
        ),
        ("401 UNAUTHENTICATED. API key not valid.", "providerAuth"),
        (
            "All chat models failed: RateLimitError: Error code: 429 - "
            "{'error': {'code': 'insufficient_quota'}}",
            "providerRateLimit",
        ),
        ("429 RESOURCE_EXHAUSTED. Quota exceeded.", "providerRateLimit"),
        (
            "All chat models failed: BadRequestError: Error code: 400 - "
            "Function tools with reasoning_effort are not supported for gpt-5 "
            "in /v1/chat/completions. Please use /v1/responses instead.",
            "providerToolsRequireResponses",
        ),
        (
            "All chat models failed: NotFoundError: Error code: 404 - "
            "The model `gpt-x` does not exist",
            "providerModelNotFound",
        ),
        # A wrong base URL on a Responses provider is not a tools problem.
        (
            "All chat models failed: NotFoundError: Error code: 404 - "
            "Invalid URL (POST /v1/responses)",
            "providerModelNotFound",
        ),
        # Failures without a specific user action keep the generic code.
        (
            "All chat models failed: APIConnectionError: Connection error.",
            "provider_error",
        ),
        ("All chat models failed: BadRequestError: Error code: 4013", "provider_error"),
        (
            "All chat models failed: FileNotFoundError: [Errno 2] "
            "No such file or directory: 'data/temp/x.jpg'",
            "provider_error",
        ),
        ("All available chat models are unavailable.", "provider_error"),
        ("", "provider_error"),
    ],
)
def test_failed_requests_get_a_stable_code(text, code):
    assert classify_provider_failure(text) == code
