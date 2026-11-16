"""Plugin view declarations and durable ChatUI interaction state."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class ViewSpec(BaseModel):
    """Declare an HTML view's host and permitted chat actions."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    entry: Path
    target: Literal["chat_message", "plugin_page"] = "chat_message"
    version: int = Field(default=1, ge=1)
    actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target_actions(self):
        """Require independent pages to use their plugin Web API.

        Returns:
            The validated declaration.

        Raises:
            ValueError: If a plugin page declares chat interaction actions.
        """
        if self.target == "plugin_page" and self.actions:
            raise ValueError(
                "plugin_page views use plugin Web APIs, not UI interaction actions."
            )
        return self


class ViewResult(BaseModel):
    """Create a named card, or replace the current interaction's card data."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    data: dict[str, Any]
    text: str = ""

    @model_validator(mode="after")
    def validate_operation(self):
        """Keep creation and replacement semantics unambiguous.

        Returns:
            The validated result.

        Raises:
            ValueError: If creation lacks text or an update supplies text.
        """
        if self.name is not None and (not self.name or not self.text.strip()):
            raise ValueError("Creating a view requires a name and fallback text.")
        if self.name is None and self.text:
            raise ValueError("A view update cannot replace the tool's text result.")
        return self

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict) -> dict:
        """Copy bounded JSON data before it enters persistent view state.

        Args:
            value: Plugin-supplied display data.

        Returns:
            An independent JSON-compatible object.

        Raises:
            ValueError: If the data is invalid or exceeds one MiB.
        """
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(encoded.encode()) > 1024 * 1024:
            raise ValueError("View data exceeds one MiB.")
        return json.loads(encoded)


class ViewActionRequest(BaseModel):
    """Untrusted input submitted by a view through the authenticated host."""

    model_config = ConfigDict(extra="forbid", strict=True)
    action_id: str = Field(min_length=1, max_length=200)
    interaction_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    data: Any = None

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: Any) -> Any:
        """Validate and copy JSON action input.

        Args:
            value: Client-supplied action arguments.

        Returns:
            JSON-compatible arguments.

        Raises:
            ValueError: If the input exceeds 64 KiB or is not JSON-compatible.
        """
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("Action data exceeds 64 KiB.")
        return json.loads(encoded)


class ViewError(ValueError):
    """An interaction failure safe to report to its originating view."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def resolve_view(
    module: str,
    name: str,
    version: int | None = None,
    *,
    target: Literal["chat_message", "plugin_page"] = "chat_message",
):
    """Resolve a currently enabled plugin's declared view and safe entry path.

    Args:
        module: Owning plugin module recorded by the host.
        name: Plugin-local view name.
        version: Required contract version, if restoring an existing instance.
        target: Host that must match the declaration. Chat instances require
            chat_message; the plugin loader validates either declared target.

    Returns:
        The plugin metadata, validated declaration, and resolved entry path.

    Raises:
        ViewError: If the plugin, contract, or entry is unavailable.
    """
    from astrbot.core.star.star import star_map

    plugin = star_map.get(module)
    if not plugin or not plugin.activated or plugin.star_cls is None:
        raise ViewError("VIEW_UNAVAILABLE", "The view's plugin is unavailable.")
    for spec in getattr(plugin.star_cls, "chatui_views", []):
        if spec.name != name:
            continue
        if spec.target != target:
            raise ViewError(
                "VIEW_UNAVAILABLE", f"This view is not registered for {target}."
            )
        if version is not None and version != spec.version:
            break
        if spec.entry != Path("views") / spec.name / "index.html":
            raise ViewError(
                "VIEW_UNAVAILABLE", "View entries must use views/<name>/index.html."
            )
        root = Path(plugin.module.__file__).resolve().parent
        entry = (root / spec.entry).resolve()
        if spec.entry.is_absolute() or not entry.is_relative_to(root):
            break
        if not entry.is_file():
            break
        return plugin, spec, entry
    raise ViewError("VIEW_UNAVAILABLE", "The view or its version is unavailable.")


async def emit_view(event, module: str, result: ViewResult) -> None:
    """Send a new card from either a tool or a message handler.

    Args:
        event: Source message event.
        module: Plugin module owning the handler.
        result: Named card creation result.
    """
    import asyncio

    from astrbot.core.message.components import Json
    from astrbot.core.message.message_event_result import MessageChain

    resolve_view(module, result.name)
    if event.get_platform_name() != "webchat":
        return
    record = await asyncio.to_thread(view_store.create, event, module, result)
    await event.send(
        MessageChain(
            chain=[
                Json({"id": record["id"], "name": record["name"], "text": result.text})
            ],
            type="chatui_view",
        )
    )


