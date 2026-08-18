"""Modern MCP 2026-07-28 client support.

The MCP Python SDK 2.x client owns protocol negotiation and transports.  This
module deliberately has no legacy session, initialize, or SSE fallback path.
"""

import asyncio
import contextvars
import copy
import hashlib
import json
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, TextIO, cast
from urllib.parse import parse_qs, urlparse

import httpx2
from mcp import Client
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.session import ClientRequestContext
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from mcp.shared.exceptions import MCPError
from mcp.types import (
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitRequestParams,
    ElicitRequestURLParams,
    ElicitResult,
    ErrorData,
    InputRequiredResult,
    LoggingMessageNotificationParams,
)
from mcp.types.version import LATEST_PROTOCOL_VERSION
from pydantic import AnyUrl

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.core.utils.log_pipe import LogPipe

from .tool import FunctionTool

MCP_PROTOCOL_VERSION = "2026-07-28"
MAX_MCP_LIST_PAGES = 100
MAX_MCP_RESOURCE_TEXT_BYTES = 1_000_000
MAX_MCP_RESOURCE_BINARY_BYTES = 5_000_000
MAX_MCP_INTERACTION_SECONDS = 300
MAX_MCP_INTERACTION_ROUNDS = 10

if (
    LATEST_PROTOCOL_VERSION != MCP_PROTOCOL_VERSION
):  # pragma: no cover - dependency gate
    raise RuntimeError("AstrBot requires MCP Python SDK 2.x with protocol 2026-07-28.")

_LLM_MCP_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SHELL_META_RE = re.compile(r"[\r\n\x00;&|<>`$]")
_SENSITIVE_FIELD_RE = re.compile(
    r"(?:password|passphrase|token|api[_-]?key|secret|card|payment)", re.I
)
_DEFAULT_STDIO_COMMAND_ALLOWLIST = frozenset(
    {
        "python",
        "python3",
        "py",
        "node",
        "npx",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "bunx",
        "deno",
        "uv",
        "uvx",
    }
)
_DENIED_STDIO_COMMANDS = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "fish",
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "osascript",
        "open",
        "curl",
        "wget",
        "nc",
        "netcat",
        "telnet",
        "ssh",
        "scp",
        "rm",
        "mv",
        "cp",
        "dd",
        "mkfs",
        "sudo",
        "su",
        "chmod",
        "chown",
        "kill",
        "killall",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
    }
)
_PYTHON_INLINE_CODE_FLAGS = frozenset({"-c"})
_JS_INLINE_CODE_FLAGS = frozenset({"-e", "--eval", "-p", "--print"})
_STDIO_ALLOWLIST_ENV = "ASTRBOT_MCP_STDIO_ALLOWED_COMMANDS"
_MCP_CONFIG_FIELDS = frozenset(
    {
        "active",
        "transport",
        "command",
        "args",
        "env",
        "url",
        "headers",
        "allow_private_network",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "terminate_on_close",
        "auth_ref",
    }
)
_REJECTED_MCP_CONFIG_FIELDS = frozenset(
    {
        "type",
        "sse_read_timeout",
        "session_read_timeout",
        "timeout",
        "cwd",
        "encoding",
        "encoding_error_handler",
    }
)


class MCPToolNameAllocationError(ValueError):
    """Raised when an MCP tool cannot receive a safe LLM-facing name."""


class MCPConnectionLostError(RuntimeError):
    """A call may have reached a server, so it must never be replayed implicitly."""


class MCPLegacyProtocolError(RuntimeError):
    """Raised when a diagnostic connection reports a pre-2026 MCP server."""


def _default_llm_mcp_tool_name(server_name: str, tool_name: str) -> str:
    identity = f"{server_name}\x00{tool_name}".encode()
    digest = hashlib.blake2s(identity, digest_size=8).hexdigest()
    readable = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{server_name}_{tool_name}")
    readable = readable.strip("_-") or "tool"
    return f"mcp_{readable[:43]}_{digest}"


class MCPToolNameAllocator:
    """Own stable, collision-free LLM-facing names for MCP tools."""

    def __init__(self, candidate_factory=_default_llm_mcp_tool_name) -> None:
        self._candidate_factory = candidate_factory
        self._name_by_identity: dict[tuple[str, str], str] = {}
        self._identity_by_name: dict[str, tuple[str, str]] = {}

    def allocate(self, server_name: str, tool_name: object) -> str:
        if not isinstance(server_name, str) or not server_name:
            raise MCPToolNameAllocationError("MCP server name is empty.")
        if not isinstance(tool_name, str) or not tool_name:
            raise MCPToolNameAllocationError("MCP tool name is empty.")
        identity = (server_name, tool_name)
        if identity in self._name_by_identity:
            return self._name_by_identity[identity]
        candidate = self._candidate_factory(server_name, tool_name)
        if not isinstance(candidate, str) or not _LLM_MCP_TOOL_NAME_RE.fullmatch(
            candidate
        ):
            raise MCPToolNameAllocationError(
                "MCP tool name allocator produced an invalid LLM name."
            )
        existing = self._identity_by_name.get(candidate)
        if existing is not None and existing != identity:
            raise MCPToolNameAllocationError(
                "MCP tool name collision; refusing ambiguous registration."
            )
        self._name_by_identity[identity] = candidate
        self._identity_by_name[candidate] = identity
        return candidate


