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
from mcp.client.auth.oauth2 import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_protected_resource_response,
)
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
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
    mcp_servers = prepared.get("mcpServers")
    if isinstance(mcp_servers, dict) and mcp_servers:
        first_server = next(iter(mcp_servers.values()))
        if isinstance(first_server, dict):
            prepared = dict(first_server)
    prepared.pop("active", None)
    prepared.pop("oauth2_enabled", None)
    prepared.pop("oauth2_authorized", None)
    prepared.pop("oauth2_grant_type", None)
    prepared.pop("_oauth_defaults_fingerprint", None)
    return prepared


def get_mcp_oauth_config(config: Mapping[str, Any]) -> MCPOAuthConfig | None:
    prepared = _prepare_config(config)
    oauth_config = prepared.get("oauth2") or prepared.get("oauth")
    if not isinstance(oauth_config, dict):
        return None
    return MCPOAuthConfig.model_validate(oauth_config)


_MCP_OAUTH_CALLBACK_PATH = "/mcp/oauth/callback"

_MCP_OAUTH_SHARED_DEFAULT_KEYS = (
    "mcp_oauth_client_name",
    "mcp_oauth_scope",
    "mcp_oauth_client_id",
    "mcp_oauth_client_secret",
)


def get_shared_mcp_oauth_defaults() -> dict[str, Any]:
    """Shared OAuth 2.0 settings from the global config.

    These defaults fill in fields omitted by a server's own ``oauth2`` config so
    that runtime connections, status checks, and authorization flows all derive
    the same token-storage fingerprint.
    """
    from astrbot.core import astrbot_config  # deferred to avoid an import cycle

    return {
        key.removeprefix("mcp_oauth_"): astrbot_config.get(key)
        for key in _MCP_OAUTH_SHARED_DEFAULT_KEYS
        if astrbot_config.get(key)
    }


def _resolve_configured_redirect_uri(
    oauth_config: MCPOAuthConfig | None,
) -> str | None:
    """Return the configured redirect_uri only when it targets the registered callback route.

    The dashboard only handles ``/mcp/oauth/callback``; a configured URI with a
    different path would never receive the OAuth callback.
    """
    configured = oauth_config.redirect_uri if oauth_config else None
    if not configured:
        return None
    if urlparse(configured).path.rstrip("/") == _MCP_OAUTH_CALLBACK_PATH:
        return configured
    logger.warning(
        "Ignoring MCP OAuth redirect_uri %s: the dashboard only handles %s; "
        "falling back to the default callback address.",
        configured,
        _MCP_OAUTH_CALLBACK_PATH,
    )
    return None


def get_mcp_oauth_redirect_uri(
    config: Mapping[str, Any], callback_base_url: str
) -> str:
    oauth_config = get_mcp_oauth_config(config)
    configured = _resolve_configured_redirect_uri(oauth_config)
    if configured:
        return configured
    return f"{callback_base_url.rstrip('/')}{_MCP_OAUTH_CALLBACK_PATH}"


def sync_default_mcp_oauth_callback_base(
    config: dict[str, Any],
    previous_config: Mapping[str, Any] | None = None,
) -> None:
    callback_base = str(config.get("callback_api_base") or "").rstrip("/")
    if not callback_base:
        return

    default_redirect_uri = f"{callback_base}{_MCP_OAUTH_CALLBACK_PATH}"
    mcp_callback_base = str(config.get("mcp_oauth_callback_base") or "").rstrip("/")
    if not mcp_callback_base or mcp_callback_base == default_redirect_uri:
        config["mcp_oauth_callback_base"] = callback_base
        return

    previous = previous_config if isinstance(previous_config, Mapping) else None
    if previous is None:
        return
    previous_base = str(previous.get("callback_api_base") or "").rstrip("/")
    if previous_base and mcp_callback_base == previous_base:
        # The stored base was auto-populated from the previous shared callback
        # address and is still managed by it; follow the new address.
        config["mcp_oauth_callback_base"] = callback_base


def get_mcp_oauth_callback_base(
    config: Mapping[str, Any], callback_base_url: str
) -> str:
    redirect_uri = get_mcp_oauth_redirect_uri(config, callback_base_url)
    return redirect_uri.removesuffix(_MCP_OAUTH_CALLBACK_PATH)


