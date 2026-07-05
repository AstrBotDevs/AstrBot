"""Unit tests for the read-path ``ask_user_choice`` history sanitizer.

Author: elecvoid243
Date: 2026-07-05
Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
§2.2 Amendment F (read-path defence).

Why this file exists
--------------------
``BotMessageAccumulator._store_tool_call`` / ``_store_tool_call_result``
prevent NEW history rows from carrying two stale ``tool_call`` halves per
``ask_user_choice`` call. Rows persisted BEFORE that filter shipped — or
while an AstrBot process still had the old code loaded — already contain
the broken pair. A hard refresh then surfaces two phantom cards next to
the InteractiveChoiceBox.

``_sanitize_ask_user_choice_tool_call_parts`` is the read-path defence:
it strips both halves before the chat API returns history to the
dashboard. These tests pin the rules:

1. Any ``tool_call`` whose entry has ``name == "ask_user_choice"`` is
   dropped (call-args half; redundant with the ``interactive_choice``
   part written by the plugin's ``chain_type`` event).
2. Any paired anonymous result half (no ``name`` + has ``result``, same
   ``call_id`` as an ask_user_choice entry in the same message) is also
   dropped — that's the synthesised-fallback half.
3. Real tool calls (with a non-empty ``name``) are preserved.
4. Non-``tool_call`` parts (text, image, ``interactive_choice``, …) are
   preserved unchanged regardless of their content.
5. Malformed input (``None``, non-list, missing keys, …) never raises.
"""

from __future__ import annotations

from astrbot.dashboard.services.chat_service import (
    _sanitize_ask_user_choice_tool_call_parts,
    _sanitize_history_bot_records,
)


def _ask_args_part(call_id: str = "call-abc") -> dict:
    return {
        "type": "tool_call",
        "tool_calls": [
            {
                "id": call_id,
                "name": "ask_user_choice",
                "args": {"prompt": "Pick one"},
                "ts": 1.0,
            }
        ],
    }


def _anonymous_result_part(call_id: str = "call-abc") -> dict:
    return {
        "type": "tool_call",
        "tool_calls": [
            {
                "id": call_id,
                "result": "User selected: A (id=A)",
                "ts": 2.0,
                "finished_ts": 2.5,
            }
        ],
    }


def _interactive_choice_part(request_id: str = "req-1") -> dict:
    return {
        "type": "interactive_choice",
        "request_id": request_id,
        "prompt": "Pick one",
        "options": [{"id": "A", "label": "alpha"}],
    }


def _other_tool_args_part(call_id: str = "call-xyz") -> dict:
    return {
        "type": "tool_call",
        "tool_calls": [
            {
                "id": call_id,
                "name": "astrbot_file_read_tool",
                "args": {"path": "/tmp/x"},
                "ts": 1.0,
            }
        ],
    }


