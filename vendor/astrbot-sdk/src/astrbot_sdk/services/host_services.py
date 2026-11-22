"""Typed modern SDK facades for Host capabilities added for full parity."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterable, Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..events import UMO, MessageEvent, MessageType
from ..messages import MessageLike, to_message_chain
from .assets import prepare_outbound_chain

if TYPE_CHECKING:
    from ..context import PluginContext


def _to_core_umo_str(target: MessageEvent | UMO | str) -> str:
    """Normalize MessageEvent, UMO, or str into AstrBot's canonical UMO string."""
    if isinstance(target, MessageEvent):
        umo = target.umo
    elif isinstance(target, UMO):
        umo = target
    else:
        return str(target)
    core_type = {
        MessageType.PRIVATE: "FriendMessage",
        MessageType.GROUP: "GroupMessage",
        MessageType.OTHER: "OtherMessage",
    }[umo.message_type]
    return f"{umo.platform_id}:{core_type}:{umo.session_id}"


class EventStateClient:
    """In-flight Host event control and reaction helpers (``event.state``)."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the client.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx

    async def set_call_llm(
        self,
        target: MessageEvent | UMO | str,
        value: bool,
    ) -> None:
        """Override whether the Host triggers default LLM handling for this event.

        Args:
            target: Active event or session UMO.
            value: Whether default LLM handling should run.
        """
        await self._ctx._invoke_capability(
            "event.state",
            "set_call_llm",
            {"umo": _to_core_umo_str(target), "value": bool(value)},
        )

    async def send_typing(self, target: MessageEvent | UMO | str) -> None:
        """Send a typing indicator for an active session event."""
        await self._ctx._invoke_capability(
            "event.state",
            "call_method",
            {"umo": _to_core_umo_str(target), "method": "send_typing", "args": {}},
        )

    async def stop_typing(self, target: MessageEvent | UMO | str) -> None:
        """Stop an active typing indicator for an active session event."""
        await self._ctx._invoke_capability(
            "event.state",
            "call_method",
            {"umo": _to_core_umo_str(target), "method": "stop_typing", "args": {}},
        )

    async def react(self, target: MessageEvent | UMO | str, emoji: str) -> None:
        """Add an emoji reaction on the in-flight Host event."""
        await self._ctx._invoke_capability(
            "event.state",
            "call_method",
            {
                "umo": _to_core_umo_str(target),
                "method": "react",
                "args": {"emoji": emoji},
            },
        )

    async def get_group(
        self,
        target: MessageEvent | UMO | str,
        group_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Query normalized group metadata for an in-flight event."""
        args = {"group_id": group_id} if group_id is not None else {}
        result = await self._ctx._invoke_capability(
            "event.state",
            "call_method",
            {
                "umo": _to_core_umo_str(target),
                "method": "get_group",
                "args": args,
            },
        )
        return result.get("result") if isinstance(result, Mapping) else None

    async def send_streaming(
        self,
        target: MessageEvent | UMO | str,
        chunks: AsyncIterable[MessageLike],
        *,
        use_fallback: bool = False,
    ) -> None:
        """Stream incremental message chunks through an in-flight Host event.

        Args:
            target: In-flight event or session UMO.
            chunks: Async iterable yielding text/segment/chain chunks.
            use_fallback: Whether adapters without native streaming fall back.
        """
        umo_str = _to_core_umo_str(target)
        opened = await self._ctx._invoke_capability(
            "event.state",
            "stream_open",
            {"umo": umo_str, "use_fallback": bool(use_fallback)},
        )
        stream_id = str(opened["stream_id"])
        aborted = False
        try:
            async for chunk in chunks:
                chain = await prepare_outbound_chain(
                    to_message_chain(chunk),
                    self._ctx.assets,
                )
                await self._ctx._invoke_capability(
                    "event.state",
                    "stream_chunk",
                    {"umo": umo_str, "stream_id": stream_id, "message": chain},
                )
        except Exception:
            aborted = True
            raise
        finally:
            await self._ctx._invoke_capability(
                "event.state",
                "stream_close",
                {"umo": umo_str, "stream_id": stream_id, "abort": aborted},
            )


class PlatformClient:
    """Forward raw platform adapter actions to the Host (``platform.raw``)."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the platform client."""
        self._ctx = ctx

    async def call_action(
        self,
        platform_id: str,
        action: str,
        *,
        platform: str | None = None,
        **params: Any,
    ) -> Any:
        """Execute a raw adapter API call on a configured platform instance.

        Args:
            platform_id: Platform adapter instance ID.
            action: Adapter action/method name.
            platform: Optional adapter type fallback name.
            **params: JSON-serializable action parameters.

        Returns:
            JSON-safe return value produced by the adapter client.
        """
        result = await self._ctx._invoke_capability(
            "platform.raw",
            "call_action",
            {
                "platform_id": platform_id,
                "platform": platform,
                "action": action,
                "params": params,
            },
        )
        return result.get("result") if isinstance(result, Mapping) else None


