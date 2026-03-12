import asyncio
import json
import re
import time
from collections.abc import Sequence
from typing import cast

import websockets
from aiohttp import ClientSession, ClientTimeout
from websockets.asyncio.client import ClientConnection, connect

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Image,
    Plain,
    Record,
    Video,
    Reply,
)
from astrbot.api.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSession
from satori import element
from satori.const import EventType
from satori.event import MessageEvent
from satori.model import Event, Opcode, Identify, Ready, Login
from satori.parser import parse
from satori.utils import decode, encode

b64_cap = re.compile(r"^data:([\w/.+-]+);base64,")

@register_platform_adapter(
    "satori", "Satori 协议适配器", support_streaming_message=False
)
class SatoriPlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings

        self.api_base_url = self.config.get(
            "satori_api_base_url",
            "http://localhost:5140/satori/v1",
        )
        self.token = self.config.get("satori_token", "")
        self.endpoint = self.config.get(
            "satori_endpoint",
            "ws://localhost:5140/satori/v1/events",
        )
        self.auto_reconnect = self.config.get("satori_auto_reconnect", True)
        self.heartbeat_interval = self.config.get("satori_heartbeat_interval", 10)
        self.reconnect_delay = self.config.get("satori_reconnect_delay", 5)

        self.metadata = PlatformMetadata(
            name="satori",
            description="Satori 通用协议适配器",
            id=self.config["id"],
            support_streaming_message=False,
        )

        self.ws: ClientConnection | None = None
        self.session: ClientSession | None = None
        self.sequence = 0
        self.logins: Sequence[Login] = []
        self.running = False
        self.heartbeat_task: asyncio.Task | None = None
        self.ready_received = False

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> None:
        from .satori_event import SatoriPlatformEvent

        await SatoriPlatformEvent.send_with_adapter(
            self,
            message_chain,
            session.session_id,
        )
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return self.metadata

    def _is_websocket_closed(self, ws) -> bool:
        """检查WebSocket连接是否已关闭"""
        if not ws:
            return True
        try:
            if hasattr(ws, "closed"):
                return ws.closed
            if hasattr(ws, "close_code"):
                return ws.close_code is not None
            return False
        except AttributeError:
            return False

    async def run(self) -> None:
        self.running = True
        self.session = ClientSession(timeout=ClientTimeout(total=30))

        retry_count = 0
        max_retries = 10

        while self.running:
            try:
                await self.connect_websocket()
                retry_count = 0
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Satori WebSocket 连接关闭: {e}")
                retry_count += 1
            except Exception as e:
                logger.error(f"Satori WebSocket 连接失败: {e}")
                retry_count += 1

            if not self.running:
                break

            if retry_count >= max_retries:
                logger.error(f"达到最大重试次数 ({max_retries})，停止重试")
                break

            if not self.auto_reconnect:
                break

            delay = min(self.reconnect_delay * (2 ** (retry_count - 1)), 60)
            await asyncio.sleep(delay)

        if self.session:
            await self.session.close()

    async def connect_websocket(self) -> None:
        logger.info(f"Satori 适配器正在连接到 WebSocket: {self.endpoint}")
        logger.info(f"Satori 适配器 HTTP API 地址: {self.api_base_url}")

        if not self.endpoint.startswith(("ws://", "wss://")):
            logger.error(f"无效的WebSocket URL: {self.endpoint}")
            raise ValueError(f"WebSocket URL必须以ws://或wss://开头: {self.endpoint}")

        try:
            websocket = await connect(
                self.endpoint,
                additional_headers={},
                max_size=10 * 1024 * 1024,  # 10MB
            )

            self.ws = websocket

            await asyncio.sleep(0.1)

            await self.send_identify()

            self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            async for message in websocket:
                try:
                    await self.handle_message(message)  # type: ignore
                except Exception as e:
                    logger.error(f"Satori 处理消息异常: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Satori WebSocket 连接关闭: {e}")
            raise
        except Exception as e:
            logger.error(f"Satori WebSocket 连接异常: {e}")
            raise
        finally:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
            if self.ws:
                try:
                    await self.ws.close()
                except Exception as e:
                    logger.error(f"Satori WebSocket 关闭异常: {e}")

    async def send_identify(self) -> None:
        if not self.ws:
            raise Exception("WebSocket连接未建立")

        if self._is_websocket_closed(self.ws):
            raise Exception("WebSocket连接已关闭")

        identify_payload = Identify(token=self.token)
        # 只有在有序列号时才添加sn字段
        if self.sequence > 0:
            identify_payload.sn = self.sequence

        try:
            message_str = encode({"op": Opcode.IDENTIFY, "body": identify_payload.dump()})
            await self.ws.send(message_str)
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"发送 IDENTIFY 信令时连接关闭: {e}")
            raise
        except Exception as e:
            logger.error(f"发送 IDENTIFY 信令失败: {e}")
            raise

    async def heartbeat_loop(self) -> None:
        try:
            while self.running and self.ws:
                await asyncio.sleep(self.heartbeat_interval)

                if self.ws and not self._is_websocket_closed(self.ws):
                    try:
                        ping_payload = {"op": Opcode.PING}
                        await self.ws.send(encode(ping_payload))
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.error(f"Satori WebSocket 连接关闭: {e}")
                        break
                    except Exception as e:
                        logger.error(f"Satori WebSocket 发送心跳失败: {e}")
                        break
                else:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"心跳任务异常: {e}")

    async def handle_message(self, message: str) -> None:
        try:
            data = decode(message)

            op = data.get("op")
            body = data.get("body", {})

            if op == Opcode.READY:
                resp = Ready.parse(body)
                self.logins = resp.logins
                self.ready_received = True

                # 输出连接成功的bot信息
                for i, login in enumerate(self.logins):
                    logger.info(
                        f"Satori 连接成功 - Bot {i + 1}: "
                        f"platform={login.platform}, "
                        f"user_id={login.user.id if login.user else ''}, "
                        f"user_name={login.user.name if login.user else ''}",
                    )
            elif op == Opcode.PONG:
                pass

            elif op == Opcode.EVENT:  # EVENT
                await self.handle_event(body)

            elif op == Opcode.META:
                # TODO: META 消息会携带 satori-server 支持的 proxy_urls, 用于资源链接的下载
                pass

        except json.JSONDecodeError as e:
            logger.error(f"解析 WebSocket 消息失败: {e}, 消息内容: {message}")
        except Exception as e:
            logger.error(f"处理 WebSocket 消息异常: {e}")

    async def handle_event(self, event_data: dict) -> None:
        try:
            event = Event.parse(event_data)
        except Exception as e:
            if (
                "self_id" in event_data
                or ("login" in event_data and "self_id" in event_data["login"])
                or ("login" in event_data and "user" in event_data["login"] and "self_id" in event_data["login"]["user"])
            ):
                logger.error(f"解析事件失败: {e}")
            else:
                logger.debug(f"解析事件失败: {e}")
        else:
            self.sequence = event.sn
            if event.type == EventType.MESSAGE_CREATED:
                if event.user and event.user.id == event.login.user.id:
                    return
                if abm := await self.convert_satori_message(cast(MessageEvent, event)):
                    await self.handle_msg(abm)

    async def convert_satori_message(self, event: MessageEvent) -> AstrBotMessage | None:
        try:
            abm = AstrBotMessage()
            abm.message_id = event.message.id
            abm.timestamp = int(event.timestamp.timestamp())
            abm.raw_message = {
                "message": event.message.dump(),
                "user": event.user.dump(),
                "channel": event.channel.dump(),
                "guild": event.guild.dump() if event.guild else None,
                "login": event.login.dump(),
            }
            channel_id = event.channel.id
            if channel_id.startswith("private:"):
                abm.type = MessageType.FRIEND_MESSAGE
                abm.session_id = channel_id
            else:
                abm.type = MessageType.GROUP_MESSAGE
                abm.group = Group(
                    group_id=channel_id,
                    group_name=event.channel.name,
                    group_avatar=event.guild.avatar if event.guild else None,
                )
                if event.guild and event.guild.id != channel_id:  # 二级频道
                    abm.session_id = f"{event.guild.id}:{channel_id}"
                else:  # 一级群组
                    abm.session_id = channel_id

            abm.sender = MessageMember(
                user_id=event.user.id,
                nickname=event.user.nick or event.user.name or "",
            )
            abm.self_id = event.login.user.id
            # 消息链
            abm.message = []

            elements = event.message.message
            if raw_quote := event.message._raw_data.get("quote"):
                quote: element.Quote | None = element.transform([raw_quote])[0]  # type: ignore
            elif quotes := element.select(elements, element.Quote):
                quote = quotes[0]
            else:
                quote = None
            if quote:
                elements = [e for e in elements if not isinstance(e, element.Quote)]
                if quote_abm := self._convert_quote_message(quote, abm.self_id):
                    sender_id = quote_abm.sender.user_id
                    if isinstance(sender_id, str) and sender_id.isdigit():
                        sender_id = int(sender_id)
                    elif not isinstance(sender_id, int):
                        sender_id = 0  # 默认值

                    reply_component = Reply(
                        id=quote_abm.message_id,
                        chain=quote_abm.message,
                        sender_id=quote_abm.sender.user_id,
                        sender_nickname=quote_abm.sender.nickname,
                        time=quote_abm.timestamp,
                        message_str=quote_abm.message_str,
                        text=quote_abm.message_str,
                        qq=sender_id,
                    )
                    abm.message.append(reply_component)
 
            # 解析消息内容
            content_elements = self.parse_satori_elements(elements)
            abm.message.extend(content_elements)

            abm.message_str = ""
            for comp in content_elements:
                if isinstance(comp, Plain):
                    abm.message_str += comp.text
            return abm

        except Exception as e:
            logger.error(f"转换 Satori 消息失败: {e}")
            return None


    def _convert_quote_message(self, quote: element.Quote, self_id: str) -> AstrBotMessage | None:
        """转换引用消息"""
        try:
            quote_abm = AstrBotMessage()
            quote_abm.message_id = quote.id or ""

            # 解析引用消息的发送者
            quote_authors = element.select(quote, element.Author)
            if quote_authors:
                quote_author = quote_authors[0]
                quote_abm.sender = MessageMember(
                    user_id=quote_author.id,
                    nickname=quote_author.name or "",
                )
            else:
                # 如果没有作者信息，使用默认值
                quote_abm.sender = MessageMember(
                    user_id=self_id,
                    nickname="内容",
                )

            # 解析引用消息内容
            quote_abm.message = self.parse_satori_elements(quote.children)

            quote_abm.message_str = ""
            for comp in quote_abm.message:
                if isinstance(comp, Plain):
                    quote_abm.message_str += comp.text

            quote_abm.timestamp = int(time.time())

            # 如果没有任何内容，使用默认文本
            if not quote_abm.message_str.strip():
                quote_abm.message_str = "[引用消息]"

            return quote_abm
        except Exception as e:
            logger.error(f"转换引用消息失败: {e}")
            return None

    def parse_satori_elements(self, elements: list[element.Element]) -> list:
        """解析 Satori 消息元素"""
        parsed_elements = []

        for item in elements:
            if isinstance(item, element.Text):
                parsed_elements.append(Plain(text=item.text))
            elif isinstance(item, element.Sharp):
                parsed_elements.append(Plain(text=f"#{item.id}"))
            elif isinstance(item, element.Link):
                parsed_elements.extend(
                    self.parse_satori_elements(item.children)
                )
                if item.href:
                    parsed_elements.append(Plain(text=f" ({item.href})"))
            elif isinstance(item, element.Br):
                parsed_elements.append(Plain(text="\n"))
            elif isinstance(item, element.Paragraph):
                prev = parsed_elements[-1] if parsed_elements else None
                if prev and isinstance(prev, Plain):
                    if not prev.text.endswith("\n"):
                        prev.text += "\n"
                else:
                    parsed_elements.append(Plain(text="\n"))
                parsed_elements.extend(
                    self.parse_satori_elements(item.children)
                )
                parsed_elements.append(Plain(text="\n"))
            elif isinstance(item, element.At):
                if item.type:
                    parsed_elements.append(AtAll())
                else:
                    user_id = item.id or ""
                    parsed_elements.append(At(qq=user_id, name=item.name or user_id))
            elif isinstance(item, element.Image):
                file = item.src
                if mat := b64_cap.match(item.src):
                    file = f"base64://{item.src[len(mat[0]):]}"
                parsed_elements.append(Image(file=file))
            elif isinstance(item, element.File):
                file = item.src
                if mat := b64_cap.match(item.src):
                    file = f"base64://{item.src[len(mat[0]):]}"
                parsed_elements.append(File(name=item.title or "文件", file=file))
            elif isinstance(item, element.Audio):
                file = item.src
                if mat := b64_cap.match(item.src):
                    file = f"base64://{item.src[len(mat[0]):]}"
                parsed_elements.append(Record(file=file))
            elif isinstance(item, element.Video):
                file = item.src
                if mat := b64_cap.match(item.src):
                    file = f"base64://{item.src[len(mat[0]):]}"
                parsed_elements.append(Video(file=file))
            elif isinstance(item, element.Emoji):
                if item.name:
                    parsed_elements.append(Plain(text=f"[表情:{item.name}]"))
                else:
                    parsed_elements.append(Face(id=item.id))
            elif isinstance(item, element.Custom):
                if item.tag == "ark":
                    data = item._attrs.get("data", "")
                    if data:
                        import html

                        decoded_data = html.unescape(data)
                        parsed_elements.append(Plain(text=f"[ARK卡片数据: {decoded_data}]"))
                    else:
                        parsed_elements.append(Plain(text="[ARK卡片]"))
                elif item.tag == "json":
                    data = item._attrs.get("data", "")
                    if data:
                        import html

                        decoded_data = html.unescape(data)
                        parsed_elements.append(Plain(text=f"[JSON卡片数据: {decoded_data}]"))
                    else:
                        parsed_elements.append(Plain(text="[JSON卡片]"))
                else:
                    parsed_elements.extend(
                        self.parse_satori_elements(item.children)
                    )
            else:
                parsed_elements.extend(
                    self.parse_satori_elements(item.children)
                )
        return parsed_elements

    async def handle_msg(self, message: AstrBotMessage) -> None:
        from .satori_event import SatoriPlatformEvent

        message_event = SatoriPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            adapter=self,
        )
        self.commit_event(message_event)

    async def send_http_request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        platform: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        if not self.session:
            raise Exception("HTTP session 未初始化")

        headers = {
            "Content-Type": "application/json",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if platform and user_id:
            headers["Satori-Platform"] = platform
            headers["Satori-User-Id"] = user_id
        elif self.logins:
            current_login = self.logins[0]
            headers["Satori-Platform"] = current_login.platform
            headers["Satori-User-Id"] = current_login.user.id if current_login.user else ""

        if not path.startswith("/"):
            path = "/" + path

        # 使用新的API地址配置
        url = f"{self.api_base_url.rstrip('/')}{path}"

        try:
            async with self.session.request(
                method,
                url,
                json=data,
                headers=headers,
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                return {}
        except Exception as e:
            logger.error(f"Satori HTTP 请求异常: {e}")
            return {}

    async def terminate(self) -> None:
        self.running = False

        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"Satori WebSocket 关闭异常: {e}")

        if self.session:
            await self.session.close()
