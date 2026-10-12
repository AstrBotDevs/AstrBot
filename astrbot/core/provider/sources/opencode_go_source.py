"""OpenCode Go provider for AstrBot.

OpenCode Go is a subscription service that exposes open-source programming
models through an OpenAI-compatible gateway. Different models are served by
different API protocols:

- ``/chat/completions``: OpenAI Chat Completions format
- ``/messages``: Anthropic Messages format
- ``/responses``: OpenAI Responses format

This adapter routes each model to the protocol it supports and delegates to
the matching AstrBot provider implementation instead of re-implementing any
protocol. The model-to-protocol mapping is seeded from known defaults and
refreshed from ``GET /models`` metadata. Every request carries a stable
per-conversation session identifier in the ``x-opencode-session`` header.
"""

import contextvars
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

import httpx

from astrbot import logger
from astrbot.core.utils.network_utils import create_proxy_client

from ..entities import LLMResponse
from ..headers import build_provider_headers
from ..register import register_provider_adapter
from .anthropic_source import ProviderAnthropic
from .openai_responses_source import ProviderOpenAIResponses
from .openai_source import ProviderOpenAIOfficial

# OpenCode Go API base. The Anthropic delegate strips the ``/v1`` suffix and
# the SDK re-appends ``/v1/messages``, so both protocols share this value.
OPENCODE_GO_API_BASE = "https://opencode.ai/zen/go/v1"

# Endpoint paths under OPENCODE_GO_API_BASE.
ENDPOINT_CHAT_COMPLETIONS = "/chat/completions"  # OpenAI-compatible
ENDPOINT_MESSAGES = "/messages"  # Anthropic Messages format
ENDPOINT_RESPONSES = "/responses"  # OpenAI Responses format

# Seed model-to-endpoint mapping from the service documentation. Refreshed
# from GET /models metadata so documentation updates are picked up.
DEFAULT_MODEL_ENDPOINTS: dict[str, str] = {
    # /chat/completions (OpenAI-compatible)
    "glm-5.3-flash": ENDPOINT_CHAT_COMPLETIONS,
    "glm-5.3": ENDPOINT_CHAT_COMPLETIONS,
    "glm-5.2": ENDPOINT_CHAT_COMPLETIONS,
    "kimi-k3": ENDPOINT_CHAT_COMPLETIONS,
    "kimi-k2.7-code": ENDPOINT_CHAT_COMPLETIONS,
    "kimi-k2.6": ENDPOINT_CHAT_COMPLETIONS,
    "longcat-2.0": ENDPOINT_CHAT_COMPLETIONS,
    "longcat-2.5-preview-free": ENDPOINT_CHAT_COMPLETIONS,
    "step-5-preview-free": ENDPOINT_CHAT_COMPLETIONS,
    "deepseek-v4.1-flash": ENDPOINT_CHAT_COMPLETIONS,
    "deepseek-v4-pro": ENDPOINT_CHAT_COMPLETIONS,
    "deepseek-v4-flash": ENDPOINT_CHAT_COMPLETIONS,
    "deepseek-v4-flash-vision-exp": ENDPOINT_CHAT_COMPLETIONS,
    "mimo-v2.6-flash": ENDPOINT_CHAT_COMPLETIONS,
    "mimo-v2.6-pro": ENDPOINT_CHAT_COMPLETIONS,
    "mimo-v2.5": ENDPOINT_CHAT_COMPLETIONS,
    "mimo-v2.5-pro": ENDPOINT_CHAT_COMPLETIONS,
    "hy4-preview": ENDPOINT_CHAT_COMPLETIONS,
    "hy3": ENDPOINT_CHAT_COMPLETIONS,
    "space-bunny": ENDPOINT_CHAT_COMPLETIONS,
    # /messages (Anthropic Messages format)
    "claude-haiku-5-5": ENDPOINT_MESSAGES,
    "minimax-m3": ENDPOINT_MESSAGES,
    "minimax-m2.7": ENDPOINT_MESSAGES,
    "qwen3.8-max": ENDPOINT_MESSAGES,
    "qwen3.8-flash": ENDPOINT_MESSAGES,
    "qwen3.7-plus": ENDPOINT_MESSAGES,
    # /responses (OpenAI Responses format)
    "grok-4.7": ENDPOINT_RESPONSES,
    "grok-4.6": ENDPOINT_RESPONSES,
    "gpt-6-luna": ENDPOINT_RESPONSES,
    "gpt-5.6-luna": ENDPOINT_RESPONSES,
    "muse-spark-1.3-contributor": ENDPOINT_RESPONSES,
    "muse-spark-1.2-contributor": ENDPOINT_RESPONSES,
}

