import asyncio
import re
from collections.abc import AsyncGenerator

from aiocqhttp import CQHttp, Event
from aiocqhttp.exceptions import ActionFailed

from astrbot import logger
from astrbot.core.message.components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Group, MessageMember
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult

from .forward_node_splitter import split_long_text_node


class AiocqhttpMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: CQHttp,
        forward_message_max_retries: int = 3,
        forward_message_fallback_enabled: bool = True,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._bot = bot
        self.forward_message_max_retries = forward_message_max_retries
        self.forward_message_fallback_enabled = forward_message_fallback_enabled

    @staticmethod
    async def _from_segment_to_dict(segment: BaseMessageComponent) -> dict:
        """修复部分字段"""
        if isinstance(segment, Image | Record):
            # For Image and Record segments, we convert them to base64
            bs64 = await segment.convert_to_base64()
            return {
                "type": segment.type.lower(),
                "data": {
                    "file": f"base64://{bs64}",
                },
            }
        if isinstance(segment, File):
            # For File segments, we need to handle the file differently
            d = await segment.to_dict()
            file_val = d.get("data", {}).get("file", "")
            if file_val:
                import pathlib

                try:
                    # 使用 pathlib 处理路径，能更好地处理 Windows/Linux 差异
                    path_obj = pathlib.Path(file_val)
                    # 如果是绝对路径且不包含协议头 (://)，则转换为标准的 file: URI
                    if path_obj.is_absolute() and "://" not in file_val:
                        d["data"]["file"] = path_obj.as_uri()
                except Exception:
                    # 如果不是合法路径（例如已经是特定的特殊字符串），则跳过转换
                    pass
            return d
        if isinstance(segment, Video):
            d = await segment.to_dict()
            return d
        return await segment.to_dict()

    @staticmethod
    async def _parse_onebot_json(message_chain: MessageChain):
        """解析成 OneBot json 格式"""
        ret = []
        for segment in message_chain.chain:
            if isinstance(segment, At):
                # At 组件后插入一个空格，避免与后续文本粘连
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
                ret.append({"type": "text", "data": {"text": " "}})
            elif isinstance(segment, Plain):
                if not segment.text.strip():
                    continue
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
            else:
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
        return ret

    @classmethod
    async def _dispatch_send(
        cls,
        bot: CQHttp,
        event: Event | None,
        is_group: bool,
        session_id: str | None,
        messages: list[dict],
    ) -> None:
        # session_id 必须是纯数字字符串
        session_id_int = (
            int(session_id) if session_id and session_id.isdigit() else None
        )
        routing_params = {}
        if isinstance(event, Event) and event.get("self_id"):
            routing_params["self_id"] = event["self_id"]

        if is_group and isinstance(session_id_int, int):
            await bot.send_group_msg(
                group_id=session_id_int,
                message=messages,
                **routing_params,
            )
        elif not is_group and isinstance(session_id_int, int):
            await bot.send_private_msg(
                user_id=session_id_int,
                message=messages,
                **routing_params,
            )
        elif isinstance(event, Event):  # 最后兜底
            await bot.send(event=event, message=messages)
        else:
            raise ValueError(
                f"无法发送消息：缺少有效的数字 session_id({session_id}) 或 event({event})",
            )

    @classmethod
    def _is_forward_size_error(cls, exc: ActionFailed) -> bool:
        detail = str(exc).lower()
        return any(
            marker in detail
            for marker in ("resid", "message too long", "content too long", "too large")
        )

    @staticmethod
    def _forward_plain_text(messages: list[object]) -> str | None:
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                return None
            data = message.get("data")
            content = data.get("content") if isinstance(data, dict) else None
            if not isinstance(content, list):
                return None
            for segment in content:
                if not isinstance(segment, dict) or segment.get("type") != "text":
                    return None
                segment_data = segment.get("data")
                text = (
                    segment_data.get("text") if isinstance(segment_data, dict) else None
                )
                if not isinstance(text, str):
                    return None
                parts.append(text)
        return "".join(parts)

    @classmethod
    async def _send_forward_with_fallback(
        cls,
        bot: CQHttp,
        payload: dict,
        event: Event | None,
        is_group: bool,
        session_id: str | None,
        max_retries: int = 3,
    ) -> None:
        action = "send_group_forward_msg" if is_group else "send_private_forward_msg"
        id_field = "group_id" if is_group else "user_id"

        async def send_chunk(messages: list[object]) -> None:
            chunk_payload = {id_field: session_id, "messages": messages}
            if isinstance(event, Event) and event.get("self_id"):
                chunk_payload["self_id"] = event["self_id"]
            await bot.call_action(action, **chunk_payload)

        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("Forward message payload did not contain nodes")
        try:
            await send_chunk(messages)
            return
        except ActionFailed as exc:
            if not cls._is_forward_size_error(exc):
                raise

        pending = [messages]
        retries = 0
        while pending:
            chunk = pending.pop(0)
            try:
                await send_chunk(chunk)
                continue
            except ActionFailed as exc:
                if not cls._is_forward_size_error(exc):
                    raise
                retries += 1
                if len(chunk) > 1 and retries <= max_retries:
                    midpoint = len(chunk) // 2
                    pending[:0] = [chunk[:midpoint], chunk[midpoint:]]
                    continue
                text = cls._forward_plain_text(chunk)
                if text is None:
                    raise
                for segment in split_long_text_node(
                    text, 1500, r"[^。？！~…]+[。？！~…]+"
                ):
                    await cls._dispatch_send(
                        bot,
                        event,
                        is_group,
                        session_id,
                        [{"type": "text", "data": {"text": segment}}],
                    )

    @classmethod
    async def send_message(
        cls,
        bot: CQHttp,
        message_chain: MessageChain,
        event: Event | None = None,
        is_group: bool = False,
        session_id: str | None = None,
        forward_message_max_retries: int = 3,
        forward_message_fallback_enabled: bool = True,
    ) -> None:
        """发送消息至 QQ 协议端（aiocqhttp）。

        Args:
            bot (CQHttp): aiocqhttp 机器人实例
            message_chain (MessageChain): 要发送的消息链
            event (Event | None, optional): aiocqhttp 事件对象.
            is_group (bool, optional): 是否为群消息.
            session_id (str | None, optional): 会话 ID（群号或 QQ 号

        """
        # 转发消息、文件消息不能和普通消息混在一起发送
        send_one_by_one = any(
            isinstance(seg, Node | Nodes | File) for seg in message_chain.chain
        )
        if not send_one_by_one:
            ret = await cls._parse_onebot_json(message_chain)
            if not ret:
                return
            await cls._dispatch_send(bot, event, is_group, session_id, ret)
            return
        for seg in message_chain.chain:
            if isinstance(seg, Node | Nodes):
                # 合并转发消息
                if isinstance(seg, Node):
                    nodes = Nodes([seg])
                    seg = nodes

                payload = await seg.to_dict()

                if forward_message_fallback_enabled:
                    await cls._send_forward_with_fallback(
                        bot,
                        payload,
                        event,
                        is_group,
                        session_id,
                        forward_message_max_retries,
                    )
                else:
                    action = (
                        "send_group_forward_msg"
                        if is_group
                        else "send_private_forward_msg"
                    )
                    payload["group_id" if is_group else "user_id"] = session_id
                    await bot.call_action(action, **payload)
            elif isinstance(seg, File):
                d = await cls._from_segment_to_dict(seg)
                await cls._dispatch_send(bot, event, is_group, session_id, [d])
            else:
                messages = await cls._parse_onebot_json(MessageChain([seg]))
                if not messages:
                    continue
                await cls._dispatch_send(bot, event, is_group, session_id, messages)
                await asyncio.sleep(0.5)

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        """发送消息"""
        event = getattr(self.message_obj, "raw_message", None)

        is_group = bool(self.get_group_id())
        session_id = self.get_group_id() if is_group else self.get_sender_id()

        await self.send_message(
            bot=self._bot,
            message_chain=message,
            event=event,  # 不强制要求一定是 Event
            is_group=is_group,
            session_id=session_id,
            forward_message_max_retries=self.forward_message_max_retries,
            forward_message_fallback_enabled=self.forward_message_fallback_enabled,
        )
        return await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        return await self.send_non_streaming_response(
            generator,
            use_fallback=use_fallback,
            sentence_pattern=re.compile(r"[^。？！~…]+[。？！~…]+"),
        )

    async def get_group(self, group_id=None, **kwargs):
        """Get OneBot group details while preserving inbound data on failures.

        Args:
            group_id: Optional OneBot group identifier.
            **kwargs: Reserved compatibility arguments.

        Returns:
            Enriched group information, or a basic group when an API is unavailable.
        """
        resolved_group_id = group_id or self.get_group_id()
        if not resolved_group_id:
            return None
        resolved_group_id = str(resolved_group_id)
        api_group_id = (
            int(resolved_group_id) if resolved_group_id.isdigit() else resolved_group_id
        )

        current_group = self.message_obj.group
        group = (
            current_group
            if current_group and current_group.group_id == resolved_group_id
            else Group(group_id=resolved_group_id)
        )

        routing_params = {}
        if getattr(self.message_obj, "self_id", None):
            routing_params["self_id"] = self.message_obj.self_id

        try:
            info = await self._bot.call_action(
                "get_group_info",
                group_id=api_group_id,
                **routing_params,
            )
            if isinstance(info, dict):
                group.group_name = info.get("group_name") or group.group_name
                member_count = info.get("member_count")
                if member_count is not None:
                    try:
                        group.member_count = int(member_count)
                    except TypeError, ValueError:
                        logger.warning(
                            "[aiocqhttp] Invalid member_count for group %s",
                            resolved_group_id,
                        )
        except Exception as exc:
            logger.warning(
                "[aiocqhttp] Failed to get group information for %s: %s",
                resolved_group_id,
                exc,
            )

        try:
            members = await self._bot.call_action(
                "get_group_member_list",
                group_id=api_group_id,
                **routing_params,
            )
        except Exception as exc:
            logger.warning(
                "[aiocqhttp] Failed to get members for group %s: %s",
                resolved_group_id,
                exc,
            )
            return group
        if not isinstance(members, list):
            return group

        owner_id = None
        admin_ids: list[str] = []
        for member in members:
            if not isinstance(member, dict) or member.get("user_id") is None:
                continue
            if member.get("role") == "owner":
                owner_id = str(member["user_id"])
            if member.get("role") == "admin":
                admin_ids.append(str(member["user_id"]))

        group.group_admins = admin_ids
        group.group_owner = owner_id
        group.members = [
            MessageMember(
                user_id=str(member["user_id"]),
                nickname=member.get("nickname") or member.get("card"),
            )
            for member in members
            if isinstance(member, dict) and member.get("user_id") is not None
        ]
        if group.member_count is None:
            group.member_count = len(group.members)
        return group