def _prepare_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copied server config and reject the removed wrapper format."""
    if "mcpServers" in config:
        raise ValueError("Legacy MCP mcpServers wrapper is not supported.")
    return {
        key: copy.deepcopy(value) for key, value in config.items() if key != "active"
    }


def _is_truthy_config_value(value: object) -> bool:
    return value is True


def _allow_private_network_access(config: dict[str, Any]) -> bool:
    return _is_truthy_config_value(config.get("allow_private_network", False))


def _validate_remote_url(url: str, *, allow_private_network: bool = False) -> None:
    """Validate an MCP endpoint before every new HTTP connection/request."""
    from dataclasses import replace

    from astrbot.core.utils.outbound_http import (
        MCP_REMOTE,
        OutboundRequestError,
        validate_outbound_url,
    )

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            "MCP remote connection URL must use http or https and include a hostname."
        )
    if parsed.username or parsed.password:
        raise ValueError("MCP remote connection URL must not contain credentials.")
    policy = replace(MCP_REMOTE, allow_private_network=allow_private_network)
    try:
        validate_outbound_url(url, policy)
    except OutboundRequestError as exc:
        message = str(exc)
        if "resolved" in message:
            hostname = parsed.hostname or ""
            raise ValueError(
                f"MCP remote connection URL hostname could not be resolved: {hostname}"
            ) from exc
        raise ValueError(
            "MCP remote connection URL cannot target private or local IP addresses."
        ) from exc


def _create_mcp_http_client_without_redirects(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
    *,
    url: str | None = None,
    allow_private_network: bool = False,
) -> httpx2.AsyncClient:
    """Create the only HTTP client used for MCP endpoint traffic.

    The request hook repeats the DNS/IP validation before each request.  This
    makes a new DNS answer observable before httpx opens a connection and is
    intentionally paired with disabled redirects.
    """

    async def validate_request(request: httpx2.Request) -> None:
        _validate_remote_url(
            str(request.url), allow_private_network=allow_private_network
        )

    from dataclasses import replace

    from astrbot.core.utils.outbound_http import MCP_REMOTE, pin_httpx_transport

    transport = pin_httpx_transport(
        httpx2.AsyncHTTPTransport(),
        replace(MCP_REMOTE, allow_private_network=allow_private_network),
    )
    kwargs: dict[str, Any] = {
        "follow_redirects": False,
        "trust_env": False,
        "transport": transport,
        "event_hooks": {"request": [validate_request]},
    }
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    if auth is not None:
        kwargs["auth"] = auth
    if url is not None:
        _validate_remote_url(url, allow_private_network=allow_private_network)
    return httpx2.AsyncClient(**kwargs)


def _normalize_stdio_command_name(command: str) -> str:
    name = (
        PureWindowsPath(command).name if "\\" in command else Path(command).name
    ).lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _get_stdio_command_allowlist() -> set[str]:
    configured = os.environ.get(_STDIO_ALLOWLIST_ENV, "")
    if not configured.strip():
        return set(_DEFAULT_STDIO_COMMAND_ALLOWLIST)
    return {
        _normalize_stdio_command_name(item)
        for item in configured.split(",")
        if item.strip()
    }


def _validate_stdio_args(command_name: str, args: object) -> None:
    if args is None:
        return
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("MCP stdio args must be a list of strings.")
    if any("\x00" in arg or "\r" in arg or "\n" in arg for arg in args):
        raise ValueError("MCP stdio args cannot contain control characters.")
    if command_name.startswith("python") or command_name == "py":
        if any(
            arg == "-c"
            or (arg.startswith("-") and not arg.startswith("--") and "c" in arg)
            for arg in args
        ):
            raise ValueError(
                "MCP stdio Python servers must be launched from a module or file; inline code flags are not allowed."
            )
    if command_name in {"node", "deno", "bun"} or command_name.startswith("node"):
        if any(
            arg in _JS_INLINE_CODE_FLAGS
            or arg == "eval"
            or (
                arg.startswith("-")
                and not arg.startswith("--")
                and any(letter in arg for letter in "ep")
            )
            for arg in args
        ):
            raise ValueError(
                "MCP stdio JavaScript servers must be launched from a package or file; inline eval flags are not allowed."
            )


def validate_mcp_server_config(config: dict[str, Any]) -> None:
    """Strictly validate the fork's modern MCP server configuration."""
    if not isinstance(config, dict):
        raise ValueError("MCP server configuration must be an object.")
    unknown = set(config) - _MCP_CONFIG_FIELDS
    rejected = set(config) & _REJECTED_MCP_CONFIG_FIELDS
    if rejected:
        raise ValueError(
            f"Removed MCP configuration fields are not supported: {', '.join(sorted(rejected))}."
        )
    if unknown:
        raise ValueError(
            f"Unknown MCP configuration fields are not supported: {', '.join(sorted(unknown))}."
        )
    command, url, transport = (
        config.get("command"),
        config.get("url"),
        config.get("transport"),
    )
    if bool(command) == bool(url):
        raise ValueError("MCP configuration requires exactly one of command or url.")
    if transport not in {None, "stdio", "streamable_http"}:
        raise ValueError(
            "MCP transport must be stdio or streamable_http; SSE is not supported."
        )
    if url is not None:
        if transport != "streamable_http":
            raise ValueError("Remote MCP servers require transport=streamable_http.")
        if not isinstance(url, str):
            raise ValueError("MCP remote URL must be a string.")
        _validate_remote_url(
            url, allow_private_network=_allow_private_network_access(config)
        )
        headers = config.get("headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            raise ValueError("MCP headers must be an object of strings.")
    else:
        if transport not in {None, "stdio"}:
            raise ValueError(
                "A command MCP server must use transport=stdio when transport is provided."
            )
        validate_mcp_stdio_config(config)
    for key in ("connect_timeout_seconds", "read_timeout_seconds"):
        value = config.get(key)
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0
        ):
            raise ValueError(f"MCP {key} must be a positive number.")
    for key in ("active", "allow_private_network", "terminate_on_close"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"MCP {key} must be a boolean.")
    if "auth_ref" in config and (
        not isinstance(config["auth_ref"], str) or not config["auth_ref"]
    ):
        raise ValueError("MCP auth_ref must be a non-empty string.")


