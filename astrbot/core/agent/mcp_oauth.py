from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.auth.extensions.client_credentials import (
    ClientCredentialsOAuthProvider,
)
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import BaseModel, ConfigDict

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class MCPOAuthError(Exception):
    """Base exception for MCP OAuth flows."""


class MCPOAuthAuthorizationRequiredError(MCPOAuthError):
    """Raised when interactive OAuth authorization is required."""


class MCPOAuthConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grant_type: Literal["authorization_code", "client_credentials"] = (
        "authorization_code"
    )
    client_id: str | None = None
    client_secret: str | None = None
    token_endpoint_auth_method: (
        Literal["none", "client_secret_post", "client_secret_basic"] | None
    ) = None
    scope: str | None = None
    redirect_uri: str | None = None
    timeout: float = 300.0
    client_name: str | None = "AstrBot MCP Client"
    client_uri: str | None = None
    logo_uri: str | None = None
    contacts: list[str] | None = None
    tos_uri: str | None = None
    policy_uri: str | None = None
    software_id: str | None = None
    software_version: str | None = None
    client_metadata_url: str | None = None


def _prepare_config(config: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(config)
    if prepared.get("mcpServers"):
        first_key = next(iter(prepared["mcpServers"]))
        prepared = dict(prepared["mcpServers"][first_key])
    prepared.pop("active", None)
    return prepared


def get_mcp_oauth_config(config: Mapping[str, Any]) -> MCPOAuthConfig | None:
    prepared = _prepare_config(config)
    oauth_config = prepared.get("oauth2") or prepared.get("oauth")
    if not isinstance(oauth_config, dict):
        return None
    return MCPOAuthConfig.model_validate(oauth_config)


def has_mcp_oauth_config(config: Mapping[str, Any]) -> bool:
    return get_mcp_oauth_config(config) is not None


def _get_storage_fingerprint(config: Mapping[str, Any]) -> str:
    prepared = _prepare_config(config)
    oauth_config = get_mcp_oauth_config(prepared)
    if oauth_config is None:
        raise MCPOAuthError("OAuth 2.0 is not configured for this MCP server.")

    fingerprint_payload = {
        "url": prepared.get("url"),
        "transport": prepared.get("transport") or prepared.get("type"),
        "grant_type": oauth_config.grant_type,
        "client_id": oauth_config.client_id,
        "client_secret": oauth_config.client_secret,
        "token_endpoint_auth_method": oauth_config.token_endpoint_auth_method,
        "scope": oauth_config.scope,
        "redirect_uri": oauth_config.redirect_uri,
        "client_metadata_url": oauth_config.client_metadata_url,
    }
    canonical = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_mcp_oauth_storage_path(config: Mapping[str, Any]) -> Path:
    data_dir = Path(get_astrbot_data_path()) / "mcp_oauth"
    return data_dir / f"{_get_storage_fingerprint(config)}.json"


class MCPFileTokenStorage(TokenStorage):
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._lock = asyncio.Lock()

    @classmethod
    def from_mcp_config(cls, config: Mapping[str, Any]) -> MCPFileTokenStorage:
        return cls(get_mcp_oauth_storage_path(config))

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load MCP OAuth storage %s: %s",
                self.storage_path,
                exc,
            )
            return {}

    def _save_unlocked(self, payload: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(self.storage_path, 0o600)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to set permissions on MCP OAuth storage %s: %s",
                self.storage_path,
                exc,
            )

    async def get_tokens(self) -> OAuthToken | None:
        async with self._lock:
            payload = self._load_unlocked()
        token_payload = payload.get("tokens")
        if not token_payload:
            return None
        return OAuthToken.model_validate(token_payload)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
            if tokens.expires_in is not None:
                payload["token_expires_at"] = time.time() + float(tokens.expires_in)
            else:
                payload.pop("token_expires_at", None)
            self._save_unlocked(payload)

    async def clear_tokens(self) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload.pop("tokens", None)
            payload.pop("token_expires_at", None)
            self._save_unlocked(payload)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        async with self._lock:
            payload = self._load_unlocked()
        client_info_payload = payload.get("client_info")
        if not client_info_payload:
            return None
        return OAuthClientInformationFull.model_validate(client_info_payload)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload["client_info"] = client_info.model_dump(
                mode="json",
                exclude_none=True,
            )
            self._save_unlocked(payload)

    async def get_redirect_uri(self) -> str | None:
        async with self._lock:
            payload = self._load_unlocked()
        redirect_uri = payload.get("redirect_uri")
        return str(redirect_uri) if isinstance(redirect_uri, str) else None

    async def set_redirect_uri(self, redirect_uri: str) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload["redirect_uri"] = redirect_uri
            self._save_unlocked(payload)

    async def get_token_expires_at(self) -> float | None:
        async with self._lock:
            payload = self._load_unlocked()
        expires_at = payload.get("token_expires_at")
        if isinstance(expires_at, (int, float)):
            return float(expires_at)
        return None