class ViewStore:
    """Persist view snapshots and reserve callbacks across workers."""

    def __init__(self, path: Path | None = None):
        self.path = path

    @contextmanager
    def connect(self):
        """Open the view database, creating its tables on first use.

        Yields:
            A connection with dictionary-style rows, closed on exit.
        """
        path = self.path or Path(get_astrbot_data_path()) / "chatui.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            "CREATE TABLE IF NOT EXISTS views ("
            "id TEXT PRIMARY KEY, owner TEXT, session_id TEXT, platform TEXT, "
            "module TEXT, name TEXT, version INTEGER, revision INTEGER, "
            "data TEXT, text TEXT, message_id TEXT, run_id TEXT);"
            "CREATE TABLE IF NOT EXISTS actions ("
            "view_id TEXT, id TEXT, request TEXT, started REAL, status TEXT, "
            "result TEXT, PRIMARY KEY(view_id, id));"
        )
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, event, module: str, result: ViewResult) -> dict:
        """Persist a card created by a plugin message or tool handler.

        Args:
            event: Authenticated WebChat event.
            module: Owning plugin module.
            result: Validated card creation result.

        Returns:
            A serialized view snapshot.
        """
        _, spec, _ = resolve_view(module, result.name)
        raw = event.message_obj.raw_message
        owner, session_id, payload = raw
        record = {
            "id": uuid.uuid4().hex,
            "owner": owner,
            "session_id": session_id,
            "platform": payload.get("_platform_history_id", "webchat"),
            "module": module,
            "name": spec.name,
            "version": spec.version,
            "revision": 1,
            "data": result.data,
            "text": result.text,
            "message_id": None,
            "run_id": str(event.message_obj.message_id),
        }
        with self.connect() as db:
            stored = {**record, "data": json.dumps(record["data"], ensure_ascii=False)}
            db.execute(
                "INSERT INTO views VALUES (:id,:owner,:session_id,:platform,"
                ":module,:name,:version,:revision,:data,:text,:message_id,:run_id)",
                stored,
            )
        return record

    def get(self, view_id: str) -> dict:
        """Read a persisted snapshot.

        Args:
            view_id: Instance identifier.

        Returns:
            The stored record with decoded JSON data.

        Raises:
            ViewError: If the instance no longer exists.
        """
        with self.connect() as db:
            row = db.execute("SELECT * FROM views WHERE id=?", (view_id,)).fetchone()
        if not row:
            raise ViewError("VIEW_UNAVAILABLE", "This view is unavailable.")
        record = dict(row)
        record["data"] = json.loads(record["data"])
        return record

    def bind_message(self, view_id: str, message_id: str) -> None:
        """Associate a card with its persisted source message.

        Args:
            view_id: Instance identifier.
            message_id: Saved message identifier.
        """
        with self.connect() as db:
            db.execute(
                "UPDATE views SET message_id=? WHERE id=?", (message_id, view_id)
            )

    def begin(self, view_id: str, request: ViewActionRequest) -> dict | None:
        """Reserve an action or return its already recorded outcome.

        Args:
            view_id: Authorized instance identifier.
            request: Validated action input.

        Returns:
            A previous result for a retry, otherwise None for a new reservation.

        Raises:
            ViewError: On conflicting, stale, running, or uncertain requests.
        """
        encoded = json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM actions WHERE view_id=? AND id=?",
                (view_id, request.interaction_id),
            ).fetchone()
            if previous:
                if previous["request"] != encoded:
                    raise ViewError(
                        "INVALID_INPUT",
                        "Interaction ID was reused with different input.",
                    )
                if previous["result"]:
                    return json.loads(previous["result"])
                code = (
                    "ACTION_IN_PROGRESS"
                    if time.time() - previous["started"] < 180
                    else "ACTION_OUTCOME_UNKNOWN"
                )
                raise ViewError(code, "This action has already been accepted.")
            active = db.execute(
                "SELECT id,started FROM actions WHERE view_id=? AND status='running'",
                (view_id,),
            ).fetchone()
            if active:
                raise ViewError(
                    "ACTION_IN_PROGRESS"
                    if time.time() - active["started"] < 180
                    else "ACTION_OUTCOME_UNKNOWN",
                    "Another action is still pending.",
                )
            row = db.execute(
                "SELECT revision FROM views WHERE id=?", (view_id,)
            ).fetchone()
            if not row:
                raise ViewError("VIEW_UNAVAILABLE", "This view is unavailable.")
            if row["revision"] != request.expected_revision:
                raise ViewError(
                    "REVISION_CONFLICT",
                    "The view has changed. Review it and try again.",
                )
            db.execute(
                "INSERT INTO actions VALUES (?,?,?,?,?,NULL)",
                (view_id, request.interaction_id, encoded, time.time(), "running"),
            )
        return None

    def finish(
        self,
        view_id: str,
        interaction_id: str,
        data: dict | None = None,
        error: dict | None = None,
    ) -> dict:
        """Commit an update and action outcome together.

        Args:
            view_id: Reserved view identifier.
            interaction_id: Accepted action identifier.
            data: Replacement snapshot, or None to preserve it.
            error: Safe failure details, or None on success.

        Returns:
            A replayable action receipt.
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT result FROM actions WHERE view_id=? AND id=?",
                (view_id, interaction_id),
            ).fetchone()
            if previous and previous["result"]:
                return json.loads(previous["result"])
            if data is not None and error is None:
                db.execute(
                    "UPDATE views SET data=?,revision=revision+1 WHERE id=?",
                    (json.dumps(data, ensure_ascii=False), view_id),
                )
            row = db.execute(
                "SELECT data,revision FROM views WHERE id=?", (view_id,)
            ).fetchone()
            result = {
                "view_id": view_id,
                "interaction_id": interaction_id,
                "error": error,
            }
            if row:
                result["snapshot"] = {
                    "data": json.loads(row["data"]),
                    "revision": row["revision"],
                }
            db.execute(
                "UPDATE actions SET status=?,result=? WHERE view_id=? AND id=?",
                (
                    "failed" if error else "completed",
                    json.dumps(result),
                    view_id,
                    interaction_id,
                ),
            )
        return result

    def delete_session(self, session_id: str) -> None:
        """Remove cards and action records belonging to a deleted session.

        Args:
            session_id: Deleted chat or thread identifier.
        """
        with self.connect() as db:
            db.execute(
                "DELETE FROM actions WHERE view_id IN (SELECT id FROM views WHERE session_id=?)",
                (session_id,),
            )
            db.execute("DELETE FROM views WHERE session_id=?", (session_id,))


view_store = ViewStore()
