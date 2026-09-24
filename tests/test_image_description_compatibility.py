"""Safe compatibility parsing for common caption-model response wrappers."""

import json

import pytest
import test_image_description as caption_tests

from astrbot.core.image_description import _parse_description_response, describe_images
from astrbot.core.provider.entities import LLMResponse, TokenUsage

SECRET_ID = "caption-compat-occurrence-secret-3c0a"
SECRET_RESPONSE = "caption-compat-response-secret-6b41"
SECRET_ERROR = "caption-compat-error-secret-2fa1"
PREVIOUS_DESCRIPTION = "previous private observation"
NOTICE = "Image description failed; previous observations were preserved and no repair call was made."


@pytest.fixture
def setup_caption(tmp_path):
    """Reuse the deterministic caption provider and image setup."""
    return caption_tests.setup_caption.__wrapped__(tmp_path)


def _single_private_image(turn):
    ref = turn.references.pop("a")
    turn.references.pop("b")
    ref.occurrence_id = SECRET_ID
    turn.references[SECRET_ID] = ref
    preview = turn.pending_visuals.pop("a")
    turn.pending_visuals.pop("b")
    turn.pending_visuals[SECRET_ID] = preview
    return ref


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            '\ufeffObservation:\n```json\n{"images":[{"image_id":"a","description":"shape"}]}\n```',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            '```\n{"images":[{"image_id":"a","description":"shape"}]}\n```',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            '{"images":[{"image_id":"a","description":"shape"}]} }}] \n',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
    ],
)
def test_parser_accepts_common_wrappers_and_one_unambiguous_json(text, expected):
    assert _parse_description_response(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        '{"images":[{"image_id":"a","description":"first","description":"second"}]}',
        '{"images":[]}\nCandidate 2: {"images":[]}',
        'Model wrapper: {"candidate": broken {"images":[]}',
        '```json\n{"images":[]}\n',
        '```python\n{"images":[]}\n```',
        "Plain caption text without a JSON envelope.",
    ],
)
def test_parser_rejects_ambiguous_or_malformed_wrappers(text):
    with pytest.raises(ValueError):
        _parse_description_response(text)


@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_parser_accepts_common_raw_line_breaks_inside_json_strings(control):
    raw_object = (
        '{"images":[{"image_id":"a","description":"before' + control + 'after"}]}'
    )
    assert _parse_description_response(raw_object)["images"][0]["description"] == (
        f"before{control}after"
    )


def test_parser_rejects_other_raw_control_characters():
    valid_object = '{"images":[{"image_id":"a","description":"shape"}]}'
    with pytest.raises(ValueError):
        _parse_description_response(valid_object.replace("shape", "before\x01after"))
    with pytest.raises(ValueError):
        _parse_description_response("\x01" + valid_object)
    with pytest.raises(ValueError):
        _parse_description_response(valid_object + "\x01")


def test_parser_keeps_structural_text_inside_description():
    description = 'text contains ] } [ { and "quotes" plus ``` marks'
    text = json.dumps({"images": [{"image_id": "a", "description": description}]})

    assert _parse_description_response(text)["images"][0]["description"] == description


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "provider_error"),
    [
        (
            '{"images":[{"image_id":"a","description":"first","description":"second"}]}',
            False,
        ),
        ("Plain caption text " + SECRET_RESPONSE, False),
        (
            json.dumps(
                {
                    "images": [
                        {"image_id": "wrong-private-image-id", "description": "shape"}
                    ]
                }
            ),
            False,
        ),
        (None, True),
    ],
)
async def test_failed_outputs_preserve_description_and_log_no_payload(
    setup_caption, monkeypatch, content, provider_error
):
    turn, provider = setup_caption
    ref = _single_private_image(turn)
    ref.description = PREVIOUS_DESCRIPTION
    ref.description_status = "ready"
    if provider_error:
        provider.response = RuntimeError(
            f"{SECRET_ERROR} {SECRET_ID} {SECRET_RESPONSE}"
        )
    else:
        provider.response = LLMResponse(
            role="assistant",
            completion_text=content,
            reasoning_content=SECRET_RESPONSE,
            usage=TokenUsage(input_other=3),
        )
    warning = []

    def capture_warning(template, *args):
        warning.append(template % args if args else template)

    monkeypatch.setattr(
        caption_tests.describe_images.__globals__["logger"],
        "warning",
        capture_warning,
    )
    result = await describe_images(
        turn, provider, occurrence_ids=[SECRET_ID], refresh=True
    )

    log_text = "\n".join(warning)
    assert result is None
    assert NOTICE in turn.notices
    assert provider.calls == 1
    assert ref.description == PREVIOUS_DESCRIPTION
    assert ref.description_status == "ready"
    assert ref.description_version == 0
    turn.db.update_image_description.assert_not_awaited()
    for private_value in (
        SECRET_ID,
        SECRET_RESPONSE,
        SECRET_ERROR,
        "wrong-private-image-id",
    ):
        assert private_value not in log_text


@pytest.mark.asyncio
async def test_wrapped_response_updates_current_description_once(setup_caption):
    turn, provider = setup_caption
    ref = turn.references["a"]
    provider.response = LLMResponse(
        role="assistant",
        completion_text=(
            "\ufeffObservation:\n```json\n"
            + json.dumps({"images": [{"image_id": "a", "description": "a blue chair"}]})
            + "\n```"
        ),
        usage=TokenUsage(input_other=3),
    )

    assert await describe_images(turn, provider, occurrence_ids=["a"]) is None
    assert ref.description == "a blue chair"
    assert ref.description_status == "ready"
    assert ref.description_version == 1
    assert provider.calls == 1
    turn.db.update_image_description.assert_not_awaited()
