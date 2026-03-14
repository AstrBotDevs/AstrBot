from __future__ import annotations

import asyncio
import copy
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic

from astrbot import logger
from astrbot.core.agent.mcp_elicitation_registry import pending_mcp_elicitation
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_config_path,
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
    get_astrbot_plugin_data_path,
    get_astrbot_plugin_path,
    get_astrbot_root,
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

if TYPE_CHECKING:
    import mcp


DEFAULT_MCP_CLIENT_CAPABILITIES = {
    "elicitation": {
        "enabled": False,
        "timeout_seconds": 300,
    },
    "sampling": {
        "enabled": False,
    },
    "roots": {
        "enabled": False,
        "paths": [],
    },
}

DEFAULT_MCP_ROOT_PATHS = ("data", "temp")
DEFAULT_MCP_ELICITATION_TIMEOUT_SECONDS = 300
MCP_ELICITATION_ACCEPT_KEYWORDS = {
    "accept",
    "done",
    "ok",
    "okay",
    "yes",
    "完成",
    "已完成",
    "同意",
}
MCP_ELICITATION_DECLINE_KEYWORDS = {
    "decline",
    "reject",
    "refuse",
    "no",
    "拒绝",
    "不同意",
}
MCP_ELICITATION_CANCEL_KEYWORDS = {
    "cancel",
    "stop",
    "退出",
    "取消",
}


def get_root_path_alias_resolvers():
    return {
        "root": get_astrbot_root,
        "data": get_astrbot_data_path,
        "config": get_astrbot_config_path,
        "plugins": get_astrbot_plugin_path,
        "plugin_data": get_astrbot_plugin_data_path,
        "temp": get_astrbot_temp_path,
        "skills": get_astrbot_skills_path,
        "knowledge_base": get_astrbot_knowledge_base_path,
        "backups": get_astrbot_backups_path,
    }


class UnsupportedSamplingRequestError(ValueError):
    """Raised when a sampling request cannot be safely mapped."""


class UnsupportedElicitationRequestError(ValueError):
    """Raised when an elicitation request cannot be safely mapped."""


@dataclass(slots=True)
class MCPElicitationCapabilityConfig:
    enabled: bool = False
    timeout_seconds: int = DEFAULT_MCP_ELICITATION_TIMEOUT_SECONDS


@dataclass(slots=True)
class MCPSamplingCapabilityConfig:
    enabled: bool = False


@dataclass(slots=True)
class MCPRootsCapabilityConfig:
    enabled: bool = False
    paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MCPClientCapabilitiesConfig:
    elicitation: MCPElicitationCapabilityConfig
    sampling: MCPSamplingCapabilityConfig
    roots: MCPRootsCapabilityConfig

    @classmethod
    def from_server_config(
        cls, server_config: dict[str, Any] | None
    ) -> MCPClientCapabilitiesConfig:
        normalized = normalize_mcp_server_config(server_config or {})
        elicitation_cfg = normalized["client_capabilities"]["elicitation"]
        sampling_cfg = normalized["client_capabilities"]["sampling"]
        roots_cfg = normalized["client_capabilities"]["roots"]
        return cls(
            elicitation=MCPElicitationCapabilityConfig(
                enabled=bool(elicitation_cfg.get("enabled", False)),
                timeout_seconds=int(
                    elicitation_cfg.get(
                        "timeout_seconds",
                        DEFAULT_MCP_ELICITATION_TIMEOUT_SECONDS,
                    )
                ),
            ),
            sampling=MCPSamplingCapabilityConfig(
                enabled=bool(sampling_cfg.get("enabled", False)),
            ),
            roots=MCPRootsCapabilityConfig(
                enabled=bool(roots_cfg.get("enabled", False)),
                paths=list(roots_cfg.get("paths", [])),
            ),
        )


