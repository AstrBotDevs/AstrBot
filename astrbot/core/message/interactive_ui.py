"""Plugin view declarations and durable interactive message state."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from astrbot.core.config.default import DB_PATH
from astrbot.core.message.components import InteractiveView
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class ViewSpec(BaseModel):
    """Declare a plugin view and its permitted actions."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    target: Literal[
        "chat_message", "chat_workbench", "chat_workbench_with_launcher", "plugin_page"
    ] = "plugin_page"
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=500)
    version: int = Field(default=1, ge=1)
    actions: list[str] = Field(default_factory=list)

    @property
    def entry(self) -> Path:
        """Return the conventional entry path relative to the plugin root."""
        return Path("views") / self.name / "index.html"

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
                "Standalone views use plugin Web APIs, not UI interaction actions."
            )
        return self


class ViewResult(BaseModel):
    """Create a named card, or replace the current interaction's card data."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    data: dict[str, Any]
    text: str = ""
    title: str = Field(default="", max_length=200)

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
        if self.name is None and self.title:
            raise ValueError("A view update cannot replace its title.")
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


def resolve_view_spec(
    module: str,
    name: str,
    version: int | None = None,
    *,
    target: str | None = None,
):
    """Resolve a view declaration from a currently enabled plugin.

    Args:
        module: Owning plugin module recorded by the host.
        name: Plugin-local view name.
        version: Required contract version, if restoring an existing instance.
        target: Exact host to validate, or None to select an interactive view.

    Returns:
        The plugin metadata and validated declaration.

    Raises:
        ViewError: If the plugin or view contract is unavailable.
    """
    from astrbot.core.star.star import star_map

    plugin = star_map.get(module)
    if not plugin or not plugin.activated or plugin.star_cls is None:
        raise ViewError("VIEW_UNAVAILABLE", "The view's plugin is unavailable.")
    for spec in plugin.views:
        if spec.name != name:
            continue
        if (target is not None and spec.target != target) or (
            target is None and spec.target == "plugin_page"
        ):
            raise ViewError(
                "VIEW_UNAVAILABLE",
                f"This view is not registered for {target or 'chat_message or chat_workbench'}.",
            )
        if version is not None and version != spec.version:
            break
        return plugin, spec
    raise ViewError("VIEW_UNAVAILABLE", "The view or its version is unavailable.")


async def emit_view(event: AstrMessageEvent, module: str, result: ViewResult) -> None:
    """Send a new card from either a tool or a message handler.

    Args:
        event: Source message event.
        module: Plugin module owning the handler.
        result: Named card creation result.
    """
    _, spec = resolve_view_spec(module, result.name)
    if not event.platform_meta.support_ui_interaction:
        return
    platform_id = event.get_platform_id()
    record = await asyncio.to_thread(
        view_store.create,
        module,
        spec,
        result,
        owner=event.get_sender_id(),
        session_id=event.get_extra("view_session_id", event.get_session_id()),
        platform_id=platform_id,
        history_platform_id=event.get_extra("view_history_platform_id", platform_id),
        run_id=str(event.message_obj.message_id),
    )
    await event.send(
        MessageChain(
            chain=[
                InteractiveView(
                    view_id=record["id"],
                    module=module,
                    name=spec.name,
                    version=spec.version,
                    title=result.title,
                    fallback_text=result.text,
                )
            ]
        )
    )


class ViewStore:
    """Persist view snapshots and reserve callbacks across workers."""

    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else Path(DB_PATH)

    @contextmanager
    def connect(self):
        """Open a connection to the main SQLite database.

        Yields:
            A connection with dictionary-style rows, closed on exit.
        """
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def create(
        self,
        module: str,
        spec: ViewSpec,
        result: ViewResult,
        *,
        owner: str,
        session_id: str,
        platform_id: str,
        history_platform_id: str,
        run_id: str,
    ) -> dict:
        """Persist a card created by a plugin message or tool handler.

        Args:
            module: Owning plugin module.
            spec: Resolved view declaration.
            result: Validated card creation result.
            owner: Authenticated actor identifier.
            session_id: Session identifier for the card's history.
            platform_id: Unique platform adapter instance identifier.
            history_platform_id: Adapter's history namespace for the session.
            run_id: Originating request identifier before message binding.

        Returns:
            A serialized view snapshot.
        """
        record = {
            "id": uuid.uuid4().hex,
            "owner": owner,
            "session_id": session_id,
            "platform_id": platform_id,
            "history_platform_id": history_platform_id,
            "module": module,
            "name": spec.name,
            "version": spec.version,
            "revision": 1,
            "data": result.data,
            "text": result.text,
            "message_id": None,
            "run_id": run_id,
        }
        with self.connect() as db:
            stored = {**record, "data": json.dumps(record["data"], ensure_ascii=False)}
            db.execute(
                "INSERT INTO interactive_views VALUES "
                "(:id,:owner,:session_id,:platform_id,:history_platform_id,"
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
            row = db.execute(
                "SELECT * FROM interactive_views WHERE id=?", (view_id,)
            ).fetchone()
        if not row:
            raise ViewError("VIEW_UNAVAILABLE", "This view is unavailable.")
        record = dict(row)
        record["data"] = json.loads(record["data"])
        return record

    def bind_message(
        self,
        view_id: str,
        message_id: str,
        *,
        platform_id: str,
        session_id: str,
        history_platform_id: str,
    ) -> None:
        """Bind the first persisted source message for a card.

        Args:
            view_id: Instance identifier.
            message_id: Saved message identifier.
            platform_id: Adapter instance that saved the message.
            session_id: Session that owns the message.
            history_platform_id: History namespace that contains the message.
        """
        with self.connect() as db:
            db.execute(
                "UPDATE interactive_views SET message_id=? "
                "WHERE id=? AND message_id IS NULL "
                "AND platform_id=? AND session_id=? AND history_platform_id=?",
                (message_id, view_id, platform_id, session_id, history_platform_id),
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
                "SELECT * FROM interactive_view_actions WHERE view_id=? AND id=?",
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
                "SELECT id,started FROM interactive_view_actions WHERE view_id=? AND status='running'",
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
                "SELECT revision FROM interactive_views WHERE id=?", (view_id,)
            ).fetchone()
            if not row:
                raise ViewError("VIEW_UNAVAILABLE", "This view is unavailable.")
            if row["revision"] != request.expected_revision:
                raise ViewError(
                    "REVISION_CONFLICT",
                    "The view has changed. Review it and try again.",
                )
            db.execute(
                "INSERT INTO interactive_view_actions VALUES (?,?,?,?,?,NULL)",
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
                "SELECT result FROM interactive_view_actions WHERE view_id=? AND id=?",
                (view_id, interaction_id),
            ).fetchone()
            if previous and previous["result"]:
                return json.loads(previous["result"])
            if data is not None and error is None:
                db.execute(
                    "UPDATE interactive_views SET data=?,revision=revision+1 WHERE id=?",
                    (json.dumps(data, ensure_ascii=False), view_id),
                )
            row = db.execute(
                "SELECT data,revision FROM interactive_views WHERE id=?", (view_id,)
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
                "UPDATE interactive_view_actions SET status=?,result=? WHERE view_id=? AND id=?",
                (
                    "failed" if error else "completed",
                    json.dumps(result),
                    view_id,
                    interaction_id,
                ),
            )
        return result

    def delete_session(self, platform_id: str, session_id: str) -> None:
        """Remove cards and action records belonging to a deleted session.

        Args:
            platform_id: Adapter instance that owns the session.
            session_id: Deleted chat or thread identifier.
        """
        with self.connect() as db:
            db.execute(
                "DELETE FROM interactive_view_actions WHERE view_id IN "
                "(SELECT id FROM interactive_views WHERE platform_id=? AND session_id=?)",
                (platform_id, session_id),
            )
            db.execute(
                "DELETE FROM interactive_views WHERE platform_id=? AND session_id=?",
                (platform_id, session_id),
            )


view_store = ViewStore()