class CronClient:
    """Schedule Host-managed cron and one-shot jobs (``cron.schedule``)."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the cron client."""
        self._ctx = ctx

    async def add_basic_job(
        self,
        name: str,
        cron_expression: str,
        handler: Callable[..., Any],
        *,
        description: str | None = None,
        timezone: str | None = None,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
        persistent: bool = False,
    ) -> dict[str, Any]:
        """Register a recurring cron job executed via Host -> Runner callback.

        Args:
            name: Human-readable job name.
            cron_expression: Standard 5-field cron expression.
            handler: Async or sync callback executed when the job triggers.
            description: Optional job description.
            timezone: Optional IANA timezone string.
            payload: Optional JSON object passed as keyword args when firing.
            enabled: Whether the job starts enabled.
            persistent: Whether to persist the basic job record in DB.

        Returns:
            Serialized Host cron job metadata dictionary.
        """
        handler_id = f"cron:{uuid.uuid4().hex}"
        self._ctx.cron_handlers[handler_id] = handler
        result = await self._ctx._invoke_capability(
            "cron.schedule",
            "add_basic_job",
            {
                "handler_id": handler_id,
                "name": name,
                "cron_expression": cron_expression,
                "description": description,
                "timezone": timezone,
                "payload": dict(payload) if payload is not None else None,
                "enabled": enabled,
                "persistent": persistent,
            },
        )
        return dict(result.get("job") or {}) if isinstance(result, Mapping) else {}

    async def add_once_job(
        self,
        name: str,
        run_at: datetime | str,
        handler: Callable[..., Any],
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        job_id: str | None = None,
        replace_existing: bool = False,
    ) -> str:
        """Schedule a one-shot date-triggered job on the Host APScheduler.

        Args:
            name: Display job name.
            run_at: Target fire timestamp (datetime or ISO-8601 string).
            handler: Async or sync callback executed once at ``run_at``.
            args: Positional arguments forwarded when firing.
            kwargs: Keyword arguments forwarded when firing.
            job_id: Optional explicit APScheduler job ID.
            replace_existing: Replace an existing scheduler job with the same ID.

        Returns:
            Scheduled APScheduler job ID.
        """
        handler_id = f"cron:{uuid.uuid4().hex}"
        self._ctx.cron_handlers[handler_id] = handler
        run_date = run_at.isoformat() if isinstance(run_at, datetime) else str(run_at)
        options: dict[str, Any] = {
            "id": job_id or uuid.uuid4().hex,
            "name": name,
            "replace_existing": replace_existing,
        }
        result = await self._ctx._invoke_capability(
            "cron.schedule",
            "add_scheduler_job",
            {
                "handler_id": handler_id,
                "trigger": {"type": "date", "params": {"run_date": run_date}},
                "args": list(args),
                "kwargs": dict(kwargs) if kwargs is not None else {},
                "options": options,
            },
        )
        return str((result or {}).get("job_id") or options["id"])

    async def list_jobs(self, job_type: str | None = None) -> list[dict[str, Any]]:
        """List scheduled Host cron jobs."""
        result = await self._ctx._invoke_capability(
            "cron.schedule",
            "list_jobs",
            {"job_type": job_type},
        )
        return [dict(item) for item in (result or {}).get("jobs") or []]

    async def delete_job(self, job_id: str) -> None:
        """Delete a basic cron job by job_id."""
        await self._ctx._invoke_capability(
            "cron.schedule",
            "delete_job",
            {"job_id": str(job_id)},
        )

    async def remove_scheduler_job(self, job_id: str) -> None:
        """Remove a one-shot/APScheduler job by job_id."""
        await self._ctx._invoke_capability(
            "cron.schedule",
            "remove_job",
            {"job_id": str(job_id)},
        )


