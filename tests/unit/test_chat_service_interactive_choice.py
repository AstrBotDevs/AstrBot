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


# ---------------------------------------------------------------------------
# Bug fix: ask_user_choice tool_call / tool_call_result must not produce a
# tool_call part. The interactive_choice part already represents the same
# invocation; persisting both causes a duplicate "tool" entry to render next
# to the InteractiveChoiceBox after a hard refresh.
#
# Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
# (Amendment F: skip ask_user_choice in BotMessageAccumulator)
# ---------------------------------------------------------------------------


ASK_USER_CHOICE_NAME = "ask_user_choice"


def _tool_call_envelope(
    call_id: str,
    name: str = ASK_USER_CHOICE_NAME,
    args: dict | None = None,
    ts: float = 1.0,
) -> str:
    return json.dumps(
        {
            "id": call_id,
            "name": name,
            "args": args if args is not None else {"prompt": "Pick one"},
            "ts": ts,
        },
        ensure_ascii=False,
    )


def _tool_call_result_envelope(
    call_id: str,
    result: str,
    ts: float = 2.0,
) -> str:
    return json.dumps(
        {"id": call_id, "ts": ts, "result": result},
        ensure_ascii=False,
    )


def test_tool_call_for_ask_user_choice_is_skipped() -> None:
    """A `tool_call` event for ask_user_choice must NOT append a tool_call part."""
    accumulator = BotMessageAccumulator()

    accumulator.add_plain(
        _tool_call_envelope("call-abc"),
        chain_type="tool_call",
        streaming=False,
    )

    assert accumulator.build_message_parts() == []


def test_tool_call_result_for_ask_user_choice_is_skipped() -> None:
    """The matching `tool_call_result` for a skipped ask_user_choice call
    must not fall back to creating a tool_call part (the call was filtered,
    so there is no pending entry to attach to)."""
    accumulator = BotMessageAccumulator()

    # tool_call arrives first (filtered)
    accumulator.add_plain(
        _tool_call_envelope("call-abc"),
        chain_type="tool_call",
        streaming=False,
    )
    # tool_call_result arrives (no pending entry → fallback would create
    # a tool_call part with only {id, result, finished_ts}; we must NOT do
    # that for ask_user_choice)
    accumulator.add_plain(
        _tool_call_result_envelope("call-abc", "User selected: A (id=A)"),
        chain_type="tool_call_result",
        streaming=False,
    )

    assert accumulator.build_message_parts() == []


def test_tool_call_for_other_tool_still_persists() -> None:
    """Regression guard: the skip filter must not affect other tool names."""
    accumulator = BotMessageAccumulator()

    accumulator.add_plain(
        _tool_call_envelope("call-xyz", name="astrbot_file_read_tool"),
        chain_type="tool_call",
        streaming=False,
    )
    accumulator.add_plain(
        _tool_call_result_envelope("call-xyz", "file contents"),
        chain_type="tool_call_result",
        streaming=False,
    )

    [part] = accumulator.build_message_parts()
    assert part["type"] == "tool_call"
    assert part["tool_calls"][0]["name"] == "astrbot_file_read_tool"
    assert part["tool_calls"][0]["id"] == "call-xyz"
    assert part["tool_calls"][0]["result"] == "file contents"


def test_interactive_choice_and_ask_user_choice_tool_call_yield_only_interactive_part() -> None:
    """End-to-end: emitting both the tool_call + tool_call_result for
    ask_user_choice AND the interactive_choice chain_type should yield
    a single `interactive_choice` part — the InteractiveChoiceBox is the
    sole user-visible representation."""
    accumulator = BotMessageAccumulator()

    # The LLM runtime emits tool_call (filtered by name)
    accumulator.add_plain(
        _tool_call_envelope("call-abc"),
        chain_type="tool_call",
        streaming=False,
    )
    # The LLM runtime emits tool_call_result (filtered, paired with the
    # skipped tool_call)
    accumulator.add_plain(
        _tool_call_result_envelope("call-abc", "User selected: A (id=A)"),
        chain_type="tool_call_result",
        streaming=False,
    )
    # The plugin emits the interactive_choice chain_type
    accumulator.add_plain(
        _envelope(request_id="req-1"),
        chain_type="interactive_choice",
        streaming=False,
    )

    parts = accumulator.build_message_parts()
    assert len(parts) == 1
    assert parts[0]["type"] == "interactive_choice"
    assert parts[0]["request_id"] == "req-1"