OPENCODE_GO_SESSION_HEADER = "x-opencode-session"
DEFAULT_MODEL = "kimi-k3"

_OPENCODE_SESSION_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "opencode_go_session", default=""
)
_OPENCODE_AUTH_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "opencode_go_auth", default=""
)


def _install_session_hook(
    client: httpx.AsyncClient, *, inject_auth: bool = False
) -> None:
    """Attach per-request header hooks to an httpx client.

    Args:
        client: The httpx client used by one of the protocol delegates.
        inject_auth: Whether to override the Authorization header with the
            bearer token tracked in the auth context. Used for delegates so
            key rotation is picked up; the outer client manages its own key
            rotation and must not be overridden.
    """

    async def _attach_headers(request: httpx.Request) -> None:
        session_id = _OPENCODE_SESSION_CTX.get()
        if session_id:
            request.headers[OPENCODE_GO_SESSION_HEADER] = session_id
        if inject_auth:
            auth = _OPENCODE_AUTH_CTX.get()
            if auth:
                request.headers["Authorization"] = auth

    client.event_hooks["request"] = [
        *client.event_hooks.get("request", []),
        _attach_headers,
    ]


class _OpenCodeAnthropic(ProviderAnthropic):
    """Anthropic Messages delegate with the OpenCode Go session hook.

    The base class already resolves ``/v1`` correctly for the gateway and
    the Authorization bearer header is merged into ``custom_headers`` by the
    caller; this subclass only guarantees a hooked HTTP client exists even
    when no proxy is configured.
    """

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        client = super()._create_http_client(provider_config)
        if client is None:
            # The base class returns None without a proxy so the SDK builds
            # its default client. Re-create one here so the hook is present.
            httpx_module: Any = httpx
            try:
                from anthropic import _base_client as anthropic_base_client

                httpx_module = getattr(
                    anthropic_base_client,
                    "httpx",
                    getattr(anthropic_base_client, "httpx2", httpx),
                )
            except ImportError:
                pass
            client = create_proxy_client(
                "OpenCodeGoAnthropic",
                headers=self.custom_headers,
                httpx_module=httpx_module,
            )
        _install_session_hook(client, inject_auth=True)
        return client


class _OpenCodeResponses(ProviderOpenAIResponses):
    """OpenAI Responses delegate with the OpenCode Go session hook."""

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        client = super()._create_http_client(provider_config)
        _install_session_hook(client, inject_auth=True)
        return client


