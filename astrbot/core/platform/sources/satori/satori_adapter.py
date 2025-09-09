import asyncio
import json
import time
import websockets
from websockets.asyncio.client import connect
from typing import Optional
from aiohttp import ClientSession, ClientTimeout
from websockets.asyncio.client import ClientConnection
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.api.message_components import Plain, Image, At, File, Record
from xml.etree import ElementTree as ET


@register_platform_adapter(
    "satori",
    "Satori 协议适配器",
)
class SatoriPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.settings = platform_settings

        self.api_base_url = self.config.get(
            "satori_api_base_url", "http://localhost:5140/satori/v1"
        )
        self.token = self.config.get("satori_token", "")
        self.endpoint = self.config.get(
            "satori_endpoint", "ws://127.0.0.1:5140/satori/v1/events"
        )
        self.auto_reconnect = self.config.get("satori_auto_reconnect", True)
        self.heartbeat_interval = self.config.get("satori_heartbeat_interval", 10)
        self.reconnect_delay = self.config.get("satori_reconnect_delay", 5)

        self.ws: Optional[ClientConnection] = None
        self.session: Optional[ClientSession] = None
        self.sequence = 0
        self.logins = []
        self.running = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.ready_received = False

    async def send_by_session(
        self, session: MessageSession, message_chain: MessageChain
    ):
        from .satori_event import SatoriPlatformEvent

        await SatoriPlatformEvent.send_with_adapter(
            self, message_chain, session.session_id
        )
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(name="satori", description="Satori 通用协议适配器")

    def _is_websocket_closed(self, ws) -> bool:
        """检查WebSocket连接是否已关闭"""
        if not ws:
            return True
        try:
            if hasattr(ws, "closed"):
                return ws.closed
            elif hasattr(ws, "close_code"):
                return ws.close_code is not None
            else:
                return False
        except AttributeError:
            return False

    async def run(self):
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

    async def connect_websocket(self):
        logger.info(f"Satori 适配器正在连接到 WebSocket: {self.endpoint}")
        logger.info(f"Satori 适配器 HTTP API 地址: {self.api_base_url}")

        if not self.endpoint.startswith(("ws://", "wss://")):
            logger.error(f"无效的WebSocket URL: {self.endpoint}")
            raise ValueError(f"WebSocket URL必须以ws://或wss://开头: {self.endpoint}")

        try:
            websocket = await connect(self.endpoint, additional_headers={})
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

    async def send_identify(self):
        if not self.ws:
            raise Exception("WebSocket连接未建立")

        if self._is_websocket_closed(self.ws):
            raise Exception("WebSocket连接已关闭")

        identify_payload = {
            "op": 3,  # IDENTIFY
            "body": {
                "token": str(self.token) if self.token else "",  # 字符串
            },
        }

        # 只有在有序列号时才添加sn字段
        if self.sequence > 0:
            identify_payload["body"]["sn"] = self.sequence

        try:
            message_str = json.dumps(identify_payload, ensure_ascii=False)
            await self.ws.send(message_str)
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"发送 IDENTIFY 信令时连接关闭: {e}")
            raise
        except Exception as e:
            logger.error(f"发送 IDENTIFY 信令失败: {e}")
            raise

    async def heartbeat_loop(self):
        try:
            while self.running and self.ws:
                await asyncio.sleep(self.heartbeat_interval)

                if self.ws and not self._is_websocket_closed(self.ws):
                    try:
                        ping_payload = {
                            "op": 1,  # PING
                            "body": {},
                        }
                        await self.ws.send(json.dumps(ping_payload, ensure_ascii=False))
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

    async def handle_message(self, message: str):
        try:
            data = json.loads(message)
            op = data.get("op")
            body = data.get("body", {})

            if op == 4:  # READY
                self.logins = body.get("logins", [])
                self.ready_received = True

                # 输出连接成功的bot信息
                if self.logins:
                    for i, login in enumerate(self.logins):
                        platform = login.get("platform", "")
                        user = login.get("user", {})
                        user_id = user.get("id", "")
                        user_name = user.get("name", "")
                        logger.info(
                            f"Satori 连接成功 - Bot {i + 1}: platform={platform}, user_id={user_id}, user_name={user_name}"
                        )

                if "sn" in body:
                    self.sequence = body["sn"]

            elif op == 2:  # PONG
                pass

            elif op == 0:  # EVENT
                await self.handle_event(body)
                if "sn" in body:
                    self.sequence = body["sn"]

            elif op == 5:  # META
                if "sn" in body:
                    self.sequence = body["sn"]

        except json.JSONDecodeError as e:
            logger.error(f"解析 WebSocket 消息失败: {e}, 消息内容: {message}")
        except Exception as e:
            logger.error(f"处理 WebSocket 消息异常: {e}")

    async def handle_event(self, event_data: dict):
        try:
            event_type = event_data.get("type")
            sn = event_data.get("sn")
            if sn:
                self.sequence = sn

            if event_type == "message-created":
                message = event_data.get("message", {})
                user = event_data.get("user", {})
                channel = event_data.get("channel", {})
                guild = event_data.get("guild")
                login = event_data.get("login", {})
                timestamp = event_data.get("timestamp")

                if user.get("id") == login.get("user", {}).get("id"):
                    return

                abm = await self.convert_satori_message(
                    message, user, channel, guild, login, timestamp
                )
                if abm:
                    await self.handle_msg(abm)

        except Exception as e:
            logger.error(f"处理事件失败: {e}")

    async def convert_satori_message(
        self,
        message: dict,
        user: dict,
        channel: dict,
        guild: Optional[dict],
        login: dict,
        timestamp: Optional[int] = None,
    ) -> Optional[AstrBotMessage]:
        try:
            abm = AstrBotMessage()
            abm.message_id = message.get("id", "")
            abm.raw_message = {
                "message": message,
                "user": user,
                "channel": channel,
                "guild": guild,
                "login": login,
            }

            if guild and guild.get("id"):
                abm.type = MessageType.GROUP_MESSAGE
                abm.group_id = guild.get("id", "")
                abm.session_id = channel.get("id", "")
            else:
                abm.type = MessageType.FRIEND_MESSAGE
                abm.session_id = channel.get("id", "")

            abm.sender = MessageMember(
                user_id=user.get("id", ""),
                nickname=user.get("nick", user.get("name", "")),
            )

            abm.self_id = login.get("user", {}).get("id", "")

            # 消息链
            abm.message = []

            content = message.get("content", "")
            
            quote = message.get("quote")
            content_for_parsing = content  # 副本
            
            if not quote and "<quote" in content:
                # 如果quote字段不存在，但内容中有<quote>标签，则尝试从中提取引用信息
                import re
                quote_match = re.search(r'<quote\s+id="([^"]+)">([^<]*)</quote>', content)
                if quote_match:
                    quote_id = quote_match.group(1)
                    quote_content = quote_match.group(2)
                    quote = {
                        "id": quote_id,
                        "content": quote_content
                    }
                    content_for_parsing = re.sub(r'<quote\s+id="[^"]+">[^<]*</quote>', '', content, 1)

            if quote:
                # 引用消息
                quote_abm = await self._convert_quote_message(quote)
                if quote_abm:
                    from astrbot.api.message_components import Reply
                    # 确保qq参数是整数类型
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
            content_elements = await self.parse_satori_elements(content_for_parsing)
            abm.message.extend(content_elements)

            # parse message_str
            abm.message_str = ""
            for comp in abm.message:
                if isinstance(comp, Plain):
                    abm.message_str += comp.text

            # 优先使用Satori事件中的时间戳
            if timestamp is not None:
                abm.timestamp = timestamp
            else:
                abm.timestamp = int(time.time())

            return abm

        except Exception as e:
            logger.error(f"转换 Satori 消息失败: {e}")
            return None

    async def _convert_quote_message(self, quote: dict) -> Optional[AstrBotMessage]:
        """转换引用消息"""
        try:
            quote_abm = AstrBotMessage()
            quote_abm.message_id = quote.get("id", "")
            
            # 解析引用消息的发送者
            quote_author = quote.get("author", {})
            if quote_author:
                quote_abm.sender = MessageMember(
                    user_id=quote_author.get("id", ""),
                    nickname=quote_author.get("nick", quote_author.get("name", "")),
                )
            else:
                # 如果没有作者信息，使用默认值
                quote_abm.sender = MessageMember(
                    user_id=quote.get("user_id", ""),
                    nickname="内容",
                )
            
            # 解析引用消息内容
            quote_content = quote.get("content", "")
            quote_abm.message = await self.parse_satori_elements(quote_content)
            
            # 构建引用消息的文本表示
            quote_abm.message_str = ""
            for comp in quote_abm.message:
                if isinstance(comp, Plain):
                    quote_abm.message_str += comp.text
                    
            quote_abm.timestamp = int(quote.get("timestamp", time.time()))
            
            return quote_abm
        except Exception as e:
            logger.error(f"转换引用消息失败: {e}")
            return None

    async def parse_satori_elements(self, content: str) -> list:
        """解析 Satori 消息元素"""
        elements = []

        if not content:
            return elements

        try:
            # 处理命名空间前缀问题
            processed_content = content
            if 'xmlns:' in content or ':' in content.split('>')[0]:
                # 如果存在命名空间，添加默认命名空间声明
                if not content.startswith('<root'):
                    processed_content = f"<root xmlns:satori='http://satori.org'>{content}</root>"
                else:
                    processed_content = content
            else:
                processed_content = f"<root>{content}</root>"
                
            root = ET.fromstring(processed_content)
            await self._parse_xml_node(root, elements)
        except ET.ParseError as e:
            # 如果解析失败，将整个内容当作纯文本
            if content.strip():
                elements.append(Plain(text=content))
        except Exception as e:
            raise e

        # 如果没有解析到任何元素，将整个内容当作纯文本
        if not elements and content.strip():
            elements.append(Plain(text=content))

        return elements

    async def _parse_xml_node(self, node: ET.Element, elements: list) -> None:
        """递归解析 XML 节点"""
        if node.text and node.text.strip():
            elements.append(Plain(text=node.text))

        for child in node:
            tag_name = child.tag.lower()
            attrs = child.attrib

            if tag_name == "at":
                user_id = attrs.get("id") or attrs.get("name", "")
                elements.append(At(qq=user_id, name=user_id))

            elif tag_name in ("img", "image"):
                src = attrs.get("src", "")
                if not src:
                    continue
                if src.startswith("data:image/"):
                    src = src.split(",")[1]
                    elements.append(Image.fromBase64(src))
                elif src.startswith("http"):
                    elements.append(Image.fromURL(src))
                else:
                    logger.error(f"未知的图片 src 格式: {str(src)[:16]}")

            elif tag_name == "file":
                src = attrs.get("src", "")
                name = attrs.get("name", "文件")
                if src:
                    elements.append(File(file=src, name=name))

            elif tag_name in ("audio", "record"):
                src = attrs.get("src", "")
                if not src:
                    continue
                if src.startswith("data:audio/"):
                    src = src.split(",")[1]
                    elements.append(Record.fromBase64(src))
                elif src.startswith("http"):
                    elements.append(Record.fromURL(src))
                else:
                    logger.error(f"未知的音频 src 格式: {str(src)[:16]}")

            elif tag_name == "quote":
                # quote标签已经被特殊处理，这里不需要再解析其内容
                pass

            else:
                # 未知标签，递归处理其内容
                if child.text and child.text.strip():
                    elements.append(Plain(text=child.text))
                await self._parse_xml_node(child, elements)

            # 处理标签后的文本
            if child.tail and child.tail.strip():
                elements.append(Plain(text=child.tail))

    async def handle_msg(self, message: AstrBotMessage):
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
            headers["satori-platform"] = platform
            headers["satori-user-id"] = user_id
        elif self.logins:
            current_login = self.logins[0]
            headers["satori-platform"] = current_login.get("platform", "")
            user = current_login.get("user", {})
            headers["satori-user-id"] = user.get("id", "") if user else ""

        if not path.startswith("/"):
            path = "/" + path

        # 使用新的API地址配置
        url = f"{self.api_base_url.rstrip('/')}{path}"

        try:
            async with self.session.request(
                method, url, json=data, headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    return {}
        except Exception as e:
            logger.error(f"Satori HTTP 请求异常: {e}")
            return {}

    async def terminate(self):
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