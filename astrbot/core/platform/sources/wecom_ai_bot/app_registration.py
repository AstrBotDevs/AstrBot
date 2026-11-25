"""Official WeCom AI Bot QR registration without a scanner identity claim."""

import sys
from urllib.parse import urlsplit

import aiohttp


async def wecom_ai_registration(action: str, registration_code: str = "") -> dict:
    """Run one official QR request and project its credential result.

    Args:
        action: Registration start or poll.
        registration_code: The server-held code returned by start.

    Returns:
        A pending, created, expired or error registration result.

    Raises:
        ValueError: The action or official response is invalid.
    """
    if action == "start":
        path = "generate"
        params = {
            "source": "astrbot",
            "plat": 2
            if sys.platform == "win32"
            else 3
            if sys.platform.startswith("linux")
            else 1,
        }
    elif (
        action == "poll"
        and isinstance(registration_code, str)
        and registration_code.strip()
    ):
        path = "query_result"
        params = {"scode": registration_code}
    else:
        raise ValueError("Invalid WeCom registration request")
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10), trust_env=False
    ) as http:
        async with http.get(
            "https://work.weixin.qq.com/ai/qc/" + path,
            params=params,
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise ValueError("WeCom registration request failed")
            value = await response.json()
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Invalid WeCom registration response")
    if action == "start":
        code, address = data.get("scode"), data.get("auth_url")
        if (
            not isinstance(code, str)
            or not code.strip()
            or not isinstance(address, str)
        ):
            raise ValueError("Incomplete WeCom registration response")
        url = urlsplit(address)
        if (
            url.scheme != "https"
            or url.hostname != "work.weixin.qq.com"
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise ValueError("Invalid WeCom verification URL")
        return {
            "status": "pending",
            "registration_code": code,
            "verification_uri_complete": address,
            "expires_in": 300,
            "interval": 3,
        }
    status = str(data.get("status", "")).lower()
    if status == "success":
        bot = data.get("bot_info") or {}
        if not all(
            isinstance(bot.get(k), str) and bot[k].strip() for k in ("botid", "secret")
        ):
            raise ValueError("Incomplete WeCom bot credentials")
        return {
            "status": "created",
            "wecomaibot_ws_bot_id": bot["botid"],
            "wecomaibot_ws_secret": bot["secret"],
            "wecom_ai_bot_connection_mode": "long_connection",
        }
    if status in {"expired", "timeout"}:
        return {"status": "expired"}
    if status in {"fail", "failed", "error"}:
        return {"status": "error"}
    return {"status": "pending"}
