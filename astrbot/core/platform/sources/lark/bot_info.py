from dataclasses import dataclass
from typing import Any

import aiohttp

from .app_registration import DEFAULT_FEISHU_OPEN_DOMAIN, DEFAULT_LARK_OPEN_DOMAIN

TENANT_ACCESS_TOKEN_INTERNAL_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
BOT_INFO_PATH = "/open-apis/bot/v3/info"
LARK_PLATFORM_POLICY_DENIED_CODE = 21001


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


async def _request_json(
    method: str,
    endpoint: str,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Call a Lark Open API endpoint and return its JSON body.

    Args:
        method: HTTP method, such as ``GET`` or ``POST``.
        endpoint: Full Open API URL.
        action: Short description of the call, used in error messages.
        **kwargs: Extra arguments forwarded to ``aiohttp.ClientSession.request``.

    Returns:
        The decoded JSON object of a response whose business ``code`` is 0.

    Raises:
        RuntimeError: If the response is not a JSON object or has a non-zero
            ``code``. The message keeps the HTTP status, ``code``, ``msg`` and
            the ``x-tt-logid`` header so the request can be traced with Lark
            support. Request payloads and headers are never included.
    """
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.request(method, endpoint, **kwargs) as response:
            status = response.status
            log_id = response.headers.get("x-tt-logid") or "n/a"
            data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Failed to {action}: unexpected response format "
            f"(HTTP {status}, log_id={log_id})"
        )
    code = data.get("code")
    if code != 0:
        message = (
            f"Failed to {action}: code={code}, "
            f"msg={_string_field(data, 'msg') or 'n/a'} "
            f"(HTTP {status}, log_id={log_id})"
        )
        if code == LARK_PLATFORM_POLICY_DENIED_CODE:
            # Retrying cannot get past a platform policy denial, so tell the
            # admin where to look instead.
            message += (
                ". Lark/Feishu denied the request due to platform policy; "
                "retrying will not help. Check the app and tenant status in the "
                "Lark/Feishu developer console, or contact Lark/Feishu support "
                "with the log_id."
            )
        raise RuntimeError(message)
    return data


async def request_lark_bot_info(
    *,
    domain: str,
    app_id: str,
    app_secret: str,
) -> LarkBotInfo:
    open_base = _open_base(domain)
    token_data = await _request_json(
        "POST",
        f"{open_base}{TENANT_ACCESS_TOKEN_INTERNAL_PATH}",
        "obtain Lark tenant access token",
        json={
            "app_id": app_id,
            "app_secret": app_secret,
        },
    )
    tenant_access_token = _string_field(token_data, "tenant_access_token")
    if not tenant_access_token:
        raise RuntimeError("Lark token response is missing tenant_access_token")

    bot_data = await _request_json(
        "GET",
        f"{open_base}{BOT_INFO_PATH}",
        "fetch Lark bot info",
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    bot = bot_data.get("bot")
    if not isinstance(bot, dict):
        raise RuntimeError("Lark bot info response is missing the bot field")

    return LarkBotInfo(
        app_name=_string_field(bot, "app_name"),
        open_id=_string_field(bot, "open_id"),
    )
