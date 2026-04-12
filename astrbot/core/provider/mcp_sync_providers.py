from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, ClassVar

import aiohttp


@dataclass(frozen=True, slots=True)
class SyncedMcpServer:
    name: str
    config: dict[str, Any]


class McpServerSyncProvider(abc.ABC):
    provider: ClassVar[str]

    @abc.abstractmethod
    async def fetch(self, payload: dict[str, Any]) -> list[SyncedMcpServer]:
        raise NotImplementedError

    async def list_servers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return []


_provider_registry: dict[str, type[McpServerSyncProvider]] = {}


def register_mcp_sync_provider(provider: str):
    def decorator(cls: type[McpServerSyncProvider]) -> type[McpServerSyncProvider]:
        if provider in _provider_registry:
            raise ValueError(f"MCP sync provider already registered: {provider}")
        cls.provider = provider  # type: ignore[attr-defined]
        _provider_registry[provider] = cls
        return cls

    return decorator


def get_mcp_sync_provider(provider: str) -> McpServerSyncProvider:
    cls = _provider_registry.get(provider)
    if not cls:
        raise ValueError(f"Unknown MCP sync provider: {provider}")
    return cls()


@register_mcp_sync_provider("modelscope")
class ModelscopeMcpServerSyncProvider(McpServerSyncProvider):
    async def fetch(self, payload: dict[str, Any]) -> list[SyncedMcpServer]:
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise ValueError("Missing required field: access_token")

        base_url = "https://www.modelscope.cn/openapi/v1"
        url = f"{base_url}/mcp/servers/operational"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"ModelScope API request failed: HTTP {response.status}"
                    )
                data = await response.json()

        mcp_server_list = data.get("data", {}).get("mcp_server_list", []) or []
        items: list[SyncedMcpServer] = []
        for server in mcp_server_list:
            server_name = server.get("name")
            operational_urls = server.get("operational_urls") or []
            if not server_name or not operational_urls:
                continue
            server_url = (operational_urls[0] or {}).get("url")
            if not server_url:
                continue
            items.append(
                SyncedMcpServer(
                    name=server_name,
                    config={
                        "url": server_url,
                        "transport": "sse",
                        "active": True,
                        "provider": "modelscope",
                    },
                )
            )
        return items


