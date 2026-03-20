import asyncio
import base64
import os
import random
import time
import zlib
from pathlib import Path

import aiofiles
import aiohttp
import pydantic
import websockets

from astrbot import logger
from astrbot.core.platform.message_type import MessageType

from .kook_config import KookConfig
from .kook_types import (
    KookApiPaths,
    KookGatewayIndexResponse,
    KookHelloEventData,
    KookMessageSignal,
    KookMessageType,
    KookResumeAckEventData,
    KookUserMeResponse,
    KookWebsocketEvent,
)


class KookClient:
    def __init__(self, config: KookConfig, event_callback):
        # 数据字段
        self.config = config
        self._bot_id = ""
        self._bot_username = ""
        self._bot_nickname = ""

        # 资源字段
        self._http_client = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bot {self.config.token}",
            }
        )
        self.event_callback = event_callback  # 回调函数，用于处理接收到的事件
        self.ws = None
        self.heartbeat_task = None
        self._stop_event = asyncio.Event()  # 用于通知连接结束

        # 状态/计算字段
        self.running = False
        self.session_id = None
        self.last_sn = 0  # 记录最后处理的消息序号
        self.last_heartbeat_time = 0
        self.heartbeat_failed_count = 0

    @property
    def bot_id(self):
        return self._bot_id

    @property
    def bot_nickname(self):
        return self._bot_nickname

    @property
    def bot_username(self):
        return self._bot_username

    async def get_bot_info(self) -> None:
        """获取机器人账号信息"""
        url = KookApiPaths.USER_ME

        try:
            async with self._http_client.get(url) as resp:
                if resp.status != 200:
                    logger.error(
                        f"[KOOK] 获取机器人账号信息失败，状态码: {resp.status} , {await resp.text()}"
                    )
                    return
                try:
                    resp_content = KookUserMeResponse.from_dict(await resp.json())
                except pydantic.ValidationError as e:
                    logger.error(
                        f"[KOOK] 获取机器人账号信息失败, 响应数据格式错误: \n{e}"
                    )
                    logger.error(f"[KOOK] 响应内容: {await resp.text()}")
                    return

                if not resp_content.success():
                    logger.error(
                        f"[KOOK] 获取机器人账号信息失败: {resp_content.model_dump_json()}"
                    )
                    return

                bot_id: str = resp_content.data.id
                self._bot_id = bot_id
                logger.info(f"[KOOK] 获取机器人账号ID成功: {bot_id}")
                self._bot_nickname = resp_content.data.nickname
                self._bot_username = resp_content.data.username
                logger.info(f"[KOOK] 获取机器人名称成功: {self._bot_nickname}")

        except Exception as e:
            logger.error(f"[KOOK] 获取机器人账号信息异常: {e}")

    async def get_gateway_url(self, resume=False, sn=0, session_id=None) -> str | None:
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

                resp_content = KookGatewayIndexResponse.from_dict(await resp.json())
                if not resp_content.success():
                    logger.error(f"[KOOK] 获取gateway失败: {resp_content}")
                    return None

                gateway_url: str = resp_content.data.url
                logger.info(f"[KOOK] 获取gateway成功: {gateway_url.split('?')[0]}")
                return gateway_url

        except pydantic.ValidationError as e:
            logger.error(f"[KOOK] 获取gateway失败, 响应数据格式错误: \n{e}")
            logger.error(f"[KOOK] 原始响应内容: {await resp.text()}")
            return None

        except Exception as e:
            logger.error(f"[KOOK] 获取gateway异常: {e}")
            return None

    async def connect(self, resume=False):
        """连接WebSocket"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._stop_event.clear()
        try:
            # 获取gateway地址
            gateway_url = await self.get_gateway_url(
                resume=resume, sn=self.last_sn, session_id=self.session_id
            )
            await self.get_bot_info()

            if not gateway_url:
                return False

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
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None
            return False

    async def listen(self):
        """监听WebSocket消息"""
        try:
            while self.running:
                try:
                    if self.ws is None:
                        logger.error("[KOOK] WebSocket 对象丢失，结束监听流程。")
                        break

                    msg = await asyncio.wait_for(self.ws.recv(), timeout=10)

                    if isinstance(msg, bytes):
                        try:
                            msg = zlib.decompress(msg)
                        except Exception as e:
                            logger.error(f"[KOOK] 解压消息失败: {e}")
                            continue
                        msg = msg.decode("utf-8")

                    event = KookWebsocketEvent.from_json(msg)

                    # 处理不同类型的信令
                    await self._handle_signal(event)

                except pydantic.ValidationError as e:
                    logger.error(f"[KOOK] 解析WebSocket事件数据格式失败: \n{e}")
                    logger.error(f"[KOOK] 原始响应内容: {msg}")
                    continue

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

    async def _handle_signal(self, event: KookWebsocketEvent):
        """处理不同类型的信令"""
        data = event.data

        match event.signal:
            case KookMessageSignal.MESSAGE:
                if event.sn is not None:
                    self.last_sn = event.sn
                await self.event_callback(data)

            case KookMessageSignal.HELLO:
                assert isinstance(data, KookHelloEventData)
                await self._handle_hello(data)

            case KookMessageSignal.RESUME_ACK:
                assert isinstance(data, KookResumeAckEventData)
                await self._handle_resume_ack(data)

            case KookMessageSignal.PONG:
                await self._handle_pong()

            case KookMessageSignal.RECONNECT:
                await self._handle_reconnect()

            case _:
                logger.debug(
                    f"[KOOK] 未处理的信令类型: {event.signal.name}({event.signal.value})"
                )

    async def _handle_hello(self, data: KookHelloEventData):
        """处理HELLO握手"""
        code = data.code

        if code == 0:
            self.session_id = data.session_id
            logger.info(f"[KOOK] 握手成功，session_id: {self.session_id}")
            # TODO 重置重连延迟
            # self.reconnect_delay = 1
        else:
            logger.error(f"[KOOK] 握手失败，错误码: {code}")
            if code == 40103:  # token过期
                logger.error("[KOOK] Token已过期，需要重新获取")
            self.running = False

    async def _handle_pong(self):
        """处理PONG心跳响应"""
        self.last_heartbeat_time = time.time()
        self.heartbeat_failed_count = 0

    async def _handle_reconnect(self):
        """处理重连指令"""
        logger.warning("[KOOK] 收到重连指令")
        # 清空本地状态
        self.last_sn = 0
        self.session_id = None
        self.running = False

    async def _handle_resume_ack(self, data: KookResumeAckEventData):
        """处理RESUME确认"""
        self.session_id = data.session_id
        logger.info(f"[KOOK] Resume成功，session_id: {self.session_id}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.running:
            try:
                # 随机化心跳间隔 (±5秒)
                interval = max(
                    1, self.config.heartbeat_interval + random.randint(-5, 5)
                )
                await asyncio.sleep(interval)

                if not self.running:
                    break

                # 发送心跳
                await self._send_ping()

                # 等待PONG响应
                await asyncio.sleep(self.config.heartbeat_timeout)

                # 检查是否收到PONG响应
                if (
                    time.time() - self.last_heartbeat_time
                    > self.config.heartbeat_timeout
                ):
                    self.heartbeat_failed_count += 1
                    logger.warning(
                        f"[KOOK] 心跳超时，失败次数: {self.heartbeat_failed_count}"
                    )

                    if (
                        self.heartbeat_failed_count
                        >= self.config.max_heartbeat_failures
                    ):
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
        if self.ws is None:
            logger.warning("[KOOK] 尚未连接kook WebSocket服务器, 跳过发送心跳包流程")
            return
        try:
            ping_data = KookWebsocketEvent(
                signal=KookMessageSignal.PING,
                data=None,
                sn=self.last_sn,
            )
            await self.ws.send(ping_data.to_json())
        except Exception as e:
            logger.error(f"[KOOK] 发送心跳失败: {e}")

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
                    if result.get("code") != 0:
                        raise RuntimeError(
                            f'发送kook消息类型 "{kook_message_type.name}" 失败: {result}'
                        )
                    # else:
                    #     logger.info("[KOOK] 发送消息成功")
                else:
                    raise RuntimeError(
                        f'发送kook消息类型 "{kook_message_type.name}" HTTP错误: {resp.status} , 响应内容 : {await resp.text()}'
                    )
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(
                f'[KOOK] 发送kook消息类型 "{kook_message_type.name}" 异常: {e}'
            )

    async def upload_asset(self, file_url: str | None) -> str:
        """上传文件到kook,获得远端资源url
        接口定义参见: https://developer.kookapp.cn/doc/http/asset
        """
        if not file_url:
            return ""

        bytes_data: bytes | None = None
        filename = "unknown"
        if file_url.startswith(("http://", "https://")):
            filename = file_url.split("/")[-1]
            return file_url

        if file_url.startswith("base64:///"):
            # b64decode的时候得开头留一个'/'的, 不然会报错
            b64_str = file_url.removeprefix("base64://")
            bytes_data = base64.b64decode(b64_str)

        elif file_url.startswith("file://") or os.path.exists(file_url):
            file_url = file_url.removeprefix("file:///")
            file_url = file_url.removeprefix("file://")

            try:
                target_path = Path(file_url).resolve()
            except Exception as exp:
                logger.error(f'[KOOK] 获取文件 "{file_url}" 绝对路径失败: "{exp}"')
                raise FileNotFoundError(
                    f'获取文件 "{file_url}" 绝对路径失败: "{exp}"'
                ) from exp

            if not target_path.is_file():
                raise FileNotFoundError(f"文件不存在: {target_path.name}")

            filename = target_path.name
            async with aiofiles.open(target_path, "rb") as f:
                bytes_data = await f.read()

        else:
            raise ValueError(f'[KOOK] 不支持的文件资源类型: "{file_url}"')

        data = aiohttp.FormData()
        data.add_field("file", bytes_data, filename=filename)

        url = KookApiPaths.ASSET_CREATE
        try:
            async with self._http_client.post(url, data=data) as resp:
                if resp.status == 200:
                    result: dict = await resp.json()
                    logger.debug(f"[KOOK] 上传文件响应: {result}")
                    if result.get("code") == 0:
                        logger.info("[KOOK] 上传文件到kook服务器成功")
                        remote_url = result["data"]["url"]
                        logger.debug(f"[KOOK] 文件远端URL: {remote_url}")
                        return remote_url
                    else:
                        raise RuntimeError(f"上传文件到kook服务器失败: {result}")
                else:
                    raise RuntimeError(
                        f"上传文件到kook服务器 HTTP错误: {resp.status} , {await resp.text()}"
                    )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"上传文件到kook服务器异常: {e}") from e

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