def validate_mcp_stdio_config(config: dict[str, Any]) -> None:
    """Validate a trusted stdio launch without allowing a shell escape."""
    if "url" in config:
        return
    command = config.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("MCP stdio server requires a non-empty command.")
    if _SHELL_META_RE.search(command):
        raise ValueError("MCP stdio command contains unsafe shell metacharacters.")
    command_name = _normalize_stdio_command_name(command)
    if (
        command_name in _DENIED_STDIO_COMMANDS
        or command_name not in _get_stdio_command_allowlist()
    ):
        raise ValueError(f"MCP stdio command `{command_name}` is not allowed.")
    _validate_stdio_args(command_name, config.get("args"))
    env = config.get("env")
    if env is not None and (
        not isinstance(env, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        )
    ):
        raise ValueError("MCP stdio env keys and values must be strings.")


def _prepare_stdio_env(config: dict[str, Any]) -> dict[str, Any]:
    if sys.platform != "win32":
        return config
    merged = dict(config)
    env = dict(merged.get("env") or {})
    lower_keys = {key.lower() for key in env}
    env.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.lower() not in lower_keys
        }
    )
    merged["env"] = env
    return merged


def _normalize_mcp_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize non-standard property-level ``required`` flags without mutation."""

    def normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [normalize(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {key: normalize(value) for key, value in node.items()}
        properties = result.get("properties")
        if not isinstance(properties, dict):
            return result
        original = node.get("properties")
        if not isinstance(original, dict):
            original = {}
        required = result.get("required")
        names = list(required) if isinstance(required, list) else []
        for name, property_schema in properties.items():
            raw = original.get(name)
            if (
                isinstance(property_schema, dict)
                and isinstance(raw, dict)
                and isinstance(raw.get("required"), bool)
            ):
                if property_schema.get("required") is raw["required"]:
                    property_schema.pop("required", None)
                if raw["required"]:
                    names.append(name)
        if names:
            result["required"] = list(dict.fromkeys(names))
        elif isinstance(required, list):
            result.pop("required", None)
        return result

    return normalize(copy.deepcopy(schema))


@dataclass(frozen=True)
class MCPInteractionKey:
    unified_msg_origin: str
    run_id: str
    request_id: str
    server_name: str


@dataclass
class _PendingInteraction:
    key: MCPInteractionKey
    sender_id: str | None
    payload: dict[str, Any]
    future: asyncio.Future[ElicitResult]
    rounds: int = 0


_mcp_interaction_context: contextvars.ContextVar[
    tuple[MCPInteractionKey, str | None, Any | None] | None
] = contextvars.ContextVar("mcp_interaction_context", default=None)


class MCPInteractionCoordinator:
    """Runtime-owned, sender-isolated coordinator for MCP elicitation.

    Platform and WebChat adapters register a small publisher/router with this
    instance.  Keeping it here avoids a process-global pending-input registry.
    """

    def __init__(
        self, publisher: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    ) -> None:
        self._publisher = publisher
        self._pending: dict[MCPInteractionKey, _PendingInteraction] = {}
        self._lock = asyncio.Lock()

    def set_publisher(
        self, publisher: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        """Attach the runtime transport publisher after service construction."""
        self._publisher = publisher

    @contextmanager
    def bind(
        self, key: MCPInteractionKey, sender_id: str | None, event: Any | None = None
    ):
        token = _mcp_interaction_context.set((key, sender_id, event))
        try:
            yield
        finally:
            _mcp_interaction_context.reset(token)

    @staticmethod
    def _validate_form_schema(schema: Any) -> None:
        if not isinstance(schema, dict) or not isinstance(
            schema.get("properties"), dict
        ):
            raise ValueError("MCP form schema must define top-level properties.")
        for name, definition in schema["properties"].items():
            if _SENSITIVE_FIELD_RE.search(str(name)) or (
                isinstance(definition, dict)
                and _SENSITIVE_FIELD_RE.search(str(definition.get("format", "")))
            ):
                raise ValueError(
                    "MCP form requests cannot collect credentials or payment data."
                )
            if (
                not isinstance(definition, dict)
                or "properties" in definition
                or "items" in definition
                and isinstance(definition["items"], dict)
                and "properties" in definition["items"]
            ):
                raise ValueError(
                    "MCP form schema must use the restricted flat schema subset."
                )

    @staticmethod
    def _validate_form_response(
        schema: dict[str, Any], content: dict[str, Any]
    ) -> dict[str, str | int | float | bool | list[str] | None]:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if (
            not isinstance(content, dict)
            or set(content) - set(properties)
            or required - set(content)
        ):
            raise ValueError("MCP form response does not match the requested fields.")
        accepted: dict[str, str | int | float | bool | list[str] | None] = {}
        for name, value in content.items():
            expected = (
                properties[name].get("type")
                if isinstance(properties[name], dict)
                else None
            )
            valid = (
                value is None
                or expected is None
                or expected == "string"
                and isinstance(value, str)
                or expected == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                or expected == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                or expected == "boolean"
                and isinstance(value, bool)
                or expected == "array"
                and isinstance(value, list)
                and all(isinstance(item, str) for item in value)
            )
            if not valid:
                raise ValueError("MCP form response has an invalid field type.")
            accepted[name] = value
        return accepted

    async def handle_elicitation(
        self,
        context: ClientRequestContext | None,
        params: ElicitRequestParams,
    ) -> ElicitResult | ErrorData:
        del context
        bound = _mcp_interaction_context.get()
        if bound is None:
            return ErrorData(
                code=-32000, message="No active AstrBot request for MCP elicitation."
            )
        key, sender_id, _event = bound
        mode = params.mode
        payload: dict[str, Any] = {
            "type": "mcp_input_request",
            "message_id": key.request_id,
            "request_id": key.request_id,
            "unified_msg_origin": key.unified_msg_origin,
            "run_id": key.run_id,
            "server_name": key.server_name,
            "mode": mode,
            "message": params.message[:2000],
        }
        if isinstance(params, ElicitRequestFormParams):
            try:
                schema_data = params.requested_schema
                self._validate_form_schema(schema_data)
            except ValueError as exc:
                return ErrorData(code=-32602, message=str(exc))
            payload["schema"] = schema_data
        elif isinstance(params, ElicitRequestURLParams):
            parsed = urlparse(params.url)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                return ErrorData(code=-32602, message="MCP elicitation URL is invalid.")
            payload["url"] = params.url
            payload["url_display"] = f"{parsed.scheme}://{parsed.hostname}"
        else:
            return ErrorData(code=-32602, message="Unsupported MCP elicitation mode.")
        loop = asyncio.get_running_loop()
        pending = _PendingInteraction(key, sender_id, payload, loop.create_future())
        async with self._lock:
            prior = self._pending.pop(key, None)
            if prior is not None and not prior.future.done():
                prior.future.set_result(ElicitResult(action="cancel"))
            self._pending[key] = pending
        try:
            if self._publisher is not None:
                await self._publisher(payload)
            return await asyncio.wait_for(pending.future, MAX_MCP_INTERACTION_SECONDS)
        except TimeoutError:
            return ElicitResult(action="cancel")
        except asyncio.CancelledError:
            raise
        finally:
            async with self._lock:
                self._pending.pop(key, None)

    async def respond(
        self,
        key: MCPInteractionKey,
        sender_id: str | None,
        action: str,
        content: dict[str, Any] | None = None,
    ) -> bool:
        if action not in {"accept", "decline", "cancel"}:
            return False
        async with self._lock:
            pending = self._pending.get(key)
            if (
                pending is None
                or pending.future.done()
                or (pending.sender_id is not None and pending.sender_id != sender_id)
            ):
                return False
            if action == "accept" and pending.payload["mode"] == "form":
                try:
                    content = self._validate_form_response(
                        pending.payload["schema"], content or {}
                    )
                except ValueError:
                    return False
            pending.future.set_result(
                ElicitResult(
                    action=cast(Literal["accept", "decline", "cancel"], action),
                    content=content
                    if action == "accept" and pending.payload["mode"] == "form"
                    else None,
                )
            )
            return True

    async def respond_from_event(self, event: Any) -> bool:
        """Consume an IM adapter's structured MCP response before follow-ups."""
        response = event.get_extra("mcp_input_response")
        if not isinstance(response, dict):
            return False
        origin = str(getattr(event, "unified_msg_origin", ""))
        if response.get("unified_msg_origin", origin) != origin:
            return False
        request_id = str(response.get("request_id") or response.get("message_id") or "")
        run_id = str(response.get("run_id") or "")
        server_name = str(response.get("server_name") or "")
        if not request_id or not run_id or not server_name:
            return False
        sender_id = event.get_sender_id()
        return await self.respond(
            MCPInteractionKey(origin, run_id, request_id, server_name),
            str(sender_id) if sender_id is not None else None,
            str(response.get("action") or ""),
            response.get("content")
            if isinstance(response.get("content"), dict)
            else None,
        )

    async def cancel_request(self, request_id: str) -> None:
        async with self._lock:
            matches = [
                pending
                for key, pending in self._pending.items()
                if key.request_id == request_id
            ]
            for pending in matches:
                if not pending.future.done():
                    pending.future.set_result(ElicitResult(action="cancel"))

    async def close(self) -> None:
        async with self._lock:
            for pending in self._pending.values():
                if not pending.future.done():
                    pending.future.set_result(ElicitResult(action="cancel"))
            self._pending.clear()


