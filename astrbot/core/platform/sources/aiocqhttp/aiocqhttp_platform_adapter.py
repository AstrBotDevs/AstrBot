import time
import asyncio
import logging
import uuid
import itertools
from typing import Awaitable, Any
from aiocqhttp import CQHttp, Event
from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.api.event import MessageChain
from .aiocqhttp_message_event import *  # noqa: F403
from astrbot.api.message_components import *  # noqa: F403
from astrbot.api import logger
from .aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter
from aiocqhttp.exceptions import ActionFailed


@register_platform_adapter(
    "aiocqhttp", "适用于 OneBot V11 标准的消息平台适配器，支持反向 WebSockets。"
)
class AiocqhttpAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings["unique_session"]
        self.host = platform_config["ws_reverse_host"]
        self.port = platform_config["ws_reverse_port"]

        self.metadata = PlatformMetadata(
            name="aiocqhttp",
            description="适用于 OneBot 标准的消息平台适配器，支持反向 WebSockets。",
            id=self.config.get("id"),
        )

        self.bot = CQHttp(
            use_ws_reverse=True,
            import_name="aiocqhttp",
            api_timeout_sec=180,
            access_token=platform_config.get(
                "ws_reverse_token"
            ),  # 以防旧版本配置不存在
        )

        @self.bot.on_request()
        async def request(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)

        @self.bot.on_notice()
        async def notice(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)

        @self.bot.on_message("group")
        async def group(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)

        @self.bot.on_message("private")
        async def private(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)

        @self.bot.on_websocket_connection
        def on_websocket_connection(_):
            logger.info("aiocqhttp(OneBot v11) 适配器已连接。")

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
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
        )
        await super().send_by_session(session, message_chain)

    async def convert_message(self, event: Event) -> AstrBotMessage:
        logger.debug(f"[aiocqhttp] RawMessage {event}")

        if event["post_type"] == "message":
            abm = await self._convert_handle_message_event(event)
            if abm.sender.user_id == "2854196310":
                # 屏蔽 QQ 管家的消息
                return
        elif event["post_type"] == "notice":
            abm = await self._convert_handle_notice_event(event)
        elif event["post_type"] == "request":
            abm = await self._convert_handle_request_event(event)

        return abm

    async def _convert_handle_request_event(self, event: Event) -> AstrBotMessage:
        """OneBot V11 请求类事件"""
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(user_id=str(event.user_id), nickname=event.user_id)
        abm.type = MessageType.OTHER_MESSAGE
        if "group_id" in event and event["group_id"]:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(event.group_id)
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        if self.unique_session and abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = str(abm.sender.user_id) + "_" + str(event.group_id)
        else:
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
        abm.sender = MessageMember(user_id=str(event.user_id), nickname=event.user_id)
        abm.type = MessageType.OTHER_MESSAGE
        if "group_id" in event and event["group_id"]:
            abm.group_id = str(event.group_id)
            abm.type = MessageType.GROUP_MESSAGE
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        if self.unique_session and abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = (
                str(abm.sender.user_id) + "_" + str(event.group_id)
            )  # 也保留群组 id
        else:
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
                abm.message.append(Poke(qq=str(event["target_id"]), type="poke"))  # noqa: F405

        return abm

    async def _convert_handle_message_event(
        self, event: Event, get_reply=True
    ) -> AstrBotMessage:
        """OneBot V11 消息类事件

        @param event: 事件对象
        @param get_reply: 是否获取回复消息。这个参数是为了防止多个回复嵌套。
        """
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.sender = MessageMember(
            str(event.sender["user_id"]), event.sender["nickname"]
        )
        if event["message_type"] == "group":
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(event.group_id)
        elif event["message_type"] == "private":
            abm.type = MessageType.FRIEND_MESSAGE
        if self.unique_session and abm.type == MessageType.GROUP_MESSAGE:
            abm.session_id = (
                abm.sender.user_id + "_" + str(event.group_id)
            )  # 也保留群组 id
        else:
            abm.session_id = (
                str(event.group_id)
                if abm.type == MessageType.GROUP_MESSAGE
                else abm.sender.user_id
            )

        abm.message_id = str(event.message_id)
        abm.message = []

        message_str = ""
        if not isinstance(event.message, list):
            err = f"aiocqhttp: 无法识别的消息类型: {str(event.message)}，此条消息将被忽略。如果您在使用 go-cqhttp，请将其配置文件中的 message.post-format 更改为 array。"
            logger.critical(err)
            try:
                self.bot.send(event, err)
            except BaseException as e:
                logger.error(f"回复消息失败: {e}")
            return

        # 按消息段类型类型适配
        for t, m_group in itertools.groupby(event.message, key=lambda x: x["type"]):
            a = None
            if t == "text":
                current_text = "".join(m["data"]["text"] for m in m_group).strip()
                if not current_text:
                    # 如果文本段为空，则跳过
                    continue
                message_str += current_text
                a = ComponentTypes[t](text=current_text)  # noqa: F405
                abm.message.append(a)

            elif t == "file":
                for m in m_group:
                    if m["data"].get("url") and m["data"].get("url").startswith("http"):
                        # Lagrange
                        logger.info("guessing lagrange")
                        file_name = m["data"].get("file_name", "file")
                        abm.message.append(File(name=file_name, url=m["data"]["url"]))
                    else:
                        try:
                            # Napcat
                            ret = None
                            if abm.type == MessageType.GROUP_MESSAGE:
                                ret = await self.bot.call_action(
                                    action="get_group_file_url",
                                    file_id=event.message[0]["data"]["file_id"],
                                    group_id=event.group_id,
                                )
                            elif abm.type == MessageType.FRIEND_MESSAGE:
                                ret = await self.bot.call_action(
                                    action="get_private_file_url",
                                    file_id=event.message[0]["data"]["file_id"],
                                )
                            if ret and "url" in ret:
                                file_url = ret["url"]  # https
                                a = File(name="", url=file_url)
                                abm.message.append(a)
                            else:
                                logger.error(f"获取文件失败: {ret}")

                        except ActionFailed as e:
                            logger.error(f"获取文件失败: {e}，此消息段将被忽略。")
                        except BaseException as e:
                            logger.error(f"获取文件失败: {e}，此消息段将被忽略。")

            elif t == "reply":
                for m in m_group:
                    if not get_reply:
                        a = ComponentTypes[t](**m["data"])  # noqa: F405
                        abm.message.append(a)
                    else:
                        try:
                            reply_event_data = await self.bot.call_action(
                                action="get_msg",
                                message_id=int(m["data"]["id"]),
                            )
                            # 添加必要的 post_type 字段，防止 Event.from_payload 报错
                            reply_event_data["post_type"] = "message"
                            new_event = Event.from_payload(reply_event_data)
                            if not new_event:
                                logger.error(
                                    f"无法从回复消息数据构造 Event 对象: {reply_event_data}"
                                )
                                continue
                            abm_reply = await self._convert_handle_message_event(
                                new_event, get_reply=False
                            )

                            reply_seg = Reply(
                                id=abm_reply.message_id,
                                chain=abm_reply.message,
                                sender_id=abm_reply.sender.user_id,
                                sender_nickname=abm_reply.sender.nickname,
                                time=abm_reply.timestamp,
                                message_str=abm_reply.message_str,
                                text=abm_reply.message_str,  # for compatibility
                                qq=abm_reply.sender.user_id,  # for compatibility
                            )

                            abm.message.append(reply_seg)
                        except BaseException as e:
                            logger.error(f"获取引用消息失败: {e}。")
                            a = ComponentTypes[t](**m["data"])  # noqa: F405
                            abm.message.append(a)
            elif t == "at":
                first_at_self_processed = False

                for m in m_group:
                    try:
                        if m["data"]["qq"] == "all":
                            abm.message.append(At(qq="all", name="全体成员"))
                            continue

                        at_info = await self.bot.call_action(
                            action="get_stranger_info",
                            user_id=int(m["data"]["qq"]),
                        )
                        if at_info:
                            nickname = at_info.get("nick", "") or at_info.get(
                                "nickname", ""
                            )
                            is_at_self = str(m["data"]["qq"]) in {abm.self_id, "all"}

                            abm.message.append(
                                At(
                                    qq=m["data"]["qq"],
                                    name=nickname,
                                )
                            )

                            if is_at_self and not first_at_self_processed:
                                # 第一个@是机器人，不添加到message_str
                                first_at_self_processed = True
                            else:
                                # 非第一个@机器人或@其他用户，添加到message_str
                                message_str += f" @{nickname}({m['data']['qq']}) "
                        else:
                            abm.message.append(At(qq=str(m["data"]["qq"]), name=""))
                    except ActionFailed as e:
                        logger.error(f"获取 @ 用户信息失败: {e}，此消息段将被忽略。")
                    except BaseException as e:
                        logger.error(f"获取 @ 用户信息失败: {e}，此消息段将被忽略。")
            else:
                for m in m_group:
                    a = ComponentTypes[t](**m["data"])  # noqa: F405
                    abm.message.append(a)

        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event

        return abm

    def run(self) -> Awaitable[Any]:
        if not self.host or not self.port:
            logger.warning(
                "aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port，将使用默认值：http://0.0.0.0:6199"
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

    async def terminate(self):
        self.shutdown_event.set()

    async def shutdown_trigger_placeholder(self):
        await self.shutdown_event.wait()
        logger.info("aiocqhttp 适配器已被优雅地关闭")

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage):
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
