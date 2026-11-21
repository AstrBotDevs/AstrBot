import asyncio
import sqlite3
import threading

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


def test_expired_callbacks_are_pruned_from_the_database(tmp_path, monkeypatch):
    registry = button_interaction._ButtonCallbackRegistry()
    path = tmp_path / "callbacks.db"
    registry.configure(path)
    monkeypatch.setattr(button_interaction.time, "time", lambda: 100.0)
    token = registry.register("old", None, expires_at=101)
    monkeypatch.setattr(button_interaction.time, "time", lambda: 200000.0)
    registry.register("new", None, expires_at=200100)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM button_callbacks WHERE token=?", (token,)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.asyncio
async def test_registration_saves_on_a_worker_thread(tmp_path, monkeypatch):
    """A locked database must not block the event loop, so saving happens
    off the loop thread while the callback is usable at once."""
    registry = button_interaction._ButtonCallbackRegistry()
    path = tmp_path / "callbacks.db"
    registry.configure(path)
    connect = sqlite3.connect
    threads = []
    release = threading.Event()
    loop = asyncio.get_running_loop()
    write_started = asyncio.Event()

    def held_connect(*args, **kwargs):
        threads.append(threading.current_thread())
        loop.call_soon_threadsafe(write_started.set)
        release.wait(timeout=10)
        return connect(*args, **kwargs)

    monkeypatch.setattr(button_interaction.sqlite3, "connect", held_connect)
    token = registry.register("approve", {"id": 1})
    assert registry.resolve(token) == ("approve", {"id": 1})
    # The loop keeps running other work while the write is still held.
    await asyncio.wait_for(write_started.wait(), timeout=10)
    assert registry._pending_writes
    release.set()
    await registry.flush()
    assert not registry._pending_writes
    assert threading.main_thread() not in threads
    restarted = button_interaction._ButtonCallbackRegistry()
    restarted.configure(path)
    assert restarted.resolve(token) == ("approve", {"id": 1})


def test_long_expired_callbacks_leave_the_cache(tmp_path, monkeypatch):
    registry = button_interaction._ButtonCallbackRegistry()
    registry.configure(tmp_path / "callbacks.db")
    monkeypatch.setattr(button_interaction.time, "time", lambda: 100.0)
    old = registry.register("old", None, expires_at=101)
    monkeypatch.setattr(button_interaction.time, "time", lambda: 200000.0)
    recent = registry.register("recent", None, expires_at=199999)
    assert old not in registry._cache
    # Within the retention day a late click still gets the expiry notice.
    with pytest.raises(button_interaction.ButtonActionExpiredError):
        registry.resolve(recent)


def test_failed_save_keeps_the_callback_and_retries(tmp_path, monkeypatch):
    registry = button_interaction._ButtonCallbackRegistry()
    path = tmp_path / "callbacks.db"
    registry.configure(path)
    connect = sqlite3.connect

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(button_interaction.sqlite3, "connect", locked)
    monkeypatch.setattr(button_interaction, "_MAX_CACHED_CALLBACKS", 1)
    first = registry.register("first", None)
    second = registry.register("second", None)
    # Unsaved callbacks stay usable and are not evicted by the cache limit.
    assert registry.resolve(first) == ("first", None)
    assert registry.resolve(second) == ("second", None)

    monkeypatch.setattr(button_interaction.sqlite3, "connect", connect)
    registry.register("third", None)
    restarted = button_interaction._ButtonCallbackRegistry()
    restarted.configure(path)
    assert restarted.resolve(first) == ("first", None)
    assert restarted.resolve(second) == ("second", None)


def test_cache_limit_drops_only_saved_callbacks(tmp_path, monkeypatch):
    registry = button_interaction._ButtonCallbackRegistry()
    registry.configure(tmp_path / "callbacks.db")
    monkeypatch.setattr(button_interaction, "_MAX_CACHED_CALLBACKS", 2)
    tokens = [registry.register(str(index), None) for index in range(4)]
    assert list(registry._cache) == tokens[2:]
    # A dropped entry is still found in the database.
    assert registry.resolve(tokens[0]) == ("0", None)


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
