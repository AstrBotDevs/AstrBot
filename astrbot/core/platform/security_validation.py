"""Fail-closed validation for platform ingress authentication."""


def validate_platform_security_config(platform_config: dict) -> None:
    """Validate authentication required by externally reachable adapters.

    Args:
        platform_config: Platform configuration being saved or loaded.

    Raises:
        ValueError: If an enabled platform would accept unauthenticated ingress.
    """
    if not platform_config.get("enable", True):
        return
    platform_type = str(platform_config.get("type") or "").strip()
    if (
        platform_type == "aiocqhttp"
        and not str(platform_config.get("ws_reverse_token") or "").strip()
    ):
        raise ValueError(
            "OneBot reverse WebSocket requires a non-empty ws_reverse_token"
        )
    if (
        platform_type == "lark"
        and str(platform_config.get("lark_connection_mode") or "socket").strip()
        == "webhook"
        and not str(platform_config.get("lark_verification_token") or "").strip()
    ):
        raise ValueError("Lark webhook mode requires a verification token")