def _get_token_endpoint_auth_method(oauth_config: MCPOAuthConfig) -> str:
    if oauth_config.token_endpoint_auth_method:
        return oauth_config.token_endpoint_auth_method
    if oauth_config.client_secret:
        return "client_secret_basic"
    return "none"


async def _raise_interactive_redirect_required(_: str) -> None:
    raise MCPOAuthAuthorizationRequiredError(
        "OAuth 2.0 authorization is required. Complete authorization in the MCP server dialog first.",
    )


async def _raise_interactive_callback_required() -> tuple[str, str | None]:
    raise MCPOAuthAuthorizationRequiredError(
        "OAuth 2.0 authorization is required. Complete authorization in the MCP server dialog first.",
    )


if OAuthClientProvider is not None:

    class AstrBotOAuthClientProvider(OAuthClientProvider):
        async def _initialize(self) -> None:
            await super()._initialize()

            storage = self.context.storage
            if not isinstance(storage, MCPFileTokenStorage):
                return

            expires_at = await storage.get_token_expires_at()
            if expires_at is not None:
                self.context.token_expiry_time = expires_at

            if (
                expires_at is not None
                and time.time() > expires_at
                and not self.context.can_refresh_token()
            ):
                raise MCPOAuthAuthorizationRequiredError(
                    "The stored OAuth 2.0 token has expired. Complete authorization in the MCP server dialog again.",
                )

else:
    AstrBotOAuthClientProvider = None  # type: ignore[assignment]


if ClientCredentialsOAuthProvider is not None:

    class AstrBotClientCredentialsOAuthProvider(ClientCredentialsOAuthProvider):
        async def _initialize(self) -> None:
            await super()._initialize()

            storage = self.context.storage
            if not isinstance(storage, MCPFileTokenStorage):
                return

            expires_at = await storage.get_token_expires_at()
            if expires_at is not None:
                self.context.token_expiry_time = expires_at

else:
    AstrBotClientCredentialsOAuthProvider = None  # type: ignore[assignment]


def _build_client_metadata(
    oauth_config: MCPOAuthConfig,
    *,
    redirect_uri: str,
) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method=_get_token_endpoint_auth_method(oauth_config),
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=oauth_config.scope,
        client_name=oauth_config.client_name,
        client_uri=oauth_config.client_uri,
        logo_uri=oauth_config.logo_uri,
        contacts=oauth_config.contacts,
        tos_uri=oauth_config.tos_uri,
        policy_uri=oauth_config.policy_uri,
        software_id=oauth_config.software_id,
        software_version=oauth_config.software_version,
    )


async def _seed_client_info_if_needed(
    storage: MCPFileTokenStorage,
    oauth_config: MCPOAuthConfig,
    *,
    redirect_uri: str,
) -> None:
    if not oauth_config.client_id:
        return

    client_info = OAuthClientInformationFull(
        redirect_uris=[redirect_uri],
        client_id=oauth_config.client_id,
        client_secret=oauth_config.client_secret,
        grant_types=["authorization_code", "refresh_token"],
        token_endpoint_auth_method=_get_token_endpoint_auth_method(oauth_config),
        response_types=["code"],
        scope=oauth_config.scope,
        client_name=oauth_config.client_name,
        client_uri=oauth_config.client_uri,
        logo_uri=oauth_config.logo_uri,
        contacts=oauth_config.contacts,
        tos_uri=oauth_config.tos_uri,
        policy_uri=oauth_config.policy_uri,
        software_id=oauth_config.software_id,
        software_version=oauth_config.software_version,
    )
    await storage.set_client_info(client_info)