def apply_mcp_oauth_defaults(
    config: Mapping[str, Any], defaults: Mapping[str, Any]
) -> dict[str, Any]:
    prepared = _prepare_config(config)
    oauth_config = prepared.get("oauth2") or prepared.get("oauth")
    if not isinstance(oauth_config, dict):
        return prepared
    prepared["_oauth_defaults_fingerprint"] = dict(defaults)
    merged = {**defaults, **oauth_config}
    if "oauth2" in prepared:
        prepared["oauth2"] = merged
    else:
        prepared["oauth"] = merged
    return prepared


def _get_oauth_defaults_fingerprint(config: Mapping[str, Any]) -> dict[str, Any]:
    oauth_config = get_mcp_oauth_config(config)
    if oauth_config is None:
        return {}
    return {
        key: getattr(oauth_config, key)
        for key in (
            "client_id",
            "client_secret",
            "scope",
            "client_name",
            "redirect_uri",
        )
    }


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
        "oauth_defaults": _get_oauth_defaults_fingerprint(prepared),
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

    async def clear_tokens(self, *, include_client_info: bool = False) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload.pop("tokens", None)
            payload.pop("token_expires_at", None)
            if include_client_info:
                payload.pop("client_info", None)
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

    async def get_protected_resource_metadata(
        self,
    ) -> ProtectedResourceMetadata | None:
        async with self._lock:
            payload = self._load_unlocked()
        metadata = payload.get("protected_resource_metadata")
        if not metadata:
            return None
        return ProtectedResourceMetadata.model_validate(metadata)

    async def set_protected_resource_metadata(
        self,
        metadata: ProtectedResourceMetadata,
    ) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload["protected_resource_metadata"] = metadata.model_dump(
                mode="json",
                exclude_none=True,
            )
            self._save_unlocked(payload)

    async def get_oauth_metadata(self) -> OAuthMetadata | None:
        async with self._lock:
            payload = self._load_unlocked()
        metadata = payload.get("oauth_metadata")
        if not metadata:
            return None
        return OAuthMetadata.model_validate(metadata)

    async def set_oauth_metadata(self, metadata: OAuthMetadata) -> None:
        async with self._lock:
            payload = self._load_unlocked()
            payload["oauth_metadata"] = metadata.model_dump(
                mode="json",
                exclude_none=True,
            )
            self._save_unlocked(payload)

    async def snapshot(self) -> dict[str, Any]:
        """Return a copy of the raw stored payload for later restore."""
        async with self._lock:
            return self._load_unlocked()

    async def restore(self, payload: dict[str, Any]) -> None:
        """Overwrite the stored payload with a previous snapshot."""
        async with self._lock:
            self._save_unlocked(dict(payload))


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
        async def _ensure_oauth_metadata(self) -> None:
            """Load or discover OAuth metadata before refreshing tokens.

            Raises:
                MCPOAuthError: If OAuth metadata cannot be discovered.
            """
            storage = self.context.storage
            if not isinstance(storage, MCPFileTokenStorage):
                return

            if self.context.protected_resource_metadata is None:
                self.context.protected_resource_metadata = (
                    await storage.get_protected_resource_metadata()
                )
            if self.context.oauth_metadata is None:
                self.context.oauth_metadata = await storage.get_oauth_metadata()

            if self.context.oauth_metadata is not None:
                return

            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.context.timeout,
            ) as client:
                if self.context.protected_resource_metadata is None:
                    protected_resource_urls = (
                        build_protected_resource_metadata_discovery_urls(
                            None,
                            self.context.server_url,
                        )
                    )
                    for url in protected_resource_urls:
                        response = await client.send(create_oauth_metadata_request(url))
                        metadata = await handle_protected_resource_response(response)
                        if metadata is None:
                            continue
                        self.context.protected_resource_metadata = metadata
                        await storage.set_protected_resource_metadata(metadata)
                        if metadata.authorization_servers:
                            self.context.auth_server_url = str(
                                metadata.authorization_servers[0]
                            )
                        break

                auth_server_url = (
                    self.context.auth_server_url
                    or self.context.get_authorization_base_url(
                        self.context.server_url,
                    )
                )
                oauth_metadata_urls = (
                    build_oauth_authorization_server_metadata_discovery_urls(
                        auth_server_url,
                        self.context.server_url,
                    )
                )
                for url in oauth_metadata_urls:
                    response = await client.send(create_oauth_metadata_request(url))
                    ok, metadata = await handle_auth_metadata_response(response)
                    if not ok:
                        break
                    if metadata is None:
                        continue
                    self.context.oauth_metadata = metadata
                    await storage.set_oauth_metadata(metadata)
                    return

            raise MCPOAuthError("Failed to discover OAuth 2.0 metadata.")

        async def _initialize(self) -> None:
            await super()._initialize()

            storage = self.context.storage
            if not isinstance(storage, MCPFileTokenStorage):
                return

            self.context.protected_resource_metadata = (
                await storage.get_protected_resource_metadata()
            )
            self.context.oauth_metadata = await storage.get_oauth_metadata()
            if self.context.protected_resource_metadata is not None:
                authorization_servers = (
                    self.context.protected_resource_metadata.authorization_servers
                )
                if authorization_servers:
                    self.context.auth_server_url = str(authorization_servers[0])

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

        async def _refresh_token(self) -> httpx.Request:
            await self._ensure_oauth_metadata()
            return await super()._refresh_token()

        async def _handle_token_response(self, response: httpx.Response) -> None:
            await super()._handle_token_response(response)

            storage = self.context.storage
            if not isinstance(storage, MCPFileTokenStorage):
                return
            if self.context.protected_resource_metadata is not None:
                await storage.set_protected_resource_metadata(
                    self.context.protected_resource_metadata,
                )
            if self.context.oauth_metadata is not None:
                await storage.set_oauth_metadata(self.context.oauth_metadata)

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


