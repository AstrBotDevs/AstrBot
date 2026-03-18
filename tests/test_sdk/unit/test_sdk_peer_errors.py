from __future__ import annotations

import pytest
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.messages import ErrorPayload, ResultMessage

pytestmark = pytest.mark.unit


def test_error_payload_accepts_docs_url_and_details() -> None:
    payload = ErrorPayload.model_validate(
        AstrBotError.invalid_input(
            "bad input",
            docs_url="https://docs.astrbot.org/sdk/errors#invalid-input",
            details={"field": "name"},
        ).to_payload()
    )

    assert payload.docs_url == "https://docs.astrbot.org/sdk/errors#invalid-input"
    assert payload.details == {"field": "name"}


def test_failed_result_round_trip_preserves_error_metadata() -> None:
    error = AstrBotError.internal_error(
        "boom",
        hint="try again later",
        docs_url="https://docs.astrbot.org/sdk/errors#internal-error",
        details={"phase": "invoke"},
    )
    message = ResultMessage(
        id="req-1",
        success=False,
        error=ErrorPayload.model_validate(error.to_payload()),
    )

    restored = AstrBotError.from_payload(message.error.model_dump() if message.error else {})

    assert restored.code == error.code
    assert restored.message == error.message
    assert restored.hint == error.hint
    assert restored.docs_url == error.docs_url
    assert restored.details == error.details
