from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.umo_alias import build_umo_alias_map, parse_umo, serialize_umo_alias


class ConversationServiceError(Exception):
    pass


@dataclass
class ConversationExport:
    file_obj: BytesIO
    filename: str
    mimetype: str = "application/jsonl"


class ConversationService:
    def __init__(
        self,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db_helper = db_helper
        self.conv_mgr = core_lifecycle.conversation_manager
        self.core_lifecycle = core_lifecycle

    async def list_conversations(
        self,
        *,
        page: int,
        page_size: int,
        platforms: str,
        message_types: str,
        search_query: str,
        exclude_ids: str,
        exclude_platforms: str,
        keyword_query: str = "",
        umo_query: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        group_by_session: bool = False,
        include_history: bool = True,
    ) -> dict:
        platform_list = [item.strip() for item in platforms.split(",") if item.strip()]
        message_type_list = [
            item.strip() for item in message_types.split(",") if item.strip()
        ]
        exclude_id_list = [
            item.strip() for item in exclude_ids.split(",") if item.strip()
        ]
        exclude_platform_list = [
            item.strip() for item in exclude_platforms.split(",") if item.strip()
        ]

        page = max(page, 1)
        if page_size < 1:
            page_size = 20
        page_size = min(page_size, 100)

        try:
            conversations, total_count = await self.conv_mgr.get_filtered_conversations(
                page=page,
                page_size=page_size,
                platforms=platform_list,
                message_types=message_type_list,
                search_query=search_query,
                exclude_ids=exclude_id_list,
                exclude_platforms=exclude_platform_list,
                keyword_query=keyword_query.strip(),
                umo_query=umo_query.strip(),
                sort_by=sort_by,
                sort_order=sort_order,
                group_by_session=group_by_session,
                include_history=include_history,
            )
        except Exception as exc:
            logger.error(f"数据库查询出错: {exc!s}\n{traceback.format_exc()}")
            raise ConversationServiceError(f"数据库查询出错: {exc!s}") from exc

        total_pages = (
            (total_count + page_size - 1) // page_size if total_count > 0 else 1
        )
        umos = sorted({conv.user_id for conv in conversations if conv.user_id})
        alias_map = build_umo_alias_map(await self.db_helper.get_umo_aliases(umos))
        webchat_titles = await self._get_webchat_titles(conversations)

        return {
            "conversations": [
                self._serialize_conversation(
                    conversation,
                    alias_map,
                    include_history=include_history,
                    webchat_title=webchat_titles.get(conversation.user_id, ""),
                )
                for conversation in conversations
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": total_pages,
                "grouped_by_session": group_by_session,
            },
        }

    async def get_filter_options(self) -> dict:
        """Build robot filter options from configured conversation platforms.

        Returns:
            Robot IDs and adapter types that exist in both configuration and
            conversation history.
        """
        history_platform_ids = set(await self.db_helper.get_conversation_platform_ids())
        configured_platforms = self.core_lifecycle.astrbot_config.get("platform", [])
        bots = [
            {
                "id": str(platform.get("id", "")),
                "type": str(platform.get("type", "")),
            }
            for platform in configured_platforms
            if platform.get("id") in history_platform_ids
        ]

        # WebChat is a built-in platform that the platform manager always
        # starts regardless of config, so expose it as a filterable bot ID even
        # when it is missing from the configured platform list.
        if "webchat" in history_platform_ids and not any(
            bot["id"] == "webchat" for bot in bots
        ):
            bots.append({"id": "webchat", "type": "webchat"})

        return {"bots": bots}

    async def get_conversation_detail(self, data: object) -> dict:
        payload = self._payload(data)
        user_id, cid = self._require_user_and_cid(payload)

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=user_id,
            conversation_id=cid,
        )
        if not conversation:
            raise ConversationServiceError("对话不存在")

        webchat_titles = await self._get_webchat_titles([conversation])
        alias_map = build_umo_alias_map(await self.db_helper.get_umo_aliases([user_id]))
        return {
            "user_id": user_id,
            "cid": cid,
            "title": conversation.title
            or webchat_titles.get(conversation.user_id, "")
            or None,
            "persona_id": conversation.persona_id,
            "history": conversation.history,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "umo_info": self._build_umo_info(user_id, alias_map),
        }

    async def update_conversation(self, data: object) -> dict:
        payload = self._payload(data)
        user_id, cid = self._require_user_and_cid(payload)
        title = payload.get("title")

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=user_id,
            conversation_id=cid,
        )
        if not conversation:
            raise ConversationServiceError("对话不存在")

        persona_id = payload.get("persona_id", conversation.persona_id)

        if title is not None or persona_id is not None:
            await self.conv_mgr.update_conversation(
                unified_msg_origin=user_id,
                conversation_id=cid,
                title=title,
                persona_id=persona_id,
            )
        return {"message": "对话信息更新成功"}

    async def delete_conversation(self, data: object) -> dict:
        payload = self._payload(data)
        if "conversations" in payload:
            return await self._delete_conversations(payload.get("conversations", []))

        user_id, cid = self._require_user_and_cid(payload)
        await self.conv_mgr.delete_conversation(
            unified_msg_origin=user_id,
            conversation_id=cid,
        )
        return {"message": "对话删除成功"}

    async def update_history(self, data: object) -> dict:
        payload = self._payload(data)
        user_id, cid = self._require_user_and_cid(payload)
        history = payload.get("history")

        if history is None:
            raise ConversationServiceError("缺少必要参数: history")

        history = self._normalize_history(history)

        conversation = await self.conv_mgr.get_conversation(
            unified_msg_origin=user_id,
            conversation_id=cid,
        )
        if not conversation:
            raise ConversationServiceError("对话不存在")

        await self.conv_mgr.update_conversation(
            unified_msg_origin=user_id,
            conversation_id=cid,
            history=history,
        )

        return {"message": "对话历史更新成功"}

    async def export_conversations(self, data: object) -> ConversationExport:
        payload = self._payload(data)
        conversations_to_export = payload.get("conversations", [])

        if not conversations_to_export:
            raise ConversationServiceError("导出列表不能为空")

        jsonl_lines = []
        exported_count = 0
        failed_items = []

        for conv_info in conversations_to_export:
            user_id = conv_info.get("user_id")
            cid = conv_info.get("cid")

            if not user_id or not cid:
                failed_items.append(f"user_id:{user_id}, cid:{cid} - 缺少必要参数")
                continue

            try:
                conversation = await self.conv_mgr.get_conversation(
                    unified_msg_origin=user_id,
                    conversation_id=cid,
                )

                if not conversation:
                    failed_items.append(f"user_id:{user_id}, cid:{cid} - 对话不存在")
                    continue

                webchat_titles = await self._get_webchat_titles([conversation])
                content = json.loads(conversation.history)
                export_record = {
                    "cid": cid,
                    "user_id": user_id,
                    "platform_id": conversation.platform_id,
                    "title": conversation.title
                    or webchat_titles.get(conversation.user_id, "")
                    or None,
                    "persona_id": conversation.persona_id,
                    "created_at": conversation.created_at,
                    "updated_at": conversation.updated_at,
                    "content": content,
                }
                jsonl_lines.append(json.dumps(export_record, ensure_ascii=False))
                exported_count += 1
            except Exception as exc:
                failed_items.append(f"user_id:{user_id}, cid:{cid} - {exc!s}")
                logger.error(
                    f"导出对话失败: user_id={user_id}, cid={cid}, error={exc!s}"
                )

        if exported_count == 0:
            raise ConversationServiceError("没有成功导出任何对话")

        jsonl_content = "\n".join(jsonl_lines)
        file_obj = BytesIO(jsonl_content.encode("utf-8"))
        file_obj.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return ConversationExport(
            file_obj=file_obj,
            filename=f"astrbot_conversations_export_{timestamp}.jsonl",
        )

    async def _delete_conversations(self, conversations: object) -> dict:
        if not isinstance(conversations, list) or not conversations:
            raise ConversationServiceError("批量删除时conversations参数不能为空")

        deleted_count = 0
        failed_items = []

        for conv in conversations:
            if not isinstance(conv, dict):
                failed_items.append(f"{conv!r} - 格式错误")
                continue
            user_id = conv.get("user_id")
            cid = conv.get("cid")

            if not user_id or not cid:
                failed_items.append(f"user_id:{user_id}, cid:{cid} - 缺少必要参数")
                continue

            try:
                await self.conv_mgr.delete_conversation(
                    unified_msg_origin=user_id,
                    conversation_id=cid,
                )
                deleted_count += 1
            except Exception as exc:
                failed_items.append(f"user_id:{user_id}, cid:{cid} - {exc!s}")

        message = f"成功删除 {deleted_count} 个对话"
        if failed_items:
            message += f"，失败 {len(failed_items)} 个"

        return {
            "message": message,
            "deleted_count": deleted_count,
            "failed_count": len(failed_items),
            "failed_items": failed_items,
        }

    @staticmethod
    def _webchat_session_id(user_id: str | None) -> str:
        """Extract the WebChat session ID from a unified message origin.

        Args:
            user_id: Unified message origin such as
                ``webchat:FriendMessage:webchat!creator!session_id``.

        Returns:
            The trailing session ID segment, or an empty string when the
            origin does not carry one.
        """
        umo = user_id or ""
        if "!" not in umo:
            return ""
        return umo.rsplit("!", 1)[-1]

    async def _get_webchat_titles(self, conversations) -> dict[str, str]:
        """Resolve WebChat session titles for conversations.

        WebChat generates and stores its title on the platform session while
        the conversation history reads the conversation title column, so the
        session display name is used as a fallback. Title lookup failures only
        degrade the fallback instead of failing the whole request.

        Args:
            conversations: Conversation objects returned by the conversation manager.

        Returns:
            Mapping from unified message origin to the WebChat session title.
        """
        session_ids: dict[str, str] = {}
        for conversation in conversations:
            if conversation.platform_id != "webchat":
                continue
            session_id = self._webchat_session_id(conversation.user_id)
            if session_id:
                session_ids[conversation.user_id] = session_id
        if not session_ids:
            return {}

        try:
            sessions = await self.db_helper.get_platform_sessions_by_ids(
                list(set(session_ids.values())),
            )
        except Exception as exc:
            logger.warning(f"查询 WebChat 会话标题失败: {exc!s}")
            return {}

        display_names = {
            session.session_id: session.display_name
            for session in sessions
            if session.display_name
        }
        return {
            user_id: display_names.get(session_id, "")
            for user_id, session_id in session_ids.items()
        }

    def _serialize_conversation(
        self,
        conversation,
        alias_map: dict,
        *,
        include_history: bool,
        webchat_title: str = "",
    ) -> dict:
        """Serialize a conversation for a list response.

        Args:
            conversation: Conversation object returned by the manager.
            alias_map: UMO aliases keyed by unified message origin.
            include_history: Whether to include the serialized message history.
            webchat_title: WebChat session title used when the conversation
                itself has no title.

        Returns:
            Conversation data suitable for a dashboard API response.
        """
        result = {
            "platform_id": conversation.platform_id,
            "user_id": conversation.user_id,
            "cid": conversation.cid,
            "title": conversation.title or webchat_title or None,
            "persona_id": conversation.persona_id,
            "token_usage": conversation.token_usage,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "umo_info": self._build_umo_info(conversation.user_id, alias_map),
        }
        if include_history:
            result["history"] = conversation.history
        return result

    @staticmethod
    def _build_umo_info(umo: str | None, alias_map: dict) -> dict:
        umo_str = umo or ""
        return {
            "umo": umo_str,
            **parse_umo(umo_str),
            **serialize_umo_alias(alias_map.get(umo_str), umo_str),
        }

    @staticmethod
    def _require_user_and_cid(payload: dict) -> tuple[str, str]:
        user_id = payload.get("user_id")
        cid = payload.get("cid")
        if not user_id or not cid:
            raise ConversationServiceError("缺少必要参数: user_id 和 cid")
        return user_id, cid

    @staticmethod
    def _normalize_history(history):
        try:
            if isinstance(history, list):
                history = json.dumps(history)
            else:
                json.loads(history)
        except json.JSONDecodeError as exc:
            raise ConversationServiceError(
                "history 必须是有效的 JSON 字符串或数组"
            ) from exc

        return json.loads(history) if isinstance(history, str) else history

    @staticmethod
    def _payload(data: object) -> dict:
        return data if isinstance(data, dict) else {}
