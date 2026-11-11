"""HTTP client for AstrBot Dashboard OpenAPI (server-side only)."""

from __future__ import annotations

from typing import Any

import httpx
from app.core.config import settings


class AstrBotClientError(Exception):
    """Raised when the AstrBot API call fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AstrBotClient:
    """Thin wrapper around AstrBot `/api/v1` bot registration APIs."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.base_url = (base_url or settings.astrbot_base_url).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else settings.astrbot_api_key
        ).strip()
        self.timeout = timeout

    def configured(self) -> bool:
        """Return True when base URL and API key are present."""
        return bool(self.base_url and self.api_key)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.configured():
            raise AstrBotClientError(
                "AstrBot API is not configured",
                status_code=503,
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            raise AstrBotClientError(f"AstrBot unreachable: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AstrBotClientError(
                f"AstrBot returned non-JSON ({response.status_code})",
                status_code=response.status_code,
            ) from exc

        if not isinstance(payload, dict):
            raise AstrBotClientError(
                "AstrBot returned unexpected payload",
                status_code=response.status_code,
            )

        if response.status_code >= 400 or payload.get("status") == "error":
            message = (
                str(payload.get("message") or payload.get("error") or "")
                or f"AstrBot error {response.status_code}"
            )
            raise AstrBotClientError(message, status_code=response.status_code)

        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    async def start_qq_registration(self) -> dict[str, Any]:
        """Create a one-time QQ official bot bind QR task."""
        return await self._request(
            "POST",
            "/api/v1/bot-types/qq_official/registration",
            json_body={"action": "start", "platform_config": {}},
        )

    async def poll_qq_registration(
        self,
        *,
        task_id: str,
        bind_key: str,
    ) -> dict[str, Any]:
        """Poll a QQ official bot bind task once."""
        return await self._request(
            "POST",
            "/api/v1/bot-types/qq_official/registration",
            json_body={
                "action": "poll",
                "task_id": task_id,
                "registration_code": task_id,
                "bind_key": bind_key,
                "platform_config": {},
            },
        )

    async def start_weixin_registration(self) -> dict[str, Any]:
        """Create a personal WeChat (weixin_oc) login QR task."""
        return await self._request(
            "POST",
            "/api/v1/bot-types/weixin_oc/registration",
            json_body={"action": "start", "platform_config": {}},
        )

    async def poll_weixin_registration(self, *, qrcode: str) -> dict[str, Any]:
        """Poll a personal WeChat login QR once (may long-poll)."""
        return await self._request(
            "POST",
            "/api/v1/bot-types/weixin_oc/registration",
            json_body={
                "action": "poll",
                "qrcode": qrcode,
                "registration_code": qrcode,
                "platform_config": {},
            },
            timeout=45.0,
        )

    async def set_bot_enabled(self, adapter_id: str, enabled: bool) -> None:
        """Enable or disable an AstrBot platform instance."""
        await self._request(
            "PATCH",
            f"/api/v1/bots/{adapter_id}/enabled",
            json_body={"enabled": enabled},
        )

    async def create_qq_official_bot(
        self,
        *,
        adapter_id: str,
        appid: str,
        secret: str,
    ) -> None:
        """Register a qq_official platform instance on AstrBot.

        Body shape matches Dashboard ``botApi.create`` (flat config nested
        under ``config``), so WebSocket soul connects the same way as 6185.
        """
        platform = {
            "id": adapter_id,
            "type": "qq_official",
            "enable": True,
            "appid": appid,
            "secret": secret,
            "enable_group_c2c": True,
            "enable_guild_direct_message": True,
            "use_markdown": True,
        }
        await self._request(
            "POST",
            "/api/v1/bots",
            json_body={
                "id": adapter_id,
                "type": "qq_official",
                "enable": True,
                "config": platform,
            },
        )

    async def create_weixin_oc_bot(
        self,
        *,
        adapter_id: str,
        token: str,
        account_id: str,
        base_url: str,
    ) -> None:
        """Register a weixin_oc (personal WeChat) platform instance."""
        await self._request(
            "POST",
            "/api/v1/bots",
            json_body={
                "id": adapter_id,
                "type": "weixin_oc",
                "enable": True,
                "config": {
                    "id": adapter_id,
                    "type": "weixin_oc",
                    "enable": True,
                    "weixin_oc_token": token,
                    "weixin_oc_account_id": account_id,
                    "weixin_oc_base_url": base_url or "https://ilinkai.weixin.qq.com",
                    "weixin_oc_bot_type": "3",
                    "weixin_oc_qr_poll_interval": 1,
                    "weixin_oc_long_poll_timeout_ms": 35_000,
                    "weixin_oc_api_timeout_ms": 120_000,
                },
            },
        )
