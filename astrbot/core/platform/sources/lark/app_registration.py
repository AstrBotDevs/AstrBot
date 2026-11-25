import base64
import gzip
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp

DEFAULT_FEISHU_OPEN_DOMAIN = "https://open.feishu.cn"
DEFAULT_LARK_OPEN_DOMAIN = "https://open.larksuite.com"
APP_REGISTRATION_PATH = "/oauth/v1/app/registration"
GROUP_MEMBERSHIP_ADDONS = {
    "preset": False,
    "scopes": {"tenant": ["im:chat.members:bot_access", "im:chat.members:read"]},
    "events": {
        "items": {
            "tenant": [
                "im.chat.member.bot.deleted_v1",
                "im.chat.member.user.deleted_v1",
            ]
        }
    },
}


@dataclass
class LarkAppRegistrationEndpoints:
    accounts_base: str
    open_base: str
    registration: str


@dataclass
class LarkAppRegistration:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def resolve_app_registration_endpoints(
    domain: str,
) -> LarkAppRegistrationEndpoints:
    normalized = (domain or DEFAULT_FEISHU_OPEN_DOMAIN).strip().rstrip("/")
    if normalized in {"feishu", DEFAULT_FEISHU_OPEN_DOMAIN}:
        accounts_base = "https://accounts.feishu.cn"
        open_base = DEFAULT_FEISHU_OPEN_DOMAIN
    elif normalized in {"lark", DEFAULT_LARK_OPEN_DOMAIN}:
        accounts_base = "https://accounts.larksuite.com"
        open_base = DEFAULT_LARK_OPEN_DOMAIN
    else:
        open_base = normalized
        accounts_base = normalized.replace("://open.", "://accounts.", 1)

    return LarkAppRegistrationEndpoints(
        accounts_base=accounts_base,
        open_base=open_base,
        registration=f"{accounts_base}{APP_REGISTRATION_PATH}",
    )