class MCPAuthStore:
    """Permission-restricted persistent OAuth token/client storage for MCP."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def _read(self) -> dict[str, Any]:
        def read() -> dict[str, Any]:
            if not self._path.exists():
                return {}
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                return {}

        return await asyncio.to_thread(read)

    async def _write(self, value: dict[str, Any]) -> None:
        def write() -> None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8"
            )
            os.chmod(temporary, 0o600)
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)

        await asyncio.to_thread(write)

    def for_identity(self, identity: str) -> _MCPAuthIdentityStore:
        return _MCPAuthIdentityStore(self, identity)

    async def status(self, identity: str) -> dict[str, Any]:
        data = await self._read()
        entry = data.get(identity, {})
        token = entry.get("token") if isinstance(entry, dict) else None
        return {
            "configured": bool(token),
            "has_refresh_token": bool(
                isinstance(token, dict) and token.get("refresh_token")
            ),
            "client_registered": bool(
                isinstance(entry, dict) and entry.get("client_info")
            ),
        }

    async def revoke(self, identity: str) -> None:
        async with self._lock:
            data = await self._read()
            data.pop(identity, None)
            await self._write(data)


class _MCPAuthIdentityStore:
    def __init__(self, store: MCPAuthStore, identity: str) -> None:
        self._store, self._identity = store, identity

    async def get_tokens(self) -> OAuthToken | None:
        data = await self._store._read()
        token = data.get(self._identity, {}).get("token")
        return OAuthToken.model_validate(token) if token else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._store._lock:
            data = await self._store._read()
            entry = data.setdefault(self._identity, {})
            entry["token"] = tokens.model_dump(mode="json")
            await self._store._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = await self._store._read()
        value = data.get(self._identity, {}).get("client_info")
        return OAuthClientInformationFull.model_validate(value) if value else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._store._lock:
            data = await self._store._read()
            entry = data.setdefault(self._identity, {})
            entry["client_info"] = client_info.model_dump(mode="json")
            await self._store._write(data)


class MCPAuthorizationCoordinator:
    """Runtime-owned bridge between SDK OAuth callbacks and Dashboard callbacks."""

    def __init__(self) -> None:
        self._urls: dict[str, asyncio.Future[str]] = {}
        self._codes: dict[str, asyncio.Future[AuthorizationCodeResult]] = {}
        self._states: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def redirect_handler(self, identity: str, authorization_url: str) -> None:
        async with self._lock:
            future = self._urls.setdefault(
                identity, asyncio.get_running_loop().create_future()
            )
            state = parse_qs(urlparse(authorization_url).query).get("state", [None])[0]
            if state:
                self._states[state] = identity
            if not future.done():
                future.set_result(authorization_url)

    async def callback_handler(self, identity: str) -> AuthorizationCodeResult:
        async with self._lock:
            future = self._codes.setdefault(
                identity, asyncio.get_running_loop().create_future()
            )
        return await asyncio.wait_for(future, MAX_MCP_INTERACTION_SECONDS)

    async def wait_for_url(self, identity: str, wait_seconds: float = 10) -> str | None:
        async with self._lock:
            future = self._urls.setdefault(
                identity, asyncio.get_running_loop().create_future()
            )
        try:
            return await asyncio.wait_for(asyncio.shield(future), wait_seconds)
        except TimeoutError:
            return None

    async def complete_callback(
        self, identity: str, code: str, state: str | None, iss: str | None
    ) -> bool:
        if not code or not state:
            return False
        async with self._lock:
            future = self._codes.get(identity)
            if future is None or future.done():
                return False
            future.set_result(AuthorizationCodeResult(code=code, state=state, iss=iss))
            return True

    async def complete_callback_from_state(
        self, code: str, state: str | None, iss: str | None
    ) -> bool:
        if not state:
            return False
        async with self._lock:
            identity = self._states.pop(state, None)
        if identity is None:
            return False
        return await self.complete_callback(identity, code, state, iss)

    async def close(self) -> None:
        """Cancel authorization waits owned by the runtime during shutdown."""
        async with self._lock:
            for future in (*self._urls.values(), *self._codes.values()):
                if not future.done():
                    future.cancel()
            self._urls.clear()
            self._codes.clear()
            self._states.clear()


class MCPClient:
    """One modern MCP connection, owned and closed by one asyncio task."""

    def __init__(
        self,
        *,
        interaction_coordinator: MCPInteractionCoordinator | None = None,
        auth_store: MCPAuthStore | None = None,
        auth_coordinator: MCPAuthorizationCoordinator | None = None,
        on_catalog_changed: Callable[[str, str], Awaitable[None] | None] | None = None,
    ) -> None:
        self.client: Client | None = None
        self.exit_stack: AsyncExitStack | None = None
        self.name: str | None = None
        self.active = True
        self.tools: list[Any] = []
        self.resources: list[Any] = []
        self.resource_templates: list[Any] = []
        self.prompts: list[Any] = []
        self.server_errlogs: list[str] = []
        self.protocol_version: str | None = None
        self.capabilities: dict[str, Any] = {}
        self.connection_status = "disconnected"
        self.server_errlogs: list[str] = []
        self._connection_task: asyncio.Task[None] | None = None
        self._watcher_task: asyncio.Task[None] | None = None
        self._mcp_server_config: dict[str, Any] | None = None
        self._server_name: str | None = None
        self._stop_event = asyncio.Event()
        self._reconnect_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._parallel_limit = 1
        self._parallel_semaphore = asyncio.Semaphore(1)
        self._interaction_coordinator = interaction_coordinator
        self._auth_store = auth_store
        self._auth_coordinator = auth_coordinator
        self._on_catalog_changed = on_catalog_changed

    def configure_parallel_limit(self, limit: int) -> None:
        normalized = max(1, min(8, int(limit)))
        if normalized != self._parallel_limit:
            self._parallel_limit = normalized
            self._parallel_semaphore = asyncio.Semaphore(normalized)

    def _record_server_error(self, level: str, data: Any) -> None:
        if level in {
            "warning",
            "error",
            "critical",
            "alert",
            "emergency",
        }:
            self.server_errlogs.append(
                redact_sensitive_text(f"[{level.upper()}] {data}")
            )

    async def _logging_callback(self, params: LoggingMessageNotificationParams) -> None:
        self._record_server_error(str(params.level), params.data)

    def _stderr_logging_callback(self, line: str) -> None:
        self.server_errlogs.append(redact_sensitive_text(line))

    def _oauth_provider(self, cfg: dict[str, Any]) -> OAuthClientProvider | None:
        auth_ref = cfg.get("auth_ref")
        if not auth_ref:
            return None
        auth_store = self._auth_store
        auth_coordinator = self._auth_coordinator
        if auth_store is None or auth_coordinator is None or self._server_name is None:
            raise RuntimeError("MCP OAuth is not available in this runtime.")
        identity = f"{self._server_name}:{auth_ref}"
        endpoint = str(cfg["url"])
        metadata = OAuthClientMetadata(
            client_name="AstrBot MCP",
            software_id="https://github.com/Xero-Team/AstrBot",
            software_version="2",
            redirect_uris=[AnyUrl("http://127.0.0.1:6185/api/v1/mcp/oauth/callback")],
        )
        return OAuthClientProvider(
            server_url=endpoint,
            client_metadata=metadata,
            storage=auth_store.for_identity(identity),
            redirect_handler=lambda authorization_url: (
                auth_coordinator.redirect_handler(identity, authorization_url)
            ),
            callback_handler=lambda: auth_coordinator.callback_handler(identity),
            validate_resource_url=lambda requested, configured: (
                self._validate_oauth_resource(requested, configured)
            ),
        )

    @staticmethod
    async def _validate_oauth_resource(requested: str, configured: str | None) -> None:
        if configured is None:
            return
        expected, received = urlparse(requested), urlparse(configured)
        if (expected.scheme, expected.netloc) != (received.scheme, received.netloc):
            raise ValueError(
                "OAuth protected resource metadata does not match the MCP endpoint."
            )

    async def _open_client(
        self, stack: AsyncExitStack, cfg: dict[str, Any], name: str
    ) -> Client:
        read_timeout = float(cfg.get("read_timeout_seconds", 60))
        if "url" in cfg:
            _validate_remote_url(
                cfg["url"], allow_private_network=_allow_private_network_access(cfg)
            )
            connect_timeout = float(cfg.get("connect_timeout_seconds", 15))
            http_client = await stack.enter_async_context(
                _create_mcp_http_client_without_redirects(
                    headers=cfg.get("headers", {}),
                    timeout=httpx2.Timeout(connect_timeout, read=read_timeout),
                    auth=self._oauth_provider(cfg),
                    url=cfg["url"],
                    allow_private_network=_allow_private_network_access(cfg),
                )
            )
            transport = streamable_http_client(
                cfg["url"],
                http_client=http_client,
                terminate_on_close=cfg.get("terminate_on_close", True),
            )
        else:
            validate_mcp_stdio_config(cfg)
            stdio_cfg = _prepare_stdio_env(cfg)
            parameters = StdioServerParameters(
                command=stdio_cfg["command"],
                args=stdio_cfg.get("args", []),
                env=stdio_cfg.get("env"),
            )
            transport = stdio_client(
                parameters,
                errlog=cast(
                    TextIO,
                    LogPipe(
                        level=logging.INFO,
                        logger=logger,
                        identifier=f"MCPServer-{name}",
                        callback=self._stderr_logging_callback,
                    ),
                ),
            )
        client = Client(
            transport,
            mode=LATEST_PROTOCOL_VERSION,
            read_timeout_seconds=read_timeout,
            logging_callback=self._logging_callback,
            elicitation_callback=self._interaction_coordinator.handle_elicitation
            if self._interaction_coordinator
            else None,
            input_required_max_rounds=MAX_MCP_INTERACTION_ROUNDS,
        )
        return await stack.enter_async_context(client)

    async def _run_connection(
        self, ready: asyncio.Future[None], *, watch_catalog: bool = True
    ) -> None:
        assert self._mcp_server_config is not None and self._server_name is not None
        attempts = 0
        try:
            while not self._stop_event.is_set():
                stack = AsyncExitStack()
                self.exit_stack = stack
                self._connected_event.clear()
                try:
                    self.connection_status = "connecting"
                    client = await self._open_client(
                        stack, self._mcp_server_config, self._server_name
                    )
                    if client.protocol_version != MCP_PROTOCOL_VERSION:
                        raise MCPLegacyProtocolError(
                            "This server supports only an older MCP protocol, which this fork does not support."
                        )
                    self.client = client
                    self.protocol_version = client.protocol_version
                    capabilities = client.server_capabilities
                    self.capabilities = (
                        capabilities.model_dump(mode="json")
                        if hasattr(capabilities, "model_dump")
                        else {}
                    )
                    await self.refresh_catalog()
                    self.connection_status = "connected"
                    self._connected_event.set()
                    if not ready.done():
                        ready.set_result(None)
                    attempts = 0
                    if watch_catalog:
                        self._watcher_task = asyncio.create_task(
                            self._watch_catalog(client),
                            name=f"mcp-subscription:{self._server_name}",
                        )
                    await self._wait_for_stop_or_reconnect()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.connection_status = "error"
                    if not ready.done():
                        ready.set_exception(exc)
                        return
                    logger.warning(
                        "MCP connection to %s was lost: %s",
                        self._server_name,
                        safe_error("", exc),
                    )
                    attempts += 1
                finally:
                    watcher = self._watcher_task
                    self._watcher_task = None
                    if watcher is not None:
                        watcher.cancel()
                        await asyncio.gather(watcher, return_exceptions=True)
                    self.client = None
                    self._connected_event.clear()
                    await stack.aclose()
                    if self.exit_stack is stack:
                        self.exit_stack = None
                if self._stop_event.is_set():
                    break
                self._reconnect_event.clear()
                await asyncio.sleep(min(2 ** min(attempts, 3), 8))
        finally:
            self.connection_status = "disconnected"
            self.client = None
            self.tools, self.resources, self.resource_templates, self.prompts = (
                [],
                [],
                [],
                [],
            )
            if not ready.done():
                ready.set_exception(
                    RuntimeError("MCP connection task exited before becoming ready.")
                )

    async def _wait_for_stop_or_reconnect(self) -> None:
        stop = asyncio.create_task(self._stop_event.wait())
        reconnect = asyncio.create_task(self._reconnect_event.wait())
        done, pending = await asyncio.wait(
            {stop, reconnect}, return_when=asyncio.FIRST_COMPLETED
        )
        del done
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def connect_to_server(
        self,
        mcp_server_config: dict[str, Any],
        name: str,
        *,
        watch_catalog: bool = True,
    ) -> None:
        validate_mcp_server_config(mcp_server_config)
        await self.cleanup()
        self._mcp_server_config = _prepare_config(mcp_server_config)
        self._server_name = name
        self.name = name
        self._stop_event.clear()
        self._reconnect_event.clear()
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._connection_task = asyncio.create_task(
            self._run_connection(ready, watch_catalog=watch_catalog),
            name=f"mcp-connection:{name}",
        )
        try:
            await ready
        except asyncio.CancelledError:
            await self.cleanup()
            raise
        except Exception:
            await self.cleanup()
            raise

    async def _list_all(self, method_name: str, result_field: str) -> list[Any]:
        client = self.client
        if client is None:
            raise RuntimeError("MCP client is not connected.")
        method = getattr(client, method_name)
        cursor: str | None = None
        cursors: set[str] = set()
        items: list[Any] = []
        for _ in range(MAX_MCP_LIST_PAGES):
            response = await method(cursor=cursor)
            items.extend(getattr(response, result_field))
            next_cursor = getattr(response, "next_cursor", None)
            if next_cursor is None:
                return items
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in cursors
            ):
                raise RuntimeError("MCP catalog returned a repeated or invalid cursor.")
            cursors.add(next_cursor)
            cursor = next_cursor
        raise RuntimeError("MCP catalog exceeded the maximum page limit.")

    async def _notify_catalog_changed(self, catalog: str) -> None:
        if self._on_catalog_changed is None or self._server_name is None:
            return
        result = self._on_catalog_changed(self._server_name, catalog)
        if result is not None:
            await result

    async def list_tools(self) -> list[Any]:
        tools = await self._list_all("list_tools", "tools")
        self.tools = tools
        await self._notify_catalog_changed("tools")
        return tools

    async def list_tools_and_save(self) -> list[Any]:
        """Refresh and return the tools catalog."""
        return await self.list_tools()

    async def list_resources(self) -> list[Any]:
        resources = await self._list_all("list_resources", "resources")
        self.resources = resources
        return resources

    async def list_resource_templates(self) -> list[Any]:
        templates = await self._list_all(
            "list_resource_templates", "resource_templates"
        )
        self.resource_templates = templates
        return templates

    async def list_prompts(self) -> list[Any]:
        prompts = await self._list_all("list_prompts", "prompts")
        self.prompts = prompts
        return prompts

    async def refresh_catalog(self) -> None:
        """Fetch every discovery catalog before replacing any cached catalog."""
        tools, resources, templates, prompts = await asyncio.gather(
            self._list_all("list_tools", "tools"),
            self._list_all("list_resources", "resources"),
            self._list_all("list_resource_templates", "resource_templates"),
            self._list_all("list_prompts", "prompts"),
        )
        self.tools, self.resources, self.resource_templates, self.prompts = (
            tools,
            resources,
            templates,
            prompts,
        )
        await self._notify_catalog_changed("tools")

    async def _watch_catalog(self, client: Client) -> None:
        """Refresh atomic catalog snapshots after modern subscriptions/listen cues."""
        try:
            async with client.listen(
                tools_list_changed=True,
                prompts_list_changed=True,
                resources_list_changed=True,
            ) as subscription:
                async for event in subscription:
                    event_name = type(event).__name__
                    if event_name == "ToolListChangedNotification":
                        await self.list_tools_and_save()
                    elif event_name == "PromptListChangedNotification":
                        await self.list_prompts()
                        await self._notify_catalog_changed("prompts")
                    elif event_name in {
                        "ResourceListChangedNotification",
                        "ResourceUpdatedNotification",
                    }:
                        resources, templates = await asyncio.gather(
                            self._list_all("list_resources", "resources"),
                            self._list_all(
                                "list_resource_templates", "resource_templates"
                            ),
                        )
                        self.resources, self.resource_templates = resources, templates
                        await self._notify_catalog_changed("resources")
        except asyncio.CancelledError:
            raise
        except MCPError as exc:
            if exc.message.casefold() == "subscription limit reached":
                # A server may support the MCP connection while rejecting the
                # optional catalog subscription due to a server-side quota.
                # The initial catalogs remain usable, so do not tear down a
                # healthy connection and retry in a tight loop.
                logger.warning(
                    "MCP catalog subscription for %s unavailable: %s",
                    self._server_name,
                    safe_error("", exc),
                )
            else:
                logger.warning(
                    "MCP catalog subscription for %s ended: %s",
                    self._server_name,
                    safe_error("", exc),
                )
                self._reconnect_event.set()
        except Exception as exc:
            logger.warning(
                "MCP catalog subscription for %s ended: %s",
                self._server_name,
                safe_error("", exc),
            )
            self._reconnect_event.set()

    async def _resolve_input_required(
        self, result: Any
    ) -> tuple[dict[str, Any], str | None]:
        if not isinstance(result, InputRequiredResult):
            return {}, None
        requests = result.input_requests or {}
        if self._interaction_coordinator is None:
            raise RuntimeError(
                "MCP requested user input but no interaction coordinator is available."
            )
        responses: dict[str, Any] = {}
        for request_id, request in requests.items():
            if not isinstance(request, ElicitRequest):
                raise RuntimeError(
                    "MCP input request uses an unsupported interaction type."
                )
            response = await self._interaction_coordinator.handle_elicitation(
                None, request.params
            )
            if isinstance(response, ErrorData):
                raise RuntimeError(response.message)
            responses[request_id] = response
        return responses, result.request_state

    async def _call_with_input_required(
        self, operation: Callable[..., Awaitable[Any]], **kwargs: Any
    ) -> Any:
        for _ in range(MAX_MCP_INTERACTION_ROUNDS):
            result = await operation(**kwargs)
            if not isinstance(result, InputRequiredResult):
                return result
            responses, state = await self._resolve_input_required(result)
            kwargs["input_responses"] = responses
            kwargs["request_state"] = state
        raise RuntimeError("MCP input request exceeded the maximum interaction rounds.")

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any], read_timeout_seconds: float
    ) -> Any:
        async with self._parallel_semaphore:
            client = self.client
            if client is None:
                raise MCPConnectionLostError(
                    "MCP server connection was lost; the tool call was not retried."
                )
            try:
                return await self._call_with_input_required(
                    client.call_tool,
                    name=tool_name,
                    arguments=arguments,
                    read_timeout_seconds=read_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except (
                getattr(__import__("anyio"), "ClosedResourceError", RuntimeError),
                httpx2.TransportError,
            ) as exc:
                self._reconnect_event.set()
                raise MCPConnectionLostError(
                    "MCP connection was interrupted. The tool call was not retried."
                ) from exc

    async def read_resource(self, uri: str) -> Any:
        client = self.client
        if client is None:
            raise RuntimeError("MCP client is not connected.")
        result = await self._call_with_input_required(client.read_resource, uri=uri)
        for content in getattr(result, "contents", []):
            mime_type = getattr(content, "mime_type", None)
            if isinstance(mime_type, str) and len(mime_type) > 256:
                raise ValueError("MCP resource MIME type exceeds the safety limit.")
            if (
                hasattr(content, "text")
                and len(content.text.encode()) > MAX_MCP_RESOURCE_TEXT_BYTES
            ):
                raise ValueError("MCP resource text exceeds the safety limit.")
            if (
                hasattr(content, "blob")
                and len(content.blob) > MAX_MCP_RESOURCE_BINARY_BYTES
            ):
                raise ValueError("MCP binary resource exceeds the safety limit.")
        return result

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> Any:
        client = self.client
        if client is None:
            raise RuntimeError("MCP client is not connected.")
        return await self._call_with_input_required(
            client.get_prompt, name=name, arguments=arguments
        )

    async def complete(
        self,
        reference: Any,
        argument: dict[str, str],
        context_arguments: dict[str, str] | None = None,
    ) -> Any:
        client = self.client
        if client is None:
            raise RuntimeError("MCP client is not connected.")
        return await client.complete(reference, argument, context_arguments)

    async def cleanup(self) -> None:
        task = self._connection_task
        self._connection_task = None
        self._stop_event.set()
        self._reconnect_event.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.client = None

    def runtime_status(self) -> dict[str, Any]:
        return {
            "connection_status": self.connection_status,
            "protocol_version": self.protocol_version,
            "capabilities": self.capabilities,
            "tool_count": len(self.tools),
            "resource_count": len(self.resources),
            "resource_template_count": len(self.resource_templates),
            "prompt_count": len(self.prompts),
        }


class MCPTool[TContext](FunctionTool):
    """LLM-facing wrapper that preserves the MCP SDK 2 tool metadata."""

    def __init__(
        self,
        mcp_tool: Any,
        mcp_client: MCPClient,
        mcp_server_name: str,
        *,
        llm_tool_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        original_name = mcp_tool.name
        if llm_tool_name is None:
            llm_tool_name = MCPToolNameAllocator().allocate(
                mcp_server_name, original_name
            )
        if not _LLM_MCP_TOOL_NAME_RE.fullmatch(llm_tool_name):
            raise MCPToolNameAllocationError("Invalid LLM-facing MCP tool name.")
        super().__init__(
            name=llm_tool_name,
            description=mcp_tool.description or "",
            parameters=_normalize_mcp_input_schema(mcp_tool.input_schema),
        )
        self.mcp_tool = mcp_tool
        self.mcp_client = mcp_client
        self.mcp_server_name = mcp_server_name
        self.mcp_tool_name = original_name
        self.title = mcp_tool.title
        self.input_schema = copy.deepcopy(mcp_tool.input_schema)
        self.output_schema = copy.deepcopy(mcp_tool.output_schema)
        self.annotations = copy.deepcopy(mcp_tool.annotations)
        self.icons = copy.deepcopy(mcp_tool.icons)
        self.meta = copy.deepcopy(mcp_tool.meta)

    async def call(self, context: ContextWrapper[TContext], **kwargs: Any) -> Any:
        event = getattr(getattr(context, "context", None), "event", None)
        key = MCPInteractionKey(
            unified_msg_origin=str(getattr(event, "unified_msg_origin", "unknown")),
            run_id=str(getattr(context, "run_id", getattr(event, "run_id", "unknown"))),
            request_id=str(
                getattr(context, "request_id", getattr(event, "message_id", "unknown"))
            ),
            server_name=self.mcp_server_name,
        )
        coordinator = self.mcp_client._interaction_coordinator
        if coordinator is None:
            return await self.mcp_client.call_tool(
                self.mcp_tool_name, kwargs, context.tool_call_timeout
            )
        sender_id = getattr(event, "sender_id", None)
        if sender_id is None:
            sender_id = getattr(getattr(event, "message_obj", None), "sender_id", None)
        with coordinator.bind(
            key, str(sender_id) if sender_id is not None else None, event
        ):
            return await self.mcp_client.call_tool(
                self.mcp_tool_name, kwargs, context.tool_call_timeout
            )