class KnowledgeBaseClient:
    """Manage and query Host knowledge bases (``kb.manage``)."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the knowledge-base client."""
        self._ctx = ctx

    async def create(
        self,
        kb_name: str,
        *,
        embedding_provider_id: str,
        description: str | None = None,
        emoji: str | None = None,
        rerank_provider_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k_dense: int | None = None,
        top_k_sparse: int | None = None,
        top_m_final: int | None = None,
    ) -> dict[str, Any]:
        """Create a knowledge base on the Host."""
        payload: dict[str, Any] = {
            "kb_name": kb_name,
            "embedding_provider_id": embedding_provider_id,
        }
        for key, value in (
            ("description", description),
            ("emoji", emoji),
            ("rerank_provider_id", rerank_provider_id),
            ("chunk_size", chunk_size),
            ("chunk_overlap", chunk_overlap),
            ("top_k_dense", top_k_dense),
            ("top_k_sparse", top_k_sparse),
            ("top_m_final", top_m_final),
        ):
            if value is not None:
                payload[key] = value
        result = await self._ctx._invoke_capability("kb.manage", "create_kb", payload)
        return dict((result or {}).get("kb") or {})

    async def list(self) -> list[dict[str, Any]]:
        """List all Host knowledge bases."""
        result = await self._ctx._invoke_capability("kb.manage", "list_kbs", {})
        return [dict(item) for item in (result or {}).get("kbs") or []]

    async def get(self, kb_id: str) -> dict[str, Any] | None:
        """Fetch one knowledge base record by ID."""
        result = await self._ctx._invoke_capability(
            "kb.manage",
            "get_kb",
            {"kb_id": kb_id},
        )
        kb = (result or {}).get("kb")
        return dict(kb) if isinstance(kb, Mapping) else None

    async def get_by_name(self, kb_name: str) -> dict[str, Any] | None:
        """Fetch one knowledge base record by name."""
        result = await self._ctx._invoke_capability(
            "kb.manage",
            "get_kb_by_name",
            {"kb_name": kb_name},
        )
        kb = (result or {}).get("kb")
        return dict(kb) if isinstance(kb, Mapping) else None

    async def delete(self, kb_id: str) -> bool:
        """Delete one knowledge base by ID."""
        result = await self._ctx._invoke_capability(
            "kb.manage",
            "delete_kb",
            {"kb_id": kb_id},
        )
        return bool((result or {}).get("deleted"))


class MessageHistoryClient:
    """Platform message history storage and queries (``message.history``)."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the message-history client."""
        self._ctx = ctx

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict[str, Any],
        *,
        sender_id: str | None = None,
        sender_name: str | None = None,
        turn_id: str | None = None,
        max_messages: int | None = None,
    ) -> dict[str, Any]:
        """Insert a raw platform history record."""
        result = await self._ctx._invoke_capability(
            "message.history",
            "insert",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "content": dict(content),
                "sender_id": sender_id,
                "sender_name": sender_name,
                "turn_id": turn_id,
                "max_messages": max_messages,
            },
        )
        return dict((result or {}).get("record") or {})

    async def insert_chain(
        self,
        platform_id: str,
        user_id: str,
        content: MessageLike,
        *,
        role: str = "user",
        sender_id: str | None = None,
        sender_name: str | None = None,
        max_messages: int | None = None,
    ) -> dict[str, Any]:
        """Insert a MessageChain history record after staging local media assets."""
        chain = await prepare_outbound_chain(
            to_message_chain(content),
            self._ctx.assets,
        )
        result = await self._ctx._invoke_capability(
            "message.history",
            "insert_message_chain",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "message_chain": chain,
                "role": role,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "max_messages": max_messages,
            },
        )
        return dict((result or {}).get("record") or {})

    async def get(
        self,
        platform_id: str,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        """Retrieve paginated message history records."""
        result = await self._ctx._invoke_capability(
            "message.history",
            "get",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "page": page,
                "page_size": page_size,
            },
        )
        return [dict(item) for item in (result or {}).get("records") or []]

    async def count(self, platform_id: str, user_id: str) -> int:
        """Count stored message history records for a user on a platform."""
        result = await self._ctx._invoke_capability(
            "message.history",
            "count",
            {"platform_id": platform_id, "user_id": user_id},
        )
        return int((result or {}).get("count") or 0)

    async def update(
        self,
        message_id: int,
        *,
        content: dict[str, Any] | None = None,
        turn_id: str | None = None,
    ) -> None:
        """Update one existing message history record by ID."""
        await self._ctx._invoke_capability(
            "message.history",
            "update",
            {
                "message_id": int(message_id),
                "content": dict(content) if content is not None else None,
                "turn_id": turn_id,
            },
        )

    async def delete(
        self,
        platform_id: str,
        user_id: str,
        *,
        offset_sec: int = 86400,
    ) -> None:
        """Delete aged history records for a user on a platform."""
        await self._ctx._invoke_capability(
            "message.history",
            "delete",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "offset_sec": int(offset_sec),
            },
        )

    async def delete_by_id(self, message_id: int) -> None:
        """Delete one history record by ID."""
        await self._ctx._invoke_capability(
            "message.history",
            "delete_by_id",
            {"message_id": int(message_id)},
        )


__all__ = [
    "CronClient",
    "EventStateClient",
    "KnowledgeBaseClient",
    "MessageHistoryClient",
    "PlatformClient",
]
