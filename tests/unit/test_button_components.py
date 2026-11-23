import sqlite3

import pytest

from astrbot.core.message.components import (
    ActionRow,
    Button,
)
from astrbot.core.platform import button_interaction
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)


def test_action_row_serializes_portable_buttons():
    row = ActionRow(
        buttons=[
            Button(
                id="confirm",
                label="Confirm",
                action=Button.CallbackAction(data={"order_id": 42}),
                style=Button.Style.PRIMARY,
            ),
            Button(
                id="docs",
                label="Docs",
                action=Button.UrlAction(url="https://example.com/docs"),
            ),
        ],
        fallback_text="Choose an action",
    )

    assert row.toDict() == {
        "type": "actionrow",
        "data": {
            "buttons": [
                {
                    "id": "confirm",
                    "label": "Confirm",
                    "action": {
                        "type": "callback",
                        "data": {"order_id": 42},
                    },
                    "style": "primary",
                },
                {
                    "id": "docs",
                    "label": "Docs",
                    "action": {
                        "type": "url",
                        "url": "https://example.com/docs",
                    },
                    "style": "default",
                },
            ],
            "fallback_text": "Choose an action",
        },
    }


@pytest.mark.parametrize(
    ("action", "action_type"),
    [
        (
            {"type": "callback", "data": {"flags": [True, None], "count": 42}},
            Button.CallbackAction,
        ),
        ({"type": "callback"}, Button.CallbackAction),
        ({"type": "url", "url": "https://example.com/docs"}, Button.UrlAction),
    ],
)
def test_button_action_round_trips_through_json(action, action_type):
    button = Button(id="confirm", label="Confirm", action=action, style="primary")
    restored = Button.parse_raw(button.json())

    assert isinstance(restored.action, action_type)
    assert restored.style is Button.Style.PRIMARY
    assert restored.toDict() == {
        "type": "button",
        "data": {
            "id": "confirm",
            "label": "Confirm",
            "action": action,
            "style": "primary",
        },
    }


@pytest.mark.parametrize(
    "action",
    [
        {"type": "unknown", "url": "https://example.com/docs"},
        {"type": "url", "data": {"item_id": 42}},
        {"url": "https://example.com/docs"},
    ],
)
def test_button_rejects_invalid_action_discriminators(action):
    with pytest.raises(ValueError):
        Button(id="confirm", label="Confirm", action=action)


def test_button_schema_discriminates_nested_actions():
    schema = Button.schema()
    action = schema["properties"]["action"]

    assert action["discriminator"]["propertyName"] == "type"
    assert set(action["discriminator"]["mapping"]) == {"callback", "url"}
    assert {entry["$ref"] for entry in action["oneOf"]} == set(
        action["discriminator"]["mapping"].values()
    )


def test_callback_codec_round_trip():
    payload = encode_button_callback(
        "approve",
        {"request_id": "req-1", "flags": [True, None]},
    )

    assert decode_button_callback(payload) == (
        "approve",
        {"request_id": "req-1", "flags": [True, None]},
    )


@pytest.mark.parametrize("data", [{"invalid": {1, 2}}, float("nan")])
def test_callback_action_rejects_non_json_data(data):
    with pytest.raises(ValueError, match="JSON-compatible"):
        Button.CallbackAction(data=data)


def test_callback_codec_uses_compact_opaque_token():
    payload = encode_button_callback("approve")

    assert payload.startswith("astrbot:")
    assert len(payload.encode("utf-8")) <= 64
    assert "approve" not in payload
    assert decode_button_callback(payload) == ("approve", None)


def test_callback_registry_survives_process_restart(tmp_path, monkeypatch):
    registry = button_interaction._ButtonCallbackRegistry()
    registry.configure(tmp_path / "callbacks.db")
    monkeypatch.setattr(button_interaction, "_button_callback_registry", registry)
    payload = button_interaction.encode_button_callback(
        "approve",
        {"request_id": "req-1"},
    )

    restarted_registry = button_interaction._ButtonCallbackRegistry()
    restarted_registry.configure(tmp_path / "callbacks.db")
    monkeypatch.setattr(
        button_interaction,
        "_button_callback_registry",
        restarted_registry,
    )

    assert button_interaction.decode_button_callback(payload) == (
        "approve",
        {"request_id": "req-1"},
    )


@pytest.mark.parametrize("payload", ["approve", "astrbot:{}", "astrbot:not-json"])
def test_callback_codec_rejects_invalid_payload(payload):
    with pytest.raises(ValueError):
        decode_button_callback(payload)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_action_timeout_requires_positive_finite_seconds(timeout):
    with pytest.raises(ValueError):
        ActionRow(buttons=[], action_timeout=timeout)


def test_action_row_starts_shared_deadline_on_first_render(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    row = ActionRow(buttons=[], action_timeout=60)
    clock[0] = 200.0
    assert row.toDict()["data"]["action_timeout"] == 60
    assert row.action_expires_at == 260
    clock[0] = 220.0
    assert row.action_expires_at == 260
    assert ActionRow(buttons=[]).action_expires_at is None


@pytest.mark.parametrize("restart", [False, True])
def test_callback_expiry_survives_cache_and_restart(tmp_path, monkeypatch, restart):
    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    registry = button_interaction._ButtonCallbackRegistry()
    db_path = tmp_path / "callbacks.db"
    registry.configure(db_path)
    monkeypatch.setattr(button_interaction, "_button_callback_registry", registry)
    payload = encode_button_callback("approve", {"item": 42}, expires_at=160)
    assert decode_button_callback(payload) == ("approve", {"item": 42})

    if restart:
        registry = button_interaction._ButtonCallbackRegistry()
        registry.configure(db_path)
        monkeypatch.setattr(button_interaction, "_button_callback_registry", registry)

    clock[0] = 159.0
    assert decode_button_callback(payload) == ("approve", {"item": 42})
    clock[0] = 160.0
    with pytest.raises(ValueError, match="expired"):
        decode_button_callback(payload)
    with pytest.raises(button_interaction.ButtonActionExpiredError):
        decode_button_callback(payload)
    assert decode_button_callback(payload, allow_expired=True) == (
        "approve",
        {"item": 42},
    )
    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM button_callbacks").fetchone()[0]
            == 1
        )


def test_new_deadline_does_not_renew_old_callback(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    registry = button_interaction._ButtonCallbackRegistry()
    monkeypatch.setattr(button_interaction, "_button_callback_registry", registry)
    old = encode_button_callback("approve", {"item": 42}, expires_at=160)
    new = encode_button_callback("approve", {"item": 42}, expires_at=220)
    unlimited = encode_button_callback("approve", {"item": 42})
    assert len({old, new, unlimited}) == 3
    clock[0] = 160.0
    with pytest.raises(ValueError, match="expired"):
        decode_button_callback(old)
    assert decode_button_callback(new) == ("approve", {"item": 42})
    clock[0] = 10_000.0
    assert decode_button_callback(unlimited) == ("approve", {"item": 42})
