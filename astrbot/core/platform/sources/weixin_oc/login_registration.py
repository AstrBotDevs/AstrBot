from dataclasses import dataclass
from typing import Any

from .weixin_oc_client import WeixinOCClient

DEFAULT_WEIXIN_OC_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_WEIXIN_OC_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_WEIXIN_OC_BOT_TYPE = "3"
DEFAULT_WEIXIN_OC_QR_POLL_INTERVAL = 1
DEFAULT_WEIXIN_OC_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_WEIXIN_OC_API_TIMEOUT_MS = 15_000


@dataclass
class WeixinOCLoginRegistration:
    qrcode: str
    qrcode_img_content: str
    interval: int


def normalize_weixin_oc_base_url(base_url: str | None) -> str:
    return (base_url or DEFAULT_WEIXIN_OC_BASE_URL).strip().rstrip("/")


def _string_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _int_config(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, minimum)


def weixin_oc_login_result(
    data: dict[str, Any],
    *,
    default_base_url: str,
) -> dict[str, Any]:
    raw_status = _string_field(data, "status") or "wait"
    if raw_status == "confirmed":
        bot_token = _string_field(data, "bot_token")
        if not bot_token:
            return {"status": "error", "message": "登录成功但未返回 token"}
        base_url = _string_field(data, "baseurl") or default_base_url
        return {
            "status": "created",
            "qr_status": raw_status,
            "weixin_oc_token": bot_token,
            "weixin_oc_account_id": _string_field(data, "ilink_bot_id"),
            "weixin_oc_base_url": normalize_weixin_oc_base_url(base_url),
            "weixin_oc_user_id": _string_field(data, "ilink_user_id"),
        }
    if raw_status == "expired":
        return {"status": "expired", "qr_status": raw_status, "message": "二维码已过期"}
    if raw_status in {"cancel", "canceled", "denied"}:
        return {"status": "denied", "qr_status": raw_status, "message": "用户取消登录"}
    return {"status": "pending", "qr_status": raw_status}


def _client(
    *,
    adapter_id: str,
    base_url: str,
    api_timeout_ms: int,
) -> WeixinOCClient:
    return WeixinOCClient(
        adapter_id=adapter_id,
        base_url=base_url,
        cdn_base_url=DEFAULT_WEIXIN_OC_CDN_BASE_URL,
        api_timeout_ms=api_timeout_ms,
    )


async def request_weixin_oc_login_qr(
    platform_config: dict[str, Any],
) -> WeixinOCLoginRegistration:
    base_url = normalize_weixin_oc_base_url(
        _string_field(platform_config, "weixin_oc_base_url")
    )
    bot_type = _string_field(platform_config, "weixin_oc_bot_type")
    if not bot_type:
        bot_type = DEFAULT_WEIXIN_OC_BOT_TYPE
    api_timeout_ms = _int_config(
        platform_config.get("weixin_oc_api_timeout_ms"),
        DEFAULT_WEIXIN_OC_API_TIMEOUT_MS,
        1_000,
    )
    interval = _int_config(
        platform_config.get("weixin_oc_qr_poll_interval"),
        DEFAULT_WEIXIN_OC_QR_POLL_INTERVAL,
        1,
    )

    client = _client(
        adapter_id=str(platform_config.get("id") or "weixin_oc"),
        base_url=base_url,
        api_timeout_ms=api_timeout_ms,
    )
    try:
        data = await client.request_json(
            "GET",
            "ilink/bot/get_bot_qrcode",
            params={"bot_type": bot_type},
            token_required=False,
            timeout_ms=15_000,
        )
    finally:
        await client.close()

    qrcode = _string_field(data, "qrcode")
    qrcode_img_content = _string_field(data, "qrcode_img_content")
    if not qrcode or not qrcode_img_content:
        raise RuntimeError("个人微信二维码响应格式异常")

    return WeixinOCLoginRegistration(
        qrcode=qrcode,
        qrcode_img_content=qrcode_img_content,
        interval=interval,
    )


async def poll_weixin_oc_login_once(
    *,
    platform_config: dict[str, Any],
    qrcode: str,
) -> dict[str, Any]:
    if not qrcode:
        raise ValueError("Missing qrcode")

    base_url = normalize_weixin_oc_base_url(
        _string_field(platform_config, "weixin_oc_base_url")
    )
    api_timeout_ms = _int_config(
        platform_config.get("weixin_oc_api_timeout_ms"),
        DEFAULT_WEIXIN_OC_API_TIMEOUT_MS,
        1_000,
    )
    long_poll_timeout_ms = _int_config(
        platform_config.get("weixin_oc_long_poll_timeout_ms"),
        DEFAULT_WEIXIN_OC_LONG_POLL_TIMEOUT_MS,
        1_000,
    )

    client = _client(
        adapter_id=str(platform_config.get("id") or "weixin_oc"),
        base_url=base_url,
        api_timeout_ms=api_timeout_ms,
    )
    try:
        data = await client.request_json(
            "GET",
            "ilink/bot/get_qrcode_status",
            params={"qrcode": qrcode},
            token_required=False,
            timeout_ms=long_poll_timeout_ms,
            headers={"iLink-App-ClientVersion": "1"},
        )
    finally:
        await client.close()

    return weixin_oc_login_result(data, default_base_url=base_url)
