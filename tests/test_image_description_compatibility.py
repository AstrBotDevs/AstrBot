"""Safe compatibility parsing for common caption-model response wrappers."""

import json

import pytest
import test_image_description as caption_tests

from astrbot.core.image_description import (
    _parse_description_response,
    describe_images,
)
from astrbot.core.provider.entities import LLMResponse, TokenUsage

SECRET_ID = "caption-compat-occurrence-secret-3c0a"
SECRET_RESPONSE = "caption-compat-response-secret-6b41"
PREVIOUS_DESCRIPTION = "previous private observation"
NOTICE = "Image description failed; previous observations were preserved and no repair call was made."
NON_JSON_C0_CONTROLS = tuple(
    chr(value) for value in range(0x20) if value not in {0x09, 0x0A, 0x0D}
)


@pytest.fixture
def setup_caption(tmp_path):
    """Reuse the existing deterministic caption provider and image setup."""
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
            '\ufeff  {"images": [{"image_id": "a", "description": "shape"}]}  ',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            'The visual result follows:\n```JSON\n{"images": [{"image_id": "a", "description": "shape"}]}\n```\nThat is all.',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            '```\n{"images": [{"image_id": "a", "description": "shape"}]}\n```',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            '{"images": [{"image_id": "a", "description": "shape"}]} }]] \n\t',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            '```json\n{"images": [{"image_id": "a", "description": "shape"}]} }]] \n```',
            {"images": [{"image_id": "a", "description": "shape"}]},
        ),
        (
            "```json\n"
            + json.dumps(
                {
                    "images": [
                        {
                            "image_id": "a",
                            "description": 'text contains ] } [ { and "quotes" plus ``` marks',
                        }
                    ]
                }
            )
            + "\n```",
            {
                "images": [
                    {
                        "image_id": "a",
                        "description": 'text contains ] } [ { and "quotes" plus ``` marks',
                    }
                ]
            },
        ),
    ],
)
def test_parser_accepts_unambiguous_bom_fence_and_explanation_wrappers(text, expected):
    assert _parse_description_response(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        '{"images":[{"image_id":"a","description":"first","description":"second"}]}',
        '{"images":[{"image_id":"a","description":"one"}]}\n'
        'Candidate 2: {"images":[{"image_id":"a","description":"two"}]}',
        'Model wrapper: {"candidate": broken '
        '{"images":[{"image_id":"a","description":"shape"}]}',
        '```json\n{"images":[]}\n',
        '```json\n{"images":[]}\n```\n```json\n{"images":[]}\n```',
        '```python\n{"images":[]}\n```',
        '{"images":[],"images":[]}',
        '["malformed outer", {"images":[{"image_id":"a","description":"shape"}]',
        '[image 1] {"images":[]}',
        '{"images":[{"image_id":"a","description":"shape"}]} }} trailing text',
        '```json\n{"images":[{"image_id":"a","description":"shape"}]} }}\nnot-json\n```',
        '```json\n{"images":[{"image_id":"a","description":"shape"}]}\n``` }}',
        "Plain caption text without a JSON envelope.",
    ],
)
def test_parser_rejects_ambiguous_or_malformed_wrappers(text):
    with pytest.raises(ValueError):
        _parse_description_response(text)


@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
def test_parser_accepts_lf_cr_tab_inside_json_strings_with_wrappers(control):
    description = f"before{control}after"
    raw_object = (
        '{"images":[{"image_id":"a","description":"before' + control + 'after"}]}'
    )
    expected = {"images": [{"image_id": "a", "description": description}]}

    assert _parse_description_response(raw_object) == expected
    assert _parse_description_response(f"```json\n{raw_object} }} \n```") == expected


@pytest.mark.parametrize("control", NON_JSON_C0_CONTROLS)
def test_parser_rejects_other_c0_controls_inside_and_around_json(control):
    valid_object = '{"images":[{"image_id":"a","description":"shape"}]}'
    candidates = (
        '{"images":[{"image_id":"a","description":"before' + control + 'after"}]}',
        control + valid_object,
        valid_object + control,
    )

    for candidate in candidates:
        with pytest.raises(ValueError):
            _parse_description_response(candidate)


