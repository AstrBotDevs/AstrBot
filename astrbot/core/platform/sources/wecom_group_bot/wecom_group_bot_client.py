"""企业微信消息推送机器人（原群机器人）主动发送客户端"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.message_components import Image, Plain


class WecomGroupBotClient:
    """封装 webhook 主动推送能力"""

    async def send_plain_message(
        self,
        webhook_url: str,
        chat_id: str | None,
        plain: Plain,
        mentioned_list: list[str] | None = None,
    ) -> None:
        content = plain.text.strip()
        if not content:
            return
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }
        if chat_id:
            payload["chatid"] = chat_id
        if mentioned_list:
            payload["text"]["mentioned_list"] = mentioned_list
        await self._post(webhook_url, payload)

    async def send_image_message(self, webhook_url: str, chat_id: str | None, image: Image) -> None:
        base64_data = await image.convert_to_base64()
        if not base64_data:
            logger.warning("无法获取图片 base64 数据，跳过发送")
            return
        image_bytes = base64.b64decode(base64_data)
        payload = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": hashlib.md5(image_bytes).hexdigest(),
            },
        }
        if chat_id:
            payload["chatid"] = chat_id
        await self._post(webhook_url, payload)

    async def _post(self, webhook_url: str, payload: dict[str, Any]) -> None:
        if not webhook_url:
            logger.error("未提供 webhook_url，无法发送企业微信消息推送机器人（原群机器人）消息")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=10) as response:
                    text = await response.text()
                    if response.status != 200:
                        logger.error(
                            "发送企业微信消息推送机器人（原群机器人）消息失败，状态码=%s，响应=%s",
                            response.status,
                            text,
                        )
                        return
                    data = json.loads(text) if text else {}
                    if data.get("errcode") not in (None, 0):
                        logger.error("企业微信返回错误: %s", data)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("发送企业微信消息推送机器人（原群机器人）消息失败: %s", exc)
