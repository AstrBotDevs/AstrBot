"""飞书(Lark) Webhook 服务器实现

实现飞书事件订阅的 Webhook 模式，支持:
1. 请求 URL 验证 (challenge 验证)
2. 事件加密/解密 (AES-256-CBC)
3. 签名校验 (SHA256)
4. 事件接收和处理
"""

import asyncio
import base64
import hashlib
import json
from collections.abc import Awaitable, Callable

from Crypto.Cipher import AES

from astrbot.api import logger


class AESCipher:
    """AES 加密/解密工具类"""

    def __init__(self, key: str):
        self.bs = AES.block_size
        self.key = hashlib.sha256(self.str_to_bytes(key)).digest()

    @staticmethod
    def str_to_bytes(data):
        u_type = type(b"".decode("utf8"))
        if isinstance(data, u_type):
            return data.encode("utf8")
        return data

    @staticmethod
    def _unpad(s):
        return s[: -ord(s[len(s) - 1 :])]

    def decrypt(self, enc):
        iv = enc[: AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[AES.block_size :]))

    def decrypt_string(self, enc):
        enc = base64.b64decode(enc)
        return self.decrypt(enc).decode("utf8")


class LarkWebhookServer:
    """飞书 Webhook 服务器

    仅支持统一 Webhook 模式
    """

    def __init__(self, config: dict, event_queue: asyncio.Queue):
        """初始化 Webhook 服务器

        Args:
            config: 飞书配置
            event_queue: 事件队列
        """
        self.app_id = config["app_id"]
        self.app_secret = config["app_secret"]
        self.encrypt_key = config.get("lark_encrypt_key", "")
        self.verification_token = config.get("lark_verification_token", "")

        self.event_queue = event_queue
        self.callback: Callable[[dict], Awaitable[None]] | None = None

        # 初始化加密工具
        self.cipher = None
        if self.encrypt_key:
            self.cipher = AESCipher(self.encrypt_key)

    def verify_signature(
        self,
        timestamp: str,
        nonce: str,
        encrypt_key: str,
        body: bytes,
        signature: str,
    ) -> bool:
        """验证签名

        Args:
            timestamp: 请求时间戳
            nonce: 随机数
            encrypt_key: 加密密钥
            body: 请求体
            signature: 签名

        Returns:
            签名是否有效
        """
        # 拼接字符串: timestamp + nonce + encrypt_key + body
        bytes_b1 = (timestamp + nonce + encrypt_key).encode("utf-8")
        bytes_b = bytes_b1 + body
        h = hashlib.sha256(bytes_b)
        calculated_signature = h.hexdigest()
        return calculated_signature == signature

    def decrypt_event(self, encrypted_data: str) -> dict:
        """解密事件数据

        Args:
            encrypted_data: 加密的事件数据

        Returns:
            解密后的事件字典
        """
        if not self.cipher:
            raise ValueError("未配置 encrypt_key，无法解密事件")

        decrypted_str = self.cipher.decrypt_string(encrypted_data)
        return json.loads(decrypted_str)

    async def handle_challenge(self, event_data: dict) -> dict:
        """处理 challenge 验证请求

        Args:
            event_data: 事件数据

        Returns:
            包含 challenge 的响应
        """
        challenge = event_data.get("challenge", "")
        logger.info(f"[Lark Webhook] 收到 challenge 验证请求: {challenge}")

        return {"challenge": challenge}

    async def handle_callback(self, request) -> tuple[dict, int] | dict:
        """处理 webhook 回调，可被统一 webhook 入口复用

        Args:
            request: Quart 请求对象

        Returns:
            响应数据
        """
        # 获取原始请求体
        body = await request.get_data()

        try:
            event_data = await request.json
        except Exception as e:
            logger.error(f"[Lark Webhook] 解析请求体失败: {e}")
            return {"error": "Invalid JSON"}, 400

        if not event_data:
            logger.error("[Lark Webhook] 请求体为空")
            return {"error": "Empty request body"}, 400

        # 如果配置了 encrypt_key，进行签名验证
        if self.encrypt_key:
            timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
            nonce = request.headers.get("X-Lark-Request-Nonce", "")
            signature = request.headers.get("X-Lark-Signature", "")

            if timestamp and nonce and signature:
                if not self.verify_signature(
                    timestamp, nonce, self.encrypt_key, body, signature
                ):
                    logger.error("[Lark Webhook] 签名验证失败")
                    return {"error": "Invalid signature"}, 401

        # 检查是否是加密事件
        if "encrypt" in event_data:
            try:
                event_data = self.decrypt_event(event_data["encrypt"])
                logger.debug(f"[Lark Webhook] 解密后的事件: {event_data}")
            except Exception as e:
                logger.error(f"[Lark Webhook] 解密事件失败: {e}")
                return {"error": "Decryption failed"}, 400

        # 验证 token
        if self.verification_token:
            header = event_data.get("header", {})
            if header:
                token = header.get("token", "")
            else:
                token = event_data.get("token", "")
            if token != self.verification_token:
                logger.error("[Lark Webhook] Verification Token 不匹配。")
                return {"error": "Invalid verification token"}, 401

        # 处理 URL 验证 (challenge)
        if event_data.get("type") == "url_verification":
            return await self.handle_challenge(event_data)

        # 调用回调函数处理事件
        if self.callback:
            try:
                await self.callback(event_data)
            except Exception as e:
                logger.error(f"[Lark Webhook] 处理事件回调失败: {e}", exc_info=True)
                return {"error": "Event processing failed"}, 500

        return {}

    def set_callback(self, callback: Callable[[dict], Awaitable[None]]):
        """设置事件回调函数

        Args:
            callback: 处理事件的异步函数
        """
        self.callback = callback