def _other_tool_result_part(call_id: str = "call-xyz") -> dict:
    return {
        "type": "tool_call",
        "tool_calls": [
            {
                "id": call_id,
                "name": "astrbot_file_read_tool",
                "result": "file contents",
                "ts": 1.0,
                "finished_ts": 1.5,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Core ask_user_choice half removal
# ---------------------------------------------------------------------------


def test_drops_ask_user_choice_args_part_alone() -> None:
    """A standalone ask_user_choice args part must be stripped."""
    parts = [_ask_args_part()]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == []


def test_drops_paired_anonymous_result_part() -> None:
    """The synthesised-result half paired with an ask_user_choice args
    half in the same message must be dropped too."""
    parts = [_ask_args_part(), _anonymous_result_part()]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == []


def test_preserves_interactive_choice_part_alongside_stale_halves() -> None:
    """The ``interactive_choice`` part is the canonical representation
    for ask_user_choice; it must survive the sanitiser untouched even
    when both broken halves are present in the same message."""
    parts = [
        _interactive_choice_part(),
        _ask_args_part(),
        _anonymous_result_part(),
    ]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == [_interactive_choice_part()]


def test_preserves_non_ask_user_choice_tool_calls() -> None:
    """Real tool calls (with a name) for non-ask_user_choice tools must
    pass through unchanged, both their args half and result half."""
    parts = [_other_tool_args_part(), _other_tool_result_part()]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == parts


def test_mixed_message_with_ask_user_choice_and_other_tool() -> None:
    """End-to-end: a message containing an ask_user_choice pair AND a
    separate real tool call must keep the real tool and drop the pair."""
    parts = [
        _ask_args_part("call-abc"),
        _anonymous_result_part("call-abc"),
        _other_tool_args_part("call-xyz"),
        _other_tool_result_part("call-xyz"),
        _interactive_choice_part(),
    ]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == [
        _other_tool_args_part("call-xyz"),
        _other_tool_result_part("call-xyz"),
        _interactive_choice_part(),
    ]


# ---------------------------------------------------------------------------
# One tool_call part holding multiple tool_calls
# ---------------------------------------------------------------------------


def test_multi_entry_part_drops_only_ask_user_choice_entries() -> None:
    """When one ``tool_call`` part bundles several calls (e.g. when the
    accumulator's pending bucket was flushed with multiple entries in
    one go), only the matching entries are removed — the other entries
    keep their entry and the part itself stays alive."""
    bundled_part = {
        "type": "tool_call",
        "tool_calls": [
            {"id": "call-abc", "name": "ask_user_choice", "args": {}, "ts": 1.0},
            {"id": "call-xyz", "name": "astrbot_file_read_tool", "args": {}, "ts": 1.1},
        ],
    }
    parts = [bundled_part, _anonymous_result_part("call-abc")]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == [
        {
            "type": "tool_call",
            "tool_calls": [
                {
                    "id": "call-xyz",
                    "name": "astrbot_file_read_tool",
                    "args": {},
                    "ts": 1.1,
                }
            ],
        }
    ]


def test_multi_entry_part_empties_when_all_entries_match() -> None:
    """If every entry in a bundled ``tool_call`` part is stale the part
    itself disappears (no empty ``tool_calls: []`` shell is left behind)."""
    bundled_part = {
        "type": "tool_call",
        "tool_calls": [
            {"id": "call-abc", "name": "ask_user_choice", "args": {}, "ts": 1.0},
            {"id": "call-abc", "result": "x", "ts": 2.0, "finished_ts": 2.5},
        ],
    }
    parts = [bundled_part]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == []


# ---------------------------------------------------------------------------
# Defensive behaviour — malformed / unusual input must not raise
# ---------------------------------------------------------------------------


def test_keeps_anonymous_result_without_paired_ask_args() -> None:
    """An anonymous result part whose id has NO matching ask_user_choice
    args entry in the same message must be preserved (the runtime always
    sends ``name``, but a defensive read path must not nuke a tool call
    whose name was lost for any other reason)."""
    parts = [_anonymous_result_part("call-orphan")]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == parts


def test_empty_list_is_a_no_op() -> None:
    """Empty part list returns unchanged."""
    assert _sanitize_ask_user_choice_tool_call_parts([]) == []


def test_non_list_input_is_returned_unchanged() -> None:
    """``None`` or any non-list input must not raise — defensive guard
    against corrupted DB rows."""
    assert _sanitize_ask_user_choice_tool_call_parts(None) is None
    assert _sanitize_ask_user_choice_tool_call_parts("not-a-list") == "not-a-list"
    assert _sanitize_ask_user_choice_tool_call_parts({}) == {}


def test_malformed_tool_call_entries_do_not_crash() -> None:
    """Tool-call entries that are not dicts (or lack ``id``) must be
    ignored by the matcher and preserved as-is in the sanitised output."""
    parts = [
        {
            "type": "tool_call",
            "tool_calls": [
                "garbage-entry",
                None,
                {"no_id": True, "name": "ask_user_choice"},
                {"id": "call-keep", "name": "ask_user_choice", "args": {}},
            ],
        }
    ]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    # None / string preserved (malformed); entries with no id preserved;
    # only the well-formed ask_user_choice entry with an id is dropped.
    assert sanitized == [
        {
            "type": "tool_call",
            "tool_calls": [
                "garbage-entry",
                None,
                {"no_id": True, "name": "ask_user_choice"},
            ],
        }
    ]


def test_non_tool_call_part_types_are_preserved_unchanged() -> None:
    """plain / image / interactive_choice parts must never be touched,
    even when they live next to stale halves."""
    parts = [
        {"type": "plain", "text": "hello"},
        {"type": "image", "attachment_id": "abc"},
        {"type": "interactive_choice", "request_id": "req-1"},
        _ask_args_part(),
    ]

    sanitized = _sanitize_ask_user_choice_tool_call_parts(parts)

    assert sanitized == [
        {"type": "plain", "text": "hello"},
        {"type": "image", "attachment_id": "abc"},
        {"type": "interactive_choice", "request_id": "req-1"},
    ]


# ---------------------------------------------------------------------------
# _sanitize_history_bot_records — wraps the part-level function
# ---------------------------------------------------------------------------


def test_sanitize_bot_records_only_touches_bot_rows() -> None:
    """User rows and rows with non-bot ``content.type`` must be left
    alone even when their ``message`` field contains parts that look
    like ask_user_choice (defensive — user message parts should never
    carry tool_call, but the wrapper must not crash)."""
    history = [
        {
            "id": 1,
            "content": {"type": "user", "message": [{"type": "plain", "text": "hi"}]},
        },
        {
            "id": 2,
            "content": {
                "type": "bot",
                "message": [_ask_args_part(), _anonymous_result_part()],
            },
        },
        {
            "id": 3,
            "content": {"type": "bot", "message": [_other_tool_args_part()]},
        },
        {"id": 4, "content": None},
        {"id": 5},
    ]

    sanitized = _sanitize_history_bot_records(history)

    # Row 1: untouched.
    assert sanitized[0] == history[0]
    # Row 2: bot message parts cleaned.
    assert sanitized[1]["content"]["message"] == []
    # Row 3: legitimate tool call preserved.
    assert sanitized[2]["content"]["message"] == [_other_tool_args_part()]
    # Rows 4 and 5: untouched.
    assert sanitized[3] == history[3]
    assert sanitized[4] == history[4]


def test_sanitize_bot_records_no_op_when_no_stale_parts() -> None:
    """When there is nothing stale to drop, the bot record's message
    list reference must be reused (no-op) so the no-stale-parts common
    case avoids an allocation."""
    original_message = [_other_tool_args_part()]
    history = [{"id": 1, "content": {"type": "bot", "message": original_message}}]

    sanitized = _sanitize_history_bot_records(history)

    # The same list reference should be returned untouched.
    assert sanitized is history
    assert sanitized[0]["content"]["message"] is original_message


def test_sanitize_bot_records_skips_non_dict_rows() -> None:
    """Robustness: a corrupted history list with non-dict entries must
    not crash the wrapper."""
    history = [
        None,
        "garbage",
        {"id": 1, "content": {"type": "bot", "message": [_ask_args_part()]}},
    ]

    sanitized = _sanitize_history_bot_records(history)

    assert sanitized[0] is None
    assert sanitized[1] == "garbage"
    assert sanitized[2]["content"]["message"] == []
