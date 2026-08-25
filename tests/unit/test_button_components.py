import pytest

from astrbot.core.message.components import (
    ActionRow,
    Button,
    ButtonStyle,
    CallbackAction,
    UrlAction,
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
                action=CallbackAction(data={"order_id": 42}),
                style=ButtonStyle.PRIMARY,
            ),
            Button(
                id="docs",
                label="Docs",
                action=UrlAction(url="https://example.com/docs"),
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
        CallbackAction(data=data)


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