def test_parser_preserves_escaped_control_characters_and_quotes():
    description = 'quote " slash \\ bracket [] {} line\nnext\rreturn\ttab'
    raw_object = json.dumps({"images": [{"image_id": "a", "description": description}]})

    assert _parse_description_response(raw_object) == {
        "images": [{"image_id": "a", "description": description}]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"images":[{"image_id":"a","description":"first","description":"second"}]}',
        '{"images":[{"image_id":"a","description":"one"}]}\n'
        'Candidate 2: {"images":[{"image_id":"a","description":"two"}]}',
        'Model wrapper: {"candidate": broken '
        '{"images":[{"image_id":"a","description":"shape"}]}',
        "Plain caption text " + SECRET_RESPONSE,
        json.dumps(
            {"images": [{"image_id": "wrong-private-image-id", "description": "shape"}]}
        )
        + " }}} \n",
    ],
)
async def test_invalid_compatibility_outputs_preserve_description_and_log_no_payload(
    setup_caption, monkeypatch, content
):
    turn, provider = setup_caption
    ref = _single_private_image(turn)
    ref.description = PREVIOUS_DESCRIPTION
    ref.description_status = "ready"
    response = LLMResponse(
        role="assistant",
        completion_text=content,
        reasoning_content=SECRET_RESPONSE,
        usage=TokenUsage(input_other=3),
    )
    provider.response = response
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
    for private_value in (SECRET_ID, SECRET_RESPONSE, "wrong-private-image-id"):
        assert private_value not in log_text


@pytest.mark.asyncio
async def test_wrapped_response_updates_one_current_description_once(setup_caption):
    turn, provider = setup_caption
    ref = turn.references["a"]
    provider.response = LLMResponse(
        role="assistant",
        completion_text=(
            "\ufeffObservation:\n```json\n"
            + json.dumps({"images": [{"image_id": "a", "description": "a blue chair"}]})
            + "\n```\nThe observation is complete."
        ),
        usage=TokenUsage(input_other=3),
    )

    result = await describe_images(turn, provider, occurrence_ids=["a"])

    assert result is None
    assert ref.description == "a blue chair"
    assert ref.description_status == "ready"
    assert ref.description_version == 1
    assert provider.calls == 1
    turn.db.update_image_description.assert_not_awaited()


@pytest.mark.asyncio
async def test_surplus_closers_after_unique_json_still_update_once(setup_caption):
    turn, provider = setup_caption
    ref = turn.references["a"]
    provider.response = LLMResponse(
        role="assistant",
        completion_text=(
            '{"images":[{"image_id":"a","description":"verified"}]} }}] \n'
        ),
        usage=TokenUsage(input_other=2),
    )

    result = await describe_images(turn, provider, occurrence_ids=["a"])

    assert result is None
    assert ref.description == "verified"
    assert ref.description_status == "ready"
    assert ref.description_version == 1
    assert provider.calls == 1
    turn.db.update_image_description.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["\n", "\r", "\t"])
async def test_describe_images_accepts_raw_lf_cr_tab_and_updates_ready_once(
    setup_caption, control
):
    turn, provider = setup_caption
    ref = turn.references["a"]
    description = f"first line{control}second line"
    raw_response = (
        '```json\n{"images":[{"image_id":"a","description":"first line'
        + control
        + 'second line"}]} }}\n```'
    )
    provider.response = LLMResponse(
        role="assistant",
        completion_text=raw_response,
        usage=TokenUsage(input_other=2),
    )

    result = await describe_images(turn, provider, occurrence_ids=["a"])

    assert result is None
    assert ref.description == description
    assert ref.description_status == "ready"
    assert ref.description_version == 1
    assert provider.calls == 1
    turn.db.update_image_description.assert_not_awaited()
