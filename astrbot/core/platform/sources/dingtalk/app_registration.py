import os
from dataclasses import dataclass
from typing import Any

import aiohttp

DEFAULT_DINGTALK_REGISTRATION_BASE_URL = "https://oapi.dingtalk.com"
DEFAULT_DINGTALK_REGISTRATION_SOURCE = "DING_DWS_CLAW"


@dataclass
class DingtalkAppRegistration:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def dingtalk_registration_base_url() -> str:
    return (
        os.getenv("DINGTALK_REGISTRATION_BASE_URL", "").strip()
        or DEFAULT_DINGTALK_REGISTRATION_BASE_URL
    ).rstrip("/")


def dingtalk_registration_source() -> str:
    return (
        os.getenv("DINGTALK_REGISTRATION_SOURCE", "").strip()
        or DEFAULT_DINGTALK_REGISTRATION_SOURCE
    )


def _string_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _int_field(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


async def _post_registration(
    path: str,
    payload: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.post(
            f"{dingtalk_registration_base_url()}{path}",
            json=payload,
        ) as response:
            status = response.status
            data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise RuntimeError("DingTalk registration response format is invalid")
    return status, data


def _raise_dingtalk_registration_error(
    status: int,
    raw: dict[str, Any],
    action: str,
) -> None:
    errcode = raw.get("errcode", 0)
    if status < 400 and int(errcode or 0) == 0:
        return
    errmsg = _string_field(raw, "errmsg") or "unknown error"
    raise RuntimeError(f"[{action}] {errmsg} (errcode={errcode})")


async def request_dingtalk_app_registration() -> DingtalkAppRegistration:
    status, init_raw = await _post_registration(
        "/app/registration/init",
        {"source": dingtalk_registration_source()},
    )
    _raise_dingtalk_registration_error(status, init_raw, "init")
    nonce = _string_field(init_raw, "nonce")
    if not nonce:
        raise RuntimeError("[init] missing nonce")

    status, begin_raw = await _post_registration(
        "/app/registration/begin",
        {"nonce": nonce},
    )
    _raise_dingtalk_registration_error(status, begin_raw, "begin")

    device_code = _string_field(begin_raw, "device_code")
    verification_uri_complete = _string_field(begin_raw, "verification_uri_complete")
    if not device_code:
        raise RuntimeError("[begin] missing device_code")
    if not verification_uri_complete:
        raise RuntimeError("[begin] missing verification_uri_complete")

    return DingtalkAppRegistration(
        device_code=device_code,
        user_code=_string_field(begin_raw, "user_code"),
        verification_uri=_string_field(begin_raw, "verification_uri"),
        verification_uri_complete=verification_uri_complete,
        expires_in=max(_int_field(begin_raw, "expires_in", 7200), 60),
        interval=max(_int_field(begin_raw, "interval", 3), 1),
    )


async def poll_dingtalk_app_registration_once(device_code: str) -> dict[str, Any]:
    status, raw = await _post_registration(
        "/app/registration/poll",
        {"device_code": device_code},
    )
    _raise_dingtalk_registration_error(status, raw, "poll")
    return dingtalk_registration_poll_result(raw)


def dingtalk_registration_poll_result(raw: dict[str, Any]) -> dict[str, Any]:
    status_raw = _string_field(raw, "status").upper()
    if status_raw == "WAITING":
        return {"status": "pending"}
    if status_raw == "SUCCESS":
        client_id = _string_field(raw, "client_id")
        client_secret = _string_field(raw, "client_secret")
        if not client_id or not client_secret:
            return {"status": "error", "message": "扫码成功但未获取到钉钉应用凭证"}
        return {
            "status": "created",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    if status_raw == "FAIL":
        return {
            "status": "error",
            "message": _string_field(raw, "fail_reason") or "钉钉扫码创建失败",
        }
    if status_raw == "EXPIRED":
        return {"status": "expired", "message": "钉钉扫码已过期，请重新创建"}
    return {
        "status": "error",
        "message": f"钉钉扫码创建返回未知状态: {status_raw or 'UNKNOWN'}",
    }
