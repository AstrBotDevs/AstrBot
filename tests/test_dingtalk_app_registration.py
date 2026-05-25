from astrbot.core.platform.sources.dingtalk.app_registration import (
    DEFAULT_DINGTALK_REGISTRATION_BASE_URL,
    DEFAULT_DINGTALK_REGISTRATION_SOURCE,
    dingtalk_registration_base_url,
    dingtalk_registration_poll_result,
    dingtalk_registration_source,
)


def test_dingtalk_registration_defaults(monkeypatch):
    monkeypatch.delenv("DINGTALK_REGISTRATION_BASE_URL", raising=False)
    monkeypatch.delenv("DINGTALK_REGISTRATION_SOURCE", raising=False)

    assert dingtalk_registration_base_url() == DEFAULT_DINGTALK_REGISTRATION_BASE_URL
    assert dingtalk_registration_source() == DEFAULT_DINGTALK_REGISTRATION_SOURCE


def test_dingtalk_registration_poll_result_maps_waiting_and_success():
    assert dingtalk_registration_poll_result({"status": "WAITING"}) == {
        "status": "pending"
    }

    assert dingtalk_registration_poll_result(
        {
            "status": "SUCCESS",
            "client_id": "client-id",
            "client_secret": "client-secret",
        }
    ) == {
        "status": "created",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }


def test_dingtalk_registration_poll_result_maps_fail_and_expired():
    assert dingtalk_registration_poll_result(
        {"status": "FAIL", "fail_reason": "denied"}
    ) == {
        "status": "error",
        "message": "denied",
    }

    assert dingtalk_registration_poll_result({"status": "EXPIRED"}) == {
        "status": "expired",
        "message": "钉钉扫码已过期，请重新创建",
    }