@dataclass(slots=True)
class MCPOAuthPendingFlow:
    flow_id: str
    config: dict[str, Any]
    redirect_uri: str
    created_at: float = field(default_factory=time.time)
    status: Literal[
        "initializing",
        "awaiting_user",
        "authorizing",
        "completed",
        "failed",
    ] = "initializing"
    authorization_url: str | None = None
    error: str | None = None
    callback_code: str | None = None
    callback_state: str | None = None
    callback_error: str | None = None
    oauth_state: str | None = None
    url_ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    callback_ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    async def handle_redirect(self, authorization_url: str) -> None:
        self.authorization_url = authorization_url
        parsed_url = urlparse(authorization_url)
        self.oauth_state = parse_qs(parsed_url.query).get("state", [None])[0]
        self.status = "awaiting_user"
        self.url_ready_event.set()

    async def wait_for_callback(self) -> tuple[str, str | None]:
        await self.callback_ready_event.wait()
        if self.callback_error:
            raise MCPOAuthError(self.callback_error)
        self.status = "authorizing"
        return self.callback_code or "", self.callback_state

    def submit_callback(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> None:
        self.callback_code = code
        self.callback_state = state
        self.callback_error = error
        self.callback_ready_event.set()


async def create_mcp_http_auth(
    config: Mapping[str, Any],
    *,
    interactive_flow: MCPOAuthPendingFlow | None = None,
) -> httpx.Auth | None:
    prepared = _prepare_config(config)
    if "url" not in prepared:
        return None

    oauth_config = get_mcp_oauth_config(prepared)
    if oauth_config is None:
        return None

    if OAuthClientProvider is None or OAuthClientMetadata is None:
        raise MCPOAuthError("The installed MCP dependency does not support OAuth 2.0.")

    storage = MCPFileTokenStorage.from_mcp_config(prepared)

    if oauth_config.grant_type == "client_credentials":
        if not oauth_config.client_id or not oauth_config.client_secret:
            raise MCPOAuthError(
                "OAuth client_credentials requires both client_id and client_secret.",
            )
        if AstrBotClientCredentialsOAuthProvider is None:
            raise MCPOAuthError(
                "The installed MCP dependency does not support OAuth 2.0 client_credentials.",
            )
        return AstrBotClientCredentialsOAuthProvider(
            server_url=str(prepared["url"]),
            storage=storage,
            client_id=oauth_config.client_id,
            client_secret=oauth_config.client_secret,
            token_endpoint_auth_method=_get_token_endpoint_auth_method(oauth_config),
            scopes=oauth_config.scope,
        )

    if oauth_config.grant_type != "authorization_code":
        raise MCPOAuthError(
            f"Unsupported MCP OAuth grant_type: {oauth_config.grant_type}",
        )

    if interactive_flow is None:
        stored_tokens = await storage.get_tokens()
        if stored_tokens is None:
            raise MCPOAuthAuthorizationRequiredError(
                "OAuth 2.0 authorization is required. Complete authorization in the MCP server dialog first.",
            )

        expires_at = await storage.get_token_expires_at()
        if (
            expires_at is not None
            and time.time() > expires_at
            and not stored_tokens.refresh_token
        ):
            raise MCPOAuthAuthorizationRequiredError(
                "The stored OAuth 2.0 token has expired and no refresh token is available. Complete authorization in the MCP server dialog again.",
            )

    redirect_uri = (
        interactive_flow.redirect_uri
        if interactive_flow is not None
        else oauth_config.redirect_uri
        or await storage.get_redirect_uri()
        or "http://127.0.0.1/astrbot/mcp/oauth/callback/pending"
    )

    await storage.set_redirect_uri(redirect_uri)
    await _seed_client_info_if_needed(storage, oauth_config, redirect_uri=redirect_uri)

    redirect_handler = (
        interactive_flow.handle_redirect
        if interactive_flow is not None
        else _raise_interactive_redirect_required
    )
    callback_handler = (
        interactive_flow.wait_for_callback
        if interactive_flow is not None
        else _raise_interactive_callback_required
    )

    if AstrBotOAuthClientProvider is None:
        raise MCPOAuthError("The installed MCP dependency does not support OAuth 2.0.")

    return AstrBotOAuthClientProvider(
        server_url=str(prepared["url"]),
        client_metadata=_build_client_metadata(
            oauth_config,
            redirect_uri=redirect_uri,
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=oauth_config.timeout,
        client_metadata_url=oauth_config.client_metadata_url,
    )


async def get_mcp_oauth_state(config: Mapping[str, Any]) -> dict[str, Any]:
    oauth_config = get_mcp_oauth_config(config)
    if oauth_config is None:
        return {
            "oauth2_enabled": False,
            "oauth2_authorized": False,
            "oauth2_grant_type": None,
        }

    if oauth_config.grant_type == "client_credentials":
        return {
            "oauth2_enabled": True,
            "oauth2_authorized": True,
            "oauth2_grant_type": oauth_config.grant_type,
        }

    storage = MCPFileTokenStorage.from_mcp_config(config)
    tokens = await storage.get_tokens()
    return {
        "oauth2_enabled": True,
        "oauth2_authorized": tokens is not None,
        "oauth2_grant_type": oauth_config.grant_type,
    }


async def _probe_http_oauth_connection(
    config: Mapping[str, Any],
    auth: httpx.Auth,
) -> None:
    prepared = _prepare_config(config)
    url = str(prepared["url"])
    headers = {
        str(key): str(value) for key, value in dict(prepared.get("headers", {})).items()
    }
    timeout_value = float(prepared.get("timeout", 30))
    transport_type = prepared.get("transport") or prepared.get("type") or "sse"

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout_value,
    ) as client:
        if transport_type == "streamable_http":
            response = await client.post(
                url,
                headers={
                    **headers,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "astrbot-oauth-probe",
                            "version": "1.0.0",
                        },
                    },
                },
                auth=auth,
            )
        else:
            response = await client.get(
                url,
                headers={
                    **headers,
                    "Accept": "application/json, text/event-stream",
                },
                auth=auth,
            )

    if response.status_code != 200:
        raise MCPOAuthError(
            f"OAuth authorization probe failed: HTTP {response.status_code} {response.reason_phrase}",
        )