@register_mcp_sync_provider("mcprouter")
class McpRouterMcpServerSyncProvider(McpServerSyncProvider):
    @staticmethod
    def _build_error_detail(data: dict[str, Any]) -> str:
        message = data.get("message") or data.get("error") or data.get("detail")
        code = data.get("code")
        if message is None:
            return ""
        message_text = str(message).strip()
        if not message_text:
            return ""
        if code is None:
            return message_text
        return f"{code}: {message_text}"

    async def _post_json(
        self,
        *,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        action: str,
    ) -> dict[str, Any]:
        async with session.post(url, json=payload, headers=headers) as response:
            body_text = ""
            data: dict[str, Any] = {}
            try:
                parsed = await response.json(content_type=None)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                body_text = (await response.text()).strip()

            if response.status != 200:
                reason = response.reason or ""
                detail = self._build_error_detail(data) or body_text[:300]
                if detail:
                    raise RuntimeError(
                        f"{action} failed: HTTP {response.status} {reason} ({detail})"
                    )
                raise RuntimeError(f"{action} failed: HTTP {response.status} {reason}")

            if not data:
                detail = body_text[:300] if body_text else "empty or non-json response"
                raise RuntimeError(f"{action} failed: invalid response ({detail})")

            return data

    def _ensure_api_success(self, data: dict[str, Any], *, action: str) -> None:
        if data.get("code") == 0:
            return
        detail = self._build_error_detail(data) or "unknown error"
        raise RuntimeError(f"{action} failed: {detail}")

    def _normalize_api_key(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return raw
        lower = raw.lower()
        if lower.startswith("bearer "):
            return raw[7:].strip()
        if lower.startswith("authorization:"):
            after = raw.split(":", 1)[1].strip()
            if after.lower().startswith("bearer "):
                return after[7:].strip()
            return after
        return raw

    def _build_api_headers(
        self,
        *,
        api_key: str,
        app_url: str,
        app_name: str,
    ) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if app_url:
            headers["HTTP-Referer"] = app_url
        if app_name:
            headers["X-Title"] = app_name
        return headers

    def _build_mcp_headers(
        self,
        *,
        api_key: str,
        app_url: str,
        app_name: str,
    ) -> dict[str, str]:
        return self._build_api_headers(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
        )

    @staticmethod
    def _parse_server_keys(value: Any) -> list[str]:
        if isinstance(value, list):
            parts = [str(item).strip() for item in value]
        elif isinstance(value, str):
            raw = value.replace(",", "\n").replace(";", "\n")
            parts = [line.strip() for line in raw.splitlines()]
        else:
            return []

        keys = [item for item in parts if item]
        seen: set[str] = set()
        result: list[str] = []
        for item in keys:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _matches(server: dict[str, Any], q: str) -> bool:
        if not q:
            return True
        haystacks = [
            server.get("config_name"),
            server.get("server_key"),
            server.get("name"),
            server.get("title"),
            server.get("description"),
            server.get("author_name"),
        ]
        combined = " ".join(str(v) for v in haystacks if v)
        return q in combined.lower()

    @staticmethod
    def _resolve_server_name(
        server: dict[str, Any],
        *,
        fallback: str | None = None,
    ) -> str | None:
        return (
            server.get("config_name")
            or server.get("server_key")
            or server.get("name")
            or server.get("title")
            or fallback
        )

    def _make_item(
        self,
        *,
        name: str,
        url: str,
        used_names: set[str],
        headers: dict[str, str],
        server_key: str | None = None,
    ) -> SyncedMcpServer:
        final_name = name
        if final_name in used_names:
            suffix = server_key or "dup"
            final_name = f"{final_name}-{suffix}"
        i = 2
        while final_name in used_names:
            final_name = f"{name}-{i}"
            i += 1
        used_names.add(final_name)
        return SyncedMcpServer(
            name=final_name,
            config={
                "url": url,
                "transport": "streamable_http",
                "headers": headers,
                "active": True,
                "provider": "mcprouter",
            },
        )

    async def _iter_list_servers_batches(
        self,
        *,
        list_url: str,
        api_headers: dict[str, str],
        limit: int,
        max_pages: int,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for page in range(1, max_pages + 1):
                data = await self._post_json(
                    session=session,
                    url=list_url,
                    payload={"page": page, "limit": limit},
                    headers=api_headers,
                    action="MCPRouter list-servers",
                )
                self._ensure_api_success(data, action="MCPRouter list-servers")
                raw_batch = data.get("data", {}).get("servers", []) or []
                if not raw_batch:
                    break
                batch = [item for item in raw_batch if isinstance(item, dict)]
                if batch:
                    yield batch
                if len(raw_batch) < limit:
                    break

    async def _fetch_from_provided_servers(
        self,
        *,
        provided_servers: list[Any],
        raw_max_servers: Any,
        max_servers: int,
        mcp_headers: dict[str, str],
    ) -> list[SyncedMcpServer]:
        used_names: set[str] = set()
        items: list[SyncedMcpServer] = []
        selected_servers = (
            provided_servers[:max_servers]
            if raw_max_servers is not None
            else provided_servers
        )
        for server in selected_servers:
            if not isinstance(server, dict):
                continue
            server_name = self._resolve_server_name(server)
            server_url = server.get("server_url")
            if not server_name or not server_url:
                continue
            server_key = server.get("server_key")
            items.append(
                self._make_item(
                    name=str(server_name),
                    url=str(server_url),
                    used_names=used_names,
                    headers=mcp_headers,
                    server_key=str(server_key) if server_key else None,
                )
            )
        return items

    async def _fetch_from_server_keys(
        self,
        *,
        server_keys: list[str],
        max_servers: int,
        get_url: str,
        api_headers: dict[str, str],
        mcp_headers: dict[str, str],
    ) -> list[SyncedMcpServer]:
        timeout = aiohttp.ClientTimeout(total=30)
        used_names: set[str] = set()
        items: list[SyncedMcpServer] = []
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for server_key in server_keys[:max_servers]:
                data = await self._post_json(
                    session=session,
                    url=get_url,
                    payload={"server": server_key},
                    headers=api_headers,
                    action="MCPRouter get-server",
                )
                self._ensure_api_success(data, action="MCPRouter get-server")
                server = data.get("data") or {}
                if not isinstance(server, dict):
                    continue
                server_url = server.get("server_url")
                server_name = self._resolve_server_name(server, fallback=server_key)
                if not server_url or not server_name:
                    continue
                items.append(
                    self._make_item(
                        name=str(server_name),
                        url=str(server_url),
                        used_names=used_names,
                        headers=mcp_headers,
                        server_key=server_key,
                    )
                )
        return items

    async def _fetch_from_listing(
        self,
        *,
        list_url: str,
        api_headers: dict[str, str],
        mcp_headers: dict[str, str],
        query: str,
        max_servers: int,
        limit: int,
        max_pages: int,
    ) -> list[SyncedMcpServer]:
        used_names: set[str] = set()
        items: list[SyncedMcpServer] = []
        async for batch in self._iter_list_servers_batches(
            list_url=list_url,
            api_headers=api_headers,
            limit=limit,
            max_pages=max_pages,
        ):
            for server in batch:
                if not self._matches(server, query):
                    continue
                server_url = server.get("server_url")
                server_name = self._resolve_server_name(server)
                if not server_url or not server_name:
                    continue
                server_key = server.get("server_key")
                items.append(
                    self._make_item(
                        name=str(server_name),
                        url=str(server_url),
                        used_names=used_names,
                        headers=mcp_headers,
                        server_key=str(server_key) if server_key else None,
                    )
                )
                if len(items) >= max_servers:
                    return items
        return items

    async def _validate_api_key(
        self,
        *,
        api_key: str,
        app_url: str,
        app_name: str,
        base_url: str,
    ) -> None:
        url = f"{base_url}/list-servers"
        headers = self._build_api_headers(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
        )
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = await self._post_json(
                session=session,
                url=url,
                payload={"page": 1, "limit": 1},
                headers=headers,
                action="MCPRouter API key validation",
            )

        if data.get("code") != 0:
            detail = self._build_error_detail(data) or "unknown"
            raise ValueError(f"MCPRouter API key validation failed: {detail}")

    async def fetch(self, payload: dict[str, Any]) -> list[SyncedMcpServer]:
        api_key = self._normalize_api_key(str(payload.get("api_key", "")))
        if not api_key:
            raise ValueError("Missing required field: api_key")

        app_url = str(payload.get("app_url", "")).strip()
        app_name = str(payload.get("app_name", "")).strip()

        base_url = str(payload.get("api_base", "https://api.mcprouter.to/v1")).rstrip(
            "/"
        )
        list_url = f"{base_url}/list-servers"
        get_url = f"{base_url}/get-server"

        await self._validate_api_key(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
            base_url=base_url,
        )

        api_headers = self._build_api_headers(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
        )
        mcp_headers = self._build_mcp_headers(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
        )

        query = str(payload.get("query", "")).strip().lower()
        raw_max_servers = payload.get("max_servers")
        max_servers = int(raw_max_servers or 30)
        max_servers = max(1, min(max_servers, 500))

        limit = int(payload.get("limit", 30) or 30)
        limit = max(1, min(limit, 100))

        max_pages = int(payload.get("max_pages", 10) or 10)
        max_pages = max(1, min(max_pages, 50))

        provided_servers = payload.get("servers")
        if isinstance(provided_servers, list) and provided_servers:
            return await self._fetch_from_provided_servers(
                provided_servers=provided_servers,
                raw_max_servers=raw_max_servers,
                max_servers=max_servers,
                mcp_headers=mcp_headers,
            )

        server_keys = self._parse_server_keys(payload.get("server_keys"))
        if server_keys:
            return await self._fetch_from_server_keys(
                server_keys=server_keys,
                max_servers=max_servers,
                get_url=get_url,
                api_headers=api_headers,
                mcp_headers=mcp_headers,
            )

        return await self._fetch_from_listing(
            list_url=list_url,
            api_headers=api_headers,
            mcp_headers=mcp_headers,
            query=query,
            max_servers=max_servers,
            limit=limit,
            max_pages=max_pages,
        )

    async def list_servers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        api_key = self._normalize_api_key(str(payload.get("api_key", "")))
        if not api_key:
            raise ValueError("Missing required field: api_key")

        app_url = str(payload.get("app_url", "")).strip()
        app_name = str(payload.get("app_name", "")).strip()
        base_url = str(payload.get("api_base", "https://api.mcprouter.to/v1")).rstrip(
            "/"
        )
        list_url = f"{base_url}/list-servers"

        await self._validate_api_key(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
            base_url=base_url,
        )

        api_headers = self._build_api_headers(
            api_key=api_key,
            app_url=app_url,
            app_name=app_name,
        )

        limit = 100
        max_pages = 20
        max_items = 2000

        servers: list[dict[str, Any]] = []
        async for batch in self._iter_list_servers_batches(
            list_url=list_url,
            api_headers=api_headers,
            limit=limit,
            max_pages=max_pages,
        ):
            for item in batch:
                server_url = item.get("server_url")
                server_key = item.get("server_key")
                config_name = item.get("config_name")
                if not server_url or not (server_key or config_name):
                    continue
                servers.append(item)
                if len(servers) >= max_items:
                    return servers

        return servers
