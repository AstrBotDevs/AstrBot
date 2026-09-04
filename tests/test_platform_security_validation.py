"""Tests for fail-closed platform ingress configuration."""

import pytest

from astrbot.core.platform.security_validation import (
    validate_platform_security_config,
)


def test_onebot_requires_non_empty_reverse_websocket_token() -> None:
    with pytest.raises(ValueError, match="ws_reverse_token"):
        validate_platform_security_config(
            {"type": "aiocqhttp", "enable": True, "ws_reverse_token": ""}
        )


def test_onebot_accepts_configured_reverse_websocket_token() -> None:
    validate_platform_security_config(
        {"type": "aiocqhttp", "enable": True, "ws_reverse_token": "secret"}
    )


def test_lark_webhook_requires_verification_token() -> None:
    with pytest.raises(ValueError, match="verification token"):
        validate_platform_security_config(
            {
                "type": "lark",
                "enable": True,
                "lark_connection_mode": "webhook",
                "lark_verification_token": "",
            }
        )


def test_lark_socket_mode_does_not_require_webhook_token() -> None:
    validate_platform_security_config(
        {
            "type": "lark",
            "enable": True,
            "lark_connection_mode": "socket",
        }
    )


def test_disabled_platform_does_not_require_ingress_credentials() -> None:
    validate_platform_security_config(
        {"type": "aiocqhttp", "enable": False, "ws_reverse_token": ""}
    )
