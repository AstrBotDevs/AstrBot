"""Privacy and fallback tests for concise image-description diagnostics."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import test_image_description as caption_tests

from astrbot.core.image_description import describe_images
from astrbot.core.provider.entities import LLMResponse, TokenUsage

SECRET_ID = "caption-occurrence-secret-572b"
SECRET_TEXT = "caption-response-secret-46ce"
SECRET_ERROR = "sdk-exception-secret-712a"
NOTICE = "Image description failed; previous observations were preserved and no repair call was made."


@pytest.fixture
def setup_caption(tmp_path):
    """Reuse the established image-description fixture."""
    return caption_tests.setup_caption.__wrapped__(tmp_path)


def _use_private_single_image(turn):
    """Replace fixture IDs with a recognizable value for leak checks."""
    refs = turn.references
    ref = refs.pop("a")
    refs.pop("b")
    ref.occurrence_id = SECRET_ID
    refs[SECRET_ID] = ref
    preview = turn.pending_visuals.pop("a")
    turn.pending_visuals.pop("b")
    turn.pending_visuals[SECRET_ID] = preview
    return ref


def _render_calls(mock):
    """Render structured logger calls for assertions."""
    rendered = []
    for call in mock.call_args_list:
        if not call.args:
            continue
        template, *args = call.args
        rendered.append(template % tuple(args) if args else template)
    return "\n".join(rendered)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "stage", "diagnostic"),
    [
        ("not-json-" + SECRET_TEXT, "json_parse", "json_line=1 json_column=1"),
        ("", "json_parse", "json_line=1 json_column=1"),
        ('{"images":[]}', "image_count_validation", "reason=image_count_mismatch"),
        (
            '{"images":[],"private":"value"}',
            "envelope_validation",
            "reason=invalid_envelope",
        ),
    ],
)
async def test_failure_logs_only_stage_type_and_safe_location_or_reason(
    setup_caption, monkeypatch, content, stage, diagnostic
):
    turn, provider = setup_caption
    ref = _use_private_single_image(turn)
    ref.description = "previous private observation"
    ref.description_status = "ready"
    provider.response = LLMResponse(
        role="assistant",
        completion_text=content,
        reasoning_content=SECRET_TEXT,
        usage=TokenUsage(input_other=1),
    )
    warning = MagicMock()
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )

    result = await describe_images(
        turn, provider, occurrence_ids=[SECRET_ID], refresh=True
    )

    log_text = _render_calls(warning)
    assert result is None
    assert NOTICE in turn.notices
    assert ref.description == "previous private observation"
    assert ref.description_version == 0
    assert provider.calls == 1
    assert f"stage={stage}" in log_text
    assert "error_type=" in log_text
    assert diagnostic in log_text
    assert SECRET_ID not in log_text
    assert SECRET_TEXT not in log_text
    assert "response_chars=" not in log_text
    assert "reasoning_chars=" not in log_text
    assert "Traceback" not in log_text


@pytest.mark.asyncio
async def test_provider_exception_log_does_not_include_exception_text(
    setup_caption, monkeypatch
):
    turn, provider = setup_caption
    ref = _use_private_single_image(turn)
    ref.description = "previous private observation"
    ref.description_status = "ready"
    provider.response = RuntimeError(f"{SECRET_ERROR} {SECRET_ID} {SECRET_TEXT}")
    warning = MagicMock()
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )

    result = await describe_images(
        turn, provider, occurrence_ids=[SECRET_ID], refresh=True
    )

    log_text = _render_calls(warning)
    assert result is None
    assert NOTICE in turn.notices
    assert "stage=provider_request" in log_text
    assert "error_type=RuntimeError" in log_text
    assert SECRET_ERROR not in log_text
    assert SECRET_ID not in log_text
    assert SECRET_TEXT not in log_text
    assert ref.description == "previous private observation"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_debug_environment_does_not_enable_payload_logging(
    setup_caption, monkeypatch
):
    turn, provider = setup_caption
    _use_private_single_image(turn)
    monkeypatch.setenv("ASTRBOT_IMAGE_DESCRIPTION_DEBUG", "1")
    provider.response = LLMResponse(
        role="assistant",
        completion_text=f"invalid {SECRET_TEXT}",
        usage=TokenUsage(input_other=1),
    )
    warning = MagicMock()
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )

    await describe_images(turn, provider, occurrence_ids=[SECRET_ID], refresh=True)

    log_text = _render_calls(warning)
    assert warning.call_count == 1
    assert "stage=json_parse" in log_text
    assert SECRET_TEXT not in log_text
    assert SECRET_ID not in log_text
    assert "Traceback" not in log_text


@pytest.mark.asyncio
async def test_logger_failure_does_not_break_fallback(setup_caption, monkeypatch):
    turn, provider = setup_caption
    ref = _use_private_single_image(turn)
    ref.description = "previous private observation"
    ref.description_status = "ready"
    provider.response = LLMResponse(role="assistant", completion_text="not JSON")
    warning = MagicMock(side_effect=RuntimeError(SECRET_ERROR))
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )

    result = await describe_images(
        turn, provider, occurrence_ids=[SECRET_ID], refresh=True
    )

    assert result is None
    assert NOTICE in turn.notices
    assert provider.calls == 1
    assert ref.description == "previous private observation"
    assert ref.description_status == "ready"
    assert ref.description_version == 0
    turn.db.update_image_description.assert_not_awaited()
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_success_does_not_emit_failure_warning(setup_caption, monkeypatch):
    turn, provider = setup_caption
    provider.response = LLMResponse(
        role="assistant",
        completion_text=json.dumps(
            {"images": [{"image_id": "a", "description": "visible shape"}]}
        ),
        usage=TokenUsage(input_other=1),
    )
    warning = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "error", error
    )

    await describe_images(turn, provider, occurrence_ids=["a"])

    warning.assert_not_called()
    error.assert_not_called()
    assert turn.references["a"].description == "visible shape"


@pytest.mark.asyncio
async def test_provider_exception_is_not_stringified(setup_caption, monkeypatch):
    turn, provider = setup_caption

    class ProviderFailure(RuntimeError):
        def __str__(self):
            raise AssertionError("Provider errors must not be formatted")

    provider.response = ProviderFailure()
    warning = MagicMock()
    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"], "warning", warning
    )
    assert await describe_images(turn, provider, occurrence_ids=["a"]) is None
    assert provider.calls == 1
    assert "error_type=ProviderFailure" in _render_calls(warning)
    warning.assert_called_once()
