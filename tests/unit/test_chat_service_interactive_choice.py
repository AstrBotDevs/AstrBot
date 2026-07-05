"""Unit tests for ``BotMessageAccumulator._store_interactive_choice``.

Author: elecvoid243
Date: 2026-07-05
Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md §5.1
"""

from __future__ import annotations

import json

from astrbot.dashboard.services.chat_service import BotMessageAccumulator


def _envelope(
    request_id: str = "req-1",
    prompt: str = "Pick one",
    options: list[dict] | None = None,
    title: str | None = None,
    input_placeholder: str | None = None,
    expires_at: int | float | None = None,
) -> str:
    """Build a JSON string that mirrors the plugin's wire payload."""
    if options is None:
        options = [
            {"id": "A", "label": "alpha"},
            {"id": "B", "label": "beta"},
        ]
    spec: dict = {
        "type": "interactive_choice",
        "prompt": prompt,
        "options": options,
    }
    if title is not None:
        spec["title"] = title
    if input_placeholder is not None:
        spec["input_placeholder"] = input_placeholder
    payload: dict = {"request_id": request_id, "spec": spec}
    if expires_at is not None:
        payload["expires_at"] = expires_at
    return json.dumps(payload, ensure_ascii=False)


def test_store_interactive_choice_appends_valid_part() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope(
        request_id="req-1",
        title="Color",
        input_placeholder="Type freely",
        expires_at=1700000000,
    )

    accumulator._store_interactive_choice(result_text)

    parts = accumulator.build_message_parts()
    assert len(parts) == 1
    part = parts[0]
    assert part["type"] == "interactive_choice"
    assert part["request_id"] == "req-1"
    assert part["prompt"] == "Pick one"
    assert part["options"] == [
        {"id": "A", "label": "alpha"},
        {"id": "B", "label": "beta"},
    ]
    assert part["title"] == "Color"
    assert part["input_placeholder"] == "Type freely"
    assert part["expires_at"] == 1700000000


def test_store_interactive_choice_omits_optional_fields() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope()

    accumulator._store_interactive_choice(result_text)

    [part] = accumulator.build_message_parts()
    assert part == {
        "type": "interactive_choice",
        "request_id": "req-1",
        "prompt": "Pick one",
        "options": [
            {"id": "A", "label": "alpha"},
            {"id": "B", "label": "beta"},
        ],
    }


def test_store_interactive_choice_drops_blank_optional_strings() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope(title="   ", input_placeholder="")

    accumulator._store_interactive_choice(result_text)

    [part] = accumulator.build_message_parts()
    assert "title" not in part
    assert "input_placeholder" not in part


def test_store_interactive_choice_rejects_invalid_json() -> None:
    accumulator = BotMessageAccumulator()

    accumulator._store_interactive_choice("not-json{")

    assert accumulator.build_message_parts() == []


def test_store_interactive_choice_rejects_missing_request_id() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope(request_id="   ")

    accumulator._store_interactive_choice(result_text)

    assert accumulator.build_message_parts() == []


def test_store_interactive_choice_rejects_missing_prompt() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope(prompt="   ")

    accumulator._store_interactive_choice(result_text)

    assert accumulator.build_message_parts() == []


def test_store_interactive_choice_rejects_non_list_options() -> None:
    accumulator = BotMessageAccumulator()
    # override via raw json to keep options as non-list
    payload = {
        "request_id": "req-1",
        "spec": {
            "type": "interactive_choice",
            "prompt": "Pick one",
            "options": "not-a-list",
        },
    }
    accumulator._store_interactive_choice(json.dumps(payload))

    assert accumulator.build_message_parts() == []


def test_store_interactive_choice_via_add_plain_dispatch() -> None:
    accumulator = BotMessageAccumulator()
    result_text = _envelope()

    accumulator.add_plain(
        result_text,
        chain_type="interactive_choice",
        streaming=False,
    )

    [part] = accumulator.build_message_parts()
    assert part["type"] == "interactive_choice"
    assert part["request_id"] == "req-1"


def test_add_plain_unknown_chain_type_falls_through_to_streaming() -> None:
    accumulator = BotMessageAccumulator()

    accumulator.add_plain(
        "hello",
        chain_type="unknown_type",
        streaming=False,
    )

    [part] = accumulator.build_message_parts()
    assert part == {"type": "plain", "text": "hello"}
