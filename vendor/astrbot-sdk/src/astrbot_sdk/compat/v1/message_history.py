"""Legacy message_history_manager facade over the message.history capability."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class MessageHistoryManagerFacade:
    """Legacy platform message history access forwarded to the Host."""

    def __init__(self, facade_context: Any) -> None:
        """Initialize the facade.

        Args:
            facade_context: Legacy Context facade used to reach the Host.
        """
        self._facade_context = facade_context

    async def _call(self, operation: str, payload: dict[str, Any]) -> Any:
        return await self._facade_context._ctx._invoke_capability(
            "message.history",
            operation,
            payload,
        )

    @staticmethod
    def _record(data: dict[str, Any] | None) -> SimpleNamespace | None:
        """Convert a serialized history record into attribute access."""
        return SimpleNamespace(**data) if data else None

    async def insert(
        self,
        platform_id: str,
        user_id: str,
        content: dict,
        sender_id: str | None = None,
        sender_name: str | None = None,
        llm_checkpoint_id: str | None = None,
        max_messages: int | None = None,
    ) -> SimpleNamespace:
        """Insert one history record on the Host."""
        result = await self._call(
            "insert",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "content": content,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "llm_checkpoint_id": llm_checkpoint_id,
                "max_messages": max_messages,
            },
        )
        return self._record((result or {}).get("record"))

    async def insert_message_chain(
        self,
        platform_id: str,
        user_id: str,
        message_chain: Any,
        role: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
        max_messages: int | None = None,
    ) -> SimpleNamespace | None:
        """Insert one message-chain history record on the Host.

        The compat MessageChain is converted to the SDK chain, which the RPC
        layer encodes natively.
        """
        chain = (
            message_chain.to_sdk()
            if hasattr(message_chain, "to_sdk")
            else message_chain
        )
        result = await self._call(
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
        return self._record((result or {}).get("record"))

    async def get(
        self,
        platform_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 200,
    ) -> list:
        """List history records for one platform/user scope."""
        result = await self._call(
            "get",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "page": page,
                "page_size": page_size,
            },
        )
        return [SimpleNamespace(**item) for item in (result or {}).get("records") or []]

    async def count(self, platform_id: str, user_id: str) -> int:
        """Count history records for one platform/user scope."""
        result = await self._call(
            "count",
            {"platform_id": platform_id, "user_id": user_id},
        )
        return int((result or {}).get("count") or 0)

    async def delete(
        self,
        platform_id: str,
        user_id: str,
        offset_sec: int = 86400,
    ) -> None:
        """Delete history older than offset_sec for one scope."""
        await self._call(
            "delete",
            {
                "platform_id": platform_id,
                "user_id": user_id,
                "offset_sec": offset_sec,
            },
        )

    async def update(
        self,
        message_id: int,
        content: dict | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """Update one history record on the Host."""
        await self._call(
            "update",
            {
                "message_id": message_id,
                "content": content,
                "llm_checkpoint_id": llm_checkpoint_id,
            },
        )

    async def delete_by_id(self, message_id: int) -> None:
        """Delete one history record by ID on the Host."""
        await self._call("delete_by_id", {"message_id": message_id})
