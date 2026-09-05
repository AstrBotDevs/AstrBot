import base64
from types import SimpleNamespace

import pytest
from Crypto.Cipher import AES

from astrbot.core.platform.sources.qqofficial.login_registration import (
    QQOFFICIAL_BIND_STATUS_COMPLETED,
    QQOFFICIAL_BIND_STATUS_EXPIRED,
    QQOFFICIAL_BIND_STATUS_PENDING,
    decrypt_qqofficial_secret,
    generate_qqofficial_bind_key,
    qqofficial_login_result,
)
from astrbot.dashboard.services import platform_service
from astrbot.dashboard.services.platform_service import PlatformService


def test_generate_qqofficial_bind_key_returns_base64_aes_key():
    bind_key = generate_qqofficial_bind_key()

    assert len(base64.b64decode(bind_key)) == 32


def test_qqofficial_login_result_maps_completed_payload():
    bind_key = base64.b64encode(bytes(range(32))).decode("ascii")
    nonce = b"123456789012"
    cipher = AES.new(base64.b64decode(bind_key), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(b"secret-value")
    encrypted_secret = base64.b64encode(nonce + ciphertext + tag).decode("ascii")

    result = qqofficial_login_result(
        {
            "data": {
                "status": QQOFFICIAL_BIND_STATUS_COMPLETED,
                "bot_appid": "123456789",
                "bot_encrypt_secret": encrypted_secret,
            },
        },
        bind_key=bind_key,
    )

    assert result == {
        "status": "created",
        "qr_status": QQOFFICIAL_BIND_STATUS_COMPLETED,
        "appid": "123456789",
        "secret": "secret-value",
        "platform_id_suffix": "_123456789",
    }


def test_qqofficial_login_result_maps_pending_and_expired_payloads():
    bind_key = base64.b64encode(bytes(range(32))).decode("ascii")

    assert qqofficial_login_result(
        {"data": {"status": QQOFFICIAL_BIND_STATUS_PENDING}},
        bind_key=bind_key,
    ) == {"status": "pending", "qr_status": QQOFFICIAL_BIND_STATUS_PENDING}

    assert qqofficial_login_result(
        {"data": {"status": QQOFFICIAL_BIND_STATUS_EXPIRED}},
        bind_key=bind_key,
    ) == {
        "status": "expired",
        "qr_status": QQOFFICIAL_BIND_STATUS_EXPIRED,
        "message": "二维码已过期",
    }


def test_decrypt_qqofficial_secret_rejects_invalid_payload():
    bind_key = base64.b64encode(bytes(range(32))).decode("ascii")

    with pytest.raises(ValueError):
        decrypt_qqofficial_secret("invalid", bind_key)


@pytest.mark.asyncio
async def test_qqofficial_webhook_registration_reuses_qr_binding(monkeypatch):
    async def fake_request_qqofficial_login_qr(platform_config: dict):
        assert platform_config["type"] == "qq_official_webhook"
        return SimpleNamespace(
            task_id="task-1",
            bind_key="bind-key",
            qrcode="qr-content",
            interval=3,
        )

    monkeypatch.setattr(
        platform_service,
        "request_qqofficial_login_qr",
        fake_request_qqofficial_login_qr,
    )
    service = PlatformService.__new__(PlatformService)

    result = await service.handle_platform_registration(
        "qq_official_webhook",
        {
            "action": "start",
            "platform_config": {"type": "qq_official_webhook"},
        },
    )

    assert result == {
        "status": "pending",
        "registration_code": "task-1",
        "task_id": "task-1",
        "bind_key": "bind-key",
        "qrcode": "qr-content",
        "qrcode_img_content": "qr-content",
        "interval": 3,
    }
