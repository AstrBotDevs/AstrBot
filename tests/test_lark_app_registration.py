import pytest

from astrbot.core.platform.sources.lark.app_registration import (
    DEFAULT_FEISHU_OPEN_DOMAIN,
    DEFAULT_LARK_OPEN_DOMAIN,
    _registration_data,
    resolve_app_registration_endpoints,
)


def test_resolve_app_registration_endpoints_uses_feishu_accounts_domain():
    endpoints = resolve_app_registration_endpoints(DEFAULT_FEISHU_OPEN_DOMAIN)

    assert endpoints.open_base == DEFAULT_FEISHU_OPEN_DOMAIN
    assert endpoints.registration == (
        "https://accounts.feishu.cn/oauth/v1/app/registration"
    )


def test_resolve_app_registration_endpoints_uses_lark_accounts_domain():
    endpoints = resolve_app_registration_endpoints(DEFAULT_LARK_OPEN_DOMAIN)

    assert endpoints.open_base == DEFAULT_LARK_OPEN_DOMAIN
    assert endpoints.registration == (
        "https://accounts.larksuite.com/oauth/v1/app/registration"
    )


def test_registration_data_accepts_wrapped_and_plain_payloads():
    wrapped = {"data": {"device_code": "device"}}
    plain = {"device_code": "device"}

    assert _registration_data(wrapped) == {"device_code": "device"}
    assert _registration_data(plain) == {"device_code": "device"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launcher",
    [
        "",
        "https://open.feishu.cn/page/cli?user_code=fixture",
        "https://open.feishu.cn/page/launcher?createOnly=true",
        "https://open.feishu.cn/page/launcher?clientID=cli_other&clientID=cli_original",
        "https://open.larksuite.com/page/launcher?ticket=fixture",
    ],
)
async def test_membership_update_requires_a_launcher_for_the_original_app(
    monkeypatch, launcher
):
    from unittest.mock import AsyncMock

    from astrbot.core.platform.sources.lark import app_registration

    monkeypatch.setattr(
        app_registration,
        "_post_registration",
        AsyncMock(
            return_value=(
                200,
                {
                    "verification_uri_complete": launcher,
                    "device_code": "device",
                    "user_code": "fixture",
                },
            )
        ),
    )
    with pytest.raises(RuntimeError, match="Lark returned"):
        await app_registration.request_app_registration(
            "feishu", membership_app_id="cli_original"
        )


@pytest.mark.asyncio
async def test_registration_keeps_the_verified_scanner_when_present(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from astrbot.core.platform.sources.lark import app_registration, bot_info
    from astrbot.dashboard.services.platform_service import PlatformService

    data = {
        "client_id": "cli_registered",
        "client_secret": "fixture-only",
        "user_info": {"tenant_brand": "feishu", "open_id": "ou_scanner"},
    }
    monkeypatch.setattr(
        app_registration,
        "_post_registration",
        AsyncMock(return_value=(200, {"data": data})),
    )
    monkeypatch.setattr(
        bot_info,
        "_post_json",
        AsyncMock(return_value={"code": 0, "tenant_access_token": "fixture-only"}),
    )
    monkeypatch.setattr(
        bot_info,
        "_get_json",
        AsyncMock(
            return_value={
                "code": 0,
                "bot": {"app_name": "Original bot", "open_id": "ou_bot"},
            }
        ),
    )
    service = PlatformService(SimpleNamespace(platform_manager=None))
    payload = {
        "action": "poll",
        "device_code": "fixture-code",
        "platform_config": {"domain": "feishu"},
    }
    result = await service.handle_platform_registration("lark", payload)
    assert result["user_open_id"] == "ou_scanner"
    assert result["bot_open_id"] == "ou_bot"
    assert result["app_id"] == "cli_registered"
    for missing in (None, " "):
        data["user_info"]["open_id"] = missing
        result = await service.handle_platform_registration("lark", payload)
        assert "user_open_id" not in result
        assert result["bot_open_id"] == "ou_bot"
