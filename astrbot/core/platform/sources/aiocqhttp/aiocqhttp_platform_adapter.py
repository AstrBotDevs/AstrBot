import asyncio
import inspect
import itertools
import logging
import time
import uuid
from collections.abc import Awaitable, Coroutine
from typing import Any, TypedDict

from aiocqhttp import CQHttp, Event
from aiocqhttp.exceptions import ActionFailed

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    ComponentTypes,
    File,
    Plain,
    Poke,
    Reply,
)
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import register_platform_adapter

from .aiocqhttp_message_event import AiocqhttpMessageEvent


class OneBotSenderPayload(TypedDict, total=False):
    user_id: str | int
    card: str
    nickname: str


class OneBotMessageSegmentData(TypedDict, total=False):
    text: str
    url: str
    file_name: str
    name: str
    file: str
    file_id: str | int
    id: str | int
    qq: str | int
    markdown: str
    content: str


class OneBotMessageSegment(TypedDict):
    type: str
    data: OneBotMessageSegmentData


def _normalize_object_dict(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    return {key: value for key, value in raw.items() if isinstance(key, str)}


def _normalize_sender(raw: object) -> OneBotSenderPayload | None:
    raw_sender = _normalize_object_dict(raw)
    if raw_sender is None:
        return None

    sender: OneBotSenderPayload = {}
    user_id = raw_sender.get("user_id")
    if isinstance(user_id, str | int):
        sender["user_id"] = user_id
    card = raw_sender.get("card")
    if isinstance(card, str):
        sender["card"] = card
    nickname = raw_sender.get("nickname")
    if isinstance(nickname, str):
        sender["nickname"] = nickname
    return sender if "user_id" in sender else None


def _normalize_segment_data(raw: object) -> OneBotMessageSegmentData:
    raw_data = _normalize_object_dict(raw) or {}
    data: OneBotMessageSegmentData = {}

    text = raw_data.get("text")
    if isinstance(text, str):
        data["text"] = text
    url = raw_data.get("url")
    if isinstance(url, str):
        data["url"] = url
    file_name = raw_data.get("file_name")
    if isinstance(file_name, str):
        data["file_name"] = file_name
    name = raw_data.get("name")
    if isinstance(name, str):
        data["name"] = name
    file = raw_data.get("file")
    if isinstance(file, str):
        data["file"] = file
    file_id = raw_data.get("file_id")
    if isinstance(file_id, str | int):
        data["file_id"] = file_id
    reply_id = raw_data.get("id")
    if isinstance(reply_id, str | int):
        data["id"] = reply_id
    qq = raw_data.get("qq")
    if isinstance(qq, str | int):
        data["qq"] = qq
    markdown = raw_data.get("markdown")
    if isinstance(markdown, str):
        data["markdown"] = markdown
    content = raw_data.get("content")
    if isinstance(content, str):
        data["content"] = content

    return data


def _normalize_segment(raw: object) -> OneBotMessageSegment | None:
    raw_segment = _normalize_object_dict(raw)
    if raw_segment is None:
        return None

    segment_type = raw_segment.get("type")
    if not isinstance(segment_type, str):
        return None

    return {
        "type": segment_type,
        "data": _normalize_segment_data(raw_segment.get("data")),
    }


def _get_optional_str(mapping: dict[str, object] | None, key: str) -> str | None:
    if mapping is None:
        return None
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _instantiate_component(
    factory: Any,
    data: OneBotMessageSegmentData,
) -> BaseMessageComponent:
    return factory(**data)


@register_platform_adapter(
    "aiocqhttp",
    "适用于 OneBot V11 标准的消息平台适配器,支持反向 WebSockets｡",
    support_streaming_message=False,
)
class AiocqhttpAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.host = platform_config["ws_reverse_host"]
        self.port = platform_config["ws_reverse_port"]
        platform_id = self.config.get("id")
        self.metadata = PlatformMetadata(
            name="aiocqhttp",
            description="适用于 OneBot 标准的消息平台适配器,支持反向 WebSockets｡",
            id=str(platform_id) if platform_id is not None else "",
            support_streaming_message=False,
        )
        self.bot = CQHttp(
            use_ws_reverse=True,
            import_name="aiocqhttp",
            api_timeout_sec=180,
            access_token=platform_config.get("ws_reverse_token"),
        )

        @self.bot.on_request()
        async def request(event: Event) -> None:
            try:
                abm = await self.convert_message(event)
                if not abm:
                    return
                await self.handle_msg(abm)
            except Exception as e:
                logger.exception(f"Handle request message failed: {e}")
                return

        @self.bot.on_notice()
        async def notice(event: Event) -> None:
            try:
                abm = await self.convert_message(event)
                if abm:
                    await self.handle_msg(abm)
            except Exception as e:
                logger.exception(f"Handle notice message failed: {e}")
                return

        @self.bot.on_message("group")
        async def group(event: Event) -> None:
            try:
                abm = await self.convert_message(event)
                if abm:
                    await self.handle_msg(abm)
            except Exception as e:
                logger.exception(f"Handle group message failed: {e}")
                return

        @self.bot.on_message("private")
        async def private(event: Event) -> None:
            try:
                abm = await self.convert_message(event)
                if abm:
                    await self.handle_msg(abm)
            except Exception as e:
                logger.exception(f"Handle private message failed: {e}")
                return

        @self.bot.on_websocket_connection
        def on_websocket_connection(_) -> None:
            logger.info("aiocqhttp(OneBot v11) 适配器已连接｡")

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        is_group = session.message_type == MessageType.GROUP_MESSAGE
        if is_group:
            session_id = session.session_id.split("_")[-1]
        else:
            session_id = session.session_id
        await AiocqhttpMessageEvent.send_message(
            bot=self.bot,
            message_chain=message_chain,
            event=None,
            is_group=is_group,
            session_id=session_id,
        )
        await super().send_by_session(session, message_chain)

    async def convert_message(self, event: Event) -> AstrBotMessage | None:
        logger.debug(f"[aiocqhttp] RawMessage {event}")
        if event["post_type"] == "message":
            abm = await self._convert_handle_message_event(event)
            if abm.sender.user_id == "2854196310":
                return None
        elif event["post_type"] == "notice":
            abm = await self._convert_handle_notice_event(event)
        elif event["post_type"] == "request":
            abm = await self._convert_handle_request_event(event)
        return abm

    async def _convert_handle_request_event(self, event: Event) -> AstrBotMessage:
        """OneBot V11 请求类事件"""
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(
            user_id=str(event.user_id),
            nickname=str(event.user_id),
        )
        abm.type = MessageType.OTHER_MESSAGE
        if event.get("group_id"):
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(event.group_id)
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = (
            str(event.group_id)
            if abm.type == MessageType.GROUP_MESSAGE
            else abm.sender.user_id
        )
        abm.message_str = ""
        abm.message = []
        abm.timestamp = int(time.time())
        abm.message_id = uuid.uuid4().hex
        abm.raw_message = event
        return abm

    async def _convert_handle_notice_event(self, event: Event) -> AstrBotMessage:
        """OneBot V11 通知类事件"""
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(
            user_id=str(event.user_id),
            nickname=str(event.user_id),
        )
        abm.type = MessageType.OTHER_MESSAGE
        if event.get("group_id"):
            abm.group_id = str(event.group_id)
            abm.type = MessageType.GROUP_MESSAGE
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = (
            str(event.group_id)
            if abm.type == MessageType.GROUP_MESSAGE
            else abm.sender.user_id
        )
        abm.message_str = ""
        abm.message = []
        abm.raw_message = event
        abm.timestamp = int(time.time())
        abm.message_id = uuid.uuid4().hex
        if "sub_type" in event:
            if event["sub_type"] == "poke" and "target_id" in event:
                abm.message.append(Poke(id=str(event["target_id"])))
        return abm

    async def _convert_handle_message_event(
        self,
        event: Event,
        get_reply=True,
    ) -> AstrBotMessage:
        """OneBot V11 消息类事件

        @param event: 事件对象
        @param get_reply: 是否获取回复消息｡这个参数是为了防止多个回复嵌套｡
        """
        sender = _normalize_sender(event.sender)
        if sender is None:
            raise ValueError("aiocqhttp: sender payload is missing or invalid")
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(
            str(sender["user_id"]),
            sender.get("card") or sender.get("nickname") or "N/A",
        )
        if event["message_type"] == "group":
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(event.group_id)
            abm.group = Group(str(event.group_id))
            abm.group.group_name = event.get("group_name", "N/A")
        elif event["message_type"] == "private":
            abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = (
            str(event.group_id)
            if abm.type == MessageType.GROUP_MESSAGE
            else abm.sender.user_id
        )
        abm.message_id = str(event.message_id)
        abm.message = []
        message_str = ""
        if not isinstance(event.message, list):
            err = f"aiocqhttp: 无法识别的消息类型: {event.message!s},此条消息将被忽略｡如果您在使用 go-cqhttp,请将其配置文件中的 message.post-format 更改为 array｡"
            logger.critical(err)
            try:
                await self.bot.send(event, err)
            except BaseException as e:
                logger.error(f"回复消息失败: {e}")
            raise ValueError(err)
        normalized_segments = [
            segment
            for raw_segment in event.message
            if (segment := _normalize_segment(raw_segment)) is not None
        ]
        for t, m_group in itertools.groupby(
            normalized_segments,
            key=lambda segment: segment["type"],
        ):
            a = None
            if t == "text":
                current_text = "".join(
                    segment["data"].get("text", "") for segment in m_group
                ).strip()
                if not current_text:
                    continue
                message_str += current_text
                a = Plain(text=current_text)
                abm.message.append(a)
            elif t == "file":
                for m in m_group:
                    data = m["data"]
                    file_url = data.get("url")
                    if file_url and file_url.startswith("http"):
                        logger.info("guessing lagrange")
                        file_name = (
                            data.get("file_name", "")
                            or data.get("name", "")
                            or data.get("file", "")
                            or "file"
                        )
                        abm.message.append(File(name=file_name, url=file_url))
                    else:
                        try:
                            file_id = data.get("file_id")
                            if file_id is None:
                                logger.error("文件消息缺少 file_id: %s", data)
                                continue
                            ret_data: dict[str, object] | None = None
                            if abm.type == MessageType.GROUP_MESSAGE:
                                ret = await self.bot.call_action(
                                    action="get_group_file_url",
                                    file_id=file_id,
                                    group_id=event.group_id,
                                )
                                ret_data = _normalize_object_dict(ret)
                            elif abm.type == MessageType.FRIEND_MESSAGE:
                                ret = await self.bot.call_action(
                                    action="get_private_file_url",
                                    file_id=file_id,
                                )
                                ret_data = _normalize_object_dict(ret)
                            resolved_url = _get_optional_str(ret_data, "url")
                            if resolved_url:
                                file_name = (
                                    _get_optional_str(ret_data, "file_name")
                                    or _get_optional_str(ret_data, "name")
                                    or data.get("file", "")
                                    or data.get("file_name", "")
                                    or "file"
                                )
                                a = File(name=file_name, url=resolved_url)
                                abm.message.append(a)
                            else:
                                logger.error(f"获取文件失败: {ret_data}")
                        except ActionFailed as e:
                            logger.error(f"获取文件失败: {e},此消息段将被忽略｡")
                        except BaseException as e:
                            logger.error(f"获取文件失败: {e},此消息段将被忽略｡")
            elif t == "reply":
                for m in m_group:
                    data = m["data"]
                    if not get_reply:
                        a = _instantiate_component(ComponentTypes[t], data)
                        abm.message.append(a)
                    else:
                        try:
                            reply_message_id = data.get("id")
                            if reply_message_id is None:
                                logger.error("回复消息缺少 id: %s", data)
                                continue
                            reply_event_data = await self.bot.call_action(
                                action="get_msg",
                                message_id=int(reply_message_id),
                            )
                            reply_event_payload = _normalize_object_dict(
                                reply_event_data,
                            )
                            if reply_event_payload is None:
                                logger.error(
                                    "无法识别的回复消息数据: %s",
                                    reply_event_data,
                                )
                                continue
                            reply_event_payload["post_type"] = "message"
                            new_event = Event.from_payload(reply_event_payload)
                            if not new_event:
                                logger.error(
                                    f"无法从回复消息数据构造 Event 对象: {reply_event_payload}",
                                )
                                continue
                            abm_reply = await self._convert_handle_message_event(
                                new_event,
                                get_reply=False,
                            )
                            reply_seg = Reply(
                                id=abm_reply.message_id,
                                chain=abm_reply.message,
                                sender_id=abm_reply.sender.user_id,
                                sender_nickname=abm_reply.sender.nickname,
                                time=abm_reply.timestamp,
                                message_str=abm_reply.message_str,
                                text=abm_reply.message_str,
                                qq=abm_reply.sender.user_id,
                            )
                            abm.message.append(reply_seg)
                        except BaseException as e:
                            logger.error(f"获取引用消息失败: {e}｡")
                            a = _instantiate_component(ComponentTypes[t], data)
                            abm.message.append(a)
            elif t == "at":
                first_at_self_processed = False
                at_parts = []
                for m in m_group:
                    data = m["data"]
                    try:
                        qq = data.get("qq")
                        if qq is None:
                            logger.error("At 消息缺少 qq: %s", data)
                            continue
                        qq_str = str(qq)
                        if qq_str == "all":
                            abm.message.append(At(qq="all", name="全体成员"))
                            continue
                        at_info = await self.bot.call_action(
                            action="get_group_member_info",
                            group_id=event.group_id,
                            user_id=int(qq),
                            no_cache=False,
                        )
                        at_info_data = _normalize_object_dict(at_info)
                        if at_info_data:
                            nickname = _get_optional_str(at_info_data, "card") or ""
                            if nickname == "":
                                at_info = await self.bot.call_action(
                                    action="get_stranger_info",
                                    user_id=int(qq),
                                    no_cache=False,
                                )
                                at_info_data = _normalize_object_dict(at_info)
                                nickname = _get_optional_str(
                                    at_info_data,
                                    "nick",
                                ) or _get_optional_str(
                                    at_info_data,
                                    "nickname",
                                )
                            is_at_self = qq_str in {abm.self_id, "all"}
                            abm.message.append(At(qq=qq_str, name=nickname or ""))
                            if is_at_self and (not first_at_self_processed):
                                first_at_self_processed = True
                            else:
                                at_parts.append(f" @{nickname}({qq_str}) ")
                        else:
                            abm.message.append(At(qq=qq_str, name=""))
                    except ActionFailed as e:
                        logger.error(f"获取 @ 用户信息失败: {e},此消息段将被忽略｡")
                    except BaseException as e:
                        logger.error(f"获取 @ 用户信息失败: {e},此消息段将被忽略｡")
                message_str += "".join(at_parts)
            elif t == "markdown":
                for m in m_group:
                    data = m["data"]
                    text = data.get("markdown") or data.get("content", "")
                    abm.message.append(Plain(text=text))
                    message_str += text
            else:
                for m in m_group:
                    data = m["data"]
                    try:
                        if t not in ComponentTypes:
                            logger.warning(
                                f"不支持的消息段类型,已忽略: {t}, data={data}",
                            )
                            continue
                        a = _instantiate_component(ComponentTypes[t], data)
                        abm.message.append(a)
                    except Exception as e:
                        logger.exception(
                            f"消息段解析失败: type={t}, data={data}. {e}",
                        )
                        continue
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event
        return abm

    def run(self) -> Coroutine[Any, Any, None]:
        if not self.host or not self.port:
            logger.warning(
                "aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port,将使用默认值:http://0.0.0.0:6199",
            )
            self.host = "0.0.0.0"
            self.port = 6199
        coro = self.bot.run_task(
            host=self.host,
            port=int(self.port),
            shutdown_trigger=self.shutdown_trigger_placeholder,
        )
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.getLogger("aiocqhttp").setLevel(logging.ERROR)
        self.shutdown_event = asyncio.Event()
        return coro

    async def terminate(self) -> None:
        if hasattr(self, "shutdown_event"):
            self.shutdown_event.set()
        await self._close_reverse_ws_connections()

    async def _close_reverse_ws_connections(self) -> None:
        api_clients = getattr(self.bot, "_wsr_api_clients", None)
        event_clients = getattr(self.bot, "_wsr_event_clients", None)
        ws_clients: set[Any] = set()
        if isinstance(api_clients, dict):
            ws_clients.update(api_clients.values())
        if isinstance(event_clients, set):
            ws_clients.update(event_clients)
        close_tasks: list[Awaitable[Any]] = []
        for ws in ws_clients:
            close_func = getattr(ws, "close", None)
            if not callable(close_func):
                continue
            try:
                close_result = close_func(code=1000, reason="Adapter shutdown")
            except TypeError:
                close_result = close_func()
            except Exception:
                continue
            if inspect.isawaitable(close_result):
                close_tasks.append(close_result)
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        if isinstance(api_clients, dict):
            api_clients.clear()
        if isinstance(event_clients, set):
            event_clients.clear()

    async def shutdown_trigger_placeholder(self) -> None:
        await self.shutdown_event.wait()
        logger.info("aiocqhttp 适配器已被关闭")

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = AiocqhttpMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            bot=self.bot,
        )
        self.commit_event(message_event)

    def get_client(self) -> CQHttp:
        return self.bot
