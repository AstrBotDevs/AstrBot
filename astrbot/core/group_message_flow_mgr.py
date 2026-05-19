from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import GroupMessageFlowCursor, GroupMessageFlowRecord


class GroupMessageFlowManager:
    """Manage persisted group message flows and per-conversation cursors."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def insert_record(
        self,
        platform_id: str,
        flow_session_id: str,
        content: list,
        rendered_text: str,
        group_id: str | None = None,
        sender_id: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
    ) -> GroupMessageFlowRecord:
        return await self.db.insert_group_message_flow_record(
            platform_id=platform_id,
            flow_session_id=flow_session_id,
            group_id=group_id,
            sender_id=sender_id,
            sender_name=sender_name,
            role=role,
            content=content,
            rendered_text=rendered_text,
        )

    async def get_records_after(
        self,
        flow_session_id: str,
        after_id: int,
        before_id: int | None = None,
        limit: int = 0,
    ) -> list[GroupMessageFlowRecord]:
        return await self.db.get_group_message_flow_records_after(
            flow_session_id=flow_session_id,
            after_id=after_id,
            before_id=before_id,
            limit=limit,
        )

    async def get_latest_record_id(self, flow_session_id: str) -> int:
        return await self.db.get_latest_group_message_flow_record_id(flow_session_id)

    async def get_cursor(
        self,
        flow_session_id: str,
        conversation_id: str,
    ) -> GroupMessageFlowCursor | None:
        return await self.db.get_group_message_flow_cursor(
            flow_session_id=flow_session_id,
            conversation_id=conversation_id,
        )

    async def set_cursor(
        self,
        platform_id: str,
        flow_session_id: str,
        conversation_id: str,
        last_record_id: int,
    ) -> GroupMessageFlowCursor:
        return await self.db.upsert_group_message_flow_cursor(
            platform_id=platform_id,
            flow_session_id=flow_session_id,
            conversation_id=conversation_id,
            last_record_id=last_record_id,
        )

    async def prune_records(self, flow_session_id: str, max_records: int) -> None:
        await self.db.prune_group_message_flow_records(flow_session_id, max_records)
