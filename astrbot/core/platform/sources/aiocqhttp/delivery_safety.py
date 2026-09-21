"""Persistent private-message circuit breaker and OneBot delivery audit."""

import asyncio
import json
import re
import sqlite3
import time
from collections.abc import Mapping
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path

from aiocqhttp import CQHttp

from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

SENSITIVE_FIELD_PATTERN = re.compile(
    r"token|secret|password|authorization|cookie|credential|access[_-]?key",
    re.IGNORECASE,
)


def _safe_payload(value, *, key: str = "", depth: int = 0):
    """Return a bounded JSON-compatible copy with credential fields redacted."""
    if SENSITIVE_FIELD_PATTERN.search(key):
        return "<redacted>"
    if depth >= 8:
        return "<maximum depth reached>"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if value.startswith("base64://"):
            return f"<base64 omitted: {len(value) - 9} characters>"
        return value if len(value) <= 8000 else f"{value[:8000]}… <truncated>"
    if isinstance(value, Mapping):
        items = list(value.items())
        result = {
            str(item_key): _safe_payload(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in items[:200]
        }
        if len(items) > 200:
            result["<truncated>"] = f"{len(items) - 200} fields omitted"
        return result
    if isinstance(value, list | tuple):
        result = [_safe_payload(item, depth=depth + 1) for item in value[:200]]
        if len(value) > 200:
            result.append(f"<{len(value) - 200} items omitted>")
        return result
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        try:
            return _safe_payload(converter(), key=key, depth=depth + 1)
        except Exception:
            pass
    return _safe_payload(str(value), key=key, depth=depth + 1)


def _payload_json(value) -> str:
    """Serialize a safe parameter snapshot without breaking message delivery."""
    try:
        encoded = json.dumps(_safe_payload(value), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return '{"error":"parameter snapshot unavailable"}'
    if len(encoded) <= 131072:
        return encoded
    return json.dumps(
        {"truncated": True, "preview": encoded[:131000]},
        ensure_ascii=False,
    )


class DeliveryBlocked(RuntimeError):
    """A private conversation requires operator review before further sends."""


class DeliveryStore:
    """Store reservations before network I/O so concurrent sends cannot bypass limits."""

    def __init__(self, path: Path | None = None):
        self.path = path or Path(get_astrbot_data_path()) / "delivery-safety.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY, umo TEXT NOT NULL, ts REAL NOT NULL,
                    action TEXT NOT NULL, text TEXT NOT NULL, normalized TEXT NOT NULL,
                    status TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    direction TEXT NOT NULL DEFAULT 'outbound',
                    params_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS deliveries_session ON deliveries(umo, id);
                CREATE TABLE IF NOT EXISTS circuits (
                    umo TEXT PRIMARY KEY, ts REAL NOT NULL, reason TEXT NOT NULL
                );
            """)
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(deliveries)").fetchall()
            }
            if "direction" not in columns:
                db.execute(
                    "ALTER TABLE deliveries ADD COLUMN direction TEXT NOT NULL DEFAULT 'outbound'"
                )
            if "params_json" not in columns:
                db.execute(
                    "ALTER TABLE deliveries ADD COLUMN params_json TEXT NOT NULL DEFAULT '{}'"
                )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def blocked(self, umo: str) -> bool:
        with self.connect() as db:
            return (
                db.execute("SELECT 1 FROM circuits WHERE umo=?", (umo,)).fetchone()
                is not None
            )

    def reserve(
        self,
        umo: str,
        action: str,
        text: str,
        now: float | None = None,
        params=None,
    ) -> int:
        """Atomically audit an attempt and latch excessive or repetitive sends.

        Args:
            umo: Platform-scoped private conversation identifier.
            action: OneBot operation being attempted.
            text: Human-readable content without binary media payloads.
            now: Optional clock override for deterministic tests.
            params: OneBot parameters to retain after size limiting and redaction.

        Returns:
            Audit row identifier for an allowed attempt.

        Raises:
            DeliveryBlocked: The circuit is latched or a safety limit is exceeded.
        """
        now = time.time() if now is None else now
        comparable = re.sub(r"\[[^\]]*\]", "", text.lower())
        normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", comparable)[:2000]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            circuit = db.execute(
                "SELECT reason FROM circuits WHERE umo=?", (umo,)
            ).fetchone()
            reason = circuit[0] if circuit else ""
            recent = db.execute(
                "SELECT ts, normalized FROM deliveries WHERE umo=? AND ts>=? "
                "AND direction='outbound' "
                "AND status NOT IN ('blocked', 'historical_prepared') ORDER BY id DESC LIMIT 61",
                (umo, now - 600),
            ).fetchall()
            if not reason:
                if sum(row["ts"] >= now - 60 for row in recent) >= 20:
                    reason = "private_send_burst_20_per_minute"
                elif len(recent) >= 60:
                    reason = "private_send_sustained_60_per_10_minutes"
                elif (
                    normalized
                    and sum(
                        row["ts"] >= now - 120
                        and bool(row["normalized"])
                        and SequenceMatcher(None, normalized, row["normalized"]).ratio()
                        >= 0.9
                        for row in recent
                    )
                    >= 2
                ):
                    reason = "private_send_repeat_3_per_2_minutes"
            if reason:
                db.execute(
                    "INSERT OR IGNORE INTO circuits VALUES (?, ?, ?)",
                    (umo, now, reason),
                )
            cursor = db.execute(
                "INSERT INTO deliveries(umo, ts, action, text, normalized, status, reason, direction, params_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'outbound', ?)",
                (
                    umo,
                    now,
                    action,
                    text[:16000],
                    normalized,
                    "blocked" if reason else "pending",
                    reason,
                    _payload_json(params if params is not None else {}),
                ),
            )
            row_id = cursor.lastrowid
        if reason:
            raise DeliveryBlocked(
                f"Private delivery blocked for {umo}: {reason}; operator review required"
            )
        return row_id

    def record_inbound(
        self,
        umo: str,
        text: str,
        params,
        *,
        blocked: bool,
        now: float | None = None,
    ) -> int:
        """Record one private inbound event independently from model history.

        Args:
            umo: Platform-scoped private conversation identifier.
            text: Message preview extracted from the OneBot event.
            params: Raw OneBot event to retain after redaction and size limiting.
            blocked: Whether the persistent circuit rejected this event.
            now: Optional clock override for deterministic tests.

        Returns:
            Audit row identifier.
        """
        now = time.time() if now is None else now
        normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower())[:2000]
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO deliveries(umo, ts, action, text, normalized, status, reason, direction, params_json) "
                "VALUES (?, ?, 'receive_private_msg', ?, ?, ?, ?, 'inbound', ?)",
                (
                    umo,
                    now,
                    text[:16000],
                    normalized,
                    "received_blocked" if blocked else "received",
                    "persistent_circuit" if blocked else "",
                    _payload_json(params),
                ),
            )
            return cursor.lastrowid

    def finish(self, row_id: int, status: str, receipt: str = ""):
        with self.connect() as db:
            db.execute(
                "UPDATE deliveries SET status=?, receipt=? WHERE id=?",
                (status, receipt, row_id),
            )

    def page(self, umo: str, before: int = 0) -> dict:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, ts, action, text, status, receipt, reason, direction, params_json FROM deliveries "
                "WHERE umo=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 51",
                (umo, before, before),
            ).fetchall()
            circuit = db.execute(
                "SELECT ts, reason FROM circuits WHERE umo=?", (umo,)
            ).fetchone()
            count = db.execute(
                "SELECT count(*) FROM deliveries WHERE umo=?", (umo,)
            ).fetchone()[0]
        items = []
        for row in rows[:50]:
            item = dict(row)
            raw_params = item.pop("params_json", "{}")
            try:
                item["params"] = json.loads(raw_params)
            except (TypeError, json.JSONDecodeError):
                item["params"] = {"error": "Stored parameters are invalid"}
            items.append(item)
        return {
            "items": items,
            "hasMore": len(rows) > 50,
            "total": count,
            "circuit": dict(circuit) if circuit else None,
        }


class SafeCQHttp(CQHttp):
    """Audit and guard every private send through this platform's public client."""

    def __init__(self, *args, platform_id: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.delivery_platform_id = platform_id
        self.delivery_store = DeliveryStore()
        self._delivery_locks: dict[str, asyncio.Lock] = {}

    async def call_action(self, action: str, **params):
        base_action = action.removesuffix("_async")
        private = base_action in {"send_private_msg", "send_private_forward_msg"} or (
            base_action in {"send_msg", "send_forward_msg"}
            and not params.get("group_id")
            and params.get("message_type") != "group"
        )
        if not private:
            return await super().call_action(action, **params)
        user_id = str(params.get("user_id") or "")
        if not user_id.isdigit():
            raise DeliveryBlocked("Private send has no valid user_id")
        umo = f"{self.delivery_platform_id}:FriendMessage:{user_id}"
        content = params.get("message", params.get("messages", []))
        if isinstance(content, str):
            text = content
        else:
            text = "".join(
                str(part.get("data", {}).get("text", ""))
                if part.get("type") == "text"
                else f"[{part.get('type', 'unknown')}]"
                for part in content
                if isinstance(part, dict)
            )
        delivery_locks = getattr(self, "_delivery_locks", None)
        if not isinstance(delivery_locks, dict):
            delivery_locks = self._delivery_locks = {}
        async with delivery_locks.setdefault(umo, asyncio.Lock()):
            try:
                row_id = self.delivery_store.reserve(
                    umo,
                    action,
                    text,
                    params=params,
                )
            except DeliveryBlocked:
                active_event_registry.request_agent_stop_all(umo)
                active_event_registry.stop_all(umo)
                from astrbot.core.pipeline.process_stage.follow_up import (
                    terminate_follow_up_session,
                )

                await terminate_follow_up_session(umo)
                raise

            # Recheck immediately before network I/O. This catches an operator
            # latch written after reservation and serializes concurrent sends.
            if self.delivery_store.blocked(umo):
                self.delivery_store.finish(row_id, "blocked")
                active_event_registry.request_agent_stop_all(umo)
                active_event_registry.stop_all(umo)
                from astrbot.core.pipeline.process_stage.follow_up import (
                    terminate_follow_up_session,
                )

                await terminate_follow_up_session(umo)
                raise DeliveryBlocked(
                    f"Private delivery blocked for {umo}; pre-send recheck failed"
                )
            try:
                response = await super().call_action(action, **params)
            except (Exception, asyncio.CancelledError):
                self.delivery_store.finish(row_id, "uncertain")
                raise
            receipt = response.get("message_id") if isinstance(response, dict) else None
            self.delivery_store.finish(
                row_id,
                "accepted" if receipt is not None else "unconfirmed",
                json.dumps(receipt) if receipt is not None else "",
            )
            return response