def _build_client_metadata_fields(
    oauth_config: MCPOAuthConfig,
    redirect_uri: str,
) -> dict[str, Any]:
    return {
        "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": _get_token_endpoint_auth_method(oauth_config),
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": oauth_config.scope,
        "client_name": oauth_config.client_name,
        "client_uri": oauth_config.client_uri,
        "logo_uri": oauth_config.logo_uri,
        "contacts": oauth_config.contacts,
        "tos_uri": oauth_config.tos_uri,
        "policy_uri": oauth_config.policy_uri,
        "software_id": oauth_config.software_id,
        "software_version": oauth_config.software_version,
    }


async def _seed_client_info_if_needed(
    storage: MCPFileTokenStorage,
    oauth_config: MCPOAuthConfig,
    *,
    redirect_uri: str,
) -> None:
    if oauth_config.client_id:
        await storage.set_client_info(
            OAuthClientInformationFull(
                **_build_client_metadata_fields(oauth_config, redirect_uri),
                client_id=oauth_config.client_id,
                client_secret=oauth_config.client_secret,
            )
        )


@dataclass(slots=True)
class MCPOAuthPendingFlow:
    flow_id: str
    config: dict[str, Any]
    redirect_uri: str
    oauth_defaults: dict[str, Any] = field(default_factory=dict)
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
    oauth_defaults: Mapping[str, Any] | None = None,
) -> httpx.Auth | None:
    prepared = apply_mcp_oauth_defaults(
        config,
        oauth_defaults
        if oauth_defaults is not None
        else get_shared_mcp_oauth_defaults(),
    )
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
        if interactive_flow
        else (
            _resolve_configured_redirect_uri(oauth_config)
            or await storage.get_redirect_uri()
            or "http://127.0.0.1/astrbot/mcp/oauth/callback/pending"
        )
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
        client_metadata=OAuthClientMetadata(
            **_build_client_metadata_fields(oauth_config, redirect_uri)
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=oauth_config.timeout,
        client_metadata_url=oauth_config.client_metadata_url,
    )


