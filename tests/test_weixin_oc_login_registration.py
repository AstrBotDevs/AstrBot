from astrbot.core.platform.sources.weixin_oc.login_registration import (
    DEFAULT_WEIXIN_OC_BASE_URL,
    normalize_weixin_oc_base_url,
    weixin_oc_login_result,
)


def test_normalize_weixin_oc_base_url_uses_default_and_strips_slash():
    assert normalize_weixin_oc_base_url("") == DEFAULT_WEIXIN_OC_BASE_URL
    assert (
        normalize_weixin_oc_base_url("https://ilinkai.weixin.qq.com/")
        == DEFAULT_WEIXIN_OC_BASE_URL
    )


def test_weixin_oc_login_result_maps_confirmed_payload():
    result = weixin_oc_login_result(
        {
            "status": "confirmed",
            "bot_token": "token",
            "ilink_bot_id": "bot-id",
            "baseurl": "https://example.com/",
            "ilink_user_id": "user-id",
        },
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    )

    assert result == {
        "status": "created",
        "qr_status": "confirmed",
        "weixin_oc_token": "token",
        "weixin_oc_account_id": "bot-id",
        "weixin_oc_base_url": "https://example.com",
        "weixin_oc_user_id": "user-id",
    }


def test_weixin_oc_login_result_maps_wait_and_expired_payloads():
    assert weixin_oc_login_result(
        {"status": "wait"},
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    ) == {"status": "pending", "qr_status": "wait"}

    assert weixin_oc_login_result(
        {"status": "expired"},
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    ) == {"status": "expired", "qr_status": "expired", "message": "二维码已过期"}