@register_provider_adapter(
    "opencode_go_chat_completion",
    "OpenCode Go Provider Adapter",
)
class ProviderOpenCodeGo(ProviderOpenAIOfficial):
    """OpenCode Go provider with per-model protocol routing.

    Chat-completions models use the inherited OpenAI pipeline directly.
    Anthropic-protocol and Responses-protocol models are delegated to the
    matching AstrBot provider adapters, so streaming, tool calls and retries
    are reused instead of re-implemented. Sessionless calls (model listing,
    connectivity tests) fall back to a stable per-instance session ID because
    the service rejects empty values.
    """

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the provider with OpenCode Go defaults.

        Args:
            provider_config: Provider configuration. ``api_base`` and ``model``
                fall back to the OpenCode Go defaults when not set.
            provider_settings: Shared provider settings.
        """
        self._fallback_session_id = uuid.uuid4().hex
        self._provider_settings = provider_settings
        merged_provider_config = dict(provider_config)
        merged_provider_config.setdefault("api_base", OPENCODE_GO_API_BASE)
        merged_provider_config.setdefault("model", DEFAULT_MODEL)
        custom_headers = dict(merged_provider_config.get("custom_headers") or {})
        custom_headers.setdefault(OPENCODE_GO_SESSION_HEADER, self._fallback_session_id)
        merged_provider_config["custom_headers"] = custom_headers
        super().__init__(merged_provider_config, provider_settings)
        self._model_endpoints: dict[str, str] = dict(DEFAULT_MODEL_ENDPOINTS)
        self._anthropic: _OpenCodeAnthropic | None = None
        self._responses: _OpenCodeResponses | None = None

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        """Create the HTTP client and attach the session header hook.

        Args:
            provider_config: Provider configuration used for proxy settings.

        Returns:
            The httpx client with the ``x-opencode-session`` request hook.
        """
        client = super()._create_http_client(provider_config)
        _install_session_hook(client)
        return client

    def _get_anthropic(self) -> _OpenCodeAnthropic:
        """Return the lazily built Anthropic Messages delegate.

        Returns:
            The delegate serving ``/messages`` models.
        """
        if self._anthropic is None:
            delegate_config = dict(self.provider_config)
            delegate_config["custom_headers"] = {
                **(delegate_config.get("custom_headers") or {}),
                # The Anthropic SDK only sends x-api-key; the gateway expects
                # the same bearer token as the other protocols.
                "Authorization": f"Bearer {self.get_current_key()}",
            }
            self._anthropic = _OpenCodeAnthropic(
                delegate_config, self._provider_settings
            )
        return self._anthropic

    def _get_responses(self) -> _OpenCodeResponses:
        """Return the lazily built OpenAI Responses delegate.

        Returns:
            The delegate serving ``/responses`` models.
        """
        if self._responses is None:
            self._responses = _OpenCodeResponses(
                self.provider_config, self._provider_settings
            )
        return self._responses

    def _extract_endpoint(self, obj: Any) -> str | None:
        """Recursively scan a /models metadata entry for its endpoint path.

        The metadata format may change over time, so instead of relying on
        fixed field names all string values are scanned for well-known
        endpoint markers.

        Args:
            obj: A value from the model metadata entry.

        Returns:
            The endpoint path, or None when no marker is found.
        """
        if isinstance(obj, dict):
            for value in obj.values():
                endpoint = self._extract_endpoint(value)
                if endpoint:
                    return endpoint
            return None
        if isinstance(obj, list):
            for value in obj:
                endpoint = self._extract_endpoint(value)
                if endpoint:
                    return endpoint
            return None
        if isinstance(obj, str):
            s = obj.strip().lower().rstrip("/")
            if "chat/completions" in s or s in {
                "chat_completions",
                "chat-completions",
                "openai-compatible",
                "openai_compatible",
            }:
                return ENDPOINT_CHAT_COMPLETIONS
            if s.endswith("/messages") or s in {"messages", "anthropic"}:
                return ENDPOINT_MESSAGES
            if s.endswith("/responses") or s in {"responses", "openai"}:
                return ENDPOINT_RESPONSES
        return None

    async def get_models(self) -> list[str]:
        """Fetch models from the gateway and refresh protocol routing.

        Returns:
            Model IDs available on OpenCode Go.
        """
        api_base = str(
            self.provider_config.get("api_base") or OPENCODE_GO_API_BASE
        ).rstrip("/")
        try:
            headers = build_provider_headers(self.provider_config.get("custom_headers"))
            # The gateway requires bearer authentication on /models as well.
            headers["Authorization"] = f"Bearer {self.get_current_key()}"
            async with create_proxy_client(
                "OpenCodeGo",
                self.provider_config.get("proxy") or None,
                headers=headers,
            ) as client:
                response = await client.get(f"{api_base}/models", timeout=15)
                response.raise_for_status()
                data = response.json()

            raw_models: list[Any] = []
            if isinstance(data, dict) and "data" in data:
                raw_models = data["data"]
            elif isinstance(data, list):
                raw_models = data

            models: list[str] = []
            fetched_endpoints: dict[str, str] = {}
            for model in raw_models:
                if not isinstance(model, dict) or "id" not in model:
                    continue
                model_id = str(model["id"])
                models.append(model_id)
                endpoint = self._extract_endpoint(model)
                if endpoint:
                    fetched_endpoints[model_id] = endpoint

            # Seed defaults first, then every listed model (unknown -> chat),
            # then the endpoints found in the live metadata.
            merged = dict(DEFAULT_MODEL_ENDPOINTS)
            for model_id in models:
                merged.setdefault(model_id, ENDPOINT_CHAT_COMPLETIONS)
            merged.update(fetched_endpoints)
            self._model_endpoints = merged
            logger.info(
                f"OpenCode Go: fetched {len(models)} models, "
                f"{len(fetched_endpoints)} endpoints resolved"
            )
            return models
        except Exception as e:
            logger.warning(f"OpenCode Go: failed to fetch models: {e}")
            return sorted(self._model_endpoints)

    async def _resolve_endpoint(self, model: str) -> str:
        """Resolve the endpoint path serving a model.

        Unknown models trigger a refresh from GET /models, falling back to the
        chat completions endpoint.

        Args:
            model: The model identifier.

        Returns:
            The endpoint path used to serve the model.
        """
        endpoint = self._model_endpoints.get(model)
        if endpoint is None:
            await self.get_models()
            endpoint = self._model_endpoints.get(model, ENDPOINT_CHAT_COMPLETIONS)
        return endpoint

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a non-streaming chat request through the model's protocol.

        Args:
            prompt: User prompt text.
            session_id: AstrBot session ID forwarded as ``x-opencode-session``.
            image_urls: Optional image URLs for multimodal models.
            audio_urls: Optional audio URLs.
            func_tool: Tool set exposed to the model.
            contexts: Prior conversation messages.
            system_prompt: Optional system prompt.
            tool_calls_result: Results of previously executed tool calls.
            model: Optional model override for this request.
            extra_user_content_parts: Extra content parts for the user message.
            tool_choice: Tool selection mode.
            request_max_retries: Max retries for the underlying HTTP request.
            **kwargs: Extra arguments forwarded to the delegate provider.

        Returns:
            The aggregated model response.
        """
        endpoint = await self._resolve_endpoint(model or self.get_model())
        _OPENCODE_SESSION_CTX.set(session_id or "")
        _OPENCODE_AUTH_CTX.set(f"Bearer {self.get_current_key()}")
        try:
            if endpoint == ENDPOINT_MESSAGES:
                return await self._get_anthropic().text_chat(
                    prompt=prompt,
                    session_id=session_id,
                    image_urls=image_urls,
                    audio_urls=audio_urls,
                    func_tool=func_tool,
                    contexts=contexts,
                    system_prompt=system_prompt,
                    tool_calls_result=tool_calls_result,
                    model=model,
                    extra_user_content_parts=extra_user_content_parts,
                    # Anthropic has no "required"; "any" is its equivalent.
                    tool_choice="any" if tool_choice == "required" else tool_choice,
                    request_max_retries=request_max_retries,
                    **kwargs,
                )
            if endpoint == ENDPOINT_RESPONSES:
                return await self._get_responses().text_chat(
                    prompt=prompt,
                    session_id=session_id,
                    image_urls=image_urls,
                    audio_urls=audio_urls,
                    func_tool=func_tool,
                    contexts=contexts,
                    system_prompt=system_prompt,
                    tool_calls_result=tool_calls_result,
                    model=model,
                    extra_user_content_parts=extra_user_content_parts,
                    tool_choice=tool_choice,
                    request_max_retries=request_max_retries,
                    **kwargs,
                )
            return await super().text_chat(
                prompt=prompt,
                session_id=session_id,
                image_urls=image_urls,
                audio_urls=audio_urls,
                func_tool=func_tool,
                contexts=contexts,
                system_prompt=system_prompt,
                tool_calls_result=tool_calls_result,
                model=model,
                extra_user_content_parts=extra_user_content_parts,
                tool_choice=tool_choice,
                request_max_retries=request_max_retries,
                **kwargs,
            )
        finally:
            _OPENCODE_AUTH_CTX.set("")
            _OPENCODE_SESSION_CTX.set("")

    async def text_chat_stream(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream a chat request through the model's protocol.

        Args:
            prompt: User prompt text.
            session_id: AstrBot session ID forwarded as ``x-opencode-session``.
            image_urls: Optional image URLs for multimodal models.
            audio_urls: Optional audio URLs.
            func_tool: Tool set exposed to the model.
            contexts: Prior conversation messages.
            system_prompt: Optional system prompt.
            tool_calls_result: Results of previously executed tool calls.
            model: Optional model override for this request.
            tool_choice: Tool selection mode.
            request_max_retries: Max retries for the underlying HTTP request.
            **kwargs: Extra arguments forwarded to the delegate provider.

        Yields:
            Incremental chunks followed by the final aggregated response.
        """
        endpoint = await self._resolve_endpoint(model or self.get_model())
        _OPENCODE_SESSION_CTX.set(session_id or "")
        _OPENCODE_AUTH_CTX.set(f"Bearer {self.get_current_key()}")
        try:
            if endpoint == ENDPOINT_MESSAGES:
                async for chunk in self._get_anthropic().text_chat_stream(
                    prompt=prompt,
                    session_id=session_id,
                    image_urls=image_urls,
                    audio_urls=audio_urls,
                    func_tool=func_tool,
                    contexts=contexts,
                    system_prompt=system_prompt,
                    tool_calls_result=tool_calls_result,
                    model=model,
                    # Anthropic has no "required"; "any" is its equivalent.
                    tool_choice="any" if tool_choice == "required" else tool_choice,
                    request_max_retries=request_max_retries,
                    **kwargs,
                ):
                    yield chunk
            elif endpoint == ENDPOINT_RESPONSES:
                async for chunk in self._get_responses().text_chat_stream(
                    prompt=prompt,
                    session_id=session_id,
                    image_urls=image_urls,
                    audio_urls=audio_urls,
                    func_tool=func_tool,
                    contexts=contexts,
                    system_prompt=system_prompt,
                    tool_calls_result=tool_calls_result,
                    model=model,
                    tool_choice=tool_choice,
                    request_max_retries=request_max_retries,
                    **kwargs,
                ):
                    yield chunk
            else:
                async for chunk in super().text_chat_stream(
                    prompt=prompt,
                    session_id=session_id,
                    image_urls=image_urls,
                    audio_urls=audio_urls,
                    func_tool=func_tool,
                    contexts=contexts,
                    system_prompt=system_prompt,
                    tool_calls_result=tool_calls_result,
                    model=model,
                    tool_choice=tool_choice,
                    request_max_retries=request_max_retries,
                    **kwargs,
                ):
                    yield chunk
        finally:
            _OPENCODE_SESSION_CTX.set("")
            _OPENCODE_AUTH_CTX.set("")

    async def terminate(self) -> None:
        """Close the outer client and any initialized protocol delegates.

        Returns:
            None.
        """
        if self._anthropic is not None:
            await self._anthropic.terminate()
        if self._responses is not None:
            await self._responses.terminate()
        await super().terminate()