async def get_mcp_oauth_state(
    config: Mapping[str, Any],
    oauth_defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    prepared = apply_mcp_oauth_defaults(
        config,
        oauth_defaults
        if oauth_defaults is not None
        else get_shared_mcp_oauth_defaults(),
    )
    oauth_config = get_mcp_oauth_config(prepared)
    authorized = (
        oauth_config is not None and oauth_config.grant_type == "client_credentials"
    )
    if oauth_config is not None and not authorized:
        storage = MCPFileTokenStorage.from_mcp_config(prepared)
        tokens = await storage.get_tokens()
        authorized = tokens is not None
        if authorized and tokens is not None:
            expires_at = await storage.get_token_expires_at()
            authorized = not (
                expires_at is not None
                and time.time() > expires_at
                and not tokens.refresh_token
            )

    return {
        "oauth2_enabled": oauth_config is not None,
        "oauth2_authorized": authorized,
        "oauth2_grant_type": oauth_config.grant_type if oauth_config else None,
    }


async def probe_mcp_http_oauth_connection(
    config: Mapping[str, Any],
    auth: httpx.Auth,
) -> None:
    """Validate OAuth-protected HTTP MCP connectivity before opening a session.

    Args:
        config: MCP server config containing HTTP URL and transport type.
        auth: Prepared HTTPX OAuth auth provider.

    Raises:
        MCPOAuthError: If the server rejects the OAuth-authenticated probe.
    """
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
        probe_session_id = None
        if transport_type == "streamable_http":
            # A streamable HTTP server may answer with an SSE body that stays
            # open; read only the response head instead of buffering it.
            async with client.stream(
                "POST",
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
            ) as response:
                status_code = response.status_code
                reason_phrase = response.reason_phrase
                probe_session_id = response.headers.get("mcp-session-id")
        else:
            # SSE servers keep the event stream open; buffering the body would
            # hang until timeout. Read only the response head.
            async with client.stream(
                "GET",
                url,
                headers={
                    **headers,
                    "Accept": "application/json, text/event-stream",
                },
                auth=auth,
            ) as response:
                status_code = response.status_code
                reason_phrase = response.reason_phrase

        if status_code != 200:
            raise MCPOAuthError(
                f"OAuth authorization probe failed: HTTP {status_code} {reason_phrase}",
            )

        if probe_session_id:
            try:
                await client.delete(
                    url,
                    headers={**headers, "mcp-session-id": probe_session_id},
                    auth=auth,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to terminate MCP OAuth probe session: {exc}")


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
        storage = MCPFileTokenStorage.from_mcp_config(flow.config)
        snapshot = await storage.snapshot()
        try:
            auth = await create_mcp_http_auth(
                flow.config,
                interactive_flow=flow,
                oauth_defaults=flow.oauth_defaults,
            )
            if auth is None:
                raise MCPOAuthError("OAuth 2.0 is not configured for this MCP server.")
            await probe_mcp_http_oauth_connection(flow.config, auth)
            flow.status = "completed"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc).strip() or exc.__class__.__name__
            if isinstance(exc, httpx.TimeoutException):
                request = getattr(exc, "request", None)
                target = f" while requesting {request.url}" if request else ""
                error_message = f"{exc.__class__.__name__}{target}"
            # Token exchange may already have persisted tokens before the flow
            # failed; restore the pre-flow payload so the reported failure stays
            # consistent with the stored authorization state.
            try:
                await storage.restore(snapshot)
            except Exception as restore_exc:  # noqa: BLE001
                logger.warning(
                    "Failed to restore MCP OAuth storage after a failed flow: %s",
                    restore_exc,
                )
            flow.error = error_message
            flow.status = "failed"
            flow.url_ready_event.set()
        finally:
            flow.done_event.set()

    async def start_authorization(
        self,
        config: Mapping[str, Any],
        *,
        callback_base_url: str,
        oauth_defaults: Mapping[str, Any] | None = None,
        server_name: str | None = None,
        force: bool = False,
    ) -> MCPOAuthPendingFlow:
        resolved_defaults = (
            oauth_defaults
            if oauth_defaults is not None
            else get_shared_mcp_oauth_defaults()
        )
        prepared = apply_mcp_oauth_defaults(config, resolved_defaults)
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
            await storage.clear_tokens(include_client_info=True)

        flow_id = uuid.uuid4().hex
        redirect_uri = get_mcp_oauth_redirect_uri(prepared, callback_base_url)

        flow = MCPOAuthPendingFlow(
            flow_id=flow_id,
            config=prepared,
            redirect_uri=redirect_uri,
            oauth_defaults=dict(resolved_defaults),
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
                # Preparation performs provider requests (metadata discovery,
                # client registration) bounded by the configured OAuth timeout.
                timeout=float(oauth_config.timeout),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            if not done:
                if flow.task is not None:
                    flow.task.cancel()
                    await asyncio.gather(flow.task, return_exceptions=True)
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
