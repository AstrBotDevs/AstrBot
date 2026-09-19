"""Error text reaching logs and the dashboard must not carry credentials."""

import pytest

from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error


@pytest.mark.parametrize(
    "key",
    [
        "sk-abcdefghijklmnopqrstuvwxyz012345",  # legacy OpenAI
        "sk-proj-abcdefghijklmnopqrstuvwxyz012345",  # project keys
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",  # Anthropic
        "sk-1234567890abcdef_-1234567890",  # dashsk-_ bodies
    ],
)
def test_vendor_keys_are_redacted(key: str) -> None:
    redacted = redact_sensitive_text(f"401 Incorrect API key provided: {key}")

    assert key not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize(
    "message",
    [
        'api_key="supersecretvalue"',
        "api_key=supersecretvalue&model=x",
        "https://example.com/v1?key=supersecretvalue",
        "Authorization: Bearer abcdefghijklmnop",
        "bearer abcdefghijklmnop",
        'authorization: "Bearer abcdefghijklmnop"',
    ],
)
def test_named_credentials_are_redacted(message: str) -> None:
    redacted = redact_sensitive_text(message)

    assert "supersecretvalue" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "[REDACTED]" in redacted


def test_short_placeholders_are_left_alone() -> None:
    """A short stand-in is not a credential and should stay readable in logs."""
    message = "using access_token=sk-test for the sandbox"

    assert (
        redact_sensitive_text(message)
        == "using access_token=[REDACTED] for the sandbox"
    )


def test_safe_error_keeps_the_prefix_and_redacts_the_body() -> None:
    assert (
        safe_error(
            "request failed: ",
            Exception(
                "401 Incorrect API key provided: sk-proj-abcdefghijklmnopqrstuvwxyz012345"
            ),
        )
        == "request failed: 401 Incorrect API key provided: [REDACTED]"
    )


def test_safe_error_can_be_asked_not_to_redact() -> None:
    assert safe_error("", "api_key=supersecretvalue", redact=False) == (
        "api_key=supersecretvalue"
    )