class MCPOAuthManager:
    _FLOW_TTL_SECONDS = 900

    def __init__(self) -> None:
        self._flows: dict[str, MCPOAuthPendingFlow] = {}
        self._state_to_flow_id: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _prune_flows(self) -> None:
        threshold = time.time() - self._FLOW_TTL_SECONDS
        async with self._lock:
            expired_ids = [
                flow_id
                for flow_id, flow in self._flows.items()
                if flow.created_at < threshold
            ]
            for flow_id in expired_ids:
                expired_states = [
                    state
                    for state, state_flow_id in self._state_to_flow_id.items()
                    if state_flow_id == flow_id
                ]
                for state in expired_states:
                    self._state_to_flow_id.pop(state, None)
                self._flows.pop(flow_id, None)

    async def _run_flow(self, flow: MCPOAuthPendingFlow) -> None:
        try:
            auth = await create_mcp_http_auth(flow.config, interactive_flow=flow)
            if auth is None:
                raise MCPOAuthError("OAuth 2.0 is not configured for this MCP server.")
            await _probe_http_oauth_connection(flow.config, auth)
            flow.status = "completed"
        except Exception as exc:  # noqa: BLE001
            flow.error = str(exc)
            flow.status = "failed"
            flow.url_ready_event.set()
        finally:
            flow.done_event.set()

    async def start_authorization(
        self,
        config: Mapping[str, Any],
        *,
        callback_base_url: str,
        server_name: str | None = None,
        force: bool = False,
    ) -> MCPOAuthPendingFlow:
        prepared = _prepare_config(config)
        oauth_config = get_mcp_oauth_config(prepared)
        if oauth_config is None:
            raise MCPOAuthError("OAuth 2.0 is not configured for this MCP server.")
        if oauth_config.grant_type != "authorization_code":
            raise MCPOAuthError(
                "Interactive login is only available for authorization_code flows.",
            )
        if "url" not in prepared:
            raise MCPOAuthError("OAuth 2.0 is only supported for HTTP MCP transports.")

        await self._prune_flows()

        storage = MCPFileTokenStorage.from_mcp_config(prepared)
        if force:
            await storage.clear_tokens()

        flow_id = uuid.uuid4().hex
        redirect_uri = f"{callback_base_url.rstrip('/')}/mcp/oauth/callback"

        flow = MCPOAuthPendingFlow(
            flow_id=flow_id,
            config=prepared,
            redirect_uri=redirect_uri,
        )
        flow.task = asyncio.create_task(
            self._run_flow(flow),
            name=f"mcp-oauth:{flow_id}",
        )

        async with self._lock:
            self._flows[flow_id] = flow

        wait_url_task = asyncio.create_task(flow.url_ready_event.wait())
        wait_done_task = asyncio.create_task(flow.done_event.wait())
        try:
            done, pending = await asyncio.wait(
                {wait_url_task, wait_done_task},
                timeout=15,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            if not done:
                raise MCPOAuthError(
                    "Timed out while preparing the OAuth 2.0 authorization flow.",
                )
        finally:
            if not wait_url_task.done():
                wait_url_task.cancel()
            if not wait_done_task.done():
                wait_done_task.cancel()

        if flow.status == "failed":
            raise MCPOAuthError(flow.error or "Failed to start OAuth 2.0 flow.")

        if flow.oauth_state:
            async with self._lock:
                self._state_to_flow_id[flow.oauth_state] = flow.flow_id

        return flow

    async def submit_callback(
        self,
        flow_id: str | None = None,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
    ) -> None:
        resolved_flow_id = flow_id
        if resolved_flow_id is None and state:
            resolved_flow_id = self._state_to_flow_id.get(state)

        async with self._lock:
            flow = self._flows.get(resolved_flow_id or "")
        if flow is None:
            raise KeyError(flow_id or state or "")
        flow.submit_callback(code=code, state=state, error=error)

    def get_flow_status(self, flow_id: str) -> dict[str, Any]:
        flow = self._flows.get(flow_id)
        if flow is None:
            raise KeyError(flow_id)
        return {
            "flow_id": flow.flow_id,
            "status": flow.status,
            "authorization_url": flow.authorization_url,
            "redirect_uri": flow.redirect_uri,
            "error": flow.error,
        }
