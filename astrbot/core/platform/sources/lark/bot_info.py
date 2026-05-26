from dataclasses import dataclass
from typing import Any

import aiohttp

from .app_registration import DEFAULT_FEISHU_OPEN_DOMAIN, DEFAULT_LARK_OPEN_DOMAIN

TENANT_ACCESS_TOKEN_INTERNAL_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
BOT_INFO_PATH = "/open-apis/bot/v3/info"


@dataclass
class LarkBotInfo:
    app_name: str
    open_id: str


def _open_base(domain: str) -> str:
    normalized = (domain or DEFAULT_FEISHU_OPEN_DOMAIN).strip().rstrip("/")
    if normalized in {"feishu", DEFAULT_FEISHU_OPEN_DOMAIN}:
        return DEFAULT_FEISHU_OPEN_DOMAIN
    if normalized in {"lark", DEFAULT_LARK_OPEN_DOMAIN}:
        return DEFAULT_LARK_OPEN_DOMAIN
    return normalized


def _string_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


async def _post_json(
    endpoint: str,
    payload: dict[str, str],
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.post(endpoint, json=payload) as response:
            data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise RuntimeError("飞书接口响应格式异常")
    return data


async def _get_json(
    endpoint: str,
    *,
    headers: dict[str, str],
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(endpoint, headers=headers) as response:
            data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise RuntimeError("飞书接口响应格式异常")
    return data


async def request_lark_bot_info(
    *,
    domain: str,
    app_id: str,
    app_secret: str,
) -> LarkBotInfo:
    open_base = _open_base(domain)
    token_data = await _post_json(
        f"{open_base}{TENANT_ACCESS_TOKEN_INTERNAL_PATH}",
        {
            "app_id": app_id,
            "app_secret": app_secret,
        },
    )
    if token_data.get("code") != 0:
        raise RuntimeError(_string_field(token_data, "msg") or "获取飞书访问令牌失败")

    tenant_access_token = _string_field(token_data, "tenant_access_token")
    if not tenant_access_token:
        raise RuntimeError("飞书访问令牌响应缺少 tenant_access_token")

    bot_data = await _get_json(
        f"{open_base}{BOT_INFO_PATH}",
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    if bot_data.get("code") != 0:
        raise RuntimeError(_string_field(bot_data, "msg") or "获取飞书机器人信息失败")

    bot = bot_data.get("bot")
    if not isinstance(bot, dict):
        raise RuntimeError("飞书机器人信息响应缺少 bot 字段")

    return LarkBotInfo(
        app_name=_string_field(bot, "app_name"),
        open_id=_string_field(bot, "open_id"),
    )