def normalize_mcp_server_config(server_config: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted MCP server config fields for backward compatibility."""
    normalized = copy.deepcopy(server_config)

    client_capabilities = normalized.get("client_capabilities")
    if not isinstance(client_capabilities, dict):
        client_capabilities = {}

    elicitation_cfg = client_capabilities.get("elicitation")
    if isinstance(elicitation_cfg, bool):
        elicitation_cfg = {"enabled": elicitation_cfg}
    elif not isinstance(elicitation_cfg, dict):
        elicitation_cfg = {}

    sampling_cfg = client_capabilities.get("sampling")
    if isinstance(sampling_cfg, bool):
        sampling_cfg = {"enabled": sampling_cfg}
    elif not isinstance(sampling_cfg, dict):
        sampling_cfg = {}

    roots_cfg = client_capabilities.get("roots")
    if isinstance(roots_cfg, bool):
        roots_cfg = {"enabled": roots_cfg}
    elif not isinstance(roots_cfg, dict):
        roots_cfg = {}

    raw_root_paths = roots_cfg.get("paths", [])
    if not isinstance(raw_root_paths, list):
        raw_root_paths = []
    normalized_root_paths = [
        str(path).strip()
        for path in raw_root_paths
        if isinstance(path, str) and path.strip()
    ]

    client_capabilities["elicitation"] = {
        "enabled": bool(elicitation_cfg.get("enabled", False)),
        "timeout_seconds": _normalize_positive_int(
            elicitation_cfg.get(
                "timeout_seconds",
                DEFAULT_MCP_ELICITATION_TIMEOUT_SECONDS,
            ),
            DEFAULT_MCP_ELICITATION_TIMEOUT_SECONDS,
        ),
    }
    client_capabilities["sampling"] = {
        "enabled": bool(sampling_cfg.get("enabled", False)),
    }
    client_capabilities["roots"] = {
        "enabled": bool(roots_cfg.get("enabled", False)),
        "paths": normalized_root_paths,
    }
    normalized["client_capabilities"] = client_capabilities
    return normalized


def _normalize_positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    if normalized <= 0:
        return default
    return normalized


def normalize_mcp_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize the full MCP configuration file structure."""
    normalized = {"mcpServers": {}}
    if not isinstance(config, dict):
        return normalized

    raw_servers = config.get("mcpServers", {})
    if not isinstance(raw_servers, dict):
        return normalized

    for name, server_config in raw_servers.items():
        if not isinstance(server_config, dict):
            continue
        normalized["mcpServers"][name] = normalize_mcp_server_config(server_config)
    return normalized


class MCPClientSubCapabilityBridge(Generic[TContext]):
    """Bridge MCP client sub-capability requests into AstrBot runtime calls."""

    def __init__(self, server_name: str | None = None) -> None:
        self._server_name = server_name or "<unknown>"
        self._capabilities = MCPClientCapabilitiesConfig.from_server_config({})
        self._interaction_lock = asyncio.Lock()
        self._active_run_context: ContextWrapper[TContext] | None = None

    def configure_from_server_config(self, server_config: dict[str, Any]) -> None:
        self._capabilities = MCPClientCapabilitiesConfig.from_server_config(
            server_config
        )

    def set_server_name(self, server_name: str | None) -> None:
        if server_name:
            self._server_name = server_name

    @property
    def sampling_enabled(self) -> bool:
        return self._capabilities.sampling.enabled

    @property
    def elicitation_enabled(self) -> bool:
        return self._capabilities.elicitation.enabled

    @property
    def elicitation_timeout_seconds(self) -> int:
        return self._capabilities.elicitation.timeout_seconds

    @property
    def roots_enabled(self) -> bool:
        return self._capabilities.roots.enabled

    def get_sampling_capabilities(self) -> mcp.types.SamplingCapability | None:
        if not self.sampling_enabled:
            return None

        import mcp

        return mcp.types.SamplingCapability()

    async def handle_list_roots(
        self,
        _request_context: Any,
    ) -> mcp.types.ListRootsResult | mcp.types.ErrorData:
        import mcp

        if not self.roots_enabled:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message="Roots are not enabled for this MCP server.",
            )

        try:
            return mcp.types.ListRootsResult(roots=self._build_root_entries())
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Roots request failed for MCP server %s: %s",
                self._server_name,
                exc,
                exc_info=True,
            )
            return mcp.types.ErrorData(
                code=mcp.types.INTERNAL_ERROR,
                message="Roots request failed inside AstrBot.",
                data=str(exc),
            )

    def clear_runtime_state(self) -> None:
        self._active_run_context = None

    @asynccontextmanager
    async def interactive_call(
        self,
        run_context: ContextWrapper[TContext] | None,
    ):
        if not (self.sampling_enabled or self.elicitation_enabled):
            yield
            return

        async with self._interaction_lock:
            self._active_run_context = run_context
            try:
                yield
            finally:
                self._active_run_context = None

    async def handle_sampling(
        self,
        _request_context: Any,
        params: mcp.types.CreateMessageRequestParams,
    ) -> (
        mcp.types.CreateMessageResult
        | mcp.types.CreateMessageResultWithTools
        | mcp.types.ErrorData
    ):
        import mcp

        if not self.sampling_enabled:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message="Sampling is not enabled for this MCP server.",
            )

        run_context = self._active_run_context
        if run_context is None:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message=(
                    "Sampling requests are only supported during an active AstrBot "
                    "MCP interaction."
                ),
            )

        try:
            return await self._execute_sampling(run_context, params)
        except UnsupportedSamplingRequestError as exc:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Sampling request failed for MCP server %s: %s",
                self._server_name,
                exc,
                exc_info=True,
            )
            return mcp.types.ErrorData(
                code=mcp.types.INTERNAL_ERROR,
                message="Sampling request failed inside AstrBot.",
                data=str(exc),
            )

    async def handle_elicitation(
        self,
        _request_context: Any,
        params: mcp.types.ElicitRequestParams,
    ) -> mcp.types.ElicitResult | mcp.types.ErrorData:
        import mcp

        if not self.elicitation_enabled:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message="Elicitation is not enabled for this MCP server.",
            )

        run_context = self._active_run_context
        if run_context is None:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message=(
                    "Elicitation requests are only supported during an active AstrBot "
                    "MCP interaction."
                ),
            )

        try:
            return await self._execute_elicitation(run_context, params)
        except UnsupportedElicitationRequestError as exc:
            return mcp.types.ErrorData(
                code=mcp.types.INVALID_REQUEST,
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Elicitation request failed for MCP server %s: %s",
                self._server_name,
                exc,
                exc_info=True,
            )
            return mcp.types.ErrorData(
                code=mcp.types.INTERNAL_ERROR,
                message="Elicitation request failed inside AstrBot.",
                data=str(exc),
            )

    async def _execute_sampling(
        self,
        run_context: ContextWrapper[TContext],
        params: mcp.types.CreateMessageRequestParams,
    ) -> mcp.types.CreateMessageResult:
        import mcp

        plugin_context, event = self._extract_bound_runtime(run_context)
        if plugin_context is None or event is None:
            raise UnsupportedSamplingRequestError(
                "Sampling requires an AstrBot agent context bound to the MCP tool call."
            )

        if params.includeContext not in (None, "none"):
            raise UnsupportedSamplingRequestError(
                "Sampling includeContext is not supported in the initial AstrBot integration."
            )

        if params.tools or params.toolChoice:
            raise UnsupportedSamplingRequestError(
                "Tool-assisted sampling is not supported in the initial AstrBot integration."
            )

        contexts = self._translate_sampling_messages(params.messages)
        umo = getattr(event, "unified_msg_origin", None)
        if not isinstance(umo, str) or not umo:
            raise UnsupportedSamplingRequestError(
                "Sampling requires a valid unified message origin."
            )

        provider_id = await plugin_context.get_current_chat_provider_id(umo)
        provider = plugin_context.get_using_provider(umo)
        if provider is None:
            raise UnsupportedSamplingRequestError(
                "Sampling requires an active chat provider."
            )

        provider_kwargs: dict[str, Any] = {"max_tokens": params.maxTokens}
        if params.temperature is not None:
            provider_kwargs["temperature"] = params.temperature
        if params.stopSequences:
            provider_kwargs["stop"] = params.stopSequences
            provider_kwargs["stopSequences"] = params.stopSequences
        if params.metadata:
            provider_kwargs["metadata"] = params.metadata

        llm_resp = await plugin_context.llm_generate(
            chat_provider_id=provider_id,
            contexts=contexts,
            system_prompt=params.systemPrompt or "",
            **provider_kwargs,
        )

        if llm_resp.role == "err":
            raise RuntimeError(llm_resp.completion_text or "Provider returned error")
        if llm_resp.tools_call_args:
            raise UnsupportedSamplingRequestError(
                "Tool-assisted sampling responses are not supported in the initial AstrBot integration."
            )

        text = llm_resp.completion_text
        if text is None:
            raise RuntimeError("Provider returned no textual sampling result")

        model_name = provider.get_model() or provider.meta().model or provider.meta().id
        return mcp.types.CreateMessageResult(
            role="assistant",
            content=mcp.types.TextContent(type="text", text=text),
            model=model_name,
            stopReason="endTurn",
        )

    @staticmethod
    def _extract_bound_runtime(
        run_context: ContextWrapper[TContext],
    ) -> tuple[Any | None, Any | None]:
        agent_context = getattr(run_context, "context", None)
        plugin_context = getattr(agent_context, "context", None)
        event = getattr(agent_context, "event", None)
        return plugin_context, event

    async def _execute_elicitation(
        self,
        run_context: ContextWrapper[TContext],
        params: mcp.types.ElicitRequestParams,
    ) -> mcp.types.ElicitResult:
        import mcp

        plugin_context, event = self._extract_bound_runtime(run_context)
        if event is None:
            raise UnsupportedElicitationRequestError(
                "Elicitation requires an AstrBot event bound to the MCP tool call."
            )

        sender_id = event.get_sender_id()
        if not sender_id:
            raise UnsupportedElicitationRequestError(
                "Elicitation requires a stable sender ID."
            )

        if isinstance(params, mcp.types.ElicitRequestFormParams):
            return await self._execute_form_elicitation(
                plugin_context,
                event,
                sender_id,
                params,
            )
        if isinstance(params, mcp.types.ElicitRequestURLParams):
            return await self._execute_url_elicitation(
                event,
                sender_id,
                params,
            )
        raise UnsupportedElicitationRequestError(
            f"Unsupported elicitation params type: {type(params).__name__}"
        )

    @staticmethod
    def _translate_sampling_messages(
        messages: list[mcp.types.SamplingMessage],
    ) -> list[dict[str, str]]:
        translated: list[dict[str, str]] = []
        for message in messages:
            text = MCPClientSubCapabilityBridge._sampling_message_to_text(message)
            translated.append(
                {
                    "role": message.role,
                    "content": text,
                }
            )
        return translated

    @staticmethod
    def _sampling_message_to_text(message: mcp.types.SamplingMessage) -> str:
        import mcp

        text_parts: list[str] = []
        for block in message.content_as_list:
            if isinstance(block, mcp.types.TextContent):
                text_parts.append(block.text)
                continue

            if isinstance(block, mcp.types.ImageContent):
                raise UnsupportedSamplingRequestError(
                    "Image sampling inputs are not supported in the initial AstrBot integration."
                )
            if isinstance(block, mcp.types.AudioContent):
                raise UnsupportedSamplingRequestError(
                    "Audio sampling inputs are not supported in the initial AstrBot integration."
                )

            raise UnsupportedSamplingRequestError(
                f"Sampling content block '{type(block).__name__}' is not supported in the initial AstrBot integration."
            )

        return "\n".join(text_parts)

    async def _execute_form_elicitation(
        self,
        plugin_context: Any,
        event: Any,
        sender_id: str,
        params: mcp.types.ElicitRequestFormParams,
    ) -> mcp.types.ElicitResult:
        import mcp

        properties = self._get_elicitation_properties(params.requestedSchema)
        deadline = asyncio.get_running_loop().time() + self.elicitation_timeout_seconds
        await self._send_elicitation_message(
            event,
            self._build_form_elicitation_prompt(params, properties),
            payload=self._build_form_elicitation_payload(params, properties),
        )

        while True:
            reply_text = await self._wait_for_elicitation_reply(
                event=event,
                sender_id=sender_id,
                deadline=deadline,
            )
            if reply_text is None:
                return mcp.types.ElicitResult(action="cancel")

            action = self._parse_cancel_or_decline_action(reply_text)
            if action is not None:
                return mcp.types.ElicitResult(action=action)

            try:
                content = self._parse_form_elicitation_reply(
                    requested_schema=params.requestedSchema,
                    reply_text=reply_text,
                )
            except UnsupportedElicitationRequestError as exc:
                content = await self._try_llm_form_reply_fallback(
                    plugin_context=plugin_context,
                    event=event,
                    params=params,
                    reply_text=reply_text,
                    direct_parse_error=exc,
                )
                if content is not None:
                    return mcp.types.ElicitResult(
                        action="accept",
                        content=content,
                    )
                await self._send_elicitation_message(
                    event,
                    self._build_form_retry_prompt(exc),
                )
                continue

            return mcp.types.ElicitResult(
                action="accept",
                content=content,
            )

    async def _try_llm_form_reply_fallback(
        self,
        *,
        plugin_context: Any,
        event: Any,
        params: mcp.types.ElicitRequestFormParams,
        reply_text: str,
        direct_parse_error: UnsupportedElicitationRequestError,
    ) -> dict[str, str | int | float | bool | list[str] | None] | None:
        if plugin_context is None:
            return None

        umo = getattr(event, "unified_msg_origin", None)
        if not isinstance(umo, str) or not umo:
            return None

        try:
            provider_id = await plugin_context.get_current_chat_provider_id(umo)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Unable to resolve provider for MCP elicitation fallback on %s: %s",
                self._server_name,
                exc,
            )
            return None

        prompt = self._build_elicitation_llm_fallback_prompt(
            params=params,
            reply_text=reply_text,
            direct_parse_error=direct_parse_error,
        )
        try:
            llm_resp = await plugin_context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=self._build_elicitation_llm_fallback_system_prompt(),
                max_tokens=256,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "LLM fallback failed during MCP elicitation for %s: %s",
                self._server_name,
                exc,
            )
            return None

        if getattr(llm_resp, "role", None) == "err":
            logger.debug(
                "Provider returned error during MCP elicitation fallback for %s: %s",
                self._server_name,
                getattr(llm_resp, "completion_text", "") or "<empty>",
            )
            return None

        raw_text = getattr(llm_resp, "completion_text", "") or ""
        normalized = self._strip_code_fence(raw_text).strip()
        if not normalized:
            return None

        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            logger.debug(
                "LLM fallback returned non-JSON content during MCP elicitation for %s: %s",
                self._server_name,
                normalized,
            )
            return None

        if not isinstance(payload, dict):
            return None

        try:
            return self._coerce_form_payload(payload, params.requestedSchema)
        except UnsupportedElicitationRequestError as exc:
            logger.debug(
                "LLM fallback returned invalid MCP elicitation payload for %s: %s",
                self._server_name,
                exc,
            )
            return None

    async def _execute_url_elicitation(
        self,
        event: Any,
        sender_id: str,
        params: mcp.types.ElicitRequestURLParams,
    ) -> mcp.types.ElicitResult:
        import mcp

        deadline = asyncio.get_running_loop().time() + self.elicitation_timeout_seconds
        await self._send_elicitation_message(
            event,
            self._build_url_elicitation_prompt(params),
            payload=self._build_url_elicitation_payload(params),
        )

        while True:
            reply_text = await self._wait_for_elicitation_reply(
                event=event,
                sender_id=sender_id,
                deadline=deadline,
            )
            if reply_text is None:
                return mcp.types.ElicitResult(action="cancel")

            action = self._parse_url_action(reply_text)
            if action is not None:
                return mcp.types.ElicitResult(action=action)

            await self._send_elicitation_message(
                event,
                "Please reply `done`, `decline`, or `cancel` to continue this MCP request.",
            )

    async def _send_elicitation_message(
        self,
        event: Any,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if payload and self._is_webchat_event(event):
            try:
                await event.send(
                    MessageChain(
                        chain=[Json(data=payload)],
                        type="elicitation",
                    )
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Falling back to plain-text MCP elicitation message for %s: %s",
                    self._server_name,
                    exc,
                )

        await event.send(MessageChain().message(message))

    async def _wait_for_elicitation_reply(
        self,
        *,
        event: Any,
        sender_id: str,
        deadline: float,
    ) -> str | None:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return None

        try:
            async with pending_mcp_elicitation(
                event.unified_msg_origin,
                sender_id,
            ) as future:
                reply = await asyncio.wait_for(future, timeout=remaining)
        except asyncio.TimeoutError:
            return None

        reply_text = reply.message_text.strip()
        if reply_text:
            return self._strip_code_fence(reply_text)
        return reply.message_outline.strip()

    def _build_form_elicitation_prompt(
        self,
        params: mcp.types.ElicitRequestFormParams,
        properties: dict[str, dict[str, Any]],
    ) -> str:
        required_fields = set(
            self._get_required_elicitation_fields(params.requestedSchema)
        )
        lines = [f"MCP server `{self._server_name}` needs more information."]
        if params.message.strip():
            lines.append(params.message.strip())
        if properties:
            lines.append("Requested fields:")
            for field_name, schema in properties.items():
                field_type = self._get_elicitation_field_type(schema)
                desc = str(schema.get("description", "")).strip()
                suffix = " required" if field_name in required_fields else " optional"
                if desc:
                    lines.append(f"- {field_name} ({field_type},{suffix}): {desc}")
                else:
                    lines.append(f"- {field_name} ({field_type},{suffix})")
        if len(properties) == 1:
            lines.append("Reply with plain text or JSON.")
        elif len(properties) > 1:
            lines.append("Reply with JSON or `field: value` lines.")
        else:
            lines.append("Reply `accept` to continue.")
        lines.append("Reply `decline` to refuse or `cancel` to stop.")
        return "\n".join(lines)

    def _build_form_elicitation_payload(
        self,
        params: mcp.types.ElicitRequestFormParams,
        properties: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        required_fields = set(
            self._get_required_elicitation_fields(params.requestedSchema)
        )
        fields: list[dict[str, Any]] = []
        for field_name, schema in properties.items():
            enum_values = schema.get("enum")
            fields.append(
                {
                    "name": field_name,
                    "label": str(schema.get("title") or field_name),
                    "description": str(schema.get("description", "")).strip(),
                    "required": field_name in required_fields,
                    "type": self._get_elicitation_field_type(schema),
                    "enum": (
                        [str(value) for value in enum_values]
                        if isinstance(enum_values, list)
                        else []
                    ),
                }
            )
        return {
            "kind": "form",
            "server_name": self._server_name,
            "message": params.message.strip(),
            "prompt": self._build_form_elicitation_prompt(params, properties),
            "fields": fields,
        }

    @staticmethod
    def _build_form_retry_prompt(exc: UnsupportedElicitationRequestError) -> str:
        return (
            "I could not use that reply for the MCP elicitation.\n"
            f"Reason: {exc}\n"
            "Please try again, or reply `decline` / `cancel`."
        )

    def _build_url_elicitation_prompt(
        self,
        params: mcp.types.ElicitRequestURLParams,
    ) -> str:
        lines = [
            f"MCP server `{self._server_name}` needs an external confirmation step."
        ]
        if params.message.strip():
            lines.append(params.message.strip())
        lines.append(f"URL: {params.url}")
        lines.append(
            "Reply `done` after you finish, `decline` to refuse, or `cancel` to stop."
        )
        return "\n".join(lines)

    def _build_url_elicitation_payload(
        self,
        params: mcp.types.ElicitRequestURLParams,
    ) -> dict[str, Any]:
        return {
            "kind": "url",
            "server_name": self._server_name,
            "message": params.message.strip(),
            "prompt": self._build_url_elicitation_prompt(params),
            "url": params.url,
        }

    @staticmethod
    def _build_elicitation_llm_fallback_system_prompt() -> str:
        return (
            "You extract structured MCP elicitation data from a user's natural-language reply.\n"
            "Return only a JSON object.\n"
            "Use only keys from the provided schema.\n"
            "Do not invent facts. Omit fields that are not clearly supported.\n"
            "Use proper JSON types for booleans, integers, numbers, and arrays.\n"
            "Do not wrap the JSON in markdown fences."
        )

    def _build_elicitation_llm_fallback_prompt(
        self,
        *,
        params: mcp.types.ElicitRequestFormParams,
        reply_text: str,
        direct_parse_error: UnsupportedElicitationRequestError,
    ) -> str:
        return (
            f"MCP server: {self._server_name}\n"
            f"Original elicitation message:\n{params.message.strip() or '<empty>'}\n\n"
            f"Requested JSON schema:\n"
            f"{json.dumps(params.requestedSchema, ensure_ascii=False, indent=2)}\n\n"
            f"User reply:\n{reply_text}\n\n"
            f"Direct parser error:\n{direct_parse_error}\n\n"
            "Produce the best possible JSON object that matches the schema."
        )

    def _parse_form_elicitation_reply(
        self,
        *,
        requested_schema: dict[str, Any],
        reply_text: str,
    ) -> dict[str, str | int | float | bool | list[str] | None]:
        properties = self._get_elicitation_properties(requested_schema)
        if not properties:
            return {}

        normalized_reply = reply_text.strip()
        if not normalized_reply:
            raise UnsupportedElicitationRequestError("The reply is empty.")

        if normalized_reply.startswith("{"):
            try:
                payload = json.loads(normalized_reply)
            except json.JSONDecodeError as exc:
                raise UnsupportedElicitationRequestError(
                    "The JSON reply could not be parsed."
                ) from exc
            if not isinstance(payload, dict):
                raise UnsupportedElicitationRequestError(
                    "The JSON reply must be an object."
                )
        elif len(properties) == 1:
            field_name = next(iter(properties))
            payload = {field_name: normalized_reply}
        else:
            payload = self._parse_key_value_lines(normalized_reply, properties)
            if not payload:
                payload = self._parse_natural_language_form_reply(
                    reply_text=normalized_reply,
                    requested_schema=requested_schema,
                )
            if not payload:
                raise UnsupportedElicitationRequestError(
                    "Please reply with JSON, natural language, or `field: value` lines."
                )

        return self._coerce_form_payload(payload, requested_schema)

    def _parse_natural_language_form_reply(
        self,
        *,
        reply_text: str,
        requested_schema: dict[str, Any],
    ) -> dict[str, Any]:
        properties = self._get_elicitation_properties(requested_schema)
        if not properties:
            return {}

        parsed = self._parse_field_patterns(reply_text, properties)
        parsed.update(self._match_enum_values(reply_text, properties, parsed.keys()))
        if parsed:
            return parsed

        target_fields = self._get_required_elicitation_fields(requested_schema)
        if not target_fields:
            target_fields = list(properties.keys())
        if len(target_fields) == 1:
            return {target_fields[0]: reply_text}

        return {}

    def _coerce_form_payload(
        self,
        payload: dict[str, Any],
        requested_schema: dict[str, Any],
    ) -> dict[str, str | int | float | bool | list[str] | None]:
        properties = self._get_elicitation_properties(requested_schema)
        required_fields = self._get_required_elicitation_fields(requested_schema)
        normalized_keys = {
            field_name.casefold(): field_name for field_name in properties.keys()
        }

        coerced: dict[str, str | int | float | bool | list[str] | None] = {}
        for raw_key, raw_value in payload.items():
            normalized_key = str(raw_key).strip().casefold()
            field_name = normalized_keys.get(normalized_key)
            if field_name is None:
                continue
            coerced[field_name] = self._coerce_form_value(
                field_name=field_name,
                raw_value=raw_value,
                schema=properties[field_name],
            )

        missing_required = [
            field_name for field_name in required_fields if field_name not in coerced
        ]
        if missing_required:
            raise UnsupportedElicitationRequestError(
                "Missing required field(s): " + ", ".join(missing_required)
            )
        return coerced

    def _coerce_form_value(
        self,
        *,
        field_name: str,
        raw_value: Any,
        schema: dict[str, Any],
    ) -> str | int | float | bool | list[str] | None:
        field_type = self._get_elicitation_field_type(schema)
        if raw_value is None:
            return None

        if field_type == "string":
            value = str(raw_value).strip()
        elif field_type == "integer":
            if isinstance(raw_value, bool):
                raise UnsupportedElicitationRequestError(
                    f"Field `{field_name}` must be an integer."
                )
            try:
                value = int(str(raw_value).strip())
            except (TypeError, ValueError) as exc:
                raise UnsupportedElicitationRequestError(
                    f"Field `{field_name}` must be an integer."
                ) from exc
        elif field_type == "number":
            if isinstance(raw_value, bool):
                raise UnsupportedElicitationRequestError(
                    f"Field `{field_name}` must be a number."
                )
            try:
                value = float(str(raw_value).strip())
            except (TypeError, ValueError) as exc:
                raise UnsupportedElicitationRequestError(
                    f"Field `{field_name}` must be a number."
                ) from exc
        elif field_type == "boolean":
            value = self._coerce_boolean_value(field_name, raw_value)
        elif field_type == "array":
            value = self._coerce_string_array_value(field_name, raw_value)
        else:
            raise UnsupportedElicitationRequestError(
                f"Field `{field_name}` uses unsupported type `{field_type}`."
            )

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            raise UnsupportedElicitationRequestError(
                f"Field `{field_name}` must be one of: {', '.join(map(str, enum_values))}."
            )
        return value

    @staticmethod
    def _coerce_boolean_value(field_name: str, raw_value: Any) -> bool:
        if isinstance(raw_value, bool):
            return raw_value

        normalized = str(raw_value).strip().casefold()
        truthy = {"true", "1", "yes", "y", "on", "是", "好的"}
        falsy = {"false", "0", "no", "n", "off", "否", "不是"}
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False
        raise UnsupportedElicitationRequestError(
            f"Field `{field_name}` must be a boolean."
        )

    @staticmethod
    def _coerce_string_array_value(field_name: str, raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]

        normalized = str(raw_value).strip()
        if not normalized:
            return []
        parts = [
            part.strip()
            for chunk in normalized.splitlines()
            for part in chunk.split(",")
            if part.strip()
        ]
        if not parts:
            raise UnsupportedElicitationRequestError(
                f"Field `{field_name}` must be a string array."
            )
        return parts

    @staticmethod
    def _parse_key_value_lines(
        reply_text: str,
        properties: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        normalized_keys = {
            field_name.casefold(): field_name for field_name in properties.keys()
        }
        parsed: dict[str, str] = {}
        for line in reply_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            delimiter = ":" if ":" in stripped else ("：" if "：" in stripped else None)
            if delimiter is None:
                continue
            raw_key, raw_value = stripped.split(delimiter, 1)
            field_name = normalized_keys.get(raw_key.strip().casefold())
            if field_name is None:
                continue
            parsed[field_name] = raw_value.strip()
        return parsed

    @staticmethod
    def _parse_field_patterns(
        reply_text: str,
        properties: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        parsed: dict[str, str] = {}
        separators = r"[:：=]|是|为"
        boundaries = r"(?:[,，;；。]|$)"
        for field_name in properties:
            pattern = re.compile(
                rf"{re.escape(field_name)}\s*(?:{separators})\s*(.+?)(?={boundaries})",
                re.IGNORECASE,
            )
            match = pattern.search(reply_text)
            if match:
                value = match.group(1).strip().strip("`'\"")
                if value:
                    parsed[field_name] = value
        return parsed

    @staticmethod
    def _match_enum_values(
        reply_text: str,
        properties: dict[str, dict[str, Any]],
        ignore_fields: set[str] | Any,
    ) -> dict[str, str]:
        normalized_reply = reply_text.casefold()
        parsed: dict[str, str] = {}
        ignored = set(ignore_fields)
        for field_name, schema in properties.items():
            if field_name in ignored:
                continue
            enum_values = schema.get("enum")
            if not isinstance(enum_values, list) or not enum_values:
                continue

            matches = [
                str(enum_value)
                for enum_value in enum_values
                if str(enum_value).casefold() in normalized_reply
            ]
            if len(matches) == 1:
                parsed[field_name] = matches[0]
        return parsed

    @staticmethod
    def _get_elicitation_properties(
        requested_schema: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        properties = requested_schema.get("properties", {})
        if not isinstance(properties, dict):
            raise UnsupportedElicitationRequestError(
                "Form-mode elicitation requires a top-level properties object."
            )
        normalized_properties: dict[str, dict[str, Any]] = {}
        for field_name, field_schema in properties.items():
            if isinstance(field_name, str) and isinstance(field_schema, dict):
                normalized_properties[field_name] = field_schema
        return normalized_properties

    @staticmethod
    def _get_required_elicitation_fields(
        requested_schema: dict[str, Any],
    ) -> list[str]:
        required_fields = requested_schema.get("required", [])
        if not isinstance(required_fields, list):
            return []
        return [field for field in required_fields if isinstance(field, str)]

    @staticmethod
    def _get_elicitation_field_type(field_schema: dict[str, Any]) -> str:
        field_type = field_schema.get("type", "string")
        if isinstance(field_type, list):
            for candidate in field_type:
                if candidate in {"string", "integer", "number", "boolean", "array"}:
                    return candidate
            raise UnsupportedElicitationRequestError(
                "Unsupported multi-type elicitation field."
            )
        if not isinstance(field_type, str):
            return "string"
        return field_type

    @staticmethod
    def _parse_cancel_or_decline_action(reply_text: str) -> str | None:
        normalized = reply_text.strip().casefold()
        if normalized in MCP_ELICITATION_CANCEL_KEYWORDS:
            return "cancel"
        if normalized in MCP_ELICITATION_DECLINE_KEYWORDS:
            return "decline"
        return None

    @staticmethod
    def _parse_url_action(reply_text: str) -> str | None:
        normalized = reply_text.strip().casefold()
        if normalized in MCP_ELICITATION_ACCEPT_KEYWORDS:
            return "accept"
        if normalized in MCP_ELICITATION_DECLINE_KEYWORDS:
            return "decline"
        if normalized in MCP_ELICITATION_CANCEL_KEYWORDS:
            return "cancel"
        return None

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```") or not stripped.endswith("```"):
            return stripped
        lines = stripped.splitlines()
        if len(lines) <= 2:
            return stripped.removeprefix("```").removesuffix("```").strip()
        return "\n".join(lines[1:-1]).strip()

    @staticmethod
    def _is_webchat_event(event: Any) -> bool:
        platform_name = getattr(event, "get_platform_name", None)
        if callable(platform_name):
            try:
                return platform_name() == "webchat"
            except Exception:  # noqa: BLE001
                return False
        return False

    def _build_root_entries(self) -> list[mcp.types.Root]:
        import mcp

        roots: list[mcp.types.Root] = []
        seen_paths: set[str] = set()
        for name, path in self._iter_resolved_root_paths():
            normalized_path = str(path)
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            roots.append(
                mcp.types.Root(
                    uri=path.as_uri(),
                    name=name,
                )
            )
        return roots

    def _iter_resolved_root_paths(self) -> list[tuple[str, Path]]:
        configured_paths = self._capabilities.roots.paths or list(
            DEFAULT_MCP_ROOT_PATHS
        )
        resolved_entries: list[tuple[str, Path]] = []
        for entry in configured_paths:
            resolved = self._resolve_root_path_entry(entry)
            if resolved is not None:
                resolved_entries.append(resolved)
        return resolved_entries

    def _resolve_root_path_entry(self, entry: str) -> tuple[str, Path] | None:
        normalized_entry = entry.strip()
        if not normalized_entry:
            return None

        alias_key = normalized_entry.lower()
        alias_resolvers = get_root_path_alias_resolvers()
        if alias_key in alias_resolvers:
            path = Path(alias_resolvers[alias_key]()).resolve()
            display_name = alias_key
        else:
            candidate_path = Path(normalized_entry).expanduser()
            if not candidate_path.is_absolute():
                candidate_path = Path(get_astrbot_root()) / candidate_path
            path = candidate_path.resolve()
            display_name = path.name or normalized_entry

        if not path.exists():
            logger.warning(
                "Skipping missing MCP root path for server %s: %s",
                self._server_name,
                path,
            )
            return None

        return display_name, path
