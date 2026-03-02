import asyncio
import base64
import json
import random
import time
import zlib
from pathlib import Path

import aiofiles
import aiohttp
import websockets

from astrbot import logger
from astrbot.core.platform.message_type import MessageType

from .kook_types import KookApiPaths, KookMessageType


class KookClient:
    def __init__(self, token, event_callback):
        self._bot_id = ""
        self._http_client = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bot {token}",
            }
        )
        self.event_callback = event_callback  # 回调函数，用于处理接收到的事件
        self.ws = None
        self.running = False
        self._stop_event = asyncio.Event()  # 用于通知连接结束
        self.session_id = None
        self.last_sn = 0  # 记录最后处理的消息序号
        self.heartbeat_task = None
        self.reconnect_delay = 1  # 重连延迟，指数退避
        self.max_reconnect_delay = 60  # 最大重连延迟
        self.heartbeat_interval = 30  # 心跳间隔
        self.heartbeat_timeout = 6  # 心跳超时时间
        self.last_heartbeat_time = 0
        self.heartbeat_failed_count = 0
        self.max_heartbeat_failures = 3  # 最大心跳失败次数

    @property
    def bot_id(self):
        return self._bot_id

    async def get_bot_id(self) -> str:
        """获取机器人账号ID"""
        url = KookApiPaths.USER_ME

        try:
            async with self._http_client.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"[KOOK] 获取机器人账号ID失败，状态码: {resp.status}")
                    return ""

                data = await resp.json()
                if data.get("code") != 0:
                    logger.error(f"[KOOK] 获取机器人账号ID失败: {data}")
                    return ""

                bot_id: str = data["data"]["id"]
                logger.info(f"[KOOK] 获取机器人账号ID成功: {bot_id}")
                return bot_id
        except Exception as e:
            logger.error(f"[KOOK] 获取机器人账号ID异常: {e}")
            return ""

    async def get_gateway_url(self, resume=False, sn=0, session_id=None):
        """获取网关连接地址"""
        url = KookApiPaths.GATEWAY_INDEX

        # 构建连接参数
        params = {}
        if resume:
            params["resume"] = 1
            params["sn"] = sn
            if session_id:
                params["session_id"] = session_id

        try:
            async with self._http_client.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"[KOOK] 获取gateway失败，状态码: {resp.status}")
                    return None

                data = await resp.json()
                if data.get("code") != 0:
                    logger.error(f"[KOOK] 获取gateway失败: {data}")
                    return None

                gateway_url = data["data"]["url"]
                logger.info(f"[KOOK] 获取gateway成功: {gateway_url}")
                return gateway_url
        except Exception as e:
            logger.error(f"[KOOK] 获取gateway异常: {e}")
            return None

    async def connect(self, resume=False):
        """连接WebSocket"""
        self._stop_event.clear()
        try:
            # 获取gateway地址
            gateway_url = await self.get_gateway_url(
                resume=resume, sn=self.last_sn, session_id=self.session_id
            )
            bot_id = await self.get_bot_id()

            if not gateway_url:
                return False
            if not bot_id:
                return False

            self._bot_id = bot_id

            # 连接WebSocket
            self.ws = await websockets.connect(gateway_url)
            self.running = True
            logger.info("[KOOK] WebSocket 连接成功")

            # 启动心跳任务
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 开始监听消息
            await self.listen()
            return True

        except Exception as e:
            logger.error(f"[KOOK] WebSocket 连接失败: {e}")
            return False

    async def listen(self):
        """监听WebSocket消息"""
        try:
            while self.running:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=10)  # type: ignore

                    if isinstance(msg, bytes):
                        try:
                            msg = zlib.decompress(msg)
                        except Exception as e:
                            logger.error(f"[KOOK] 解压消息失败: {e}")
                            continue
                        msg = msg.decode("utf-8")

                    logger.debug(f"[KOOK] 收到原始消息: {msg}")
                    data = json.loads(msg)

                    # 处理不同类型的信令
                    await self._handle_signal(data)

                except asyncio.TimeoutError:
                    # 超时检查，继续循环
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("[KOOK] WebSocket连接已关闭")
                    break
                except Exception as e:
                    logger.error(f"[KOOK] 消息处理异常: {e}")
                    break

        except Exception as e:
            logger.error(f"[KOOK] WebSocket 监听异常: {e}")
        finally:
            self.running = False
            self._stop_event.set()

    async def _handle_signal(self, data):
        """处理不同类型的信令"""
        signal_type = data.get("s")

        if signal_type == 0:  # 事件消息
            # 更新消息序号
            if "sn" in data:
                self.last_sn = data["sn"]
            await self.event_callback(data)

        elif signal_type == 1:  # HELLO握手
            await self._handle_hello(data)

        elif signal_type == 3:  # PONG心跳响应
            await self._handle_pong(data)

        elif signal_type == 5:  # RECONNECT重连指令
            await self._handle_reconnect(data)

        elif signal_type == 6:  # RESUME ACK
            await self._handle_resume_ack(data)

        else:
            logger.debug(f"[KOOK] 未处理的信令类型: {signal_type}")

    async def _handle_hello(self, data):
        """处理HELLO握手"""
        hello_data = data.get("d", {})
        code = hello_data.get("code", 0)

        if code == 0:
            self.session_id = hello_data.get("session_id")
            logger.info(f"[KOOK] 握手成功，session_id: {self.session_id}")
            # 重置重连延迟
            self.reconnect_delay = 1
        else:
            logger.error(f"[KOOK] 握手失败，错误码: {code}")
            if code == 40103:  # token过期
                logger.error("[KOOK] Token已过期，需要重新获取")
            self.running = False

    async def _handle_pong(self, data):
        """处理PONG心跳响应"""
        self.last_heartbeat_time = time.time()
        self.heartbeat_failed_count = 0
        logger.debug("[KOOK] 收到心跳响应")

    async def _handle_reconnect(self, data):
        """处理重连指令"""
        logger.warning("[KOOK] 收到重连指令")
        # 清空本地状态
        self.last_sn = 0
        self.session_id = None
        self.running = False

    async def _handle_resume_ack(self, data):
        """处理RESUME确认"""
        resume_data = data.get("d", {})
        self.session_id = resume_data.get("session_id")
        logger.info(f"[KOOK] Resume成功，session_id: {self.session_id}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                # 随机化心跳间隔 (30±5秒)
                interval = self.heartbeat_interval + random.randint(-5, 5)
                await asyncio.sleep(interval)

                if not self.running:
                    break

                # 发送心跳
                await self._send_ping()

                # 等待PONG响应
                await asyncio.sleep(self.heartbeat_timeout)

                # 检查是否收到PONG响应
                if time.time() - self.last_heartbeat_time > self.heartbeat_timeout:
                    self.heartbeat_failed_count += 1
                    logger.warning(
                        f"[KOOK] 心跳超时，失败次数: {self.heartbeat_failed_count}"
                    )

                    if self.heartbeat_failed_count >= self.max_heartbeat_failures:
                        logger.error("[KOOK] 心跳失败次数过多，准备重连")
                        self.running = False
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[KOOK] 心跳异常: {e}")
                self.heartbeat_failed_count += 1

    async def _send_ping(self):
        """发送心跳PING"""
        try:
            ping_data = {"s": 2, "sn": self.last_sn}
            await self.ws.send(json.dumps(ping_data))  # type: ignore
            logger.debug(f"[KOOK] 发送心跳，sn: {self.last_sn}")
        except Exception as e:
            logger.error(f"[KOOK] 发送心跳失败: {e}")

    async def reconnect(self):
        """重连方法"""
        logger.info(f"[KOOK] 开始重连，延迟: {self.reconnect_delay}秒")
        await asyncio.sleep(self.reconnect_delay)

        # 关闭当前连接
        await self.close()

        # 尝试重连
        success = await self.connect(resume=True)

        if success:
            # 重连成功，重置延迟
            self.reconnect_delay = 1
            logger.info("[KOOK] 重连成功")
        else:
            # 重连失败，增加延迟（指数退避）
            self.reconnect_delay = min(
                self.reconnect_delay * 2, self.max_reconnect_delay
            )
            logger.warning(f"[KOOK] 重连失败，下次延迟: {self.reconnect_delay}秒")

        return success

    async def send_text(
        self,
        target_id: str,
        content: str,
        astrbot_message_type: MessageType,
        kook_message_type: KookMessageType,
        reply_message_id: str | int = "",
    ):
        """发送文本消息
        消息发送接口文档参见: https://developer.kookapp.cn/doc/http/message#%E5%8F%91%E9%80%81%E9%A2%91%E9%81%93%E8%81%8A%E5%A4%A9%E6%B6%88%E6%81%AF
        KMarkdown格式参见: https://developer.kookapp.cn/doc/kmarkdown-desc
        """
        url = KookApiPaths.CHANNEL_MESSAGE_CREATE
        if astrbot_message_type == MessageType.FRIEND_MESSAGE:
            url = KookApiPaths.DIRECT_MESSAGE_CREATE

        payload = {
            "target_id": target_id,
            "content": content,
            "type": kook_message_type,
        }
        if reply_message_id:
            payload["quote"] = reply_message_id
            payload["reply_msg_id"] = reply_message_id

        try:
            async with self._http_client.post(url, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("code") == 0:
                        logger.info("[KOOK] 发送消息成功")
                    else:
                        logger.error(
                            f'[KOOK] 发送kook消息类型 "{kook_message_type.name}" 失败: {result}'
                        )
                else:
                    logger.error(
                        f'[KOOK] 发送kook消息类型 "{kook_message_type.name}" HTTP错误: {resp.status} , 响应内容 : {await resp.text()}'
                    )
        except Exception as e:
            logger.error(
                f'[KOOK] 发送kook消息类型 "{kook_message_type.name}" 异常: {e}'
            )

    async def upload_asset(self, file_url: str | None) -> str:
        """上传文件到kook,获得远端资源url
        接口定义参见: https://developer.kookapp.cn/doc/http/asset
        """
        if file_url is None:
            return ""

        bytes_data: bytes | None = None
        filename = "unknown"
        if file_url.startswith(("http://", "https://")):
            filename = file_url.split("/")[-1]
            return file_url

        elif file_url.startswith("base64://"):
            if file_url.startswith("base64:///"):
                b64_str = file_url.removeprefix("base64:///")
            else:
                b64_str = file_url.removeprefix("base64://")
            bytes_data = base64.b64decode(b64_str)

        else:
            file_url = file_url.replace("file:///", "")
            file_url = file_url.replace("file://", "")
            filename = Path(file_url).name
            async with aiofiles.open(file_url, "rb") as f:
                bytes_data = await f.read()

        data = aiohttp.FormData()
        data.add_field("file", bytes_data, filename=filename)

        url = KookApiPaths.ASSET_CREATE
        try:
            async with self._http_client.post(url, data=data) as resp:
                if resp.status == 200:
                    result: dict = await resp.json()
                    if result.get("code") == 0:
                        logger.info("[KOOK] 发送文件消息成功")
                        remote_url = result["data"]["url"]
                        logger.debug(f"[KOOK] 文件远端URL: {remote_url}")
                        return remote_url
                    else:
                        logger.error(f"[KOOK] 发送文件消息失败: {result}")
                else:
                    logger.error(f"[KOOK] 发送文件消息HTTP错误: {resp.status}")
        except Exception as e:
            logger.error(f"[KOOK] 发送文件消息异常: {e}")

        return ""

    async def wait_until_closed(self):
        """提供给外部调用的等待方法"""
        await self._stop_event.wait()

    async def close(self):
        """关闭连接"""
        self.running = False
        self._stop_event.set()

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
                logger.error(f"[KOOK] 关闭WebSocket异常: {e}")

        if self._http_client:
            await self._http_client.close()

        logger.info("[KOOK] 连接已关闭")
