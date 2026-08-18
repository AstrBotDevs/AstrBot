import asyncio
import inspect
import itertools
import logging
import time
import uuid
from collections.abc import Awaitable, Coroutine
from typing import Any, cast

from aiocqhttp import CQHttp, Event
from aiocqhttp.exceptions import ActionFailed

from astrbot import logger
from astrbot.core.message.components import *
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSession

from ...register import register_platform_adapter
from .aiocqhttp_message_event import *
from .aiocqhttp_message_event import AiocqhttpMessageEvent


def _payload_field(payload: Any, name: str) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(name)
    getter = getattr(payload, "get", None)
    if callable(getter):
        try:
            return getter(name)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
    return getattr(payload, name, None)


@register_platform_adapter(
    "aiocqhttp",
    "适用于 OneBot V11 标准的消息平台适配器，支持反向 WebSockets。",
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
        self.forward_message_max_retries = int(
            platform_config.get("forward_message_max_retries", 3)
        )
        self.forward_message_fallback_enabled = bool(
            platform_config.get("forward_message_fallback_enabled", True)
        )

        self.metadata = PlatformMetadata(
            name="aiocqhttp",
            description="适用于 OneBot 标准的消息平台适配器，支持反向 WebSockets。",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )
        self._inbound_tasks: set[asyncio.Task[None]] = set()

        self.bot = CQHttp(
            use_ws_reverse=True,
            import_name="aiocqhttp",
            api_timeout_sec=180,
            access_token=platform_config.get(
                "ws_reverse_token",
            ),  # 以防旧版本配置不存在
        )

        @self.bot.on_request()
        async def request(event: Event) -> None:
            self._start_inbound_task(self._process_inbound_event(event), "request")

        @self.bot.on_notice()
        async def notice(event: Event) -> None:
            self._start_inbound_task(self._process_inbound_event(event), "notice")

        @self.bot.on_message("group")
        async def group(event: Event) -> None:
            self._start_inbound_task(
                self._process_inbound_event(event),
                "group message",
            )

        @self.bot.on_message("private")
        async def private(event: Event) -> None:
            self._start_inbound_task(
                self._process_inbound_event(event),
                "private message",
            )

        @self.bot.on_websocket_connection
        def on_websocket_connection(_) -> None:
            logger.info("aiocqhttp(OneBot v11) 适配器已连接。")

    def _start_inbound_task(
        self,
        coro: Coroutine[Any, Any, None],
        label: str,
    ) -> None:
        task = asyncio.create_task(coro, name=f"aiocqhttp:{label}")
        self._inbound_tasks.add(task)
        task.add_done_callback(self._on_inbound_task_done)

    def _on_inbound_task_done(self, task: asyncio.Task[None]) -> None:
        self._inbound_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("aiocqhttp inbound task failed", exc_info=exc)

    async def _process_inbound_event(self, event: Event) -> None:
        abm = await self.convert_message(event)
        if abm:
            await self.handle_msg(abm)

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ):
        is_group = session.message_type == MessageType.GROUP_MESSAGE
        if is_group:
            session_id = session.session_id.split("_")[-1]
        else:
            session_id = session.session_id
        await AiocqhttpMessageEvent.send_message(
            bot=self.bot,
            message_chain=message_chain,
            event=None,  # 这里不需要 event，因为是通过 session 发送的
            is_group=is_group,
            session_id=session_id,
            forward_message_max_retries=self.forward_message_max_retries,
            forward_message_fallback_enabled=self.forward_message_fallback_enabled,
        )
        return await super().send_by_session(session, message_chain)

    async def convert_message(self, event: Event) -> AstrBotMessage | None:
        logger.debug(f"[aiocqhttp] RawMessage {event}")
        abm: AstrBotMessage | None = None

        if event["post_type"] == "message":
            abm = await self._convert_handle_message_event(event)
            if abm.sender.user_id == "2854196310":
                # 屏蔽 QQ 管家的消息
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
            user_id=str(event.user_id), nickname=str(event.user_id)
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
            user_id=str(event.user_id), nickname=str(event.user_id)
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
    ) -> AstrBotMessage:
        """OneBot V11 消息类事件

        @param event: 事件对象
        """
        assert event.sender is not None
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(
            str(event.sender["user_id"]),
            event.sender.get("card") or event.sender.get("nickname", "N/A"),
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
            err = f"aiocqhttp: 无法识别的消息类型: {event.message!s}，此条消息将被忽略。如果您在使用 go-cqhttp，请将其配置文件中的 message.post-format 更改为 array。"
            logger.critical(err)
            try:
                await self.bot.send(event, err)
            except Exception as e:
                logger.error(f"回复消息失败: {e}")
            raise ValueError(err)

        # 按消息段类型类型适配
        routing_params = {"self_id": event.self_id} if event.self_id else {}
        for t, m_group in itertools.groupby(event.message, key=lambda x: x["type"]):
            a = None
            if t == "text":
                current_text = "".join(m["data"]["text"] for m in m_group).strip()
                if not current_text:
                    # 如果文本段为空，则跳过
                    continue
                message_str += current_text
                a = ComponentTypes[t](text=current_text)
                abm.message.append(a)

            elif t == "file":
                for m in m_group:
                    file_data = m["data"]
                    if file_data.get("url") and file_data.get("url").startswith("http"):
                        # Lagrange
                        logger.info("guessing lagrange")
                        # 检查多个可能的文件名字段
                        file_name = (
                            file_data.get("file_name", "")
                            or file_data.get("name", "")
                            or file_data.get("file", "")
                            or "file"
                        )
                        abm.message.append(File(name=file_name, url=file_data["url"]))
                    else:
                        file_name = (
                            file_data.get("file_name", "")
                            or file_data.get("name", "")
                            or file_data.get("file", "")
                            or "file"
                        )
                        file_component = File(name=file_name)
                        file_id = str(file_data.get("file_id", "")).strip()
                        if file_id:

                            async def _resolve_file_url(
                                *,
                                file_id: str = file_id,
                                file_name: str = file_name,
                                is_group_message: bool = (
                                    abm.type == MessageType.GROUP_MESSAGE
                                ),
                                group_id: int | str | None = event.get("group_id"),
                                routing_params: dict[str, object] = dict(
                                    routing_params
                                ),
                            ) -> tuple[str | None, str | None]:
                                ret = None
                                if is_group_message and group_id is not None:
                                    ret = await self.bot.call_action(
                                        "get_group_file_url",
                                        file_id=file_id,
                                        group_id=group_id,
                                        **routing_params,
                                    )
                                elif not is_group_message:
                                    ret = await self.bot.call_action(
                                        "get_private_file_url",
                                        file_id=file_id,
                                        **routing_params,
                                    )
                                if not ret or "url" not in ret:
                                    logger.error(f"获取文件失败: {ret}")
                                    return None, file_name
                                resolved_name = (
                                    ret.get("file_name", "")
                                    or ret.get("name", "")
                                    or file_name
                                )
                                return str(ret["url"]), resolved_name

                            file_component.set_url_resolver(_resolve_file_url)
                        abm.message.append(file_component)

            elif t == "reply":
                for m in m_group:
                    a = ComponentTypes[t](**m["data"])
                    abm.message.append(a)
            elif t == "at":
                first_at_self_processed = False
                # Accumulate @ mention text for efficient concatenation
                at_parts = []

                for m in m_group:
                    try:
                        if m["data"]["qq"] == "all":
                            abm.message.append(At(qq="all", name="全体成员"))
                            continue

                        target = str(m["data"]["qq"])
                        is_at_self = target in {abm.self_id, "all"}
                        abm.message.append(At(qq=target, name=""))

                        if is_at_self and not first_at_self_processed:
                            # 第一个@是机器人，不添加到message_str
                            first_at_self_processed = True
                        else:
                            # 非第一个@机器人或@其他用户，添加到message_str
                            at_parts.append(f" @{target} ")
                    except ActionFailed as e:
                        logger.error(f"解析 @ 消息段失败: {e}，此消息段将被忽略。")
                    except Exception as e:
                        logger.error(f"解析 @ 消息段失败: {e}，此消息段将被忽略。")

                message_str += "".join(at_parts)
            elif t == "mface":
                continue
            elif t == "markdown":
                for m in m_group:
                    text = m["data"].get("markdown") or m["data"].get("content", "")
                    abm.message.append(Plain(text=text))
                    message_str += text
            else:
                for m in m_group:
                    try:
                        if t not in ComponentTypes:
                            logger.warning(
                                f"不支持的消息段类型，已忽略: {t}, data={m['data']}"
                            )
                            continue
                        a = ComponentTypes[t](**m["data"])
                        abm.message.append(a)
                    except Exception as e:
                        logger.exception(
                            f"消息段解析失败: type={t}, data={m['data']}. {e}"
                        )
                        continue

        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event

        return abm

    async def run(self) -> None:
        if not self.host or not self.port:
            logger.warning(
                "aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port，将使用默认值：http://127.0.0.1:6199",
            )
            self.host = "127.0.0.1"
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
        await coro

    async def terminate(self) -> None:
        if hasattr(self, "shutdown_event"):
            self.shutdown_event.set()
        await self._close_reverse_ws_connections()
        inbound_tasks = list(self._inbound_tasks)
        if inbound_tasks:
            await asyncio.gather(*inbound_tasks, return_exceptions=True)
        self._inbound_tasks.clear()

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

    def create_event(self, message: AstrBotMessage) -> AiocqhttpMessageEvent:
        """Creates an aiocqhttp message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created aiocqhttp message event.
        """
        event = AiocqhttpMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            bot=self.bot,
            forward_message_max_retries=self.forward_message_max_retries,
            forward_message_fallback_enabled=self.forward_message_fallback_enabled,
        )
        raw_event = getattr(message, "raw_message", None)
        if (
            not event.is_private_chat()
            and raw_event is not None
            and _payload_field(raw_event, "post_type") == "message"
            and _payload_field(raw_event, "message_type") == "group"
        ):
            sender = _payload_field(raw_event, "sender")
            role = _payload_field(sender, "role") if sender is not None else None
            if role is not None:
                event.set_platform_member_role(str(role), source="adapter")
        return event

    async def handle_msg(self, message: AstrBotMessage) -> None:
        self.commit_event(self.create_event(message))