def _registration_data(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    if isinstance(data, dict):
        return data
    return raw


def _string_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value
    return ""


def _int_field(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


async def _post_registration(
    endpoint: str,
    form: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.post(
            endpoint,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as response:
            status = response.status
            data = await response.json(content_type=None)
    if not isinstance(data, dict):
        raise RuntimeError("飞书应用创建响应格式异常")
    return status, data


def _raise_registration_error(status: int, raw: dict[str, Any], fallback: str) -> None:
    data = _registration_data(raw)
    if status < 400 and not raw.get("error") and not data.get("error"):
        return
    message = (
        _string_field(raw, "error_description")
        or _string_field(data, "error_description")
        or _string_field(raw, "error")
        or _string_field(data, "error")
        or fallback
    )
    raise RuntimeError(message)


async def request_app_registration(
    domain: str, *, membership_app_id: str | None = None
) -> LarkAppRegistration:
    endpoints = resolve_app_registration_endpoints(domain)
    status, raw = await _post_registration(
        endpoints.registration,
        {
            "action": "begin",
            "archetype": "PersonalAgent",
            "auth_method": "client_secret",
            "request_user_info": "open_id tenant_brand",
        },
    )
    _raise_registration_error(status, raw, "发起扫码创建失败")
    data = _registration_data(raw)
    user_code = _string_field(data, "user_code")
    verification_uri = _string_field(data, "verification_uri")
    verification_uri_complete = _string_field(data, "verification_uri_complete")
    if membership_app_id is not None:
        # Lark's SDK attaches the target and incremental addons to the launcher.
        # Keep the original device code for AstrBot's separate poll request.
        launcher = urlsplit(verification_uri_complete)
        if (
            not _string_field(data, "device_code")
            or launcher.scheme != "https"
            or f"https://{launcher.netloc}" != endpoints.open_base
            or launcher.path != "/page/launcher"
            or launcher.fragment
        ):
            raise RuntimeError("Lark returned no launcher for the requested app")
        query = parse_qs(launcher.query, keep_blank_values=True)
        if "createOnly" in query or query.get("clientID", [membership_app_id]) != [
            membership_app_id
        ]:
            raise RuntimeError("Lark returned a different app registration target")
        manifest = json.dumps(GROUP_MEMBERSHIP_ADDONS, separators=(",", ":")).encode()
        query.update(
            {
                "from": ["sdk"],
                "tp": ["sdk"],
                "source": ["AstrBot"],
                "clientID": [membership_app_id],
                "addons": [
                    base64.urlsafe_b64encode(gzip.compress(manifest, mtime=0))
                    .decode()
                    .rstrip("=")
                ],
            }
        )
        verification_uri_complete = launcher._replace(
            query=urlencode(query, doseq=True)
        ).geturl()
        verification_uri = verification_uri_complete
    elif not verification_uri_complete and user_code:
        verification_uri_complete = (
            f"{endpoints.open_base}/page/cli?{urlencode({'user_code': user_code})}"
        )

    return LarkAppRegistration(
        device_code=_string_field(data, "device_code"),
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=_int_field(data, "expires_in", 300),
        interval=_int_field(data, "interval", 5),
    )


def _tenant_brand(data: dict[str, Any]) -> str:
    user_info = data.get("user_info")
    if isinstance(user_info, dict):
        return _string_field(user_info, "tenant_brand")
    return _string_field(data, "tenant_brand")


async def poll_app_registration_once(
    *,
    domain: str,
    device_code: str,
    membership_app_id: str | None = None,
) -> dict[str, Any]:
    endpoints = resolve_app_registration_endpoints(domain)
    status, raw = await _post_registration(
        endpoints.registration,
        {
            "action": "poll",
            "device_code": device_code,
        },
    )
    data = _registration_data(raw)
    error = _string_field(raw, "error") or _string_field(data, "error")
    client_id = _string_field(data, "client_id")
    client_secret = _string_field(data, "client_secret")
    tenant_brand = _tenant_brand(data)

    if status < 400 and not error and client_id:
        result_domain = (
            DEFAULT_LARK_OPEN_DOMAIN
            if tenant_brand == "lark"
            else DEFAULT_FEISHU_OPEN_DOMAIN
        )
        if membership_app_id is not None:
            expected_brand = (
                "lark" if endpoints.open_base == DEFAULT_LARK_OPEN_DOMAIN else "feishu"
            )
            if (
                client_id != membership_app_id
                or tenant_brand
                and tenant_brand != expected_brand
            ):
                return {
                    "status": "error",
                    "message": "Lark returned a different app or domain",
                }
            result_domain = endpoints.open_base
        elif not client_secret and tenant_brand == "lark":
            client_secret = await _poll_lark_secret(device_code)
        if not client_secret:
            return {"status": "error", "message": "应用创建成功但未获取到凭证"}
        user_info = data.get("user_info")
        user_open_id = (
            _string_field(user_info, "open_id").strip()
            if isinstance(user_info, dict)
            else ""
        )
        return {
            "status": "created",
            "app_id": client_id,
            "app_secret": client_secret,
            **(
                {"user_open_id": user_open_id}
                if user_open_id and not any(char.isspace() for char in user_open_id)
                else {}
            ),
            "tenant_brand": tenant_brand,
            "domain": result_domain,
        }
    if error == "authorization_pending":
        return {"status": "pending"}
    if error == "slow_down":
        return {"status": "slow_down"}
    if error == "access_denied":
        return {"status": "denied", "message": "用户取消了扫码创建"}
    if error in {"expired_token", "invalid_grant"}:
        return {"status": "expired", "message": "扫码已过期，请再次创建"}

    message = (
        _string_field(raw, "error_description")
        or _string_field(data, "error_description")
        or error
        or "获取扫码创建状态失败"
    )
    return {"status": "error", "message": message}


async def _poll_lark_secret(device_code: str) -> str:
    endpoints = resolve_app_registration_endpoints(DEFAULT_LARK_OPEN_DOMAIN)
    status, raw = await _post_registration(
        endpoints.registration,
        {
            "action": "poll",
            "device_code": device_code,
        },
    )
    if status >= 400 or raw.get("error"):
        return ""
    return _string_field(_registration_data(raw), "client_secret")
